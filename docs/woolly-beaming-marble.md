# Plan: Fix Missing TA Features for `ta_ensemble` in Alpha Search

## Problem Statement

```
WARNING | apps.reference.domains.alpha_search.backtest_plugin |
[XRPUSDT] Skipping ta_ensemble: missing required features=
['bb_position', 'bb_width', 'rsi_14', 'price_sma_20_deviation',
 'volume_sma_ratio', 'stoch_k'] (tf_sec=0)
```

**Root cause**: `FeatureMirrorWriter` writes ALL `EVT:FEATURES_CALCULATED` events —
including tick-level ones (`tf_sec=0`) — to `logs/alpha_input/alpha_input_v1.jsonl`.
The standalone alpha_search runtime replays these tick records through `ScenarioWorker`,
which emits `CMD:PROCESS_STRATEGY` with `tf_sec=0`. The `backtest_plugin` finds the
tick-level cache entry (no TA indicators) → `ta_ensemble` fails silently with the warning.

**Why tick events have no TA features**:
TA indicators (RSI, Bollinger Bands, Stochastic, SMA) require OHLCV bar history.
They are computed only in `feature_engineering.py:_update_bar_ta_state()` during
`on_bar_closed()` (tf_sec ≥ 60). Tick events (`tf_sec=0`) never have TA features.

---

## Causal Chain

```
feature_engineering.py:790     → EVT:FEATURES_CALCULATED (tf_sec=0, NO TA features)
feature_engineering.py:1355    → EVT:FEATURES_CALCULATED (tf_sec=300, WITH TA features)
                                          ↓ both events reach FeatureMirrorWriter
feature_mirror_writer.py:104   → tf_sec = payload.get("tf_sec", 300)
feature_mirror_writer.py:133   → _write_record(record)  ← NO tf_sec filter → BOTH written
                                          ↓ alpha_input_v1.jsonl contains tick + bar records
ingest.py                      → yields ALL valid AlphaInputV1 records (no tf_sec filter)
scenario_worker.py:122,143     → passes snapshot.tf_sec through to EVT + CMD payloads
backtest_plugin.py:349         → tf_sec = payload.get("tf_sec", 300) = 0 (explicit)
backtest_plugin.py:358         → cache_key = (XRPUSDT, 0, ts) → tick cache hit
backtest_plugin.py:390-401     → ta_ensemble: required features missing → WARNING + SKIP
```

---

## Context: XRPUSDT Independence

| Environment | Status | Reasoning |
|---|---|---|
| Aurora production | `XRPUSDT: []` (disabled) | Production decision: no live trading |
| Alpha search aurora provider | Not in symbols list | Only BTCUSDT/ETHUSDT/SOLUSDT evaluated by aurora model |
| **Alpha search ta_ensemble** | `symbols: null` (ALL symbols) | XRPUSDT IS supposed to be evaluated here |
| `FeatureMirrorWriter` symbols | `config.instruments.keys()` = ALL instruments | XRPUSDT events DO flow into JSONL |

XRPUSDT is correctly wired into ta_ensemble (independent of production Aurora).
The only blocker is tick-level events polluting the JSONL stream.

---

## Scope: What Changes and What Doesn't

| File | Change | Reason |
|---|---|---|
| `apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py` | **ADD tf_sec filter** | Primary fix — root cause |
| `tests/unit/alpha_search/test_feature_mirror_writer.py` | **CREATE new test file** | No tests exist for this module |
| `apps/reference/domains/alpha_search/runtime/contracts.py` | No change | `ge=0` is correct: tf_sec=0 is valid for live-streaming future use |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | No change | Fail-closed behavior is correct; upstream fix is sufficient |
| `apps/reference/domains/alpha_search/runtime/ingest.py` | No change | Dumb pass-through is correct design |
| `apps/reference/domains/alpha_search/runtime/scenario_worker.py` | No change | Transparent pass-through is correct |
| `config/alpha_search.yaml` | No change | ta_ensemble `symbols: null` is correct |
| `apps/reference/main.py` | No change | `symbols=list(config.instruments.keys())` is correct |

---

## Implementation Steps

### Step 1 — Primary Fix: `feature_mirror_writer.py`

**File**: `apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py`

Insert after line 104 (immediately after `tf_sec` extraction, before `ts` extraction):

```python
# Current (line 104):
tf_sec = payload.get("tf_sec", 300)

# ADD after line 104:
# Skip tick-level events (tf_sec=0): they lack bar-aggregated TA indicators
# (bb_position, rsi_14, bb_width, stoch_k, etc.) which ta_ensemble requires.
# Only bar-close events (tf_sec >= 60) carry complete feature sets.
if not tf_sec or tf_sec < 60:
    self._snapshots_skipped += 1
    return
```

**Consistency note**: This mirrors the identical guard already present in:
- `feature_engineering.py:1370`: `elif not tf_sec or tf_sec < 60:`
- `aurora_handler.py:600`: `# Gate 2: tf_sec=0 → REJECT`

**Stats update**: The `_snapshots_skipped` counter must be incremented to preserve
accurate reporting through `FeatureMirrorWriter.stats`.

---

### Step 2 — New Test File: `tests/unit/alpha_search/test_feature_mirror_writer.py`

Create a new test file (no tests currently exist for this module).

**Test cases (8 total, red→green pattern)**:

```
test_tick_level_skipped                  ← BUG REGRESSION: tf_sec=0 must not be written
test_bar_level_300_written               ← tf_sec=300 is written (positive path)
test_bar_level_other_non_zero_written    ← tf_sec=60 also passes (any bar tf_sec)
test_symbol_filter_blocks_unknown        ← existing symbol filter still works
test_symbol_filter_allows_all_when_none  ← symbols=None writes all symbols
test_empty_features_skipped              ← empty features dict → skipped
test_regime_injected_from_cache          ← latest regime is co-emitted in record
test_stats_counters_accurate             ← _snapshots_written/_skipped count correctly
```

**Test helper scaffolding** (matches patterns in `test_backtest_plugin.py`):

```python
def _make_writer(tmp_path, symbols=None):
    """Create FeatureMirrorWriter with isolated output path."""
    output = tmp_path / "alpha_input_v1.jsonl"
    writer = FeatureMirrorWriter(
        event_bus=MockEventBus(),
        output_path=output,
        symbols=symbols,
    )
    return writer, output

def _tick_event(symbol="XRPUSDT", tf_sec=0):
    return {"pld": {"symbol": symbol, "features": {"price": "0.5"},
                    "tf_sec": tf_sec, "ts": 1740000000000}}

def _bar_event(symbol="XRPUSDT", tf_sec=300):
    return {"pld": {"symbol": symbol, "features": {"price": "0.5"},
                    "tf_sec": tf_sec, "ts": 1740000000000,
                    "bar": {"close_ts": 1740000300000}}}
```

**Key regression test**:

```python
def test_tick_level_skipped(tmp_path):
    """BUG-REGRESSION: tf_sec=0 must NOT be written to JSONL."""
    writer, output = _make_writer(tmp_path)
    writer._on_features(_tick_event(tf_sec=0))
    assert writer._snapshots_skipped == 1
    assert writer._snapshots_written == 0
    assert not output.exists() or output.read_text().strip() == ""

def test_bar_level_300_written(tmp_path):
    """tf_sec=300 bar events MUST be written (ta_ensemble needs them)."""
    writer, output = _make_writer(tmp_path)
    writer._on_features(_bar_event(tf_sec=300))
    assert writer._snapshots_written == 1
    assert writer._snapshots_skipped == 0
    records = [json.loads(l) for l in output.read_text().splitlines()]
    assert records[0]["tf_sec"] == 300
    assert records[0]["symbol"] == "XRPUSDT"
```

---

## Verification

### Unit tests (must pass green)

```bash
pytest tests/unit/alpha_search/test_feature_mirror_writer.py -v
```

All 8 new tests must pass.

### Full test suite gate

```bash
pytest -q
```

No regressions against current baseline (340 passing).

### Manual smoke (optional — confirms end-to-end)

1. Inspect `logs/alpha_input/alpha_input_v1.jsonl` after fix — no lines with `"tf_sec": 0`
2. XRPUSDT bar records (`"tf_sec": 300`) remain present with TA feature keys
3. Live run: warning `Skipping ta_ensemble: missing required features` no longer fires for XRPUSDT

---

## Files Modified

```
apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py  [EDIT]
tests/unit/alpha_search/test_feature_mirror_writer.py                  [CREATE]
```

## Commit message (proposed)

```
FIX-ALPHA-SEARCH-TICK-FILTER: filter tf_sec<60 in FeatureMirrorWriter

FeatureMirrorWriter was writing tick-level EVT:FEATURES_CALCULATED
(tf_sec=0) to alpha_input_v1.jsonl. The standalone alpha_search
runtime replayed these records through ScenarioWorker, causing
CMD:PROCESS_STRATEGY with tf_sec=0. ta_ensemble then received tick
features lacking bar-aggregated TA indicators (bb_position, rsi_14,
bb_width, stoch_k, etc.) and emitted a WARNING + skipped scoring.

Fix: add `if not tf_sec or tf_sec < 60: skip` guard in
FeatureMirrorWriter._on_features, consistent with identical guards in
feature_engineering.py:1370 and aurora_handler.py:600.

XRPUSDT is NOT affected by production Aurora strategies (disabled) but
IS independently evaluated by ta_ensemble in alpha_search — this fix
unblocks correct evaluation.

Tests: 8 new unit tests in test_feature_mirror_writer.py (no prior
coverage existed for this module).
```
