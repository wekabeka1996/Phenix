## Event inputs in DecisionMaking

- `DecisionMaking.__init__` registers for `EVT:FEATURES_CALCULATED`, `EVT:RISK_ASSESSMENT_COMPLETED`, `EVT:PORTFOLIO_STATE_UPDATED`, `EVT:REGIME_DETECTED`, and `EVT:EXPOSURE_SUMMARY_UPDATED` via the FSM (see `apps/reference/domains/decision_making/decision_making.py:449-455`). The domain dict (`apps/reference/domains/decision_making/domain_dict.json`) and `README.md` echo the same wiring. | IMPLEMENTED_ACTIVE |
- Alpha production occurs inside `on_features`: when a feature bundle arrives, DecisionMaking calls `AlphaModelRegistry.calculate_all_alpha`, emits `EVT:ALPHA_SCORE_CALCULATED` (and logs to WAL), and writes a DM log entry before continuing with risk/decision logic (`apps/reference/domains/decision_making/decision_making.py:659-733`). | IMPLEMENTED_ACTIVE |

## Regime usage (if any)

- `on_regime` stores the latest regime and updates the minimal behavior FSM state (`IdleFlat`/`Tension`) so downstream gating can react (`decision_making.py:849-859`). This means regime events feed a cached value instead of triggering stand‑alone flows. | IMPLEMENTED_ACTIVE |
- When both features and risk are ready, `_check_and_trigger_decision_for_symbol` builds a context that includes the last regime before calling `_make_decision_for_symbol` (`decision_making.py:883-938`). | IMPLEMENTED_ACTIVE |
- `_make_decision_for_symbol` consults `regime_threshold_multipliers` from config to scale the signal threshold (`decision_making.py:1298-1315`). The regime factor is also logged in the DM breadcrumb (`DECISION_EVAL`). | IMPLEMENTED_ACTIVE |
- If the current regime forbids the side (e.g., `TREND_UP` blocks sells, `TREND_DOWN` blocks buys), the code rejects before sizing, writes rejections with `NormalizedRejectReasons`/NRR codes, and emits a regime-specific skip event (`decision_making.py:1418-1474`). | IMPLEMENTED_ACTIVE |
- Sizing picks up `decision.sizing_modifiers` entries keyed by regime names; `_make_decision_for_symbol` multiplies the base notional by `regime_multiplier` when present, then logs the multiplier in the `why` chain (`decision_making.py:1512-1788`). | IMPLEMENTED_ACTIVE |

## Alpha usage (if any)

- `alpha_registry` is initialized with the `Momentum`, `MeanReversion`, and `Volatility` models when the domain starts (`decision_making.py:122-135`) so every `EVT:FEATURES_CALCULATED` can fire an alpha calculation. | IMPLEMENTED_ACTIVE |
- The domain only emits `EVT:ALPHA_SCORE_CALCULATED` and records the scores in WAL for auditing; there is no additional branch in `_make_decision_for_symbol` that increases thresholds or sizing directly based on alpha values. | IMPLEMENTED_ACTIVE |

## Effect on threshold / sizing

- Signal threshold = `decision_policy.signal_threshold` × `regime_threshold_multipliers.get(regime, DEFAULT)` (approx. `decision_making.py:1298-1315`). This multiplier directly scales the amount of signal strength needed to pass the gate. | IMPLEMENTED_ACTIVE |
- Position sizing applies `sizing_modifiers` from the config (`config/domains/sizing.yaml`), injecting `regime_multiplier` into `sizing_meta` and multiplying the base notional just before Kelly sizing (decision_making.py:1512-1788). | IMPLEMENTED_ACTIVE |
- Regime-based rejecting paths (lines 1418-1475) use `NormalizedRejectReasons` to ensure the rejection reason is tracked per regime, supporting the “sit quiet” vs “active trade” question. | IMPLEMENTED_ACTIVE |

## STATUS matrix

| mechanism | file:line | description | STATUS |
| --- | --- | --- | --- |
| FSM event listeners (features/risk/portfolio/regime/exposure) | `decision_making.py:449-455` | Sets up the DecisionMaking inputs; the domain dict and README reiterate the events. | IMPLEMENTED_ACTIVE |
| Alpha scoring + EVT:ALPHA_SCORE_CALCULATED | `decision_making.py:122-733` | Creates alpha registry, calculates scores per symbol, emits the event, and logs to WAL; no downstream branch changes behavior beyond the event. | IMPLEMENTED_ACTIVE |
| Regime caching + behavior state | `decision_making.py:849-863` | Saves the latest regime and flips the minimal behavior gate state (`IdleFlat`/`Tension`) for future decisions. | IMPLEMENTED_ACTIVE |
| Signal threshold multiplier | `decision_making.py:1298-1315` | Retrieves `regime_threshold_multipliers` from config and multiplies the base threshold before evaluating the signal. | IMPLEMENTED_ACTIVE |
| Regime filter | `decision_making.py:1418-1475` | Rejects trading intents that conflict with trend regimes, records the rejection via `NormalizedRejectReasons`, and emits DM logs. | IMPLEMENTED_ACTIVE |
| Regime-aware sizing | `decision_making.py:1512-1788` | Applies `regime_multiplier` from sizing config to the base notional/Kelly sizing, and logs it in the `why` chain. | IMPLEMENTED_ACTIVE |
| domain dict | `apps/reference/domains/decision_making/domain_dict.json` | Declares imported events and exported `EVT:TRADE_INTENT_PROPOSED`. | DOC_ONLY |
| README/EVENTS/ANALYSIS | `apps/reference/domains/decision_making/README.md`, `/EVENTS.md`, `/ANALYSIS_SUMMARY.md` | Describe expected workflows, metrics, and events but have no live code effect. | DOC_ONLY |
