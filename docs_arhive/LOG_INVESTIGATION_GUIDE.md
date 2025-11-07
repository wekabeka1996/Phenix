
# 🔍 Testnet Log Investigation Guide

**When you run testnet, watch for these patterns to understand system behavior.**

---

## 1. Mode-Resolver Activation (first 10 seconds)

**Log Pattern**:
```
[mode-resolver] Applying 'hybrid_live_data_testnet_exec' mode decision overrides
  signal_threshold: 0.05 → 0.15
  max_risk_score: 0.9 → 0.90
  kelly_boost: 1.0 → 1.2
```

**What it means**:
- System read `trading.mode` from config
- Merged testnet-specific overrides into decision config
- Signal threshold lowered to 0.15 (more signals expected)

**If missing**: Mode-resolver didn't run → check config_loader.py line 149

---

## 2. Regime Detection (every 5m bar)

**Log Pattern**:
```
REGIME_DETECTED: regime=HIGH_VOLATILITY confidence=0.82 volatility=45bps
```

**Expected values**:
- `regime`: HIGH_VOL, LOW_VOL, TREND_UP, TREND_DOWN, MEAN_REV, UNCERTAIN
- `confidence`: 0.7-1.0 (>0.7 is good)
- `volatility`: basis points (10-100 typical)

**What happens next**:
- If confidence > 0.7: regime_threshold_multiplier (Δθ) applied to signal_threshold
  - HIGH_VOL: ×1.20 (stricter: 0.15 × 1.20 = 0.18)
  - LOW_VOL: ×0.90 (easier: 0.15 × 0.90 = 0.135)

- If confidence ≤ 0.7: DEFAULT=1.0 used (no adjustment)

**Check**: Are Δθ multipliers being applied? Look for next log...

---

## 3. Signal Calculation & Filtering

**Log Pattern**:
```
DECISION_EVAL:
  sym=BTCUSDT
  score=0.28
  threshold=0.18 (Δθ=1.20 applied)
  regime=HIGH_VOLATILITY
  obi=0.45 tfi=0.32 delta_price=0.01
  decision=PASS (score > threshold)
```

**Decode**:
- `score`: weighted average of signals = 0.6×obi + 0.35×tfi + 0.05×delta_price
- `threshold`: 0.15 (testnet base) × 1.20 (HIGH_VOL regime) = 0.18
- `decision`: PASS if score > threshold, else SKIP

**What to watch**:
- Are scores > thresholds? (If always SKIP → regime might be wrong)
- Are Δθ multipliers changing? (If all 1.0 → regime detection issue)

---

## 4. Position Sizing & Kelly

**Log Pattern (With Kelly OFF - default)**:
```
SIZING_DECISION:
  q_decision=0.0125 (risk_fraction_q path)
  m_regime=0.60 (HIGH_VOL modifier)
  q_adjusted=0.0075 (0.0125 × 0.60)
  kappa=0.85 (dynamic liquidity)
  q_final=0.0064 (0.0075 × 0.85)
  notional_usd=320 (0.0064 × 50000 BTC price)
```

**Decode**:
- `q_decision`: Base size from risk_fraction_q (1% of equity)
- `m_regime`: Sizing modifier from regime (0.5-1.2)
- `kappa`: Liquidity adjustment (0.3-1.0), fetched from FeatureStore or clamped
- `q_final`: Position size in BTC
- `notional_usd`: Notional value in dollars

**What to watch**:
- Is `m_regime` changing per regime? (Should vary 0.5-1.2)
- Is `kappa` in bounds [0.3, 1.0]? (If always 1.0 → depth data missing)
- Does notional stay under `max_portfolio_fraction`? (20% of equity_free_usdt)

**Log Pattern (With Kelly ON - optional)**:
```
KELLY_CALC:
  p_raw=0.52 (from Kelly model)
  p_clipped=0.52 (after [0.45, 0.65] clamp)
  r=2.0 (TP_bps/SL_bps = 100/50)
  kelly_frac=0.33 (Kelly: 2×p-1 / r = 2×0.52-1 / 2 = 0.52)
  kelly_capped=0.25 (min(0.33, 0.25 cap))
  q_kelly=0.0125 (0.25 × 0.05 equity)
  q_final=min(q_decision, q_kelly) = 0.0064 (min(0.0125, 0.0125×0.60×0.85))
```

**When to expect Kelly**:
- Only if `trading.decision.kelly.base_probability` is set and > 0
- Currently disabled in config (won't see this unless you enable)
- If enabled: system uses `min(q_risk, q_kelly)` path

---

## 5. Bridge (EVT→CMD Conversion)

**Log Pattern**:
```
BRIDGE:
  intent_rid=abc-123
  why_chain_len=4 (full XAI chain preserved)
  why_short="score=0.28 m_regime=0.60 q_final=0.0064 kappa=0.85" (first element, truncated to 80)
  cmd_rid=xyz-789
  parent_span=abc-123 (tracing link)
```

**What it shows**:
- Full XAI chain stored in data_ref (for cold storage analysis)
- First element truncated to ≤80 chars (pydantic validation)
- Message linked to parent event for tracing

**Check WHY length**:
```
if len(why_short) > 80:
    ❌ ERROR: truncate_why() not working!
else:
    ✅ OK: Message will pass validation
```

---

## 6. Execution (ORDER_PLACED → BRACKETS)

**Log Pattern**:
```
ORDER_PLACED:
  order_id=987654
  symbol=BTCUSDT
  side=BUY
  type=MARKET
  qty=0.0064 BTC
  notional_usd=320

BRACKETS_PLACED:
  entry_price=50000
  sl_price=49750 (entry × (1 - 50/10000))
  tp_low=50250 (entry × (1 + 50×0.6/10000))
  tp_high=50500 (entry × (1 + 50×1.0/10000))
  orders=[SL, TP_low, TP_high]
```

**What to watch**:
- SL at 50 bps = 0.5% below entry (from config)
- TP_low at 0.3% (0.6 × SL) = favorable r/reward
- TP_high at 0.5% (1.0 × SL) = full SL ratio
- All orders linked by oco_group_id (OCO group)

---

## 7. Position Closed (Success Path)

**Log Pattern**:
```
POSITION_CLOSED:
  entry_price=50000
  exit_price=50500 (TP triggered)
  exit_reason=TAKE_PROFIT_HIGH
  pnl_usd=32 (0.0064 × (50500-50000))
  pnl_pct=10.0% (32 / 320 * 100)
  kelly_r=1.0 (actual payoff_r achieved)
```

**Trace**:
- Entry → Order Placed → SL/TP Brackets → Exit (TP or SL)
- P&L calc: qty × (exit - entry)
- Check if p&l matches expected r ratio

---

## 8. Error Patterns to Watch

### 8a. WHY Validation Error
```
ValidationError: why must be <=80 chars
  Input: "score=0.28 regime=HIGH_VOL m_regime=0.60 q_final=0.0064 kappa=0.85 kelly_frac=0.33..."
```

**Root cause**: Bridge not truncating
**Fix**: Check `truncate_why()` called before Message creation

### 8b. Regime Not Detected
```
REGIME_DETECTED: regime=UNCERTAIN confidence=0.45
  → Δθ=1.0 (DEFAULT used, no adjustment)
  → All signals harder to pass threshold
```

**Root cause**: Feature data missing or model confidence low
**Fix**: Wait for more market data or check FeatureStore depth data

### 8c. Kappa Fallback
```
KAPPA_FALLBACK: depth=None → kappa=1.0 (no liquidity info)
```

**Root cause**: FeatureStore doesn't have depth heuristic
**Fix**: Check if depth data is being calculated/stored

### 8d. Risk Gate Blocking
```
INTENT_REJECTED: reason=RISK_GATE
  risk_score=0.95 > max_allowed=0.90
  blocked_reason=testnet_override: max_risk_score=0.90
```

**Root cause**: Risk score exceeded testnet limit
**Fix**: Position already too large; wait for P&L or adjust risk_fraction_q

---

## 🎯 Checklist for First 30 Minutes

- [ ] **Regime detected** with confidence > 0.7 (not UNCERTAIN)
- [ ] **Mode-resolver log** shows testnet overrides applied (signal_threshold=0.15)
- [ ] **At least 1 DECISION_EVAL** log with score > threshold (decision=PASS)
- [ ] **No WHY ValidationError** (truncation working)
- [ ] **Order placed** with type=MARKET (testnet config)
- [ ] **Brackets placed** with SL@50bps, TP ratios correct
- [ ] **P&L tracked** (positive or negative, but calculated)
- [ ] **Kappa** in [0.3, 1.0] bounds (or 1.0 fallback)
- [ ] **m_regime** varying per regime (not always 1.0)

---

## 🔗 Log Source Locations (Code References)

| Log Pattern | File | Line(s) |
|-------------|------|---------|
| `[mode-resolver]` | config_loader.py | 104-108 |
| `REGIME_DETECTED` | regime_detector.py | ~200 |
| `DECISION_EVAL` | decision_making.py | 1265-1280 |
| `SIZING_DECISION` | decision_making.py | 1270-1280 |
| `BRIDGE` | main.py | 420-430 |
| `ORDER_PLACED` | fsm_manage.py | ~290 |
| `BRACKETS_PLACED` | fsm_manage.py | ~300 |
| `POSITION_CLOSED` | fsm_manage.py | ~350 |

---

## 💡 Pro Tips

1. **Grep for specific logs**:
   ```bash
   # Watch regime changes
   grep "REGIME_DETECTED" logs/*.jsonl | jq '.regime' | sort | uniq -c

   # Count PASS vs SKIP decisions
   grep "DECISION_EVAL" logs/*.jsonl | grep -c "decision=PASS"

   # Find WHY length violations
   grep "why_short" logs/*.jsonl | awk '{print length($NF)}'
   ```

2. **Track cumulative P&L**:
   ```bash
   grep "POSITION_CLOSED" logs/*.jsonl | jq '.pnl_usd' | awk '{sum+=$1} END {print "Total P&L: $"sum}'
   ```

3. **Analyze regime-sizing correlation**:
   ```bash
   grep "SIZING_DECISION" logs/*.jsonl | jq '[.regime, .m_regime, .q_final]'
   ```

---

**Log file location**: Check `apps/reference/main.py` logger config for path (typically `logs/` or stdout if configured for streaming)

**Ready to investigate!** 🚀
