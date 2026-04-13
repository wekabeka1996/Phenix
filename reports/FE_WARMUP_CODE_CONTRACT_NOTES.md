# FE Warmup Code Contract Notes

## Call chain: `full_ready` computation

```
on_bar_closed()
  → _calculate_and_emit_features_for_tf()
    → ready_map = { ... 14 keys ... }                      # types.py computed from HotState
    → warmup["full_ready"] = cfg.compute_warmup_full_ready_for_symbol(symbol, ready_map)  # 1st pass
    → sanitize_features_dict()                              # P0-3 sanity firewall
    → warmup["full_ready"] = cfg.compute_warmup_full_ready_for_symbol(...)  # 2nd pass (post-sanity)
    → check_book_health()                                   # P0-2 spread health gate
    → warmup["full_ready"] = cfg.compute_warmup_full_ready_for_symbol(...)  # 3rd pass (post-health)
    → if bar_data and tf_sec >= 60:
        → if not warmup_full_ready:
            → if fail_fast:
                → if _is_degraded_allowed_for_symbol(symbol):
                    → ALLOWED (degraded bypass)
                → else:
                    → REJECTED (CMD:PROCESS_STRATEGY blocked)
```

**Key observation**: `full_ready` is computed THREE times in a single call, each time potentially downgrading it. This is correct fail-closed behavior, not a bug.

## Call chain: `macro_sync:gap_too_large`

```
MacroSyncTimeSeries.update(ts_ms, price, max_gap_bins, max_late_ms)
  → bin_ts = (ts_ms // bin_ms) * bin_ms
  → if bin_ts > last_bin_ts:
      → gap_bins = (bin_ts - last_bin_ts) // bin_ms - 1
      → if gap_bins > max_gap_bins:   # 2 in config, i.e. gap_bins >= 3
          → _flag_large_gap = True    # ONE-SHOT: set here
  → last_bin_ts = bin_ts

MacroSyncTimeSeries.consume_flags()
  → returns (out_of_order, large_gap)
  → _flag_large_gap = False           # CLEARED: one-shot consumed

MacroSyncResampler.compute(symbol, anchors, now_ts_ms)
  → sym_series.consume_flags()        # checks SYMBOL series
  → if sym_large_gap: return ready=False, why="gap_too_large"
  → for anchor in anchors:
      → a_series.consume_flags()      # checks EACH ANCHOR series
      → saw_any_large_gap |= a_large_gap
  → if saw_any_large_gap: return ready=False, why="gap_too_large"   # SHARED blast
```

**Critical design property**: The gap flag is consumed ONCE per compute() call. After consumption, it resets to False. This means:
- A gap triggers `full_ready=False` for exactly ONE tick computation cycle
- The next tick computation will see `_flag_large_gap=False` and return normally
- The false window lasts ~5 seconds (one tick interval)

**Why all symbols are hit**: `compute()` checks `saw_any_large_gap` across ALL anchor series. If BTCUSDT anchor has a gap, ALL symbols that use BTCUSDT as anchor become not-ready simultaneously.

## Config-gated exclusion in full_ready

From `types.py:603-611`:
```python
if key == "absorption" and self.absorption_mode == "disabled":
    continue      # excluded
if key == "macro_resid" and (not bool(self.macro_resid_enabled)):
    continue      # excluded
if key == "macro_sync" and (not bool(self.macro_sync_enabled)):
    continue      # excluded
if key == "large_trade_imbalance" and (not bool(self.large_trade_imbalance_enabled)):
    continue      # excluded
```

**Active exclusions in runtime** (absorption mode=disabled): `absorption`, `large_trade_imbalance` (inferred disabled).

**NOT excluded**: `macro_sync` (enabled=true), `macro_resid` (enabled=true). Both participate in `full_ready`.

## Degraded bypass logic

From `feature_engineering.py:301-323`:
```python
def _is_degraded_allowed_for_symbol(self, symbol):
    degraded_allowed = cfg.warmup.degraded_allowed_strategies
    assigned_strats = registry.assignments.get(symbol, [])
    # ALL assigned strategies must be in degraded_allowed
    for strat in assigned_strats:
        if strat not in degraded_allowed:
            return False
    return True
```

**Key**: This is an ALL-or-nothing check. If a symbol has ANY non-degraded strategy, the bypass does NOT apply. Since XRPUSDT→[md_amr] and BNBUSDT→[md_amr], they qualify. Aurora symbols have [aurora] which is NOT in degraded_allowed, so they don't qualify.
