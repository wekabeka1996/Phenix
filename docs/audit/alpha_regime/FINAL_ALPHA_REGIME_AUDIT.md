## Intent vs reality

- **Intended flow (per docs)**: FeatureEngineering emits `EVT:FEATURES_CALCULATED` → Alpha ensembles compute `EVT:ALPHA_SCORE_CALCULATED` (with per-model contributions and historical weight adaptation) → RegimeDetector identifies trend/sideways/volatility regimes and emits `EVT:REGIME_DETECTED` → DecisionMaking consumes features/risk/regime/alpha to adjust QoS, thresholds, sizing, and emit `EVT:TRADE_INTENT_PROPOSED`. Config docs promise weights derived from PnL/sharpe, regime-multipliers in sizing/instrument profiles, and visible logs (`why` chains) that explain size adjustments.
- **Reality (code/runtime)**: T1-T7 show the modules exist and are wired; FeatureEngineering, RegimeDetector, DecisionMaking, and alpha models are invoked via FSM events, resolvers load v2 configs, and WAL/log outputs capture thresholds/regimes. Alpha ensemble weights rely solely on recent confidence history (not PnL); instrument-level regime multipliers are stored but rarely consumed; logs capture regime names and why chains but not per-model weights or performance stats.

## Status summary

- All domains and resolvers listed in T1-T6 are running (Implemented Active). FeatureEngineering, RegimeDetector, DecisionMaking, RiskManagement, and alpha models produce events and logs as described.
- Backtest/performance attribution exists (T7) but is offline and not integrated with runtime weighting → gap.
- Instrument regime multipliers documented but unused → partial gap.
- Logs expose regime names, decision thresholds, and `why` (T6) but not ensemble weights or PnL→ gap.

## Intent vs implementation table

| Mechanism | Docs/Source | Code file:lines | Runtime hook/event | STATUS |
| --- | --- | --- | --- | --- |
| Ensemble weights from PnL/Sharpe | `docs/audit/alpha_regime/T2_alpha_ensemble.md`, `alpha_search/ensemble.py` | `apps/reference/domains/alpha_search/ensemble.py:125-334` (uses confidence history) | `DecisionMaking.on_features` emits `EVT:ALPHA_SCORE_CALCULATED` with contributions (lines 659-733) | PARTIAL (ensemble exists but weights from confidence only → GAP) |
| Regime-aware sizing | `docs/audit/alpha_regime/T4_decision_integration.md`, `config/domains/sizing.yaml` | `decision_making.py:1512-1788` applies `regime_multiplier` from sizing resolver | `_make_decision_for_symbol` before emitting trade intent | IMPLEMENTED_ACTIVE |
| Regime detector (trend/mean/vol/crisis) | `docs/audit/alpha_regime/T3_regime_detector.md`, `config/domains/regimes.yaml` | `regime_detector.py:114-412` | `RegimeDetector.handle_event` on `EVT:FEATURES_CALCULATED` emits `EVT:REGIME_DETECTED` | IMPLEMENTED_ACTIVE |
| Mean-reversion sizing cut | `docs/audit/alpha_regime/T4_decision_integration.md`, `docs/audit/alpha_regime/T5_config_wiring.md` | Config `regimes` + `regime_threshold_multipliers` (used by decision) | `decision_making._make_decision_for_symbol` multiplies thresholds; rejections logged with `regime` metadata | IMPLEMENTED_ACTIVE (no fixed “-50%” but configurable multipliers) |
| Logging regime context | `docs/audit/alpha_regime/T6_runtime_observability.md` | `decision_making.py:1418-1483` writes `OrderLogger`/`DecisionLog` entries with `regime` and `signal_score` | OrderLogger JSONL + DecisionLog file + `EVT:TRADE_INTENT_PROPOSED why` array | IMPLEMENTED_ACTIVE |
| Ensemble weight history from backtests | `docs/audit/alpha_regime/T7_alpha_performance_attribution.md` | `apps/reference/alpha_discovery/backtest_engine.py:1-380` (computes Sharpe/PnL) | No runtime hook to load `BacktestResult` | GAP |
| Instrument-level regime multipliers | `config/instruments.yaml` + `overrides.yaml`, documented in `CONFIG_REFERENCE.md` | `apps/reference/config_symbols.py:222-359` (stores `regime_multipliers`) | Not read when sizing/performance decisions are made (currently unused) | GAP/DORMANT |

## Gaps & action items

1. **Integrate performance metrics into ensemble weights**: Connect `BacktestResult`/live PnL stats to `EnsembleModel.model_performance` (currently tracks confidence) so weights reflect actual profitability. Emit events/logs when weights update for traceability.
2. **Materialize instrument regime multipliers**: Ensure resolved `regime_multipliers` flow into `DecisionMaking`/execution sizing, or remove the field from v2 config/docs if unused.
3. **Extend logs with ensemble detail**: Record per-model weight contributions and applied multipliers (e.g., `regime_multiplier_usd`) in DecisionLog/OrderLogger entries to make “why risk changed” audible without replaying events.
