# REPORT_PACK_2: MR V1 Handler Overlay

## Package: PACK-2-MR-V1-HANDLER-OVERLAY
## Date: 2026-03-30
## Status: DONE

---

## Objective
Implement Microstructure Veto in `MeanReversionHandler._on_process_strategy` as a handler overlay.

## FACTS
1. New method `_check_microstructure_veto(symbol, signal_side, bar)` added at handler level
2. Method returns `(allowed: bool, reason: str)` — no mutation of core signal geometry
3. Call-site: after `signal.is_signal == True`, before liquidity gate check
4. Bivariate logic implemented:
   - Adverse TFI (smoothed EMA) + adverse price continuation → BLOCK (toxic)
   - Adverse TFI + absorption evidence (wick ratio or favorable rebound) → ALLOW
   - Adverse TFI + ambiguous reaction → BLOCK (conservative)
5. TFI EMA computed handler-side with configurable span (per-symbol state)
6. OBI is confirm-only — adverse TFI + non-adverse OBI → ALLOW (not toxic)
7. Missing TFI → fail-closed when `missing_policy == "block"`
8. Missing OBI → fail-closed when `obi_confirm_enabled == True`
9. Warmup: `readiness_min_bars` bars of TFI data required before veto engages → BLOCK during warmup
10. `NRR-060` added to `NormalizedRejectReasons` for MICROSTRUCTURE_VETO
11. Per-symbol config resolution: per-asset override > global default
12. All blocked signals emit both `write_trade_intent_rejected` and `EVT:STRATEGY_DECISION_BLOCKED`

## INFERENCES
1. Price reaction measured via bar wick geometry (lower/upper wick ratio) and FE `price_motion.ret_60s`
2. The `absorption` field in FE is always "0.0" so cannot be used — wick ratio serves as absorption proxy
3. Signal flow preserved: veto → liquidity gate → emit_signal (sequential gates)

## ASSUMPTIONS
1. `price_motion` dict in FE features contains `ret_10s`, `ret_60s`, `ret_300s` keyed by lookback
2. During warmup (NOT_READY), blocking is correct behavior (fail-closed)

## UNKNOWNS
1. Real-world TFI EMA values need live observation to validate threshold calibration
2. Whether `price_motion` is consistently populated in CMD:PROCESS_STRATEGY for MR timeframes

---

## Call-site Mapping

```
_on_process_strategy()
  → strategy.on_bar(symbol, bar, ts_ms)  // core signal math (UNCHANGED)
  → signal.is_signal == True?
    → _check_microstructure_veto(symbol, signal_side, bar)  // NEW: Vector 1 overlay
      → BLOCKED? → write_trade_intent_rejected + _emit_strategy_blocked
      → ALLOWED? → _check_liquidity_gate(symbol)  // existing gate
        → _emit_signal(...)  // existing emission
```

## Canonical Reason Codes Emitted

| Reason Code | Trigger | Behavior |
|---|---|---|
| `MICROSTRUCTURE_VETO:TFI_MISSING` | TFI not in features | fail-closed (block) |
| `MICROSTRUCTURE_VETO:TFI_INVALID` | TFI not parseable | fail-closed (block) |
| `MICROSTRUCTURE_VETO:NOT_READY` | < readiness_min_bars | fail-closed (block) |
| `MICROSTRUCTURE_VETO:OBI_MISSING` | OBI missing + confirm enabled | fail-closed (block) |
| `MICROSTRUCTURE_VETO:OBI_INVALID` | OBI not parseable + confirm enabled | fail-closed (block) |
| `MICROSTRUCTURE_VETO:TOXIC_FLOW_CONTINUATION` | Adverse TFI + adverse price move | block |
| `MICROSTRUCTURE_VETO:TOXIC_FLOW_AMBIGUOUS` | Adverse TFI + no absorption evidence | block |
| `MICROSTRUCTURE_VETO:TOXIC_FLOW_ZERO_RANGE` | Zero-range bar + adverse TFI | block |

---

## Files Changed

| File | Change |
|---|---|
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Added `_check_microstructure_veto()` method (~130 lines) |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Added microstructure veto state in `__init__` (TFI EMA, bar counts, per-symbol config resolution) |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Wired veto check in `_on_process_strategy` signal flow |
| `apps/reference/domains/decision_making/normalized_reject_reasons.py` | Added `MICROSTRUCTURE_VETO = "NRR-060"` |

## Validation Evidence
- Module imports cleanly: `from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler` → OK
- No mutation of `MeanReversion1mStrategy.on_bar` or core signal geometry
- No changes to generic DecisionMaking logic

## Remaining Risks
1. Full behavioral tests deferred to PACK-3
2. Price motion field availability needs runtime verification
