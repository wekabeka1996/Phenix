# DATA-RECORDER-CONTEXT-01: Architectural Analysis

**Date:** 2026-01-12
**Status:** ANALYSIS COMPLETE

## 1. Configuration & Timeframes (15m Support)

**Finding:** The 15-minute timeframe (`900` seconds) is **currently disabled** in Feature Engineering configuration.

```yaml
# config/aurora/domains.yaml
feature_engineering:
  enabled_timeframes_sec: [180, 300]  # Missing 900
```
However, other parts of the system are 15m-aware:
- `pending_entry_ttl.ttl_by_tf_sec` includes `900: 180`.
- `bar_gating.bar_ms` is `900000` (15m).

**Action Required:**
- Add `900` to `feature_engineering.enabled_timeframes_sec` in `config/aurora/domains.yaml`.

## 2. Data Payload Analysis (EVT:FEATURES_CALCULATED)

**Finding:** The current `EVT:FEATURES_CALCULATED` payload **missing the raw OHLCV bar data**.
It contains:
```python
{
    "ts": int,              # Bar end timestamp
    "symbol": str,
    "tf_sec": int,
    "features": dict,       # Calculated features
    "warmup": dict,         # Warmup state
    "price_motion": dict    # Price motion state
}
```
The raw `bar_data` (OHLCV) is available inside `FeatureEngineering._calculate_and_emit_features` but is only sent downstream inside `CMD:PROCESS_STRATEGY`, and *only* if the system is fully warmed up and gates pass.

**Architectural Gap:**
For backtesting purposes, we often want to record data *before* it passes all strategy gates (e.g. to debug why it failed). We also need the raw OHLCV (Open, High, Low, Close, Volume) to simulate strategy execution aligned with features.

**Proposed Fix:**
- Modify `FeatureEngineering.py` to inject `bar_data` (OHLCV) into the `EVT:FEATURES_CALCULATED` payload. This ensures the event is a self-contained "Data Record".

## 3. Regime Sync (The "When")

**Finding:** `RegimeDetector` is an asynchronous consumer of `EVT:FEATURES_CALCULATED`.
- **Trigger:** Listens to `features_calculated`.
- **Filtering:** Currently hardcoded to process only `basis_tf_sec` (usually 5m or 300s). It filters out everything else.
- **Output:** Emits `EVT:REGIME_DETECTED`.

**Challenge:**
If we want 15m Regime data, the `RegimeDetector` will currently **ignore** 15m features because `basis_tf_sec` is likely 300.

**Proposed Plan (Recorder Sync):**
The Recorder needs to join these two asynchronous streams:
1.  `EVT:FEATURES_CALCULATED` (arrives first, contains Bar + Features).
2.  `EVT:REGIME_DETECTED` (arrives milliseconds later, contains Regime).

**Synchronization Strategy:**
- Implement a `UnifiedRecorder` with a short-lived memory buffer (e.g., `Buffer[symbol_ts]`).
- When `FEATURES` arrives: Store in buffer. Schedule a "Flush" timeout (e.g., 500ms).
- When `REGIME` arrives: Look up in buffer, attach regime data, mark as "Complete".
- **Flush:** Write to CSV when "Complete" OR when timeout expires (writing "Regime: UNKNOWN" if missing).

## 4. Implementation Plan

### Step 1: Configuration Update
- Edit `config/aurora/domains.yaml`: Add `900` to `enabled_timeframes_sec`.

### Step 2: Payload Enrichment
- Edit `apps/reference/domains/feature_engineering/feature_engineering.py`:
  - Add `bar: bar_data` to `features_payload` dictionary before emission.

### Step 3: Create `CsvRecorder` Component
- Create `apps/reference/domains/data_recorder/recorder.py`:
  - Class `RefDataRecorder(fsm, config)`
  - `listen("EVT:FEATURES_CALCULATED")` -> Buffers row.
  - `listen("EVT:REGIME_DETECTED")` -> Updates buffer.
  - `_flush_loop()` -> Periodic writer (every 1s) to batch write to disk.
  - Output path: `data/recorder/{date}/{symbol}_{tf}_features.csv`.

### Step 4: Wiring
- Edit `apps/reference/main.py`: Initialize `RefDataRecorder` and `start()` it.

### Step 5: Validation
- Run `apps/reference/main.py` locally.
- Verify CSVs are generated in `data/recorder/`.
- Verify 15m (900s) files exist.

## 5. Investigation: Why logs/mean_reversion/bars_180s.tsv is not written?

**Symptom:** The file `logs/mean_reversion/bars_180s.tsv` is either missing or empty.

**Code Path Analysis:**
1.  **Configuration:** `mean_reversion.timeframe_sec` is set to `180` in `config/aurora/strategies/mean_reversion.yaml`. The `MeanReversionBarLogger` is correctly initialized with this timeframe.
2.  **File Creation:** The logger creates the directory and file with header immediately upon initialization (`MeanReversionBarLogger.__init__`). If the file is missing entirely, the `MeanReversionHandler` is failing to initialize (unlikely if system runs). If the file exists but has no data, the `log_bar` method is never called.
3.  **Trigger Point:** `log_bar` is called inside `MeanReversionHandler._on_process_strategy`.
4.  **Event Chain:**
    - `FeatureEngineering` calculates features.
    - If `warmup.full_ready` is **True**, it emits `CMD:PROCESS_STRATEGY`.
    - `MeanReversionHandler` receives CMD, validates `tf_sec == 180`, runs logic, and calls `log_bar`.
    - If `warmup.full_ready` is **False**, no CMD is emitted.

**Conclusion:**
The absence of data in `bars_180s.tsv` indicates that **Feature Engineering is never reaching `full_ready` state** for the 180s timeframe.
- This effectively blocks `CMD:PROCESS_STRATEGY` emission.
- Because the existing logger listens *downstream* of the strategy gate, it cannot record the "warming up" data.

**Recommendation:**
This confirms the critical need for the new **Combined Data Recorder** (proposed above). By hooking into `EVT:FEATURES_CALCULATED` (upstream event), the new recorder will capture data *regardless* of warmup status, allowing us to debug exactly *why* the system isn't warming up (by inspecting the `warmup.reasons` field in the recorded CSV).
