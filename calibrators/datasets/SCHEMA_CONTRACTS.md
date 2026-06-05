# SCHEMA_CONTRACTS.md

## Purpose

Canonical dataset schema contracts for offline calibration work. These are **NOT runtime event schemas**; they document the structure of batch calibration datasets used to fit thresholds, weights, and policy gates.

Schemas are separated from builders and runtime code to:
- Enable independent evolution of contract vs. implementation
- Provide explicit fail-closed validation before data processing
- Document causal and quality assumptions upfront
- Facilitate reproducible calibration across versions

## Non-goals

- **No builders yet**: Schemas are contracts only; dataset construction logic is deferred to Package 03B.
- **No promotion-grade calibration**: Outputs of these schemas remain recommendations until explicitly validated and config-changed.
- **No runtime imports**: Production code must not import these schema models; they are calibration-only artifacts.
- **No YAML mutation**: Calibration outputs do not automatically update YAML; promotion requires separate reviewed changes.

## Schema List

### 1. CalibrationMarketBarRowV1

**Schema ID**: `calibration_market_bar_dataset_v1`

**Purpose**: Store raw market bar data from recorder or external sources.

**Quality Level**: RAW_RUNTIME
**Primary Consumers**: aurora_regime_params, aurora_signal_weights, md_amr_weights, mean_reversion_params, system_stress_weights, md_amr_phase2b, nrr062_historical

**Required Fields**:
- `dataset_schema`: Literal `"calibration_market_bar_dataset_v1"`
- `dataset_version`: Version string (e.g., "1.0.0")
- `source_surface`: Type of data source (e.g., "recorder_csv", "binance_kline")
- `source_file`: File path or identifier
- `symbol`: Trading pair (e.g., "BTCUSDT")
- `tf_sec`: Timeframe in seconds
- `ts_ms`: Timestamp (milliseconds, wallclock)
- `open`, `high`, `low`, `close`: Price levels
- `data_quality`: Quality indicator ("good", "stale", "missing", "malformed")
- `synthetic`: Boolean flag (must be explicit)

**Optional Fields**:
- `session_date`: Date context (YYYY-MM-DD or None)
- `bar_close_ts_ms`: If different from ts_ms
- `volume`, `trade_count`: May be None for some sources

**Forbidden Assumptions**:
- Do not assume volume/trade_count if missing; check quality flag.
- Wallclock timestamps are not causal; treat as archival time only.
- Stale or malformed bars cannot join with real outcomes without auditing source.

**Synthetic Row Policy**:
- May be synthetic=True for schema validation testing.
- Real runtime data should be synthetic=False.

---

### 2. CalibrationFeatureSnapshotRowV1

**Schema ID**: `calibration_feature_snapshot_dataset_v1`

**Purpose**: Store computed feature vector with readiness metadata.

**Quality Level**: JOINED_RUNTIME
**Primary Consumers**: aurora_thresholds, aurora_signal_weights, md_amr_weights, mean_reversion_params, md_amr_phase2b

**Required Fields**:
- `dataset_schema`: Literal `"calibration_feature_snapshot_dataset_v1"`
- `dataset_version`: Schema version
- `source_surface`: Source (e.g., "ta_features_log")
- `source_file`: File path
- `symbol`, `tf_sec`, `ts_ms`: Identifying context
- `close`: Price at snapshot time
- `features`: Dict mapping feature name to value (float | int | str | bool | None)
- `missingness_mask`: Dict mapping feature name to bool (True=missing)
- `synthetic`: Boolean flag

**Optional Fields**:
- `feature_version`: Feature set version
- `ready`: True if all ready, False if degraded, None if unknown
- `not_ready_reasons`: List of reason codes if ready=False
- `regime`, `regime_confidence`: State at snapshot time
- `freshness_ms`: Staleness relative to ts_ms

**Forbidden Assumptions**:
- Do not assume features are present even if ts_ms is valid; check `ready` and `missingness_mask`.
- Presence of a feature in `features` dict does not mean it is recent or correct; check `freshness_ms`.
- Value of None in features does not imply zero or missing; check `missingness_mask`.

**Synthetic Row Policy**:
- May be synthetic=True for validation testing.
- Real feature snapshots should be synthetic=False and include complete `missingness_mask`.

---

### 3. CalibrationOracleRegimeLabelRowV1

**Schema ID**: `calibration_oracle_regime_labels_v1`

**Purpose**: Forward-looking oracle labels for regime model training.

**Quality Level**: DERIVED_LABELLED
**Primary Consumers**: aurora_regime_params, aurora_signal_weights, system_stress_weights

**Required Fields**:
- `dataset_schema`: Literal `"calibration_oracle_regime_labels_v1"`
- `dataset_version`: Schema version
- `source_dataset_id`: Parent dataset (e.g., "calibration_market_bar_dataset_v1")
- `symbol`, `tf_sec`, `ts_ms`: Label observation point
- `horizon_bars`: Number of bars ahead for label window
- `future_return_bps`: Return achieved in bps over horizon
- `future_volatility_bps`: Realized volatility in bps over horizon
- `flip_rate`: Proportion of horizon bars with direction reversal
- `oracle_regime`: Label target ("up", "down", "ranging", etc.)
- `label_version`: Algorithm version for label construction
- `split_bucket`: Time split ("train", "validation", "forward")
- `synthetic`: Boolean flag

**Forbidden Assumptions**:
- Labels are **forward-looking and causal from the observation point**; cannot use information before ts_ms.
- Split assignment is final; do not reshuffle rows between train/validation/forward without rebuilding manifest.
- future_return_bps and future_volatility_bps are **realized truth**, not forecasts.

**Synthetic Row Policy**:
- May be synthetic=True for schema validation.
- Real labels must have synthetic=False and complete source traceability.

---

### 4. CalibrationTradeDecisionRowV1

**Schema ID**: `calibration_trade_decision_dataset_v1`

**Purpose**: Capture entry decisions and intent for outcome joins.

**Quality Level**: JOINED_RUNTIME
**Primary Consumers**: objective_stack, low_vol_cost_floor

**Required Fields**:
- `dataset_schema`: Literal `"calibration_trade_decision_dataset_v1"`
- `dataset_version`: Schema version
- `symbol`: Trading pair
- `dataset_visibility`: Visibility classification ("causal_complete", "diagnostics_only", "uncertain")
- `observation_causal`: True if causal (no lookahead), False if synthetic
- `source_paths`: List of source files/lines for lineage
- `synthetic`: Boolean flag

**Optional (Causal)**:
- `decision_id`, `rid`: Unique identifiers (may be None if diagnostics-only)
- `decision_basis_ts_ms`, `request_ts_ms`, `response_ts_ms`: Causal timestamps
- `strategy_id`, `side`, `proposed_action`: Intent context
- `authority_mode`, `action`, `apply_result`, `reason_code`: Decision outcome

**Forbidden Assumptions**:
- None of the optional fields guarantee data quality or causal completeness.
- If `dataset_visibility` is not "causal_complete", timestamps may be incomplete or approximate.
- Rows with `observation_causal=False` are synthetic and cannot be used for live calibration promotion.

**Synthetic Row Policy**:
- synthetic=True for test data; synthetic=False for runtime-derived.
- observation_causal=False rows are inherently synthetic for training purposes.

---

### 5. CalibrationRealizedTradeRowV1

**Schema ID**: `calibration_realized_trade_dataset_v1`

**Purpose**: Realized trade outcome for entry/exit strategy calibration.

**Quality Level**: DERIVED_LABELLED
**Primary Consumers**: objective_stack, low_vol_cost_floor

**Required Fields**:
- `dataset_schema`: Literal `"calibration_realized_trade_dataset_v1"`
- `dataset_version`: Schema version
- `symbol`, `side`: Trade identity
- `exact_roundtrip`: True if entry and exit both captured; False if partial
- `source_paths`: Source file references
- `synthetic`: Boolean flag

**Optional Fields**:
- `attempt_id`, `decision_id`, `rid`, `lifecycle_id`: Various tracking IDs (may be None)
- `strategy_id`: Strategy name
- `intent_ts_ms`, `entry_ts_ms`, `exit_ts_ms`: Timestamps (may be None)
- `entry_price`, `exit_price`, `qty`: Trade legs
- `outcome`: Terminal status ("closed_win", "closed_loss", "open", "cancelled")
- `gross_pnl`, `realized_pnl_net`: Outcome metrics
- `fees`, `commission`: Cost
- `mfe`, `mae`: Excursion in bps
- `bars_held`: Duration
- `terminal_status`: Status code

**Forbidden Assumptions**:
- If `exact_roundtrip=False`, any pnl/fee metric is **incomplete** and cannot be used for threshold search without explicit handling.
- Missing timestamps do not imply zero duration; they imply data incompleteness.
- realized_pnl_net may be None even if outcome is "closed_win"; check source_paths for full lineage.

**Synthetic Row Policy**:
- synthetic=True for test scenarios.
- Real outcomes must be synthetic=False and sourced from settlement/ledger.

---

### 6. CalibrationLowVolGateRowV1

**Schema ID**: `calibration_low_vol_gate_dataset_v1`

**Purpose**: Gate decision outcomes for low-vol cost-floor policy calibration.

**Quality Level**: DERIVED_LABELLED
**Primary Consumers**: low_vol_cost_floor, nrr062_historical

**Required Fields**:
- `dataset_schema`: Literal `"calibration_low_vol_gate_dataset_v1"`
- `dataset_version`: Schema version
- `symbol`: Trading pair
- `exact_roundtrip`: True if gate decision fully resolved
- `source_paths`: Source references
- `synthetic`: Boolean flag

**Optional Fields**:
- `attempt_id`, `decision_id`: Gate decision identifiers
- `strategy_id`, `side`: Trade context
- `regime`, `regime_confidence`: Market state
- `direction_confidence`: Directional signal strength
- `target_net_fee_multiple`: Required return to cover fees
- `required_gross_tp_bps_floor`: Minimum target pnl
- `min_rr`: Risk/reward floor
- `gross_tp_bps`, `realized_pnl_net`: Outcome metrics
- `commission`: Cost
- `outcome`: Gate decision ("gate_allowed", "gate_rejected", etc.)
- `counterfactual_source`: Source for counterfactual labels

**Forbidden Assumptions**:
- Gate decision outcome is not the same as trade outcome; gate can allow/reject regardless of realized result.
- realized_pnl_net may not be available for rejected gates.
- counterfactual rows are not ground truth; mark clearly if used for training.

**Synthetic Row Policy**:
- synthetic=True for test data.
- Real gate outcomes must be synthetic=False with full source lineage.

---

### 7. CalibrationWalkforwardManifestV1

**Schema ID**: `calibration_walkforward_manifest_v1`

**Purpose**: Document train/validation/forward split boundaries and metadata.

**Quality Level**: DERIVED_LABELLED (metadata)
**Primary Consumers**: aurora_thresholds, aurora_regime_params, md_amr_weights, mean_reversion_params, objective_stack, system_stress_weights, md_amr_phase2b, nrr062_historical

**Required Fields**:
- `dataset_schema`: Literal `"calibration_walkforward_manifest_v1"`
- `dataset_version`: Schema version
- `dataset_id`: Target dataset (e.g., "calibration_market_bar_dataset_v1")
- `source_dataset`: Parent/source dataset name
- `train_start`, `train_end`: Training window bounds
- `validation_start`, `validation_end`: Validation window bounds
- `forward_start`, `forward_end`: Forward/holdout window bounds
- `config_snapshot`: Calibration config dict at split creation time
- `synthetic_allowed`: Boolean; True if synthetic data permitted

**Optional Fields**:
- `excluded_sessions`: List of excluded session IDs/dates
- `label_horizon_bars`: Label horizon in bars (if applicable)
- `notes`: Free-form documentation

**Forbidden Assumptions**:
- Manifest boundaries are **not automatically enforced** by the schema; calibration code must respect them.
- config_snapshot is historical context; do not assume it matches current YAML.
- excluded_sessions may not be exhaustive; audit raw data files for gaps.
- synthetic_allowed=False does not guarantee no synthetic data in the dataset; it is a contract statement.

**Synthetic Row Policy**:
- Manifest itself is typically not "synthetic" but "synthetic_allowed" field is explicit.

---

## Causal-Time Policy

### Policy Statement
All dataset rows preserve **causal time** where applicable:

- **Causal timestamp fields** (e.g., `decision_basis_ts_ms`, `request_ts_ms`, `response_ts_ms` in decision rows; `entry_ts_ms`, `exit_ts_ms` in trade rows) capture the moment of decision/event **before any outcome is known**.
- **Wallclock / archival fields** (e.g., `ts_ms` in market bar rows) record when data was captured or filed, which may be after the causal event.
- Rows with missing or degraded causal timestamps are marked with `dataset_visibility` or explicit quality fields.
- **No lookahead**: Any field labeled as causal must not depend on future information at the observation point.

### Application
- **Feature snapshots** use `ts_ms` as the observation point; `freshness_ms` captures staleness relative to causal decisions.
- **Oracle labels** are constructed **forward-looking** from `ts_ms` using `horizon_bars` or `future_*` fields; they are **not forecasts** but **realized truth**.
- **Decision rows** capture intent and metadata at decision time; outcomes are joined separately.
- **Trade outcome rows** join decision, execution, and settlement causal times; missing timestamps indicate incomplete capture.

---

## Synthetic Data Policy

### Policy Statement
- **Synthetic data** (rows with `synthetic=True`) may be used for:
  - Schema contract validation
  - Edge case testing (malformed data, missing fields, timestamp anomalies)
  - Invariant checking (e.g., all required fields present, extra fields rejected)
  - Parser/join logic verification

- **Synthetic data cannot be used for**:
  - Proving live profitability or fee-aware threshold promotion
  - Calibrating microstructure parameters without live backtest proof
  - Training regime/direction models without independent test data
  - Claiming real-world readiness or performance

### Marking
- All row schemas include explicit `synthetic: bool` field (default False where appropriate).
- Rows with `synthetic=False` represent runtime-derived or audit-backed data.
- Manifest rows (`CalibrationWalkforwardManifestV1`) have `synthetic_allowed: bool` to declare whether synthetic rows are permitted in that split.

---

## Promotion Policy

### Policy Statement
- Calibration outputs (candidate thresholds, weights, gate parameters) start as **recommendations only**.
- Promotion to live config requires:
  1. Separate reviewed package with explicit config changes
  2. Validation report showing consistent out-of-sample performance
  3. Risk gates and safety thresholds applied
  4. Documented approval and decision chain

- **YAML + Pydantic are SSOT for runtime config**; calibration artifacts are reference material unless explicitly promoted.

### No Silent Fallback
- If a calibration run fails or produces invalid candidates, default YAML is used; no implicit override occurs.
- Any change to YAML must be explicit, version-controlled, and reviewable.

---

## Versioning

- **Schema Version** (`dataset_version`): Incremented when structure changes (e.g., new required field, field renamed).
- **Feature Version** (`feature_version` in feature rows): Incremented for feature set changes (e.g., new indicator added).
- **Label Version** (`label_version` in label rows): Incremented for label algorithm changes.
- **Config Snapshot** (in manifest): Tracks config state at split creation for audit trail.

---

## Validation and Error Handling

### Fail-Closed Validation
All validation is **fail-closed**:
- Unknown schema ID → KeyError
- Missing required field → ValidationError
- Extra field not declared → ValidationError (via `extra="forbid"` in Pydantic)
- Invalid type or value → ValidationError
- Invalid or missing causal timestamp → ValidationError (context-dependent)

No silent defaults, no implicit type coercion, no field skipping.

### Schema Registry Helpers
- `list_schema_ids()`: Return sorted list of registered schemas.
- `get_schema_model(schema_id)`: Get Pydantic class for schema; raises KeyError if unknown.
- `validate_row(schema_id, row_dict)`: Validate single row; raises ValidationError on failure.
- `validate_rows(schema_id, rows)`: Validate batch; raises ValidationError on first failure with row index.
- `schema_version_for(schema_id)`: Get schema version string.

---

## Future Work (Package 03B)

Package 03B will implement:
- **Dataset builders** for objective_stack and low_vol_cost_floor (currently unimplemented).
- **Join logic** across recorder, logs, ledger, and settlement surfaces.
- **Manifest generation** for walk-forward splits.
- **Outcome join** for realized trades with complete pnl and fee accounting.

These implementations will **consume** the schema contracts defined here and produce instances that validate against them.
