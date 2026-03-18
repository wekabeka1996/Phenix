# Code-Driven Configuration Passport: `config/aurora/strategies/md_amr.yaml`

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/md_amr_strategy_passport.md`
> - **Audit date:** 2026-03-18
> - **Audit mode:** Code-driven deep sync
> - **Major drifts found:** No structural drifts since the previous audit. The profile correctly documents that the strategy relies on both registry assignment (`XRPUSDT`, `BNBUSDT`) and `md_amr.yaml`. Constants and fail-closed contracts remain perfectly aligned with current active codebase logic.
> - **Overall confidence:** HIGH

Цей паспорт описує лише фактичний live/runtime контракт стратегії `md_amr`, підтверджений через YAML, Pydantic, composition root, handler, gateway та тести.

Статус: production profile, але не вся декларативна поверхня YAML однаково підтверджена як end-to-end runtime SSOT.

Owner:
- Профіль: `config/aurora/strategies/md_amr.yaml`
- Typed contract: `apps/reference/config_models.py::MDAMRStrategyConfig`
- Runtime owner: `apps/reference/domains/decision_making/md_amr_handler.py`
- Plugin wiring: `apps/reference/domains/strategies/plugins/md_amr.py`

## 1. Що є реальним SSOT

MD-AMR активується не самим профілем YAML, а зв'язкою з двох джерел:
- `config/aurora/strategies.yaml` визначає assignment symbols для `md_amr`
- `config/aurora/strategies/md_amr.yaml` визначає профіль, asset blocks, execution policy, objective policy та локальні guard-и

Поточні live assignments для `md_amr`:
- `XRPUSDT`
- `BNBUSDT`

Важливий інваріант runtime:
- handler бере `enabled_symbols` як перетин `strategies_registry.assignments[*] contains md_amr` і `strategies.md_amr.assets.<SYM>.enabled=true`
- asset blocks у `md_amr.yaml`, які не призначені через registry, залишаються лише профільними заготовками і не стають live symbols автоматично

## 2. Startup / activation contract

`apps/reference/main.py` реєструє `MDAMRPlugin()`, а plugin створює звичайний in-process `MDAMRHandler`. Це не sentinel-path і не bridge-driven стратегія.

`MDAMRHandler._parse_config()` працює fail-closed для assigned symbols:
- якщо `md_amr` призначена в registry, але `config.strategies.md_amr` відсутній, startup падає
- якщо assigned symbol існує, але `strategies.md_amr.enabled=false`, startup падає
- якщо для assigned symbol немає `assets.<SYM>`, `exit` або непорожнього `allowed_regimes`, startup падає

Отже, для live symbols справжній контракт сильніший за старий паспорт:
- assignment обов'язковий
- profile block обов'язковий
- per-asset exit contract обов'язковий
- per-asset regime allowlist обов'язковий

## 3. Runtime event surface

Коли `md_amr` активна, handler реєструє такі основні підписки:
- `CMD:PROCESS_STRATEGY`
- `EVT:FEATURES_CALCULATED`
- `EVT:REGIME_DETECTED`
- `EVT:TRADE_EXECUTED`
- `EVT:ORDER_REJECTED`
- `EVT:PORTFOLIO_STATE_UPDATED`
- `EVT:EXPOSURE_SUMMARY_UPDATED`
- `EVT:ORDER_STATE_CHANGED`
- `EVT:TRADE_INTENT_REJECTED`

На старті handler викликає `_hydrate_state_from_rest()`, а також має `seed_startup_bars()` для cold-start counters після startup basis hydration.

## 4. Що реально споживається з профілю

`MDAMRStrategyConfig` типізує такі runtime-поля:
- базові параметри сигналу: `timeframe_sec`, `defer_ttl_sec`, `channel_window_bars`, `atr_window`, `atr_stats_window`, `hysteresis_mult`, `threshold_z`, `volatility_dampening_factor`, `thr_base`, `thr_floor`, `alpha`, `conf_min`, `max_hold_bars`, `atr_zscore_clamp`, `atr_std_floor_pct`
- витрати/масштабування: `fee_bps`, `slippage_buffer_bps`, `scaleout_fraction`, `scaleout_cost_model`
- multi-timeframe weights: `weights.d1/h1/m30/m15`
- execution policy: `execution.*`
- safety gates: `safety_gates`
- md_amr-local guards: `llm_gate`, `reconciliation`, `concentration_guard`
- per-asset contract: `assets.<SYM>`
- strategy-local objective config: `objective`

У runtime ці поля реально споживаються так:
- сигналогенератор `MDAMRStrategyV11` отримує майже всю math/config поверхню напряму з профілю
- `timeframe_sec` є жорстким фільтром: події з іншим `tf_sec` ігноруються
- `defer_ttl_sec` формує `EVT:FEATURE_DEFER_EXPIRED`
- `allowed_regimes` та `cooldown_sec` контролюють entry gate на symbol-рівні
- `concentration_guard.max_simultaneous_entries_per_bar` переводить надлишкові entry у defer path
- `llm_gate` реально читає `features.sentiment_state` і заводить тимчасовий macro-block
- `objective` реально запускає Objective Engine лише коли увімкнені і domain, і strategy profile

## 5. Objective Engine contract

Для `ENTRY` MD-AMR викликає Objective Engine лише за одночасного виконання умов:
- `domains.objective_engine.enabled=true`
- `strategies.md_amr.objective.enabled=true`
- присутні live portfolio та exposure summary
- присутні regime, regime timestamp, regime confidence
- зібрані TP/SL і thresholds у `trace`

Якщо ці залежності порушені і `strict_fail_closed=true` у domain config, handler не деградує мовчки, а відхиляє intent через `OBJECTIVE_ENGINE_FAIL_CLOSED`.

Додатковий контракт із typed config:
- коли `md_amr.objective.enabled=true`, `AuroraConfig` валідатор вимагає regime coverage для всіх regime values, що реально використовуються assigned symbols через `assets.<SYM>.allowed_regimes`

## 6. Asset-level live contract

Per-asset блок для live symbol повинен містити:
- `enabled=true`
- `allowed_regimes` як непорожній список допустимих regime labels
- `exit` block

`allowed_regimes` проходить нормалізацію alias-ів на рівні Pydantic, а handler додатково розширює сумісність режимів через власну compatibility map.

`exit` справді є runtime-критичним:
- для `ENTRY` handler обчислює regime-aware `stop_price` і `target_price`
- ці значення кладуться в `price_ctx`
- у payload також додається `tpsl_ctx`

Важливе уточнення:
- YAML містить asset blocks для `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `DOGEUSDT`, `XRPUSDT`, `BNBUSDT`
- але live `md_amr` зараз активна лише для `XRPUSDT` і `BNBUSDT`, бо тільки вони assigned у registry

## 7. Readiness, cold start та signal emission

MD-AMR має кілька реальних блокувальних шарів перед emission:
- mandatory live warmup
- runtime warmup readiness
- `basis_required_bars` із compatibility profile
- asset config presence
- regime allowlist gate
- cooldown
- concentration guard
- objective gate

Тільки після цього handler емить `EVT:STRATEGY_SIGNAL_PRODUCED` з:
- `strategy_id=md_amr`
- `intent_kind` у множині `ENTRY | FULL_CLOSE | PARTIAL_CLOSE`
- `trace` з `dir_score`, thresholds, weights, qty fields, `conf_ratio`
- `scoring.objective`, якщо objective path був пройдений
- `runtime_permissions` та `runtime_readiness`
- `price_ctx` і regime-aware TP/SL для entry

Окремо підтверджено тестами:
- gateway fail-closed валідатор вимагає повний md_amr trace
- `FULL_CLOSE` і `PARTIAL_CLOSE` обробляються reduce-only шляхом downstream у `StrategyGateway`
- cold-start bars gate реально блокує emission з `BARS_REQUIRED_COLD_START`

## 8. Execution policy: що реально означає `execution.*`

`execution` є частиною typed contract і downstream execution SSOT, але важливо розділяти два рівні:
- generic order policy downstream читається загальною execution/intent path
- сам `MDAMRHandler` локально використовує лише частину цього блоку напряму

Що реально підтверджено в handler:
- `gtx_retry_max` використовується для локального лічильника повторів після `ORDER_REJECTED`
- `gtx_fallback_to_market` не виконує реальний fallback сам по собі; handler лише логгує намір fallback і скидає retry counter

Що не варто документувати як handler-owned behavior без застереження:
- реальне перевиставлення ордера або автоматичний market fallback з цього місця не простежено

## 9. Reconciliation contract

`reconciliation.enabled` і `reconciliation.drift_tolerance` не є мертвими полями на рівні коду: у handler існує `reconcile_position(symbol, exchange_qty)`, який:
- порівнює local qty з exchange qty
- при дрифті понад tolerance синхронізує локальний стан
- при зануленні позиції скидає `bars_held`

Але в audited live path зовнішній виклик `reconcile_position()` не був простежений. Тому коректний статус такий:
- локальна reconcile logic реалізована
- end-to-end wiring цієї логіки в поточному trace не підтверджено

## 10. Що старий паспорт описував неточно

Старий документ був занадто декларативним і змішував profile surface з підтвердженою live поведінкою. Після code trace коректніше формулювати так:
- `md_amr.enabled` не достатній для активації без registry assignment
- не всі asset blocks у YAML є live-active
- `gtx_fallback_to_market` зараз слабший за назву поля: у traced handler path це не автоматичний fallback, а лише retry/fallback bookkeeping
- `reconciliation` має локальний код, але повна runtime wiring не підтверджена цим аудитом

## 11. Підсумок

`md_amr.yaml` є реальним strategy-profile SSOT для math, guards, objective policy, per-asset TP/SL та базових execution flags, але live activation визначається лише в парі з `strategies_registry.assignments`.

Практично це означає:
- strategy profile без assignment не вмикає символ
- assigned symbol без asset contract не стартує
- entry path у md_amr є жорстко fail-closed на readiness/regime/objective контрактах
- частина декларативних execution/reconciliation claims потребує обережного формулювання, бо їх end-to-end wiring не повністю доведена поточним trace
