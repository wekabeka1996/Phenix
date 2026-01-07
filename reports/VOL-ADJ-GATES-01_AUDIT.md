# VOL-ADJ-GATES-01 AUDIT REPORT

**Date**: 2026-01-07  
**Branch**: fix/vol_adj_gates  
**Goal**: Sigma-normalized motion gates for Aurora entries (Anti-Flat / Anti-FOMO)

---

## Phase 1: AUDIT FINDINGS

### 1. Price Motion Feature Computation

#### Location: `apps/reference/domains/feature_engineering/price_motion.py`

**Function**: `compute_price_motion_block()` (lines 106-187)

```python
def compute_price_motion_block(
    history: Deque[Tuple[int, decimal.Decimal]],
    *,
    ts_ms: int,
    price: decimal.Decimal,
    k_vol: float,
    windows_sec: tuple[int, int, int] = (10, 60, 300),  # <-- DEFAULT WINDOWS
) -> Dict[str, Optional[float]]:
```

**Computation Logic** (lines 152-170):
```python
ret = (price / p_then) - decimal.Decimal("1")
out[key_ret] = float(ret)

prices_window = _prices_in_window(history, start_ts, ts_ms)
vol = _robust_vol_from_prices(prices_window)  # median(|ret_i|)

denom = float(k_vol) * float(vol)
pm = float(ret) / denom
out[key_pm] = _clip(pm, -1.0, 1.0)  # sigma-normalized, clipped to [-1, 1]
```

**Formula**:
- `ret_window = (price_now / price_lookback) - 1`
- `vol_pct_window = median(|tick_return_i|)` — robust volatility proxy
- `pm_norm_window = clip(ret_window / (k_vol * vol_pct_window), -1, 1)` — sigma-normalized motion

#### Current Windows
| Window | ret | vol_pct | pm_norm |
|--------|-----|---------|---------|
| 10s | ✅ `ret_10s` | ✅ `vol_pct_10s` | ✅ `pm_norm_10s` |
| 60s | ✅ `ret_60s` | ✅ `vol_pct_60s` | ✅ `pm_norm_60s` |
| 300s | ✅ `ret_300s` | ✅ `vol_pct_300s` | ✅ `pm_norm_300s` |
| **900s** | ❌ **MISSING** | ❌ **MISSING** | ❌ **MISSING** |

#### Config Source
- `domains.decision_making.price_motion_sanity.k_vol` — normalization factor
- Loaded in `apps/reference/domains/feature_engineering/feature_engineering.py:105`

---

### 2. Where Features Are Consumed (Decision Making)

#### Location: `apps/reference/domains/decision_making/decision_making.py`

**Lines 2202-2220**: Extraction of price_motion from features event
```python
pm = feats_evt.get("price_motion") if isinstance(feats_evt, dict) else None
if pm and isinstance(pm, dict):
    pm_norm_10s = float(pm["pm_norm_10s"]) if pm.get("pm_norm_10s") is not None else None
    pm_norm_60s = float(pm["pm_norm_60s"]) if pm.get("pm_norm_60s") is not None else None
    pm_norm_300s = float(pm["pm_norm_300s"]) if pm.get("pm_norm_300s") is not None else None
    vol_pct_10s = float(pm["vol_pct_10s"]) if pm.get("vol_pct_10s") is not None else None
    vol_pct_60s = float(pm["vol_pct_60s"]) if pm.get("vol_pct_60s") is not None else None
    vol_pct_300s = float(pm["vol_pct_300s"]) if pm.get("vol_pct_300s") is not None else None
```

---

### 3. Aurora Entry Gate Site

#### Location: `apps/reference/domains/decision_making/aurora_handler.py`

**Method**: `on_features_calculated()` (lines 230-500)

**Entry Decision Flow**:
1. **Line 347**: `AuroraScoringKernel.compute()` — generates signal (BUY/SELL/neutral)
2. **Line 386-410**: Holding Period check (anti-churn)
3. **Line 422-443**: Re-entry Cooldown check (anti-ping-pong)
4. **Line 447-475**: Anchor Shock Veto check (macro protection)
5. **Line 479**: `_emit_signal()` — final signal emission

**Injection Point for Vol-Adj Gates**:
- **AFTER** kernel computation (line 347)
- **BEFORE** `_emit_signal()` (line 479)
- Ideally after line 443 (after cooldown check) and before anchor shock veto

**Block Helper**: `_emit_strategy_blocked()` (lines 176-198)
```python
def _emit_strategy_blocked(
    self,
    symbol: str,
    reason_code: str,
    reason: str,
    context: str,
    details: dict | None = None,
    why_chain: list | None = None,
) -> None:
```

---

### 4. Schema Evidence

#### Location: `schemas/decision_trace_emitted_v1.json`

```json
"pm_norm_10s": { "type": ["number", "null"] },
"pm_norm_60s": { "type": ["number", "null"] },
"pm_norm_300s": { "type": ["number", "null"] },
"vol_pct_10s": { "type": ["number", "null"] },
"vol_pct_60s": { "type": ["number", "null"] },
"vol_pct_300s": { "type": ["number", "null"] }
```

**900s keys NOT present** — schema extension required.

---

## Phase 2 Required: YES

**Reason**: `pm_norm_900s` (15m window) does **NOT** exist.

**Implementation Plan**:
1. Extend `windows_sec` tuple to include 900
2. Add keys: `ret_900s`, `vol_pct_900s`, `pm_norm_900s`
3. Update history buffer `max_window_ms` calculation
4. Update schemas (additive-only)
5. Unit tests for warmup behavior

---

## Phase 3: Gate Injection Site

**File**: `apps/reference/domains/decision_making/aurora_handler.py`

**Injection Location**: After line 443 (re-entry cooldown), before line 447 (anchor shock veto)

**Proposed Code Block**:
```python
# === [VOL-ADJ GATES: ANTI-FLAT / ANTI-FOMO] ===
# Config: aurora.decision.gates.{anti_flat_sigma, anti_fomo_sigma, motion_window_sec}
# Only applies to ENTRY proposals (not exits)
if result.side and state.position_side == "":
    motion_norm_sigma = self._get_motion_norm_sigma(symbol, features)
    if motion_norm_sigma is not None:
        gates_cfg = self._get_gates_config(symbol)
        if motion_norm_sigma < gates_cfg.anti_flat_sigma:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="GATE_ANTI_FLAT_SIGMA",
                reason="VOL_GATE",
                context="aurora_handler:anti_flat",
                details={"motion_norm_sigma": motion_norm_sigma, "threshold": gates_cfg.anti_flat_sigma},
                why_chain=["VOL_GATE", "ANTI_FLAT"],
            )
            return
        if motion_norm_sigma > gates_cfg.anti_fomo_sigma:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="GATE_ANTI_FOMO_SIGMA",
                reason="VOL_GATE",
                context="aurora_handler:anti_fomo",
                details={"motion_norm_sigma": motion_norm_sigma, "threshold": gates_cfg.anti_fomo_sigma},
                why_chain=["VOL_GATE", "ANTI_FOMO"],
            )
            return
# === END VOL-ADJ GATES ===
```

---

## Summary

| Item | Status | Location |
|------|--------|----------|
| price_motion compute | ✅ Found | `feature_engineering/price_motion.py:106` |
| pm_norm formula | ✅ Documented | `ret / (k_vol * vol_pct)`, clipped [-1, 1] |
| 10s/60s/300s windows | ✅ Exist | — |
| **900s window** | ❌ **MISSING** | Requires Phase 2 |
| Aurora entry gate site | ✅ Found | `aurora_handler.py:443-447` |
| Block helper | ✅ Available | `_emit_strategy_blocked()` |

**Next Step**: Execute Phase 2 — extend price_motion to include 900s window.
