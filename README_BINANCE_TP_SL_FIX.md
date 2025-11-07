# 🎯 Binance TP/SL API Error Handling Implementation

**Target**: Production-ready TP/SL orders on BOTH Testnet + Mainnet
**Status**: Phase 1 ✅ COMPLETE | Ready for Phase 2
**Timeline**: 8–13 hours total (2–3 hours per phase)

---

## Problem (Summary)

TP/SL orders on Binance Futures TestNet fail with specific error codes:
- **-2021 "Order would immediately trigger"**: ~60% of orders
- **-4116 "ClientOrderId is duplicated"**: Retry logic issues
- **-4137 "Quantity not allowed"**: Invalid parameters
- **-4164 "MIN_NOTIONAL"**: Order too small

Result: Ghost orders accumulate → margin blocked → new trades fail

---

## Solution (8 Phases)

### Phase 1: ✅ COMPLETE
**Contracts + Validation Rules** (30 minutes)

✅ Updated `contracts.py`:
- Added `WorkingType`, `BracketErrorCode` enums
- Added `BracketOrderPayload` class with Binance rule validation
- Added `TPSLValidationRules` class with:
  - `validate_stop_price_for_side()`: Pre-flight validation (prevents -2021)
  - `add_safety_offset()`: Calculates safe margin (tickSize + 5 bps)

✅ Created JSON Schemas (2020-12 compliant):
- `schemas/bracket_order_v1.json`
- `schemas/bracket_error_v1.json`

✅ All 9 validation tests passing

**Artifacts**:
- `PHASE1_COMPLETE_SUMMARY.md` (this file's sibling)
- `PHASE1_START_HERE.md` (setup guide)
- `test_phase1_validation.py` (9 unit tests)

---

### Phases 2–8: TODO

| Phase | Component | Duration | Key Deliverables |
|-------|-----------|----------|-------------------|
| **2** | fsm_manage.py | 1–2h | `_calculate_bracket_prices_safe()` |
| **3** | binance_execution_adapter.py | 1–2h | Error handling, retry, fallback |
| **4** | exposure_guard.py | 1–2h | Ghost order cleanup, margin audit |
| **5** | aurora_log_adapter.py | 1–2h | User Data Stream event handlers |
| **6** | Unit tests | 2–3h | 90%+ coverage |
| **7** | Documentation | 1–2h | Docstrings, runbook, monitoring |
| **8** | Commit + Deploy | TBD | Production rollout |

---

## Key Concepts (From Research)

### 5 Core Rules for TP/SL

1. **-2021 Prevention**: `stopPrice` must be on correct SIDE of current mark price
   - LONG TP: `stopPrice > mark_price`
   - LONG SL: `stopPrice < mark_price`
   - SHORT TP: `stopPrice < mark_price`
   - SHORT SL: `stopPrice > mark_price`

2. **`closePosition=true` Rule**: No `quantity` or `reduceOnly` (Binance closes entire position)

3. **Unique `newClientOrderId`**: ULID/UUID format, NEVER reuse

4. **Ghost Order Prevention**: Listen to `ORDER_TRADE_UPDATE` and `CONDITIONAL_ORDER_TRIGGER_REJECT` events

5. **Margin Audit**: Verify `totalOpenOrderInitialMargin` post-error to detect stuck reserves

---

## How To Use Phase 1 Output

### Example: Calculate Safe TP/SL

```python
from apps.reference.domains.execution_position.contracts import (
    TPSLValidationRules,
    BracketOrderPayload,
    WorkingType,
    OrderType,
)
from decimal import Decimal

# Current market state
mark_price = Decimal("157.38")
position_side = "LONG"
entry_price = Decimal("157.38")

# Calculate safe offset
offset = TPSLValidationRules.add_safety_offset(
    current_price=mark_price,
    tick_size=Decimal("0.01"),
    offset_bps=5,  # 0.05% = conservative
)

# Calculate TP and SL
tp_price = mark_price + offset
sl_price = mark_price - offset

# Validate before submission
tp_valid, tp_reason = TPSLValidationRules.validate_stop_price_for_side(
    position_side=position_side,
    current_mark=mark_price,
    stop_price=tp_price,
    is_take_profit=True,
)

sl_valid, sl_reason = TPSLValidationRules.validate_stop_price_for_side(
    position_side=position_side,
    current_mark=mark_price,
    stop_price=sl_price,
    is_take_profit=False,
)

if tp_valid and sl_valid:
    # Safe to submit!
    tp_payload = BracketOrderPayload(
        symbol="ETHUSDT",
        side="SELL",
        order_type=OrderType.TAKE_PROFIT_MARKET,
        stop_price=tp_price,
        close_position=True,  # Close entire LONG
        working_type=WorkingType.MARK_PRICE,
        new_client_order_id=f"AUR-tp-{int(time.time())}",
    )
    print(f"✅ TP payload ready: {tp_payload}")
else:
    print(f"❌ TP invalid: {tp_reason}")
    print(f"❌ SL invalid: {sl_reason}")
```

---

## Binance Documentation References

- **New Order (USDⓈ-M Futures)**: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
- **Error Codes**: https://developers.binance.com/docs/usdm-derivatives/errors
- **Account Info V3 (totalOpenOrderInitialMargin)**: https://developers.binance.com/docs/usdm-derivatives/account/balance
- **User Data Streams**: https://developers.binance.com/docs/usdm-derivatives/user-data-streams/user-data-stream-details

---

## Success Metrics (After All 8 Phases)

✅ **TP/SL Success Rate**: > 95% (from ~30%)
✅ **Ghost Orders**: 0 after 5s cleanup
✅ **Margin Never Blocked**: < 1s post-error
✅ **Code Coverage**: > 90%
✅ **Testnet = Mainnet**: Identical behavior
✅ **No Manual Intervention**: Automatic recovery

---

## Files Ready For Use

| File | Purpose | Status |
|------|---------|--------|
| `IMPLEMENTATION_PLAN_BINANCE_TP_SL_FIX.md` | Complete 8-phase roadmap | ✅ Ready |
| `PHASE1_START_HERE.md` | Setup guide for Phase 1 | ✅ Ready |
| `PHASE1_COMPLETE_SUMMARY.md` | What was delivered | ✅ Ready |
| `apps/reference/.../contracts.py` | Updated with new classes | ✅ Ready |
| `schemas/bracket_order_v1.json` | Order schema | ✅ Ready |
| `schemas/bracket_error_v1.json` | Error schema | ✅ Ready |
| `test_phase1_validation.py` | Unit tests | ✅ Ready |

---

## Next Steps

### Immediate (Phase 2)

1. Open `IMPLEMENTATION_PLAN_BINANCE_TP_SL_FIX.md`, scroll to "**Phase 2: Price Validation Logic**"
2. Implement `_calculate_bracket_prices_safe()` in `fsm_manage.py`
3. Use `TPSLValidationRules` for pre-flight checks
4. Run tests

### Before Production

1. Complete all 8 phases
2. Test on Binance Futures TestNet (1–2 days)
3. Test on Mainnet (1–2 days)
4. Deploy with runbook + monitoring

---

## Contact / Questions

Refer to:
- `RESEARCH_REQUEST_TESTNET_TP_SL_API.md` (research findings)
- `SESSION_SUMMARY_TP_SL_INVESTIGATION.md` (investigation notes)
- Individual phase documents in `/docs` folder

---

**Status**: ✅ Phase 1 Complete | 📋 7 Phases Remaining
**Last Updated**: 2025-11-07
**Prepared By**: GitHub Copilot
