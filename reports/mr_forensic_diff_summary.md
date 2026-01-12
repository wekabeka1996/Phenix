# MR-FORENSIC-001 — Diff/Wiring Summary

## Baseline
- Baseline commit (message: "сохраняємо жизнь"): `865bf5c`
- Scope diff: `apps/reference/domains/{decision_making,market_data,feature_engineering}`, `apps/reference/api`, `apps/reference/config*`, `config/**`

## What changed (wiring-relevant deltas)

### Strategy bootstrapping
- Composition root wires a **StrategyPluginRegistry + StrategyRuntime** and starts plugins based on `config.strategies_registry.assignments`.
  - This is where MR handler is created + subscribed (via `handler.register()`).

### Market data → FSM
- `MarketDataProxy` emits `EVT:MARKET_TICK_RECEIVED` (not `EVT:MARKET_TICK_FORWARDED`).
- `BarAggregator` is wired as a passive observer in composition root:
  - listens to `EVT:MARKET_TICK_RECEIVED`
  - emits `EVT:BAR_CLOSED`

### Feature Engineering
- `FeatureEngineering` subscribes to:
  - `EVT:MARKET_TICK_RECEIVED` (tick-features)
  - `EVT:BAR_CLOSED` (bar-features)
- `EVT:FEATURES_CALCULATED` payload includes `tf_sec` (tick-features use `tf_sec=0`; bar-features use `tf_sec=180/300`).

### Mean Reversion handler (MR)
- MR handler activation is SSOT-driven:
  - symbols are assigned in `config/aurora/strategies.yaml` (strategies_registry)
  - global enable + per-asset enable + timeframe live in `config/aurora/strategies/mean_reversion.yaml`
- **Critical mismatch:** MR subscribes to `EVT:MARKET_TICK_FORWARDED` (for bar building + signal generation), but the runtime emits only `EVT:MARKET_TICK_RECEIVED`.
  - Result: MR can accept `EVT:FEATURES_CALCULATED (tf_sec=180)` but its tick-driven bar builder does not run → no MR bars/state progression and no MR bar logger output.

## Evidence (SSOT + code)
- Verb registry defines:
  - `BAR_CLOSED` owner `market_data` (active)
  - `FEATURES_CALCULATED` owner `feature_engineering` (active)
  - `MARKET_TICK_RECEIVED` owner `market_data` (active)
  - `MARKET_TICK_FORWARDED` owner `market_data` (active)
- Code reality:
  - `MarketDataProxy._emit_tick()` emits `EVT:MARKET_TICK_RECEIVED` only.
  - No emitter found for `EVT:MARKET_TICK_FORWARDED` in `market_data` domain or composition root.

## Config “truth matrix” (SSOT)

| Concern | File | Keys | Effective value |
|---|---|---|---|
| MR global enable | config/aurora/strategies/mean_reversion.yaml | `mean_reversion.enabled` | `true` |
| MR timeframe | config/aurora/strategies/mean_reversion.yaml | `mean_reversion.timeframe_sec` | `180` |
| MR per-asset enable | config/aurora/strategies/mean_reversion.yaml | `mean_reversion.assets.DOGEUSDT.enabled`, `...XRPUSDT.enabled` | `true`, `true` |
| MR assignments (activation SSOT) | config/aurora/strategies.yaml | `assignments.DOGEUSDT`, `assignments.XRPUSDT` | `['mean_reversion']`, `['mean_reversion']` |
| BarAggregator enable | config/aurora/trading.yaml | `trading.market_data.bar_aggregator.enabled` | `true` |
| BarAggregator TFs | config/aurora/trading.yaml | `trading.market_data.bar_aggregator.timeframes_sec` | `[180, 300]` |
| FE enabled TFs | config/aurora/domains.yaml | `feature_engineering.enabled_timeframes_sec` | `[180, 300]` |

## FSM subscription map (who listens to what)

| Consumer | Event | Handler | Where wired |
|---|---|---|---|
| MarketDataProxy | (emits) `EVT:MARKET_TICK_RECEIVED` | `_emit_tick()` | apps/reference/domains/market_data/proxy.py:211 |
| BarAggregator | `EVT:MARKET_TICK_RECEIVED` | `bar_aggregator.on_market_tick` | apps/reference/main.py:1652 |
| BarAggregator | (emits) `EVT:BAR_CLOSED` | `_emit_bar_closed()` | apps/reference/domains/market_data/bar_aggregator.py:278 |
| FeatureEngineering | `EVT:MARKET_TICK_RECEIVED` | `on_market_tick` | apps/reference/domains/feature_engineering/feature_engineering.py:147 |
| FeatureEngineering | `EVT:BAR_CLOSED` | `on_bar_closed` | apps/reference/domains/feature_engineering/feature_engineering.py:150 |
| DecisionMaking | `EVT:FEATURES_CALCULATED` | `on_features` | apps/reference/domains/decision_making/decision_making.py:326 |
| DecisionMaking | `EVT:STRATEGY_SIGNAL_PRODUCED` | `_on_strategy_signal_gateway` | apps/reference/domains/decision_making/decision_making.py:332 |
| MR Handler | `EVT:MARKET_TICK_FORWARDED` | `_on_market_tick` | apps/reference/domains/decision_making/mean_reversion_handler.py:162 |
| MR Handler | `EVT:FEATURES_CALCULATED` | `_on_features_calculated` | apps/reference/domains/decision_making/mean_reversion_handler.py:164 |
| StrategyRuntime | (calls) `handler.register()` | N/A | apps/reference/domains/strategies/registry.py:97 |

### Notable gap
- `EVT:MARKET_TICK_FORWARDED` is **active in SSOT verb registry** (owner `market_data`) but **no code path emits it** in the current runtime wiring; therefore MR’s tick-driven path never fires.

## Impact summary
- **Primary break:** missing/unused `EVT:MARKET_TICK_FORWARDED` emission → MR never processes ticks → does not build bars → does not produce signals → `logs/mean_reversion/bars_180s.tsv` stays header-only.
- FE + BarAggregator pipeline can still emit bar-features (`EVT:FEATURES_CALCULATED` with `tf_sec=180`), but MR’s signal path remains tick-driven.

## One-sentence conclusion (point of break)
MR не працює як стратегія (немає барів/сигналів), бо **підписаний на `EVT:MARKET_TICK_FORWARDED`, але в runtime ніхто не емітить цей event (є лише `EVT:MARKET_TICK_RECEIVED`)**, тому його tick→bar→signal ланцюг не запускається.
