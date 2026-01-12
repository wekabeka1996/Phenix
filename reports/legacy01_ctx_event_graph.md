# LEGACY-01-CTX — Tick-driven chain audit (DecisionMaking/MR)

Goal: локалізувати старий шлях, який ще тригерить DecisionMaking/MR через `EVT:FEATURES_CALCULATED` (tick tf), і зафіксувати “де губиться tf_sec”.

## Факт: де народжується `tf_sec=0`

`FeatureEngineering.on_market_tick()` викликає `FeatureEngineering._calculate_and_emit_features()` → `FeatureEngineering._calculate_and_emit_features_for_tf(..., tf_sec=0, ...)` і емітить `EVT:FEATURES_CALCULATED` з `tf_sec=0`.

Ключові місця:
- `apps/reference/domains/feature_engineering/feature_engineering.py`:
  - `on_market_tick()` → tick path
  - `_calculate_and_emit_features()` (ставить `tf_sec=0`)
  - `_calculate_and_emit_features_for_tf()` (емітить `EVT:FEATURES_CALCULATED`)

## Подієвий граф (релевантні ребра)

### `EVT:MARKET_TICK_RECEIVED`
- Producer:
  - `apps/reference/domains/market_data/market_data_connector.py` (емітить `EVT:MARKET_TICK_RECEIVED`)
  - `apps/reference/domains/market_data/proxy.py` (multiprocessing path, також емісія tick)
- Consumers (подписки):
  - `apps/reference/domains/feature_engineering/feature_engineering.py: FeatureEngineering.__init__ → listen("EVT:MARKET_TICK_RECEIVED", on_market_tick)`
  - `apps/reference/main.py: initialize_domains() → listen("EVT:MARKET_TICK_RECEIVED", BarAggregator.on_market_tick)` (якщо bar_aggregator enabled)
  - `apps/reference/domains/position_tracking/position_tracking.py` (опційно, config-gated)
- Payload (фактично використовується):
  - `symbol`, `ts` (ms), `price/mid/bid/ask`, `bid_size/ask_size`, `buy_volume/sell_volume`…

### `EVT:BAR_CLOSED`
- Producer:
  - `apps/reference/domains/market_data/bar_aggregator.py: BarAggregator._emit_bar_closed()` (через `fsm.emit("EVT:BAR_CLOSED", payload, why=...)`)
- Consumers:
  - `apps/reference/domains/feature_engineering/feature_engineering.py: FeatureEngineering.__init__ → listen("EVT:BAR_CLOSED", on_bar_closed)`
  - `apps/reference/domains/decision_making/mean_reversion_handler.py: MeanReversionHandler.register → listen("EVT:BAR_CLOSED", _on_bar_closed_data_only)` (data-only)
- Payload shape:
  - `ts_ms`, `symbol`, `bar.{symbol,timeframe_sec,start_ts_ms,end_ts_ms,open,high,low,close,volume,...}`
- Дірка (OBS-02-CTX): в `ops/wal/**/*.jsonl` зараз **нема** жодних `BAR_CLOSED` записів → бари не є SSOT в WAL.

### `EVT:FEATURES_CALCULATED`
- Producer:
  - `apps/reference/domains/feature_engineering/feature_engineering.py: _calculate_and_emit_features_for_tf()`
    - tick path: `tf_sec=0`
    - bar path: `tf_sec = bar.timeframe_sec` (викликається з `on_bar_closed()`)
- Consumers (подписки):
  - `apps/reference/domains/risk_management/risk_management.py: listen("EVT:FEATURES_CALCULATED", on_features_calculated)`
  - `apps/reference/domains/decision_making/decision_making.py: listen("EVT:FEATURES_CALCULATED", on_features)`
  - `apps/reference/domains/decision_making/mean_reversion_handler.py: listen("EVT:FEATURES_CALCULATED", _on_features_calculated)` (data-only, але логить reject)
  - `apps/reference/domains/regime_detector/regime_detector.py: listen("EVT:FEATURES_CALCULATED", handle_event)` (вже має bar-only фільтр)
  - `apps/reference/domains/strategies/plugins/aurora_builtin.py: listen("EVT:FEATURES_CALCULATED", _on_features_data_only)` (data-only warmup cache)
- Payload keys (фактично очікуються/використовуються):
  - `symbol`, `ts` (ms), `tf_sec`, `features`, `warmup`, (інколи `bar_data`)

### `EVT:RISK_ASSESSMENT_COMPLETED`
- Producer:
  - `apps/reference/domains/risk_management/risk_management.py: on_features_calculated()`
- Consumers:
  - `apps/reference/domains/decision_making/decision_making.py: listen(..., on_risk)`
- Payload keys:
  - `symbol`, `ts`, `risk_parameters`
- Дірка:
  - `tf_sec` **втрачається** в RiskManagement (воно не прокидається з `EVT:FEATURES_CALCULATED` у `EVT:RISK_ASSESSMENT_COMPLETED`).

### `CMD:PROCESS_STRATEGY` (bar-only стратегічний тригер)
- Producer:
  - `apps/reference/domains/feature_engineering/feature_engineering.py: _calculate_and_emit_features_for_tf()` (bar path) емітить `CMD:PROCESS_STRATEGY` (через `fsm.emit("CMD:PROCESS_STRATEGY", ...)`)
- Consumers:
  - `apps/reference/domains/decision_making/mean_reversion_handler.py: listen("CMD:PROCESS_STRATEGY", _on_process_strategy)` (primary)
  - `apps/reference/domains/strategies/plugins/aurora_builtin.py: listen("CMD:PROCESS_STRATEGY", _on_process_strategy)` (primary for AuroraHandler)
- Дірка (OBS-02-CTX):
  - у WAL зараз **0** записів `PROCESS_STRATEGY/CMD:PROCESS_STRATEGY` → стратегічний цикл не є SSOT в WAL.

## Де саме виникає `MR rejecting features ... tf_sec 0 != 180`

Причина: MR слухає `EVT:FEATURES_CALCULATED` (data-only) і має TF guard:
- `apps/reference/domains/decision_making/mean_reversion_handler.py: _on_features_calculated()`
  - якщо `tf_sec is None` або `tf_sec != self.timeframe_sec` → `logger.warning("MR rejecting features ...")`

При tick path `tf_sec=0`, а `self.timeframe_sec` (з конфігу MR) зазвичай `180` → гарантований reject + WARN spam.

## Вердикт (що від’єднати/загейтити)

Мінімально (fail-closed для стратегій; tick залишити як телеметрію):
- Від’єднати або строго загейтити MR `EVT:FEATURES_CALCULATED` data-only path (ігнор `tf_sec<=0` без WARN; краще взагалі не слухати).
- Від’єднати/загейтити `DecisionMaking.on_features` від `EVT:FEATURES_CALCULATED`, якщо воно не є частиною bar-only SSOT (зараз це в основному лог/alpha-telemetry).
- Якщо RiskManagement має працювати bar-only: додати `tf_sec` у `EVT:RISK_ASSESSMENT_COMPLETED` або фільтрувати `EVT:FEATURES_CALCULATED` до basis tf (інакше знов губиться контекст tf).

Дублі/ризики:
- `FSMCore.emit()` формує `Message(op=\"EVT\", verb=...)` навіть якщо `event_name` починається з `CMD:` → оп-семантика “CMD vs EVT” зараз існує тільки в імені каналу, не в `Message.op`.

