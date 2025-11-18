## Events & schemas

- `apps/reference/domains/alpha_search/EVENTS.md` describes `EVT:ALPHA_SCORE_CALCULATED` whose payload includes `model_name`, `score`, `confidence`, and an optional `contributions` map that reports each model’s score/weight/contribution. | IMPLEMENTED_ACTIVE |
- `apps/reference/domains/regime_detector/EVENTS.md` plus `schemas/regime_detected_v1.json` ensure `EVT:REGIME_DETECTED` carries `ts`, `symbol`, `regime`, `confidence`, `model`, and `source_model`. | IMPLEMENTED_ACTIVE |
- `apps/reference/domains/decision_making/EVENTS.md` declares `EVT:TRADE_INTENT_PROPOSED` with `p`, `risk_budget`, `size`, and a `why` array that can surface `regime_multiplier=...`/`sizing=...` explanations; `why` is logged per intent. | IMPLEMENTED_ACTIVE |
- `apps/reference/schemas/order_logger_v1.json` defines the `order_logger` JSONL contract (`rid`, `event_type`, `symbol`, `why`, `metadata`), so OrderLogger entries can store regime reasons or signal scores. | IMPLEMENTED_ACTIVE |

## Log fields related to alpha/regime

- `apps/reference/domains/decision_making/decision_making.py:1426-1435` writes the `DECISION_EVAL` DecisionLog record containing `symbol`, `signal_score`, `signal_threshold`, `psi` vector, and `regime_threshold_factor` so analysts see the regime-modified threshold. | IMPLEMENTED_ACTIVE |
- The same file (lines 1418-1483) updates `psi_vector` with `regime` and `regime_conf` before storing it and rejecting incompatible sides; rejected intents are also sent to `OrderLoggerV1` with `metadata` that includes `"regime": current_regime` and `signal_score`/`threshold*` when relevant, capturing the regime decision context. | IMPLEMENTED_ACTIVE |
- `OrderLoggerV1` entries (via `apps/reference/telemetry/order_logger.py`) accept a flexible `metadata` object, letting DecisionMaking record regime reasons, signal biases, and size multipliers alongside `NRR` codes. | IMPLEMENTED_ACTIVE |
- The DecisionLog `why` array for `EVT:TRADE_INTENT_PROPOSED` (per `apps/reference/domains/decision_making/EVENTS.md`) routinely embeds strings like `regime_multiplier=1.2` and `sizing=... m_regime=1.2 m_vol=...`, revealing how alpha/regime adjustments shaped the final intent. | IMPLEMENTED_ACTIVE |
- Alpha contributions are present on `EVT:ALPHA_SCORE_CALCULATED` (via `decision_making.py:692-729`): the payload includes per-model `score`, `weight`, and confidence details, and the event is emitted before `DECISION_EVAL`. | IMPLEMENTED_ACTIVE |

## Example log records (anonymized)

1. Order logger entry (regime filter rejection):

```json
{
  "rid": "some-rid",
  "event_type": "ORDER_REJECTED",
  "symbol": "BTCUSDT",
  "side": "SELL",
  "nrr_code": null,
  "why": "rejected by regime filter (current regime: TREND_UP)",
  "source_fsm": "DecisionMaking",
  "metadata": {
    "reject_reason": "REGIME_FILTER",
    "regime": "TREND_UP"
  }
}
```

2. Decision log `DECISION_EVAL` (post-regime weighting):

```json
{
  "event": "DECISION_EVAL",
  "symbol": "ETHUSDT",
  "signal_score": 0.72,
  "signal_threshold": 0.05,
  "psi": {"regime": "SIDEWAYS", "regime_conf": 0.82},
  "regime_threshold_factor": 0.5
}
```

## Gaps (що неможливо зрозуміти з логів зараз)

- Although `EVT:ALPHA_SCORE_CALCULATED` includes `contributions`, there is no persistent log line or order metadata that records the final ensemble weight per model for a given intent; analysts must replay events to reconstruct weights. | GAP |
- `regime_multipliers` stored inside resolved instrument profiles (per `resolve_instrument_profile`) are not promoted to logs, so the applied multiplier per trade is only visible through `DECISION_EVAL.regime_threshold_factor` or `why` strings, not explicit fields like `regime_multiplier_usd`. | GAP |
- No log currently records the PnL or hit-rate history used by the ensemble, so even though `calculate_all_alpha` wraps `AlphaScoreRegistry`, there is no runtime trace that ties a weight change to a realized PnL series. | GAP |
