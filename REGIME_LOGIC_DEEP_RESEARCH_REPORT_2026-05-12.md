# AGENT_REPORT_V1

## Executive Summary
Авторитетная идентификация structural regime в текущем дереве живет в одном месте: apps/reference/domains/regime_detector/regime_detector.py. Детектор работает по bar-only цепочке, принимает только basis bars из EVT:FEATURES_CALCULATED, вычисляет regime в порядке Volatility -> Mean Reversion -> SMA Trend, затем пропускает результат через data-quality guards, uncertain cutoff и hysteresis, после чего эмитит EVT:REGIME_DETECTED.

Система авторитетно эмитит только 6 structural labels: TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY, UNCERTAIN. Все остальные vocabularies в репозитории, включая FLAT_LOW/FLAT_NORMAL/FLAT_HIGH, ExecutionRegimeBucket.FLAT/VOLATILE и NORMAL/STRESS/EXTREME, являются downstream-переводами или overlays, а не первичной детекцией.

Ключевой operational вывод текущего active config: detector-level uncertain_cutoff практически не работает как реальный демоутер, потому что сейчас uncertain_cutoff = 0.15 и общий confidence floor для всех detector branches тоже 0.15, а проверка в detector сделана по строгому "меньше", а не "меньше или равно". В итоге консерватизм сейчас в основном сидит downstream, в decision gates и strategy-local regime-aware maps, а не в самом detector boundary.

## Proven Facts

### Scope Boundary
- Этот отчет детально покрывает authoritative regime identification, detector-adjacent config из config/aurora/regime.yaml, system stress overlay из того же режима-домена, regime_confidence gates и словари/маппинги режимов.
- Этот отчет инвентаризирует regime-aware downstream consumers, но не разворачивает построчно каждый asset-specific objective или TP/SL map, если они только потребляют regime labels и не участвуют в первичной детекции.

### Authoritative Control Path
1. RegimeDetector слушает EVT:FEATURES_CALCULATED и игнорирует все события, где tf_sec != basis_tf_sec или tf_sec == 0.
2. Для basis bars detector валидирует symbol, ts и features, режет stale data по bar_ttl_ms, не обновляет buffers на stale path и fail-closed эмитит UNCERTAIN на stale data.
3. Detector наполняет internal price buffer и, если SMA fields не пришли во features, восстанавливает sma_short и sma_long из собственных rolling buffers. Это не магический fallback, а буферный расчет из того же bar потока.
4. Для volatility ветки detector строит ATR-пайплайн. Он предпочитает OHLC True Range, но при allow_close_to_close_atr = true умеет перейти на abs(close - prev_close).
5. Приоритет regime detection фиксированный: сначала HIGH_VOLATILITY или LOW_VOLATILITY, потом MEAN_REVERSION, потом TREND_UP/TREND_DOWN.
6. После raw classification detector применяет data-quality fail-closed, затем uncertain_cutoff, затем hysteresis и только после этого эмитит stable regime с stable confidence.
7. Aurora/DecisionMaking/ExecutionPosition downstream используют уже cached detector output и не пересчитывают structural regime заново.

### Exact Regime Vocabularies In Repo

| Family | Labels / States | Owner | Что это означает |
| --- | --- | --- | --- |
| Structural regime labels | TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY, UNCERTAIN | RegimeDetector | Единственный authoritative structural regime output |
| Structural aliases | BULL_TREND -> TREND_UP, BEAR_TREND -> TREND_DOWN | normalize_structural_regime_label | Boundary-normalization alias layer |
| Execution regime buckets | TREND_UP, TREND_DOWN, FLAT, VOLATILE, UNCERTAIN | apps/reference/core/types/regime_types.py | Risk/exposure buckets, не detector labels |
| Mean Reversion flat regimes | FLAT_LOW, FLAT_NORMAL, FLAT_HIGH | apps/reference/domains/feature_engineering/regime_mapping.py | Вторичный перевод для MR strategy |
| System stress states | NORMAL, STRESS, EXTREME | apps/reference/domains/system_stress/system_stress_overlay.py | Независимый overlay, не structural label |

### Current Active Detector Snapshot

#### Root regime.yaml fields

| Field | Current | Meaning |
| --- | --- | --- |
| basis_tf_sec | 300 | Detector clock = 5m basis bars |
| uncertain_cutoff | 0.15 | Минимальная confidence для non-UNCERTAIN emission внутри detector |
| liveness_factor | 3 | Downstream heartbeat tolerance = basis_tf_sec * liveness_factor |
| basis_import_buffer | 20 | Дополнительные warmup bars поверх canonical minimum |
| hysteresis_bars | 2 | Сколько basis bars подряд нужен raw regime для смены stable regime |
| vol_slope_gate_enabled | true | Разрешен dying-storm gate для HIGH_VOLATILITY |
| vol_slope_gate_eps | -0.005 | Порог slope gate на EMA3(vol_ratio) - EMA6(vol_ratio) |
| vol_slope_gate_confirm_bars | 5 | Сколько basis bars slope должен быть <= eps для reject |

#### Models snapshot

| Model | Fields | Current |
| --- | --- | --- |
| sma_trend | sma_short_period / sma_long_period | 48 / 192 |
| sma_trend | confidence_multiplier / confidence_min / confidence_max | 80.0 / 0.15 / 0.85 |
| volatility | enabled | true |
| volatility | atr_period / atr_sma_length | 14 / 288 |
| volatility | allow_close_to_close_atr | true |
| volatility | threshold_multiplier / low_vol_multiplier | 2.0 / 0.7 |
| volatility | high_vol_confidence_multiplier / low_vol_confidence_multiplier | 2.5 / 3.0 |
| mean_reversion | threshold / confidence_multiplier | 0.005 / 120.0 |

### Cadence, Warmup, and Time Math
- Detector работает строго на basis_tf_sec = 300 секунд, то есть на 5-минутных барах.
- Canonical warmup requirement определяется формулой из apps/reference/contracts/strategy_compatibility_matrix.py:
  regime_detector_required_bars = max(sma_long_period, atr_period + atr_sma_length - 1)
- При текущих значениях это max(192, 14 + 288 - 1) = 301 basis bars.
- С учетом basis_import_buffer = 20 полная startup import target = 321 basis bars.
- 321 bar по 5 минут = 1605 минут = 26 часов 45 минут.
- liveness_factor = 3 дает downstream heartbeat tolerance 15 минут. Если detector heartbeat не приходит дольше, downstream может fail-closed блокировать торговлю.

### Structural Regime Detection Math

#### 1. SMA Trend math
Trend confidence считается в _calculate_confidence_meta как:

confidence_unbounded = abs((sma_short - sma_long) / sma_long * confidence_multiplier)
confidence_bounded = clamp(confidence_unbounded, confidence_min, confidence_max)

С текущими значениями:
- confidence_multiplier = 80.0
- confidence_min = 0.15
- confidence_max = 0.85

Текущие breakpoints:
- floor starts until spread_ratio <= 0.15 / 80 = 0.001875, то есть 0.1875%
- ceiling starts from spread_ratio >= 0.85 / 80 = 0.010625, то есть 1.0625%

Directional conditions:
- TREND_UP требует sma_short > sma_long и price > sma_short
- TREND_DOWN требует sma_short < sma_long и price < sma_short

#### 2. Volatility math
Volatility branch uses:

vol_ratio = atr_current / atr_baseline

HIGH_VOLATILITY:
- regime fires if vol_ratio > threshold_multiplier
- candidate_confidence = confidence_min + (vol_ratio - threshold_multiplier) * high_vol_confidence_multiplier

LOW_VOLATILITY:
- regime fires if vol_ratio < low_vol_multiplier
- candidate_confidence = confidence_min + (low_vol_multiplier - vol_ratio) * low_vol_confidence_multiplier

С текущими значениями:
- threshold_multiplier = 2.0
- low_vol_multiplier = 0.7
- high_vol_confidence_multiplier = 2.5
- low_vol_confidence_multiplier = 3.0

Текущие breakpoints:
- HIGH_VOL ceiling at 0.15 + (vol_ratio - 2.0) * 2.5 >= 0.85
- Это означает vol_ratio >= 2.28
- LOW_VOL ceiling at 0.15 + (0.7 - vol_ratio) * 3.0 >= 0.85
- Это означает vol_ratio <= 0.466666...

Важный факт: volatility branch тоже использует confidence_min/confidence_max из sma_trend config. У volatility своей min/max нет; ее candidate confidence clamp-ится общим detector floor/ceiling.

#### 3. Mean Reversion math
MR branch fires, только если detector еще остается в UNCERTAIN и доступны price + обе SMA.

Вычисления:
- sma_spread = abs(sma_short - sma_long) / sma_long
- dev_short = abs(price - sma_short) / sma_short
- dev_long = abs(price - sma_long) / sma_long

MEAN_REVERSION fires, если все три значения < threshold.

Дальше:
- tightness = threshold - max(sma_spread, dev_short, dev_long)
- candidate_confidence = confidence_min + tightness * confidence_multiplier

С текущими значениями:
- threshold = 0.005
- confidence_multiplier = 120.0
- confidence_min = 0.15

Текущий theoretical max:
- maximum tightness = 0.005
- max candidate confidence = 0.15 + 0.005 * 120 = 0.75

Следствие: при текущем config MEAN_REVERSION branch вообще не может упереться в detector ceiling 0.85. Его верхняя граница сейчас 0.75.

### Post-Classification Filters

#### uncertain_cutoff gate
После raw classification detector делает:
- if regime != UNCERTAIN and confidence < uncertain_cutoff: demote to UNCERTAIN, set confidence = confidence_min

Текущий факт:
- сейчас uncertain_cutoff = 0.15
- сейчас confidence_min = 0.15
- detector сравнивает строго по <, а не по <=

Следствие:
- любой regime, уже поднятый до detector floor 0.15, не будет демоутирован этим gate
- текущий uncertain_cutoff начнет реально работать только если поднять его выше 0.15 или опустить общий floor ниже него

#### Hysteresis
Detector хранит на symbol:
- stable_regime
- pending_regime
- hysteresis_count
- stable_confidence

Текущая semantics:
- raw regime должен повториться hysteresis_bars раз подряд, чтобы стать stable
- до этого detector может продолжать эмитить предыдущий stable regime и previous stable confidence
- payload различает raw_regime/raw_confidence и stable regime/stable_confidence

#### Volatility slope gate
Для HIGH_VOLATILITY detector считает:
- vol_ratio_slope = EMA3(vol_ratio) - EMA6(vol_ratio)
- если slope <= vol_slope_gate_eps в течение vol_slope_gate_confirm_bars basis bars подряд, detector отвергает dying storm и ставит UNCERTAIN

При текущих значениях:
- eps = -0.005
- confirm_bars = 5

Это не просто flat filter. Текущий gate пропускает плоский slope около нуля и начинает aggressively reject только при уже отрицательном уклоне не выше -0.005.

### Detector Payload Semantics

| Payload field | Meaning |
| --- | --- |
| regime | Stable regime after hysteresis |
| confidence | Stable confidence after hysteresis |
| source_model | Источник raw decision текущего basis bar |
| pre_cutoff_source_model | Model до uncertain_cutoff gate |
| pre_cutoff_regime | Raw regime до uncertain_cutoff gate |
| pre_cutoff_confidence | Raw confidence до uncertain_cutoff demotion |
| pre_cutoff_clamped_to_min / max | Был ли floor/ceiling clamp до uncertain_cutoff |
| pre_cutoff_boundary_reason | Почему случился clamp |
| raw_regime / raw_confidence | Raw regime/confidence текущего basis bar до hysteresis carry |
| raw_boundary_reason | Boundary reason после uncertain_cutoff path |
| stable_confidence | Confidence последнего stable regime |
| demoted_to_uncertain | Был ли raw regime демоутирован cutoff gate |
| hysteresis_bars | Configured hysteresis bars |
| hysteresis_confirm_count | Текущий счетчик подтверждения raw regime |
| carried_previous_stable | Эмитился ли предыдущий stable regime вместо raw regime |
| emitted_confidence_kind | stable_transition_confirmed / stable_heartbeat / hysteresis_carried и т.д. |
| reason_summary | Compact trace строки с pre-cutoff, hysteresis и notes/drops |
| warmup | Readiness map для SMA/ATR/ATR baseline |
| data_quality | drops и notes для stale/missing_ohlc/close_to_close_atr и т.д. |

### Field-by-Field Sensitivity: Detector Root

| Field | Current | Что означает | Если увеличить | Если уменьшить |
| --- | --- | --- | --- | --- |
| basis_tf_sec | 300 | Базовый timeframe детектора | Режим станет инерционнее, heartbeat реже, warmup во времени длиннее | Режим станет быстрее и шумнее, heartbeat чаще |
| uncertain_cutoff | 0.15 | Detector-level minimum для non-UNCERTAIN | Больше raw regimes будут демоутироваться в UNCERTAIN | Больше слабых regimes пройдут detector boundary |
| liveness_factor | 3 | Терпимость к отсутствию detector heartbeat | Downstream дольше не будет блокировать по тишине | Downstream быстрее уйдет в fail-closed при пропаже heartbeat |
| basis_import_buffer | 20 | Extra startup bars | Меньше шанс недогрева на старте, медленнее boot | Быстрее boot, выше риск недогрева/дырок |
| hysteresis_bars | 2 | Подтверждение смены regime | Меньше flip-flop, медленнее смены режимов | Быстрее смены, больше дрожания |
| vol_slope_gate_enabled | true | Dying-storm reject | HIGH_VOL станет более селективным | HIGH_VOL станет легче получать |
| vol_slope_gate_eps | -0.005 | Порог slope reject | Ближе к нулю = gate строже, reject чаще | Более отрицательно = gate слабее |
| vol_slope_gate_confirm_bars | 5 | Сколько bars slope должен оставаться плохим | Reject медленнее и реже | Reject быстрее и чаще |

### Field-by-Field Sensitivity: SMA Trend Model

| Field | Current | Что означает | Если увеличить | Если уменьшить |
| --- | --- | --- | --- | --- |
| sma_short_period | 48 | Короткая SMA | Менее чувствительный short trend, меньше быстрых смен | Более быстрый и шумный short trend |
| sma_long_period | 192 | Длинная SMA | Более медленный baseline, дольше warmup | Быстрее адаптация, меньше smoothing |
| confidence_multiplier | 80.0 | Уклон уверенности по SMA spread | Trend confidence растет быстрее, чаще ceiling clamp | Trend confidence растет медленнее, чаще floor |
| confidence_min | 0.15 | Общий detector floor | Поднимет минимум confidence для trend, volatility и MR | Ослабит общий floor для всех detector branches |
| confidence_max | 0.85 | Общий detector ceiling | Разрешит более высокую confidence для всех detector branches | Раньше начнет ceiling clamp для всех detector branches |

### Field-by-Field Sensitivity: Volatility Model

| Field | Current | Что означает | Если увеличить | Если уменьшить |
| --- | --- | --- | --- | --- |
| enabled | true | Включена ли volatility priority branch | Structural regime чаще будет volatility-driven | Detector останется только с MR/TREND/UNCERTAIN |
| atr_period | 14 | ATR memory length | ATR сгладится, HIGH/LOW_VOL будут медленнее | ATR станет более резким |
| atr_sma_length | 288 | ATR baseline length | Baseline стабильнее, warmup дольше | Baseline адаптивнее, warmup короче |
| allow_close_to_close_atr | true | Можно ли жить без OHLC | Меньше data drops, но ATR менее информативен | Нужен полноценный OHLC, больше fail-closed data drops |
| threshold_multiplier | 2.0 | Барьер HIGH_VOL | HIGH_VOL станет реже | HIGH_VOL станет чаще |
| low_vol_multiplier | 0.7 | Барьер LOW_VOL | LOW_VOL станет чаще | LOW_VOL станет реже |
| high_vol_confidence_multiplier | 2.5 | Крутизна HIGH_VOL confidence | HIGH_VOL быстрее достигает ceiling | HIGH_VOL confidence растет мягче |
| low_vol_confidence_multiplier | 3.0 | Крутизна LOW_VOL confidence | LOW_VOL быстрее достигает ceiling | LOW_VOL confidence растет мягче |

### Field-by-Field Sensitivity: Mean Reversion Model

| Field | Current | Что означает | Если увеличить | Если уменьшить |
| --- | --- | --- | --- | --- |
| threshold | 0.005 | Допуск на SMA spread и price deviations | Больше рынков будут классифицированы как MEAN_REVERSION, max confidence вырастет | MR станет гораздо строже, max confidence снизится |
| confidence_multiplier | 120.0 | Крутизна MR confidence | Tight regimes быстрее получают высокий confidence | MR confidence будет расти мягче |

### System Stress Overlay Fields
System stress не участвует в выборе structural regime label, но живет в том же regime-domain и downstream влияет на gating.

#### Current active snapshot
- enabled = true
- sources_enabled = [price]
- require_l2_if_enabled = true
- baseline_method = rolling
- baseline_window = 100
- burn_in_bars = 120
- robust_method = none
- thresholds: atr_sigma = 2.0, vol_sigma = 2.0, gap_sigma = 3.0, range_sigma = 2.5, volume_sigma = 0.0, spread_sigma = 0.0, depth_drop_pct = 0.0
- aggregation.method = weighted_vote
- aggregation.weights = atr 0.3, vol 0.3, gap 0.2, range 0.2
- aggregation.k = 2
- state_mapping: enter_stress 0.6, exit_stress 0.4, enter_extreme 0.85, exit_extreme 0.7, consecutive_bars_enter 6, consecutive_bars_exit 4, min_duration_bars 15, switch_window_bars 200, max_switches_per_window 2, circuit_breaker_mode halt

#### Time equivalents at current 5m basis
- burn_in_bars = 120 -> 10 часов до первого live stress signal
- consecutive_bars_enter = 6 -> 30 минут подтверждения входа в STRESS/EXTREME
- consecutive_bars_exit = 4 -> 20 минут подтверждения выхода
- min_duration_bars = 15 -> минимум 75 минут в состоянии до разрешения переключения
- switch_window_bars = 200 -> окно 16 часов 40 минут для circuit breaker счетчика

#### Sensitivity summary

| Field | Что означает | Если увеличить | Если уменьшить |
| --- | --- | --- | --- |
| sources_enabled | Какие feed families вообще участвуют | Добавление orderbook расширяет schema surface и требования к данным | Меньше источников, меньше сигналов и меньше data dependencies |
| require_l2_if_enabled | Fail-fast при orderbook source | Жестче startup/runtime требования, меньше silent degradation | Мягче поведение при отсутствии L2, больше риск полуживого режима |
| baseline_window | Окно baselines | Стресс-индекс стабильнее и инерционнее | Стресс-индекс быстрее и шумнее |
| burn_in_bars | Warmup overlay | Позже первый stress signal | Быстрее старт, меньше статистики |
| robust_method | std vs mad | mad делает overlay устойчивее к выбросам | none делает overlay чувствительнее к выбросам |
| atr_sigma / vol_sigma / gap_sigma / range_sigma | Trigger thresholds | Конкретный trigger срабатывает реже | Конкретный trigger срабатывает чаще |
| aggregation.method | Способ сборки composite stress_level | weighted_vote подчеркивает приоритет весов, k_of_n подчеркивает count of fires, max делает доминирующим худший trigger | Возврат к более простому/другому aggregator меняет всю форму stress_level |
| aggregation.weights.* | Вклад fire-trigger в stress_level | Больше вес = trigger важнее | Меньше вес = trigger важность ниже |
| aggregation.k | Нормировка для k_of_n | При k_of_n больший k делает stress_level ниже при том же числе fires | При k_of_n меньший k делает stress_level выше при том же числе fires |
| enter_stress | Барьер входа в STRESS | STRESS труднее достичь | STRESS легче достичь |
| exit_stress | Барьер выхода в NORMAL | Проще выйти из STRESS | Состояние STRESS станет липче |
| enter_extreme | Барьер входа в EXTREME | EXTREME труднее достичь | EXTREME легче достичь |
| exit_extreme | Барьер выхода в STRESS | Проще выйти из EXTREME | EXTREME станет липче |
| consecutive_bars_enter | Подтверждение эскалации | Эскалация медленнее | Эскалация быстрее |
| consecutive_bars_exit | Подтверждение деэскалации | Выход из stress-state медленнее | Выход быстрее |
| min_duration_bars | Минимальное удержание state | State становится липче | State переключается чаще |
| switch_window_bars | Окно circuit breaker | Circuit breaker помнит дольше | Circuit breaker забывает быстрее |
| max_switches_per_window | Терпимость к дрожанию | Больше tolerance before halt | Быстрее перейдет в halt |
| circuit_breaker_mode | Что делать после switch storm | Более жесткий mode сильнее подавляет oscillation | Более мягкий mode допустит больше автопереключений |

### Current Regime-Domain Downstream Gates and Consumers

#### DecisionMaking regime_confidence gate
Resolution order для min/max regime_confidence thresholds в safety_gates.py:
1. strategy-local symbol-specific mapping
2. strategy-local by-regime mapping
3. domain-level by-regime mapping
4. для min only: scalar legacy fallback
5. для max: если mapping нет, upper bound отключен

Current active domain values из config/aurora/domains.yaml:
- min_regime_confidence = 0.35
- min_regime_confidence_by_regime: DEFAULT 0.35, TREND_UP 0.20, TREND_DOWN 0.20
- max_regime_confidence_by_regime: TREND_UP 0.43, TREND_DOWN 0.40
- hard_veto_consecutive_bars = 2
- consecutive_bars = 1
- nrr026_enabled = false
- nrr027_enabled = false

Operational meaning текущей конфигурации:
- below-min regime_confidence сейчас не блокирует входы через NRR-026, потому что nrr026_enabled = false
- above-max regime_confidence по TREND_UP/TREND_DOWN все еще способна блокировать входы, потому что upper-bound path не зависит от nrr026_enabled
- это делает current config необычным: нижний порог largely advisory, верхний порог живой

#### Strategy-local regime_confidence overrides
Code path поддерживает:
- strategies.<strategy>.safety_gates.regime_confidence.min_by_regime
- min_by_symbol
- max_by_regime
- max_by_symbol

Факт current tree:
- в активных strategy YAML эти override surfaces практически не используются
- активные behavior changes идут в основном из domain defaults, а не из strategy-local threshold maps

#### Execution bucket mapping
ExecutionPosition не использует raw structural labels напрямую для exposure policy. Он делает:
- TREND_UP -> TREND_UP
- TREND_DOWN -> TREND_DOWN
- MEAN_REVERSION -> FLAT
- LOW_VOLATILITY -> FLAT
- HIGH_VOLATILITY -> VOLATILE
- unknown -> UNCERTAIN

#### Mean Reversion mapping layer
MeanReversion strategy не торгует structural regime напрямую. Она делает:
- LOW_VOLATILITY -> FLAT_LOW
- MEAN_REVERSION + atr_pct -> FLAT_LOW / FLAT_NORMAL / FLAT_HIGH
- TREND_UP/TREND_DOWN/HIGH_VOLATILITY -> None
- UNCERTAIN -> None fail-closed

Current configurable MR thresholds:
- high_vol_pct = 0.003
- low_vol_pct = 0.001

Это означает:
- atr_pct > 0.3% -> FLAT_HIGH
- atr_pct < 0.1% -> FLAT_LOW
- иначе -> FLAT_NORMAL

#### MD_AMR context validity overlay
MD_AMR не определяет regime, но строит отдельный context_validity score, где regime_confidence является одним из weighted components.

Current weights from active config:
- regime_weight = 0.35
- volatility_weight = 0.2
- structure_weight = 0.2
- progress_alignment_weight = 0.25

Regime validity component там считается piecewise-linear:
- 0.0, если regime is not allowed или regime_confidence <= floor
- 1.0, если regime_confidence >= valid
- linear interpolation между floor и valid

Current thresholds:
- regime_confidence_floor = 0.35
- regime_confidence_valid = 0.6

#### Aurora regime-conditioned thresholds
Aurora decision path использует regime_threshold_multipliers как multiplier к base_threshold.

Текущий active snapshot:
- HIGH_VOLATILITY 0.2
- LOW_VOLATILITY 0.12
- MEAN_REVERSION 0.16
- TREND_UP 0.14
- TREND_DOWN 0.14
- UNCERTAIN 0.18
- DEFAULT 0.16

Политика в aurora_policy.py:
- resolve_regime_factor берет regime-specific value, иначе DEFAULT
- signal_threshold = base_threshold * factor
- далее к нему применяются side-bias multipliers
- если конкретного regime и DEFAULT нет, path уходит в deferred с MISSING_REGIME_THRESHOLD

Практический эффект:
- увеличение factor делает вход труднее
- уменьшение factor делает вход легче

#### Regime shift inception
config/aurora/regime.yaml содержит regime_shift_inception:
- enabled = false
- action = none
- micro_size_fraction = 0.25

Это не detector branch. Это downstream logic для случая raw_regime != stable_regime на первой баре сдвига regime. При текущем active config surface dormant.

## Inferred Findings
- Current uncertain_cutoff практически inert на detector boundary, потому что совпадает с общим detector floor 0.15, а код сравнивает confidence < cutoff. Чтобы cutoff начал реально демоутировать floor-level signals, его нужно поднять выше 0.15.
- confidence_min и confidence_max из sma_trend фактически глобальны для всего detector, хотя семантически названы как trend config. Они clamp-ят не только trend, но и volatility и mean-reversion branches.
- Current MEAN_REVERSION branch заведомо не может достигнуть detector ceiling 0.85. При текущих threshold и multiplier ее theoretical max = 0.75.
- Current HIGH_VOLATILITY ceiling достигается уже при vol_ratio >= 2.28. Current LOW_VOLATILITY ceiling достигается при vol_ratio <= примерно 0.4667. Это делает low-vol branch очень быстро saturating при глубоких calm regimes.
- Current TREND floor действует до SMA spread примерно 0.1875%, а ceiling начинается после примерно 1.0625%. Между этими числами detector имеет реальную чувствительную зону.
- Current SystemStressOverlay при weighted_vote и active weights 0.3/0.3/0.2/0.2 практически требует одновременного срабатывания всех четырех активных trigger families для достижения EXTREME, потому что enter_extreme = 0.85, а любая комбинация из трех текущих весов дает максимум 0.8.
- Current SystemStress STRESS можно получить уже на atr + vol, потому что 0.3 + 0.3 = 0.6 и enter_stress = 0.6.
- Current aggregation.k = 2 сейчас фактически inert, потому что живой aggregator method = weighted_vote. Поле k начнет влиять только если method переключить на k_of_n.
- Current DecisionMaking config downstream conservatism сидит не в нижнем пороге regime_confidence, а в отдельных upper bounds для TREND_UP/TREND_DOWN и в strategy-local regime-aware maps.
- Strategy-local regime_confidence override chain поддерживается кодом, но активный YAML почти не использует ее. Это означает, что реальный precedence path сейчас проще, чем допустимая schema surface.
- Unknown regime labels могут пройти boundary normalization почти без потери, если они не BULL_TREND/BEAR_TREND. Но downstream execution bucket mapping потом collapses unknown values в UNCERTAIN bucket.

## Contradictions / Evidence Gaps
- apps/reference/domains/feature_engineering/regime_mapping.py в верхнем описании все еще говорит про UNCERTAIN -> FLAT_NORMAL, но реальная реализация делает UNCERTAIN -> None fail-closed. Комментарий и код расходятся.
- config/schema поверх SystemStress допускают volume_sigma, spread_sigma, depth_drop_pct и related weight keys, но текущая runtime aggregation в apps/reference/domains/system_stress/system_stress_overlay.py считает stress_level только по atr/vol/gap/range. Это gap между allowed config surface и hot path implementation.
- SystemStressConfig имеет baseline_method = rolling | expanding, но текущий runtime overlay фактически реализует rolling window через deque(maxlen=window) и не показывает отдельную expanding branch. Это похоже на schema/runtime drift.
- Docstring RegimeDetector утверждает, что volatility и mean-reversion detection planned, хотя current runtime code их уже реально исполняет. Это doc drift, а не runtime bug.

## Root Cause Candidates
Если нужно менять то, как система именно идентифицирует regime, первыми кандидатами для вмешательства являются:
- config/aurora/regime.yaml: models.sma_trend.*
- config/aurora/regime.yaml: models.volatility.*
- config/aurora/regime.yaml: models.mean_reversion.*
- config/aurora/regime.yaml: hysteresis_bars и vol_slope_gate_*
- apps/reference/domains/regime_detector/regime_detector.py: fixed priority Volatility -> MR -> Trend

Если нужно менять не идентификацию, а downstream реакцию на уже идентифицированный regime, первыми кандидатами являются:
- config/aurora/domains.yaml: directional_sanity.*regime_confidence*
- config/aurora/strategies/aurora.yaml: decision.regime_threshold_multipliers
- config/aurora/strategies/aurora.yaml и config/aurora/strategies/md_amr.yaml: allowed_regimes и regime_tpsl maps
- config/aurora/strategies/mean_reversion.yaml: regime_thresholds и regime_sizing

## Operational Risk
- Runtime: Current detector can emit weak non-UNCERTAIN regimes at floor confidence 0.15, потому что uncertain_cutoff не режет floor-equal outputs. Если downstream gates ослабить, detector будет пропускать значительно больше marginal signals.
- Runtime: SystemStress EXTREME сейчас очень hard-to-reach из-за сочетания weights и enter_extreme. Если ожидалось более частое EXTREME, проблема, вероятно, в math/config surface, а не в bus wiring.
- Observability Gap: regime payload очень богатый, но operator может легко перепутать raw_regime/source_model с emitted stable regime, если читать только source_model без carried_previous_stable и stable_confidence.
- Config Drift: schema/runtime разрыв по SystemStress orderbook/volume triggers и baseline_method создает риск ложного ощущения, что эти knobs live и fully wired, хотя hot path не подтверждает это.

## Files / Areas Touched
- Новый отчет: REGIME_LOGIC_DEEP_RESEARCH_REPORT_2026-05-12.md
- Runtime code не изменялся.
- Основные inspected sources:
  - apps/reference/domains/regime_detector/regime_detector.py
  - config/aurora/regime.yaml
  - apps/reference/config_models.py
  - apps/reference/core/types/regime_types.py
  - apps/reference/contracts/runtime_regime_layers.py
  - apps/reference/domains/decision_making/gates/safety_gates.py
  - config/aurora/domains.yaml
  - apps/reference/domains/system_stress/system_stress_overlay.py
  - apps/reference/domains/feature_engineering/regime_mapping.py
  - apps/reference/domains/feature_engineering/mean_reversion_strategy.py
  - config/aurora/strategies/aurora.yaml
  - config/aurora/strategies/mean_reversion.yaml
  - config/aurora/strategies/md_amr.yaml

## Validation Performed
- Статический code/config trace по authoritative path, downstream gates и regime vocab mappings.
- Проверка schema surfaces через Pydantic model definitions и runtime consumers.
- Целевой pytest запуск в configured venv:
  - tests/domains/regime_detector/test_reg_fix_01_bar_only.py
  - tests/domains/regime_detector/test_regime_confidence_bar_close_audit.py
  - tests/test_system_stress_overlay.py
- Результат: 31 тест, 31 passed.

## Residual Risk
- В этом документе не развернут построчный inventory каждого per-asset regime_tpsl и objective.regimes.* weights map, потому что они уже потребляют готовые regime labels и не участвуют в первичной идентификации. Поверхности и ключевые семьи указаны, но не все asset rows расписаны отдельно.
- Не проводилась live-log forensic выборка по свежим runtime журналам. Все выводы про логику сделаны по current tree code/config/tests.
- Не доказано намерение разработчиков по части uncertain_cutoff = confidence_min. Это может быть осознанный design choice, а не ошибка.

## What Remains Unproven
- Используются ли в production какие-либо upstream payloads с non-canonical regime labels, кроме BULL_TREND/BEAR_TREND aliases.
- Нужны ли schema-declared orderbook/system stress triggers volume/spread/depth реально для live deployment, или они пока просто зарезервированы на будущее.
- Ожидалось ли бизнес-логикой, что EXTREME state в current system_stress weighted_vote будет достижим только при одновременном fire всех четырех активных trigger families.
- Хотел ли владелец стратегии, чтобы regime detector сам был жестко консервативным, или текущая архитектура сознательно выносит консерватизм вниз, в safety gates и strategy-specific multipliers.

## Minimal Safe Verdict
Если цель состоит в изменении того, какой regime detector распознает и когда он меняется, работать нужно прежде всего с config/aurora/regime.yaml и с fixed priority path внутри RegimeDetector. Если цель состоит в изменении торговой реакции на уже вычисленный regime, менять нужно не detector, а domains.yaml и regime-aware strategy maps.

Current tree разделяет эти две ответственности довольно чисто: structural regime определяет detector, а торговое поведение модифицируют downstream gates, allowlists, context-validity scores, threshold multipliers и TP/SL maps. Самый важный текущий нюанс состоит в том, что detector boundary сейчас мягче, чем downstream usage boundary.
