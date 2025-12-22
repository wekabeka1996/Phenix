# Forensic Investigation: Zero Orders (BTCUSDT Sizing Issue)

**Date**: 2025-12-22
**Incident**: User reported no orders executed despite active strategy signals.
**Affected Symbol**: `BTCUSDT`
**Log Signature**: `QTY_CALC: ... rounded_qty=0.000` leading to `NRR-999` (Quantity Zero).

## 1. Executive Summary

The trading system failed to execute `BTCUSDT` orders because the **calculated position size (~$34)** was smaller than the **minimum exchange quantity step (~$90)**.

- **Calculated Size**: $33.87 USD (Derived from 15% of ~$226 Equity).
- **Minimum Enforceable Size**: $89.98 USD (0.001 BTC Step Size @ ~$90k Price).
- **Result**: `0.00037 BTC` rounded down to `0.000 BTC`.

This is a mathematical impossibility caused by low account equity combined with valid but restrictive exchange precision rules for high-priced assets.

---

## 2. Technical Analysis

### A. The Log Evidence
```text
2025-12-22 12:04:14,216 ... QTY_CALC: price=$89986.8, raw_qty=0.00037644..., step_size=0.001, rounded_qty=0.000
```
- **Price**: $89,986.8
- **Raw Qty**: 0.00037644... BTC
- **Implied Notional**: $0.00037644 \times 89986.8 \approx 33.87$ USD
- **Configured Sizing**: `percent_equity: 0.15` (15%)
  - Implied Equity = $33.87 / 0.15 \approx 225.8$ USD.

### B. Exchange Constraints (Instrument Specs)
From `config/aurora/instruments/BTCUSDT.yaml`:
```yaml
specs:
  step_size: "0.001"  # 1 mBTC
```
- **Constraint**: You can only buy 0.001, 0.002, 0.003... BTC.
- **Minimum Cost**: $0.001 \times 89,986.8 = 89.98$ USD.

### C. The Collision
The strategy requested **$34** of exposure.
The exchange requires **min $90** (to buy even the smallest unit).
The system logic forces rounding to `step_size`:
$$ \text{rounded\_qty} = \lfloor \frac{0.000376}{0.001} \rfloor \times 0.001 = 0 \times 0.001 = 0.000 $$

---

## 3. Contributing Factors

1.  **Low Equity Environment**: The account appears to have ~$226 equity, which makes `15%` sizing ($34) insufficient for expensive assets like BTC.
2.  **Unleveraged Sizing Logic**: The `percent_equity` mode targets a percentage of *raw equity*, not leveraged buying power. It does not auto-scale to meet `min_notional`.
3.  **High Asset Price**: BTC at $90k makes the `0.001` step size extremely expensive (~$90). For comparison, ETH `0.001` @ $3k is only $3, which would have worked fine.

---

## 4. Recommendations

### Immediate Fix (Configuration)
To trade BTC with ~$226 equity, you must allocate at least ~$90 per trade (approx 40% of equity).

1.  **Option A (Aggressive %)**: Increase `percent_equity` for BTC.
    ```yaml
    # config/aurora/trading.yaml
    sizing_modifiers:
      BTCUSDT: 3.0  # Boost 15% * 3 = 45% (~$100) - requires modifier support
    # OR change base sizing
    sizing:
      percent_equity: 0.45 # 45% global (risky for other assets)
    ```

2.  **Option B (Fixed Amount - Recommended)**: Switch to fixed sizing that guarantees execution.
    ```yaml
    # config/aurora/trading.yaml
    sizing:
      mode: fixed_notional_usd
      fixed_notional_usd: 100  # Safe margin above $90
    ```
    *Note: This puts ~45% of account at risk per trade.*

### Systemic Improvement (Code)
Update `_calculate_position_size` to check if `raw_notional < (step_size * price)` and either:
1.  **Clamp Up**: Force size to at least 1 `step_size` (if risk allows).
2.  **Explicit Warning**: Log "Insufficient Equity for Minimum Lot" instead of generic "Qty Zero".

---

## 5. Conclusion
The system code is functioning correctly (respecting exchange precision). The issue is purely valid configuration mathematics: **you cannot buy $34 worth of something that is sold in $90 packs.**

**Action Item**: Update `trading.yaml` sizing configuration to allocate at least $100 per BTC trade.
