# TASK-ALPHA-FORENSIC-02: Call Graph & Integration

## Call Graph (Runtime)

```ascii
[FeatureEngineering] -> EVT:FEATURES_CALCULATED
       |
       v
[DecisionMaking.on_features] (Event Handler)
       |
       +---> [AlphaModelRegistry.calculate_all_alpha]
       |           |
       |           +-> [MomentumModel.calculate_alpha] -> AlphaScore
       |           +-> [VolatilityModel.calculate_alpha] -> AlphaScore
       |
       +---> [DecisionMaking.fsm.emit("EVT:ALPHA_SCORE_CALCULATED")]
       |
       +---> [DecisionMaking._check_and_trigger_decision_for_symbol]
                   |
                   +-> [Strategy Plugins / Hardcoded Logic]
                   |         |
                   |         +-> USES: features directly (rsi, bb, etc.)
                   |         +-> IGNORES: AlphaScore
                   |
                   v
          EVT:TRADE_INTENT_PROPOSED
```

## Impact Analysis

*   **Trade Intent:** ❌ **NO IMPACT.** The logic in `_check_and_trigger_decision_for_symbol` (and plugins like `AuroraBuiltinPlugin`) reads raw features (`rsi_14`, `bb_percent`), not `AlphaScore`.
*   **Sizing:** ❌ **NO IMPACT.** Sizing is based on regime (`RegimeDetector`) and configuration constraints.
*   **Risk Gates:** ❌ **NO IMPACT.**
*   **Observability:** ✅ **HIGH IMPACT.** `EVT:ALPHA_SCORE_CALCULATED` is emitted and logged. This serves as a "Shadow Mode" or "Parallel Analysis" system.

**Conclusion:**
Alpha Search acts as a **passive sidecar**. It computes and signals, but does not drive execution. It is seemingly ready for "Phase 2" integration where decision logic switches from raw features to Alpha Scores.

---

# TASK-ALPHA-FORENSIC-03: Contract & Schema

## AlphaScore Contract

Defined in `apps/reference/domains/alpha_search/alpha_model.py`:

| Field | Type | Constraint | Nullable | Notes |
|---|---|---|---|---|
| `model_name` | `str` | - | No | Unique ID |
| `symbol` | `str` | - | No | Target asset |
| `score` | `Decimal` | `[-1.0, 1.0]` | No | Normalized signal strength |
| `confidence` | `Decimal` | `[0.0, 1.0]` | No | Meta-score reliability |
| `timestamp` | `datetime` | - | No | UTC calculation time |
| `features_used` | `List[str]` | - | No | Traceability |
| `why` | `List[str]` | - | No | **String Array**, not single string |

## Compliance Check (XAI/Reasoning)

*   **Constraint:** `why` <= 80 chars?
*   **Implementation:** Returns `List[str]`. The individual strings (e.g., "ATR ratio 1.25 indicates elevated volatility") are typically < 80 chars.
*   **Context:** `EVT:ALPHA_SCORE_CALCULATED` payload includes the full list.
*   **Deviation:** System standard usually asks for a *concise single string* for `why` in FSM events. AlphaScore returns a *list of reasons*. This is acceptable for a detailed analytic event, but might need flattening if used in a concise log.

**Contract Violations:**
None found. The types and ranges are enforced by Pydantic. The `why` format is list-based, which is richer than the standard single-string but schema-compliant.
