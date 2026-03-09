# Plan: MD-AMR TP/SL Implementation (MD-AMR-TPSL-01)

## Status
- ✅ Step 1: `config_models.py` — `MDAMRExitConfig` + `exit` field in `MDAMRAssetConfig` — DONE
- ✅ Step 2: `md_amr.yaml` — exit blocks for all 5 symbols — DONE
- ✅ Step 3-4: `md_amr_handler.py` — `_compute_tpsl` + `_apply_tpsl_guardrails` + wiring — DONE
- ⏳ Step 5: `tests/domains/decision_making/test_md_amr_tpsl.py` — 8 tests — PENDING
- ⏳ Final: Run tests + verify config loads — PENDING

## Goal
Add regime-based TP/SL computation to `md_amr` strategy for all 5 symbols.
Per-symbol values copied from `aurora.yaml` for BTC/ETH/SOL; DOGE/XRP use averages.

---

## Key Architecture Facts

### Computation formula (identical to aurora's pct_mult mode)
```
sl_pct_eff   = exit.sl_pct    × sl_mult[regime]    (clamped to min/max_sl_pct)
tp_dist_pct  = sl_pct_eff     × exit.tp_rr × tp_mult[regime]  (RR clamped to min/max_tp_rr)

BUY:  stop_price   = entry × (1 − sl_pct_eff)
      target_price = entry × (1 + tp_dist_pct)
SELL: stop_price   = entry × (1 + sl_pct_eff)
      target_price = entry × (1 − tp_dist_pct)
```

### Config access in md_amr_handler
- `self._cfg` = `MDAMRStrategyConfig`
- per-symbol: `asset_cfg = self._cfg.assets.get(symbol)`  → currently `MDAMRAssetConfig`
- no `_get_instrument_config()` method — direct dict access

### Payload injection point
- Method `_on_process_strategy`, lines 671-703
- ENTRY-only guard: only inject for `signal.intent_kind == "ENTRY"`
- Inject `stop_price` / `target_price` into `price_ctx` sub-dict

### FSM already handles it
- `_resolve_price(pld, key)` searches root → `price_ctx` → `order` (CFG-SMART-EXTRACT-01)
- `set_intent_prices(sl_price, tp_price)` → ManageFlow bracket placement
- **No FSM changes needed**

---

## Per-Symbol Values

### Source: aurora.yaml exact values
| Symbol | sl_pct | tp_rr | source |
|--------|--------|-------|--------|
| BTCUSDT | 0.005 | 1.0 | aurora direct |
| ETHUSDT | 0.019 | 0.4 | aurora direct |
| SOLUSDT | 0.0135 | 0.36 | aurora direct |
| DOGEUSDT | 0.013 | 0.60 | avg(BTC+ETH+SOL) |
| XRPUSDT | 0.013 | 0.60 | avg(BTC+ETH+SOL) |

### BTCUSDT regime_tpsl (from aurora.yaml verbatim)
```yaml
sl_mult: { DEFAULT: 1.0, LOW_VOLATILITY: 0.80, HIGH_VOLATILITY: 1.30, TREND_UP: 1.00, TREND_DOWN: 1.00 }
tp_mult: { DEFAULT: 1.5, LOW_VOLATILITY: 1.50, HIGH_VOLATILITY: 1.60, TREND_UP: 3.50, TREND_DOWN: 3.50 }
min_sl_pct: 0.003,  max_sl_pct: 0.060,  min_tp_rr: 0.5,  max_tp_rr: 5.0,  min_dist_bps: 15
```

### ETHUSDT regime_tpsl (from aurora.yaml verbatim)
```yaml
sl_mult: { DEFAULT: 1.0, FLAT_LOW: 0.65, LOW_VOLATILITY: 0.70, FLAT_NORMAL: 0.80, MEAN_REVERSION: 0.90, TREND_UP: 1.05, TREND_DOWN: 1.05, HIGH_VOLATILITY: 1.30, UNCERTAIN: 1.00 }
tp_mult: { DEFAULT: 1.0, FLAT_LOW: 0.70, LOW_VOLATILITY: 0.75, FLAT_NORMAL: 0.85, MEAN_REVERSION: 0.80, TREND_UP: 1.20, TREND_DOWN: 1.20, HIGH_VOLATILITY: 1.60, UNCERTAIN: 1.00 }
min_sl_pct: 0.002,  max_sl_pct: 0.015,  min_tp_rr: 0.3,  max_tp_rr: 3.5,  min_dist_bps: 12
```

### SOLUSDT regime_tpsl (from aurora.yaml verbatim)
```yaml
sl_mult: { DEFAULT: 1.0, FLAT_LOW: 0.60, LOW_VOLATILITY: 0.65, FLAT_NORMAL: 0.75, MEAN_REVERSION: 0.85, TREND_UP: 1.15, TREND_DOWN: 1.15, HIGH_VOLATILITY: 1.30, UNCERTAIN: 1.00 }
tp_mult: { DEFAULT: 1.0, FLAT_LOW: 0.65, LOW_VOLATILITY: 0.70, FLAT_NORMAL: 0.80, MEAN_REVERSION: 0.75, TREND_UP: 1.30, TREND_DOWN: 1.30, HIGH_VOLATILITY: 1.60, UNCERTAIN: 1.00 }
min_sl_pct: 0.0025, max_sl_pct: 0.020,  min_tp_rr: 0.25, max_tp_rr: 3.5,  min_dist_bps: 18
```

### DOGEUSDT / XRPUSDT regime_tpsl (averaged BTC+ETH+SOL)
```yaml
# sl_mult computation: avg(BTC, ETH, SOL) — BTC missing some keys → ETH+SOL avg for those
sl_mult:
  DEFAULT: 1.00          # avg(1.0, 1.0, 1.0)
  FLAT_LOW: 0.62         # avg(0.65, 0.60) — ETH+SOL only
  LOW_VOLATILITY: 0.72   # avg(0.80, 0.70, 0.65)
  FLAT_NORMAL: 0.78      # avg(0.80, 0.75) — ETH+SOL only
  MEAN_REVERSION: 0.88   # avg(0.90, 0.85) — ETH+SOL only
  TREND_UP: 1.07         # avg(1.0, 1.05, 1.15)
  TREND_DOWN: 1.07       # avg(1.0, 1.05, 1.15)
  HIGH_VOLATILITY: 1.30  # avg(1.30, 1.30, 1.30)
  UNCERTAIN: 1.00        # avg(1.00, 1.00) — ETH+SOL only
# tp_mult:
tp_mult:
  DEFAULT: 1.20          # avg(1.5, 1.0, 1.0)
  FLAT_LOW: 0.68         # avg(0.70, 0.65) — ETH+SOL only
  LOW_VOLATILITY: 1.00   # avg(1.50, 0.75, 0.70)
  FLAT_NORMAL: 0.85      # avg(0.85, 0.80) — ETH+SOL only
  MEAN_REVERSION: 0.78   # avg(0.80, 0.75) — ETH+SOL only
  TREND_UP: 2.00         # avg(3.5, 1.20, 1.30)
  TREND_DOWN: 2.00       # avg(3.5, 1.20, 1.30)
  HIGH_VOLATILITY: 1.60  # avg(1.60, 1.60, 1.60)
  UNCERTAIN: 1.00        # avg(1.00, 1.00) — ETH+SOL only
# guardrails:
min_sl_pct: 0.0025       # avg(0.003, 0.002, 0.0025)
max_sl_pct: 0.030        # avg(0.060, 0.015, 0.020) rounded down conservatively
min_tp_rr: 0.35          # avg(0.5, 0.3, 0.25)
max_tp_rr: 4.0           # avg(5.0, 3.5, 3.5)
min_dist_bps: 15         # avg(15, 12, 18)
```

---

## Files to Modify

| File | Change |
|------|--------|
| `apps/reference/config_models.py` | Add `MDAMRExitConfig`; add `exit` optional field to `MDAMRAssetConfig` |
| `config/aurora/strategies/md_amr.yaml` | Add `exit` block per asset (5 symbols) |
| `apps/reference/domains/decision_making/md_amr_handler.py` | Add `_compute_tpsl()` + `_apply_tpsl_guardrails()` methods; wire into payload builder |
| `tests/domains/decision_making/test_md_amr_tpsl.py` | New test file (~8 tests) |

---

## Step-by-Step Implementation

### Step 1 — `config_models.py`: New Pydantic class + field

**Add `MDAMRExitConfig` BEFORE `MDAMRAssetConfig` (line ~537):**

```python
class MDAMRExitConfig(BaseModel):
    """
    MD-AMR-TPSL-01: Per-symbol exit/TP/SL config for md_amr strategy.
    Mirrors AuroraExitConfig structure but with inline tp_rr (no separate TakeProfitConfig).
    """
    model_config = ConfigDict(extra='forbid')

    sl_pct: float = Field(
        gt=0.0, lt=0.5,
        description="Base stop-loss as fraction of entry price (e.g. 0.005 = 0.5%)"
    )
    tp_rr: float = Field(
        default=1.0, gt=0.0, lt=20.0,
        description="Base take-profit risk-reward ratio (TP_dist = sl_pct * tp_rr)"
    )
    regime_tpsl: Optional[RegimeTpslConfig] = Field(
        default=None,
        description="Regime-based TP/SL multipliers (MD-AMR-TPSL-01). Reuses aurora RegimeTpslConfig."
    )
```

**Update `MDAMRAssetConfig` — add `exit` field at the end:**

```python
class MDAMRAssetConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(default=True)
    cooldown_sec: int = Field(default=60, ge=0)
    position_mode: Literal["STRICT", "DYNAMIC"] = Field(default="STRICT")
    # MD-AMR-TPSL-01: per-symbol exit/TP/SL config
    exit: Optional[MDAMRExitConfig] = Field(
        default=None,
        description="MD-AMR-TPSL-01: TP/SL config. None = no brackets emitted."
    )
```

**NOTE:** `RegimeTpslConfig` already exists at line ~2944. `MDAMRExitConfig` must reference it — ensure class ordering is correct (define `MDAMRExitConfig` after `RegimeTpslConfig`). Check current relative positions; may need to move `MDAMRExitConfig` definition to after `RegimeTpslConfig` in the file.

---

### Step 2 — `md_amr.yaml`: Add `exit` blocks

For each asset, add the `exit` section. Example for BTCUSDT:

```yaml
    BTCUSDT:
      enabled: true
      cooldown_sec: 60
      position_mode: "STRICT"
      exit:
        sl_pct: 0.005       # 0.5% base SL — from aurora.yaml BTCUSDT
        tp_rr: 1.0          # base TP risk-reward — from aurora.yaml BTCUSDT tp_low_ratio
        regime_tpsl:
          enabled: true
          mode: "pct_mult"
          sl_mult:
            DEFAULT: 1.0
            LOW_VOLATILITY: 0.80
            HIGH_VOLATILITY: 1.30
            TREND_UP: 1.00
            TREND_DOWN: 1.00
          tp_mult:
            DEFAULT: 1.5
            LOW_VOLATILITY: 1.50
            HIGH_VOLATILITY: 1.60
            TREND_UP: 3.50
            TREND_DOWN: 3.50
          min_sl_pct: 0.003
          max_sl_pct: 0.060
          min_tp_rr: 0.5
          max_tp_rr: 5.0
          min_dist_bps: 15
```

(Repeat for ETH, SOL with their values; DOGE and XRP with the computed averages.)

---

### Step 3 — `md_amr_handler.py`: Add `_compute_tpsl` + `_apply_tpsl_guardrails`

Add two methods to `MDAMRHandler`:

**`_compute_tpsl`** — orchestrates the computation:
```python
def _compute_tpsl(
    self,
    symbol: str,
    entry_price: Decimal,
    side: str,
    regime: str,
    asset_cfg,   # MDAMRAssetConfig
) -> Optional[Dict[str, Any]]:
    """MD-AMR-TPSL-01: Compute regime-based TP/SL for ENTRY signals (pct_mult mode)."""
    import decimal as _dec
    if asset_cfg is None:
        return None
    exit_cfg = getattr(asset_cfg, "exit", None)
    if exit_cfg is None:
        return None
    tpsl_cfg = getattr(exit_cfg, "regime_tpsl", None)
    if tpsl_cfg is None or not getattr(tpsl_cfg, "enabled", False):
        return None

    sl_pct_raw = getattr(exit_cfg, "sl_pct", None)
    tp_rr_raw  = getattr(exit_cfg, "tp_rr",  None)
    if sl_pct_raw is None or tp_rr_raw is None:
        self.logger.error(f"[{symbol}] MD-AMR-TPSL: exit.sl_pct and exit.tp_rr required")
        return None

    sl_pct_base = float(sl_pct_raw)
    tp_rr_base  = float(tp_rr_raw)

    sl_mult_map = dict(getattr(tpsl_cfg, "sl_mult", None) or {})
    tp_mult_map = dict(getattr(tpsl_cfg, "tp_mult", None) or {})

    regime_used = regime if regime not in ("UNKNOWN", "", None) else "DEFAULT"
    sl_mult = float(sl_mult_map.get(regime_used, sl_mult_map.get("DEFAULT", 1.0)))
    tp_mult = float(tp_mult_map.get(regime_used, tp_mult_map.get("DEFAULT", 1.0)))

    sl_pct_eff = sl_pct_base * sl_mult
    tp_rr_eff  = tp_rr_base  * tp_mult

    sl_dec      = _dec.Decimal(str(sl_pct_eff))
    tp_dist_dec = sl_dec * _dec.Decimal(str(tp_rr_eff))

    if side.upper() == "BUY":
        stop_price   = entry_price * (1 - sl_dec)
        target_price = entry_price * (1 + tp_dist_dec)
    elif side.upper() == "SELL":
        stop_price   = entry_price * (1 + sl_dec)
        target_price = entry_price * (1 - tp_dist_dec)
    else:
        return None

    result = {
        "stop_price":   stop_price,
        "target_price": target_price,
        "tpsl_ctx": {
            "mode":          "pct_mult",
            "regime_used":   regime_used,
            "sl_pct_base":   sl_pct_base,
            "sl_mult":       sl_mult,
            "sl_pct_eff":    sl_pct_eff,
            "tp_rr_base":    tp_rr_base,
            "tp_mult":       tp_mult,
            "tp_rr_eff":     tp_rr_eff,
        },
    }
    return self._apply_tpsl_guardrails(symbol, entry_price, side, result, tpsl_cfg)
```

**`_apply_tpsl_guardrails`** — clamps and validates (mirrors aurora's method exactly):
- Reads `min_sl_pct`, `max_sl_pct`, `min_tp_rr`, `max_tp_rr`, `min_dist_bps` from `tpsl_cfg`
- Clamps SL distance to `[min_sl_pct, max_sl_pct]` (WARN + clamp, not fail-closed)
- Clamps TP RR to `[min_tp_rr, max_tp_rr]` (WARN + clamp)
- Validates SL/TP on correct side of entry (fail-closed: return None)
- Validates min_dist_bps (fail-closed: return None)
- Returns updated `result` dict or `None`

---

### Step 4 — `md_amr_handler.py`: Wire into payload builder

In `_on_process_strategy`, inside the payload building block (after line 670 approximately), **before** building the `payload` dict:

```python
# MD-AMR-TPSL-01: Compute regime-based TP/SL for ENTRY signals
tpsl_result = None
if str(signal.intent_kind) == "ENTRY":
    import decimal as _dec
    try:
        _entry_price = _dec.Decimal(str(signal.price_ref))
        _asset_cfg   = self._cfg.assets.get(symbol) if self._cfg else None
        _regime      = self._regime.get(symbol, "DEFAULT")
        _side        = str(signal.side).upper()
        tpsl_result  = self._compute_tpsl(symbol, _entry_price, _side, _regime, _asset_cfg)
    except Exception as _tpsl_err:
        self.logger.debug(f"[{symbol}] MD-AMR-TPSL: computation error: {_tpsl_err}")
```

Then, after the `payload` dict is built, inject into `price_ctx`:

```python
# MD-AMR-TPSL-01: Inject TP/SL into price_ctx (same contract as aurora)
if tpsl_result is not None:
    payload["price_ctx"]["stop_price"]   = str(tpsl_result["stop_price"])
    payload["price_ctx"]["target_price"] = str(tpsl_result["target_price"])
    payload["tpsl_ctx"] = tpsl_result["tpsl_ctx"]
    _ctx = tpsl_result["tpsl_ctx"]
    payload["why_chain"].append(
        f"tpsl:regime={_ctx['regime_used']} sl_pct={_ctx['sl_pct_eff']:.4f} rr={_ctx['tp_rr_eff']:.2f}"
    )
    self.logger.info(
        f"[{symbol}] MD-AMR-TPSL: stop={tpsl_result['stop_price']:.6f} "
        f"target={tpsl_result['target_price']:.6f} regime={_ctx['regime_used']}"
    )
```

---

### Step 5 — Tests (`tests/domains/decision_making/test_md_amr_tpsl.py`)

8 tests using `MagicMock` (no real FSM needed):

| # | Test | Scenario | Expected |
|---|------|----------|----------|
| 1 | `test_buy_entry_btc_default_regime` | BUY, BTC config, regime=DEFAULT | stop < entry, target > entry |
| 2 | `test_sell_entry_eth_trend_up` | SELL, ETH config, regime=TREND_UP | stop > entry, target < entry |
| 3 | `test_no_exit_config_returns_none` | asset_cfg.exit = None | tpsl_result is None |
| 4 | `test_regime_tpsl_disabled_returns_none` | regime_tpsl.enabled = False | tpsl_result is None |
| 5 | `test_guardrail_sl_clamp_min` | sl_pct_eff < min_sl_pct → clamp up | sl distance >= min_sl_pct |
| 6 | `test_guardrail_sl_clamp_max` | sl_pct_eff > max_sl_pct → clamp down | sl distance <= max_sl_pct |
| 7 | `test_non_entry_intent_no_tpsl` | intent_kind=EXIT, exit config present | stop_price NOT in payload |
| 8 | `test_doge_averaged_config` | DOGE, averaged config, MEAN_REVERSION | multipliers applied correctly |

---

## Verification

```powershell
# New tpsl tests
.venv\Scripts\pytest tests/domains/decision_making/test_md_amr_tpsl.py -v

# Existing md_amr tests (regression)
.venv\Scripts\pytest tests/domains/decision_making/test_md_amr_v12.py -v

# Config pydantic validation
.venv\Scripts\python -c "
from apps.reference.config_loader import load_config_from_dir
c = load_config_from_dir('config/aurora')
amr = c.strategies.md_amr
for sym, a in amr.assets.items():
    print(sym, '- exit:', a.exit)
"
```

---

## Constraints

- `extra='forbid'` throughout — `exit` field on `MDAMRAssetConfig` must be `Optional` with `default=None`
- `MDAMRExitConfig` must be defined AFTER `RegimeTpslConfig` in `config_models.py` (line ordering)
- TPSL only computed for `intent_kind == "ENTRY"` — EXIT/SCALEOUT intents skip computation
- fail-open on computation exception (log debug, continue without TP/SL rather than raise)
- No new domain imports; no changes to FSM or event schema
- `RegimeTpslConfig` already validates `DEFAULT` key as mandatory — reuse without modification
