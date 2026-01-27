# Aurora BTCUSDT Config Audit (2026-01-27)

## Мета

1) Провести аудит **усіх полів BTCUSDT** у `config/aurora/strategies/aurora.yaml` (Aurora SSOT).  
2) Дати чіткий звіт по **кожному полю**: що означає, де споживається в коді, як впливає на рантайм.  
3) Найголовніше: **в яких режимах** моделі дозволено працювати.  
4) Перевірити дублювання по інших YAML (backtest YAML ігноруємо).  
5) Додати **runtime-тест**, який доводить, що ці поля реально “доходять” до системи та впливають на поведінку.

---

## TL;DR (ключові висновки)

- **Allowed regimes для BTCUSDT (Aurora)**: `["TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY", "FLAT_LOW", "FLAT_NORMAL"]`  
  Це **строгий allowlist**: якщо режим не в списку — AuroraHandler **не має права** емітити інтенти в цьому режимі.
- Знайдені “зомбі/дірки у проводці” (в AuroraHandler v7):  
  - `side_bias` (per-symbol), `regime_thresholds` (per-symbol), `liquidity_gate` (per-symbol/global) та `regime_sizing` (per-symbol) **не гарантувалися** як “живі” в новій архітектурі.  
  - Виправлено: додана проводка цих полів у рантайм (див. “Зміни в коді”).
- BTCUSDT присутній у кількох YAML, але це **різні SSOT-області** (strategy vs instruments vs registry). Найважливіший ризик дублювання: **leverage** має кілька джерел істини (див. нижче “Дублювання / джерела”).

---

## 1) Де живе конфіг BTCUSDT і як він завантажується

### Файли, що впливають на торгівлю BTCUSDT (не backtest)

- `config/aurora/strategies.yaml`  
  SSOT: які стратегії призначені символу (registry assignments).
- `config/aurora/strategies/aurora.yaml`  
  SSOT: глобальна політика Aurora (`aurora.decision`) + per-symbol overrides (`aurora.assets.BTCUSDT.*`).
- `config/aurora/instruments.yaml`  
  SSOT: tick/step/min_qty/min_notional + **execution.target_leverage/margin_mode** + sizing.margin_pct.
- `config/aurora/domains.yaml`, `config/aurora/system.yaml`, `config/aurora/regime.yaml`, `config/aurora/trading.yaml`  
  Домени, режими, режим роботи, TTL тощо.

### Важливо про backtest_override.yaml (ігноруємо в цьому аудиті)

Файл `config/aurora/backtest_override.yaml` **може** оверрайдити `strategies.*` при `trading_mode == backtest`.  
У runtime-тесті ми **явно вимикаємо backtest режим**, щоб перевірити “чистий” SSOT без оверрайдів.

---

## 2) Allowed regimes (найголовніше)

### Поточний allowlist для BTCUSDT (Aurora)

Джерело: `config/aurora/strategies/aurora.yaml` → `aurora.assets.BTCUSDT.allowed_regimes`

```
["TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY", "FLAT_LOW", "FLAT_NORMAL"]
```

### Як це працює в коді

- Споживач: `apps/reference/domains/decision_making/aurora_handler.py`
- Механіка: **STRICT allowlist** через `RegimeAllowlistContract.is_regime_allowed(...)`
  - Якщо `allowed_regimes` порожній/None → **блокуються всі режими** (fail-closed).
  - Якщо `current_regime` не входить у список → емітиться `EVT:STRATEGY_DECISION_BLOCKED` з `reason_code=REGIME_NOT_ALLOWLISTED`.

---

## 3) Поля BTCUSDT: що це, де використовується, чи “живе”

Нижче — шлях у YAML (canonical), короткий зміст і основні споживачі.

### 3.1 leverage

- `strategies.aurora.assets.BTCUSDT.leverage.target` / `.mode`
  - **Що:** цільове плече та маржинальний режим для “P1: Active Leverage Management”.
  - **Де використовується:** `apps/reference/domains/execution_position/fsm.py` → `_collect_leverage_configs()` → `LeverageBootstrapper` (startup sync на біржі).
  - **Примітка про дублювання:** це **не те саме**, що `instruments.BTCUSDT.execution.target_leverage` (див. “Дублювання” нижче).

### 3.2 weights (per-symbol signal weights)

- `strategies.aurora.assets.BTCUSDT.weights.*`
  - **Що:** ваги фіч для Aurora scoring (Score V2/Kernel).
  - **Де використовується:** `apps/reference/domains/decision_making/aurora_handler.py` → `_get_signal_weights()`.
  - **Fail-closed:** ключі ваг валідяться Pydantic’ом (канонічні ключі).

### 3.3 enabled, position_mode

- `strategies.aurora.assets.BTCUSDT.enabled`
  - **Що:** legacy пер-symbol enabled (але SSOT activation — registry assignments).
  - **Де використовується:** `AuroraHandler._is_symbol_enabled()` (спочатку перевіряє `strategies_registry.assignments`).

- `strategies.aurora.assets.BTCUSDT.position_mode` (`STRICT|DYNAMIC`)
  - **Що:** анти-пірамідинг / правила same-side позицій.
  - **Де використовується:** `apps/reference/domains/decision_making/decision_making.py` → `_resolve_position_mode()` → flip orchestration.

### 3.4 holding_period (min hold + emergency override)

- `strategies.aurora.assets.BTCUSDT.holding_period.min_duration_sec`
- `strategies.aurora.assets.BTCUSDT.holding_period.emergency_exit_threshold`
  - **Що:** анти-чорн-гейт: мінімальний час у позиції + emergency override по |score|.
  - **Де використовується:** `AuroraHandler._get_min_duration_sec()`, `_get_emergency_threshold()`, `_should_suppress_soft_exit()`.

### 3.5 reentry_cooldown_sec

- `strategies.aurora.assets.BTCUSDT.reentry_cooldown_sec`
  - **Що:** анти “ping-pong” — пауза після виходу перед новим входом.
  - **Де використовується:** `AuroraHandler._get_reentry_cooldown_sec()` + гейт “REENTRY_COOLDOWN”.

### 3.6 liquidity_gate

- `strategies.aurora.assets.BTCUSDT.liquidity_gate.{enabled,kappa_min,kappa_max,failsafe_qty_check}`
  - **Що:** hard-gate за ліквідністю (на базі `features.liquidity_kappa`).
  - **Де використовується (після виправлення):** `AuroraHandler._check_liquidity_gate()` (перед kernel scoring).
  - **Fail-closed (коли enabled=true):**
    - `warmup.ready["liquidity_kappa"]` має бути `True`
    - `features["liquidity_kappa"]` має існувати та парситися
    - `liquidity_kappa >= kappa_min`
  - **Примітка:** `kappa_max` використовується як defensive clamp (FE і так clamp’ить), `failsafe_qty_check` зараз передається в details/ctx (але не змінює sizing, бо sizing уже fail-closed по min_qty/min_notional у DecisionMaking).

### 3.7 side_bias (per-symbol override)

- `strategies.aurora.assets.BTCUSDT.side_bias.{penalty_factor,window_sec,target_ratio}`
  - **Що:** штраф за “перекіс” напрямку у вікні (менше chase’у однієї сторони).
  - **Де використовується (після виправлення):** `AuroraHandler._get_side_bias_state()` тепер враховує per-symbol override (раніше брав тільки global).
  - **Min intents:** береться з глобального `aurora.decision.side_bias_min_intents` (per-asset min_intents у схемі не передбачено).

### 3.8 regime_thresholds (per-symbol)

- `strategies.aurora.assets.BTCUSDT.regime_thresholds.*`
  - **Що:** мультиплікатори threshold’ів залежно від regime.
  - **Де використовується (після виправлення):** `AuroraHandler` тепер передає в kernel **per-symbol regime_thresholds**, якщо вони задані (інакше — глобальні `aurora.decision.regime_threshold_multipliers`).

### 3.9 regime_sizing (per-symbol)

- `strategies.aurora.assets.BTCUSDT.regime_sizing.*`
  - **Що:** множник розміру позиції за regime.
  - **Де використовується (після виправлення):** `DecisionMaking` (strategy-signal gateway) тепер читає цей dict та передає `margin_pct_mult` у `_calculate_position_size()`.
  - **Семантика реалізації:** множиться `instruments.<SYM>.sizing.margin_pct` (margin-first sizing), з clamp до `<= 1.0`.

### 3.10 exit / take_profit / trailing_stop

- `strategies.aurora.assets.BTCUSDT.exit.sl_pct`
  - **Що:** базовий SL% (використовується також як база для regime TP/SL).
  - **Де використовується:** `AuroraHandler._compute_tpsl_pct_mult()` (fail-closed якщо відсутнє), а також fallback-логіка bracket’ів в execution_position.

- `strategies.aurora.assets.BTCUSDT.exit.max_hold_sec`
  - **Що:** watchdog forced exit по часу.
  - **Де використовується:** `apps/reference/domains/execution_position/fsm_manage.py` → `_get_max_hold_sec()` / `_check_max_hold_time()`.

- `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.*`
  - **Що:** адаптація SL/TP по режимах (pct_mult або atr).
  - **Де використовується:** `AuroraHandler._compute_regime_tpsl()` + інжекція `stop_price/target_price` у `EVT:STRATEGY_SIGNAL_PRODUCED`.

- `strategies.aurora.assets.BTCUSDT.take_profit.{tp_low_ratio,tp_high_ratio,partial_exit_pct}`
  - **Що:** TP1/TP2 і % часткового виходу.
  - **Де використовується:** `execution_position/fsm_manage.py` (partial exits + TP1/TP2) та fallback bracket calc.

- `strategies.aurora.assets.BTCUSDT.trailing_stop.*`
  - **Що:** trailing stop (активація, трейл, rate-limit).
  - **Де використовується:** `execution_position/fsm_manage.py` → `_get_trailing_stop_params()` / `_check_trailing_stop()`.

### 3.11 signal_threshold, cooldown_sec

- `strategies.aurora.assets.BTCUSDT.signal_threshold.{enabled,value}`
  - **Що:** per-symbol override порогу сигналу.
  - **Де використовується:** `AuroraHandler` перед kernel compute (base_threshold).

- `strategies.aurora.assets.BTCUSDT.cooldown_sec`
  - **Що:** per-symbol cooldown у DecisionMaking gateway.
  - **Де використовується:** `DecisionMaking._get_symbol_cooldown()`.

### 3.12 volatility_entry_logic

- `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.{enabled,regime_multipliers.*}`
  - **Що:** “Smart Limit Entry” — offset ціни входу на базі ATR × multiplier (BUY нижче, SELL вище).
  - **Де використовується:** `AuroraHandler._emit_signal()` → `_get_volatility_strict()` + `regime_multipliers`.
  - **Fail-closed:** якщо ATR відсутній — сигнал **abort** + `EVT:STRATEGY_DECISION_BLOCKED (ATR_MISSING_FAIL_CLOSED)`.

### 3.13 timeframe_sec (per-symbol)

- `strategies.aurora.assets.BTCUSDT.timeframe_sec`
  - **Що:** per-symbol timeframe override.
  - **Статус:** у AuroraHandler payload зараз використовується `strategies.aurora.timeframe_sec` (глобальний), per-symbol override застосовується в інших місцях через SSOT правила timeframe (не є ключовим для BTC, бо в YAML null).

---

## 4) Дублювання по YAML (backtest YAML ігноруємо)

Пошук `BTCUSDT:` у `config/aurora/**` (без `archive/**` і без `backtest_override.yaml`) дає:

- `config/aurora/strategies/aurora.yaml` — Aurora per-symbol params (цей аудит).
- `config/aurora/strategies/mean_reversion.yaml` — MR profile також містить блок BTCUSDT, але **не активний**, якщо BTC не призначений MR у `strategies.yaml`.
- `config/aurora/instruments.yaml` — precision/execution/sizing SSOT (інший namespace).
- `config/aurora/strategies.yaml` — registry assignments (активація стратегій).
- `config/aurora/trading.yaml` — legacy `trading.execution.exposure.leverage_defaults.BTCUSDT` (використовується ExposureGuard як legacy fallback, не як SSOT sizing/leverage).

### Критичне “подвійне leverage SSOT”

BTC має:
- `strategies.aurora.assets.BTCUSDT.leverage.target = 20` (strategy leverage bootstrap)
- `instruments.BTCUSDT.execution.target_leverage = 50` (margin-first sizing + verify в execution_position)

Це різні контракти, але **ризиковано**, якщо система одночасно:
1) виставляє на біржі leverage=20 (bootstrap)  
2) рахує qty як для leverage=50 (DecisionMaking sizing)

Рекомендація: визначити єдину SSOT політику (або додати явний assert/guard, що ці значення узгоджені).

---

## 5) Зміни в коді (щоб поля були “живі”)

### AuroraHandler (новий шлях)

- `apps/reference/domains/decision_making/aurora_handler.py`
  - Додано per-symbol `side_bias` override в `_get_side_bias_state()`.
  - Додано per-symbol `regime_thresholds` override в kernel call (`_get_regime_thresholds()`).
  - Додано `liquidity_gate` (global + per-symbol) як ранній gate (`_check_liquidity_gate()`).
  - Для **typed AuroraConfig** (реальний runtime з ConfigLoader) — fail-closed на відсутність ключових decision-полів (без “тихих” дефолтів). Для mock’ів/тестів з SimpleNamespace/MagicMock збережена backward сумісність.

### DecisionMaking sizing (regime_sizing)

- `apps/reference/domains/decision_making/decision_making.py`
  - Додано витяг `regime_sizing[regime]` для aurora strategy signals та передача `margin_pct_mult` у `_calculate_position_size()`.
  - `_calculate_position_size()` тепер підтримує множник (з clamp до 1.0) та додає debug поля `margin_pct_base`, `margin_pct_mult`.

---

## 6) Додані/оновлені тести

- Новий runtime тест:
  - `tests/config/test_btcusdt_aurora_runtime_fields.py`
  - Доводить:
    - ConfigLoader завантажує BTC поля
    - AuroraHandler реально використовує per-symbol `side_bias`, `regime_thresholds`, `signal_threshold`, `volatility_entry_logic`, `liquidity_gate`, `holding_period`, `reentry_cooldown_sec`, `regime_tpsl`
    - DecisionMaking gateway бачить `regime_sizing` (margin_pct_mult) + читає `position_mode` і `cooldown_sec`
    - ExecutionPosition manage flow читає `take_profit`, `trailing_stop`, `max_hold_sec`
    - ExecPosFSM збирає `leverage` для bootstrap

- Актуалізація існуючих тестів під SSOT-поведінку:
  - `tests/domains/decision_making/test_timers_reentry_cooldown_v1.py` (allowlist + entry tracking SSOT через `EVT:TRADE_EXECUTED`)
  - `tests/domains/decision_making/test_aurora_handler.py` (warmup SSOT: REGIME_DETECTED не оновлює warmup)

### Як запустити

```
pytest -q tests/config/test_btcusdt_aurora_runtime_fields.py
```

---

## 7) Що ще варто вирішити (після аудиту)

1) **Leverage SSOT**: узгодити `strategies.*.leverage` та `instruments.*.execution.target_leverage`.  
2) `liquidity_gate.failsafe_qty_check`: або зробити реальну поведінку (якщо потрібна), або прибрати як “семантичний шум”.  
3) Перевірити, чи `regime_sizing` множник дійсно має бажану семантику (зараз він масштабує `margin_pct`).
