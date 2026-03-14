# Alpha Search Critical Bugfix & Optimized Matrix Plan

## Scope
Two structural bugs + scenario_matrix.yaml update. Additive-only changes. No refactoring.

---

## BUG #1 — ta_ensemble 0 signals (feature mismatch)

### Root Cause
`backtest_plugin.py` runs ALL providers on EVERY snapshot, regardless of features.
Live tick records (`tf_sec=0`, 95% of data) lack bar-level features (`rsi_14`, `bb_position`,
`macd_signal`, `stoch_k`, etc.) that ta_ensemble requires.
EnsembleModel.calculate_alpha() returns `score=0.0` (fail-closed) → virtual trader never
opens position → 0 signals, 0 trades, 0 PnL from ta_ensemble.

### Fix Location
`apps/reference/domains/alpha_search/backtest_plugin.py`
Method: `_on_decision_score()` — provider loop (lines ~369–403)

### Fix (additive, ~7 lines)
In the `for provider_id, model in self.providers.items():` loop, before calling
`model.calculate_alpha()`, add a required-features presence check:

```python
# Skip provider if ALL of its required features are absent (e.g. ta_ensemble on tick data)
if hasattr(model, "get_required_features"):
    _required = model.get_required_features()
    if _required and all(f not in features for f in _required):
        LOG.debug(
            f"[{symbol}] Skipping {provider_id}: "
            f"required features absent (tf_sec={cache_entry.tf_sec})"
        )
        continue
```

**Effect:**
- aurora: requires `["obi", "delta_price", "macro_resid"]` — all present in tick data → runs on all 37,055 records ✓
- ta_ensemble: requires `["rsi_14", "bb_position", …]` — ALL absent in tick data → skipped on 35,290 tick records ✓
- ta_ensemble on bar-close records (590 tf_sec=300): required features ARE present → runs and generates signals ✓

---

## BUG #2 — ShadowBook disconnected from VirtualTrader

### Root Cause
`backtest_plugin._close_virtual_position()` updates `ProviderStats` (total_pnl, trades_closed,
wins) but NEVER calls `shadow_book.record_trade()`.
`ShadowBook` is created in `scenario_manager._init_worker()` but is NOT passed to the plugin.
The two systems are parallel and unconnected → `shadow_metrics` always shows zeros.

### Fix — 3 files, additive parameter passing

#### File 1: `apps/reference/domains/alpha_search/backtest_plugin.py`

**`__init__()` — add optional parameter:**
```python
def __init__(
    self,
    event_bus: Any,
    config: Optional[AlphaSearchConfig] = None,
    config_path: Optional[str] = None,
    system_config: Optional[AlphaSearchSystemConfig] = None,
    system_config_path: Optional[str] = None,
    shadow_book: Optional[Any] = None,   # NEW
):
    ...
    self._shadow_book = shadow_book   # NEW (after existing assignments)
```

**`_close_virtual_position()` — feed trades to ShadowBook (line ~712, after dlog.write):**
```python
        # NEW: feed completed trade to ShadowBook for Sharpe/DD tracking
        if self._shadow_book is not None:
            self._shadow_book.record_trade(
                symbol=pos.symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                entry_ts=pos.entry_ts,
                exit_ts=exit_ts,
                bars_held=pos.bars_held,
                provider_id=provider_id,
            )
```

#### File 2: `apps/reference/domains/alpha_search/runtime/scenario_worker.py`

**`__init__()` — accept and forward shadow_book:**
```python
def __init__(
    self,
    spec: ScenarioSpec,
    alpha_search_config: AlphaSearchConfig,
    system_config: AlphaSearchSystemConfig,
    strategy_config: Dict[str, Any],
    log_dir: Path,
    shadow_book: Optional[Any] = None,   # NEW
):
    ...
    self._plugin = AlphaSearchBacktestPlugin(
        event_bus=self._bus,
        config=alpha_search_config,
        system_config=system_config,
        shadow_book=shadow_book,           # NEW
    )
```

#### File 3: `apps/reference/domains/alpha_search/runtime/scenario_manager.py`

**`_init_worker()` — create shadow_book before worker, pass to worker:**
```python
        # Create shadow book (BEFORE worker, passing reference in)
        shadow_book = ShadowBook(
            scenario_id=spec.scenario_id,
            notional_size=alpha_cfg.virtual_trader.notional_size,
        )

        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=system_cfg,
            strategy_config=strategy_cfg,
            log_dir=scenario_log_dir,
            shadow_book=shadow_book,       # NEW
        )
```
Remove the duplicate ShadowBook creation that currently happens after worker creation (lines 147–151
in current file — it creates shadow_book AFTER worker, so the worker has no reference to it).

---

## scenario_matrix.yaml Changes

### Summary of changes:
1. `max_scenarios: 12` (was 20 — set to actual count of enabled scenarios)
2. `S02_AURORA_AGGRESSIVE`: `enabled: false` (lowest PnL +189bp; worst risk-adjusted)
3. Add `S05_AURORA_MY_BEST` (new scenario between S04 and S11)
4. S11–S17: add `alpha_search.providers.aurora.threshold` overrides for differentiation

### New scenario S05_AURORA_MY_BEST:
```yaml
  - scenario_id: S05_AURORA_MY_BEST
    enabled: true
    strategy_type: aurora
    config_mode: override
    base_refs:
      aurora: config/aurora/strategies/aurora.yaml
      alpha_search: config/alpha_search.yaml
    overrides:
      aurora.decision.signal_threshold: 0.15
      aurora.decision.gates.anti_flat_sigma: 0.40
      aurora.decision.signal_weights.obi: 0.35
```

### S11–S17 aurora threshold differentiation via `alpha_search.providers.aurora.threshold`:
This changes the ProviderConfig threshold used by the VirtualTrader entry logic, giving each
scenario a distinct signal distribution without requiring injection into the adapter kernel.

```
S11_MR_BASELINE:             no change (ref baseline, threshold stays at alpha_search default)
S12_MR_RSI_25_75:            alpha_search.providers.aurora.threshold: 0.19
S13_MR_BB_HEAVY:             alpha_search.providers.aurora.threshold: 0.14
S15_ENSEMBLE_BALANCED:       alpha_search.providers.aurora.threshold: 0.16
S16_ENSEMBLE_MR_DOMINANT:    alpha_search.providers.aurora.threshold: 0.19
S17_ENSEMBLE_MOMENTUM_DOMINANT: alpha_search.providers.aurora.threshold: 0.13
```

> NOTE: `alpha_search.providers.aurora.threshold` IS in `AURORA_OVERRIDE_PATHS` (confirmed)
> but is **absent** from `MR_OVERRIDE_PATHS` and `ENSEMBLE_OVERRIDE_PATHS`.
> Must add it to both sets in `override_allowlist.py` — see Files table below.

---

## Files to Modify (5 files)

| File | Change |
|------|--------|
| `apps/reference/domains/alpha_search/backtest_plugin.py` | BUG#1 feature-check + BUG#2 shadow_book param + _close_virtual_position call |
| `apps/reference/domains/alpha_search/runtime/scenario_worker.py` | BUG#2 shadow_book param pass-through |
| `apps/reference/domains/alpha_search/runtime/scenario_manager.py` | BUG#2 create shadow_book before worker, pass to worker |
| `apps/reference/domains/alpha_search/runtime/override_allowlist.py` | Add `alpha_search.providers.aurora.threshold` to MR_OVERRIDE_PATHS + ENSEMBLE_OVERRIDE_PATHS |
| `config/alpha_search/scenario_matrix.yaml` | S02 disabled, S05 added, S11-17 thresholds, max_scenarios=12 |

---

## Verification

```bash
# 1. Validate schema + allowlist (no errors = fix consistent)
python -c "
from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config
from pathlib import Path
cfg = load_matrix_config(Path('config/alpha_search/scenario_matrix.yaml'))
enabled = [s.scenario_id for s in cfg.scenarios if s.enabled]
print(f'Matrix valid. Enabled ({len(enabled)}): {enabled}')
"

# 2. Run replay — confirm ta_ensemble generates signals on bar-close records
python scripts/run_alpha_search_domain.py --log-level INFO

# 3. After completion, check:
# - ta_ensemble signals_long > 0 in summary.jsonl
# - shadow_metrics.max_drawdown != 0.0 in summary.jsonl
# - shadow_metrics.sharpe_ratio != 0.0 in summary.jsonl
# - S05_AURORA_MY_BEST in results
# - S02_AURORA_AGGRESSIVE absent (disabled)
# - S11-S17 aurora signal counts differ from each other
```

---

## Expected Results After Fix

| Scenario | aurora PnL | ta_ens active | shadow_metrics |
|---|---|---|---|
| S03_AURORA_CONSERVATIVE | ~+50$ | N/A | Sharpe + DD visible |
| S05_AURORA_MY_BEST | TBD (thr=0.15) | N/A | visible |
| S11-S17 | differentiated | YES (on ~118 bar-records) | visible |
| ta_ensemble all | ~0$ (small sample) | YES | visible |

> ta_ensemble will generate signals on the ~590 bar-close records. Sample is small;
> meaningful ta_ensemble PnL comparison requires a larger bar-close dataset.
