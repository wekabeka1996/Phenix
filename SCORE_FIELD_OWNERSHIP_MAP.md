# Score Field Ownership Map

## Phase A Scope
- Contract and trace repair only.
- No threshold retune.
- No score math change.
- No signal-weight change.
- No observe-only downgrade.
- No new confidence formula.

## Live Path
`pillar_sum -> QuadraticScoringKernel.compute() -> Aurora scoring payload -> StrategyGateway strategy_trace -> low_vol_cost_floor -> SafetyGateResult / decision trace`

## LOW_VOL Direction Confidence Policy
- `LOW_VOL_COST_FLOOR` consumes explicit score lineage metadata plus field registry metadata.
- `signal_score` and `final_score` are signed-score compatibility fields and are **not** valid normalized direction confidence.
- Signed-score sources fail closed with `direction_confidence_failure_reason=signed_score_not_allowed_as_direction_confidence` when selected under the `low_vol_direction_confidence` threshold family.
- Phase A does **not** promote a new live Aurora confidence source. `strategy_confidence` and `judge_confidence` stay shadow-only unless explicitly proven live.

## Primary Fields

### `pillar_sum`
- producer: `Aurora feature assembly`
- consumer: `QuadraticScoringKernel.compute()`
- scale: `raw_signed_linear`
- numeric_contract: `finite signed float`
- threshold_family: `none`
- live_authority_status: `live_authoritative`
- allowed_as_direction_confidence: `false`
- notes: Live Aurora raw input. Not a confidence.

### `decision_score`
- producer: `QuadraticScoringKernel.compute()`
- consumer: `Aurora admission thresholds`, `StrategyGateway`, `decision trace`
- scale: `signed_decision_score`
- numeric_contract: `finite signed float`
- threshold_family: `aurora_admission`
- live_authority_status: `live_authoritative`
- allowed_as_direction_confidence: `false`
- notes: Canonical pre-objective live admission score compared to `thr_buy` / `thr_sell`.

### `score`
- producer: `Aurora scoring payload compatibility alias`
- consumer: `legacy scoring consumers`
- scale: `signed_decision_score`
- numeric_contract: `finite signed float`
- threshold_family: `aurora_admission`
- live_authority_status: `compatibility_only`
- allowed_as_direction_confidence: `false`
- notes: Mutable alias. Runtime lineage marks `post_objective_override=true` and can override scale to `signed_objective_score`.

### `signal_score`
- producer: `StrategyGateway strategy_trace assembly`
- consumer: `legacy strategy_trace consumers`
- scale: `signed_decision_score`
- numeric_contract: `finite signed float`
- threshold_family: `none`
- live_authority_status: `compatibility_only`
- allowed_as_direction_confidence: `false`
- notes: Compatibility field only. Runtime meaning follows upstream `score` lineage and may reflect post-objective override.

### `final_score_raw`
- producer: `StrategyGateway strategy_trace assembly`
- consumer: `decision trace`, `forensic consumers`
- scale: `signed_decision_score`
- numeric_contract: `finite signed float`
- threshold_family: `none`
- live_authority_status: `deprecated_alias`
- allowed_as_direction_confidence: `false`
- notes: Deprecated alias for `decision_score` fallback. Name is not authoritative.

### `final_score`
- producer: `Aurora final-stage score assembly`
- consumer: `LOW_VOL telemetry`, `decision trace`
- scale: `signed_decision_score`
- numeric_contract: `finite signed float`
- threshold_family: `none`
- live_authority_status: `compatibility_only`
- allowed_as_direction_confidence: `false`
- notes: Compatibility field for the current final signed score at the emitting stage. Lineage owns the stage truth.

### `direction_confidence`
- producer: `LOW_VOL_COST_FLOOR`
- consumer: `decision trace`, `low-vol telemetry`
- scale: `gate_resolved_confidence`
- numeric_contract: `0..1 normalized`
- threshold_family: `low_vol_direction_confidence`
- live_authority_status: `live_authoritative`
- allowed_as_direction_confidence: `false`
- notes: Gate-local resolved field. Output only, not an upstream producer field.

### `strategy_confidence`
- producer: `strategy-specific helper math`
- consumer: `LOW_VOL_COST_FLOOR candidate input`
- scale: `normalized_confidence_0_1`
- numeric_contract: `0..1 normalized`
- threshold_family: `low_vol_direction_confidence`
- live_authority_status: `shadow_only`
- allowed_as_direction_confidence: `true`
- notes: Shadow-only normalized candidate. No proven live Aurora producer in current checkout.

### `judge_confidence`
- producer: `objective or judge helper surfaces`
- consumer: `LOW_VOL_COST_FLOOR candidate input`
- scale: `normalized_confidence_0_1`
- numeric_contract: `0..1 normalized`
- threshold_family: `low_vol_direction_confidence`
- live_authority_status: `shadow_only`
- allowed_as_direction_confidence: `true`
- notes: Shadow-only normalized candidate. Requires explicit live proof before promotion.

### `aurora_pillar_confidence_candidate`
- producer: `StrategyGateway strategy_trace assembly`
- consumer: `forensic trace only`
- scale: `normalized_confidence_0_1`
- numeric_contract: `0..1 normalized`
- threshold_family: `low_vol_direction_confidence`
- live_authority_status: `shadow_only`
- allowed_as_direction_confidence: `false`
- notes: Shadow-only candidate derived from signed score / threshold geometry. Not promoted to live confidence in Phase A.

## Appendix Fields

### `raw_score`
- producer: `QuadraticScoringKernel.compute()`
- consumer: `Aurora scoring payload`, `quadratic trace`
- scale: `raw_signed_linear`
- numeric_contract: `finite signed float`
- threshold_family: `none`
- live_authority_status: `live_authoritative`
- allowed_as_direction_confidence: `false`
- notes: Kernel raw linear score.

### `objective_score`
- producer: `objective_gate_evaluator`
- consumer: `Aurora final score override`, `forensic trace`
- scale: `signed_objective_score`
- numeric_contract: `finite signed float`
- threshold_family: `objective_gate`
- live_authority_status: `live_authoritative`
- allowed_as_direction_confidence: `false`
- notes: Appendix field emitted when the objective gate produces the live final signed override.

### `model_confidence`
- producer: `objective model helper surfaces`
- consumer: `forensic trace only`
- scale: `normalized_confidence_0_1`
- numeric_contract: `0..1 normalized`
- threshold_family: `none`
- live_authority_status: `shadow_only`
- allowed_as_direction_confidence: `false`
- notes: Observability-only appendix field.

### `active_threshold`
- producer: `Aurora threshold selection`
- consumer: `StrategyGateway trace`, `decision trace`
- scale: `normalized_confidence_0_1`
- numeric_contract: `finite signed float`
- threshold_family: `aurora_admission`
- live_authority_status: `live_authoritative`
- allowed_as_direction_confidence: `false`
- notes: Threshold surface, not a confidence field.

## Runtime Trace Contract
- `score_lineage.path`
- `score_lineage.records[].field`
- `score_lineage.records[].value`
- `score_lineage.records[].scale`
- `score_lineage.records[].producer`
- `score_lineage.records[].consumer_stage`
- `score_lineage.records[].threshold_family`
- `score_lineage.records[].live_authority_status`
- `score_lineage.records[].compatibility_alias_for`
- `score_lineage.records[].post_objective_override`

## LOW_VOL Runtime Selection Contract
- `direction_confidence_selection.selected_source`
- `direction_confidence_selection.selected_scale`
- `direction_confidence_selection.raw_value`
- `direction_confidence_selection.normalized_value_if_any`
- `direction_confidence_selection.threshold_family`
- `direction_confidence_selection.threshold_value`
- `direction_confidence_selection.threshold_source`
- `direction_confidence_selection.selected_stage`
- `direction_confidence_selection.authority_status`
- `direction_confidence_selection.side_scope`
- `direction_confidence_selection.compatibility_alias_used`
