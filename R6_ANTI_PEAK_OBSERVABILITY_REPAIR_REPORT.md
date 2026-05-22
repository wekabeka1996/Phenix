# AGENT_REPORT_V1

## Executive verdict
ANTI_PEAK_OBSERVABILITY_PATCHED_AND_TESTED

## FACTS
- Baseline runtime evidence in reports/POST_RESTART_ANTI_PEAK_OBSERVABILITY_RUNTIME_VALIDATION.md showed 0 percent anti_peak coverage across inspected post-restart decision artifacts.
- Aurora already computed anti-peak truth in the decision/runtime path before this patch, primarily via AuroraDecisionMixin._build_anti_peak_observability and vol-adjusted gates in scoring_helpers._apply_vol_adj_gates.
- Before this patch, persisted artifacts were inconsistent:
  - signal and trace payloads could carry anti_peak under scoring or top-level depending on path,
  - shadow journal compact retention only preserved top-level anti_peak blocks,
  - vol-adjusted anti-flat and anti-fomo blocked events emitted price_motion details but did not emit anti_peak_observability,
  - at least one TRADE_INTENT_REJECTED path in DecisionMaking low-vol handling bypassed StrategyGateway._reject and therefore needed explicit enrichment.
- The patch is additive-only. No thresholds, scoring math, gate enablement semantics, or config values were changed.
- The canonical anti_peak_observability block now exposes flat top-level fields for enabled or disabled state, config provenance, motion classification, missing inputs, score path summary, threshold context, provenance source, readiness, and final reason.
- Legacy nested structures motion, score_path, danger_zone_shield, context_shield, system_stress, and classification were retained for compatibility.
- Shadow journal compact retention now hoists anti_peak_observability from three locations when relevant: top-level payload, scoring.anti_peak_observability, and details.anti_peak_observability.
- Updated runtime emission surfaces:
  - EVT:STRATEGY_SIGNAL_PRODUCED
  - EVT:STRATEGY_DECISION_BLOCKED
  - EVT:TRADE_INTENT_REJECTED
  - EVT:QUADRATIC_DECISION_TRACE
  - EVT:DECISION_TRACE_EMITTED
  - EVT:GATE_CHAIN_TRACE when anti_peak is naturally available from the triggering strategy signal
- JSON schemas were updated additively for the touched events. No new event names were introduced, so no YAML registry additions were required.
- Validation executed successfully:
  - pytest tests/domains/decision_making/test_anti_peak_trace_persistence.py tests/domains/decision_making/test_aurora_price_motion_provenance.py -q -> 22 passed
  - pytest tests/domains/decision_making/test_aurora_quadratic_logging.py tests/domains/decision_making/test_intent_builder_payload_contract.py tests/contracts/test_aurora_tpsl_owner_ctx_schema_additive.py tests/domains/decision_making/test_low_vol_cost_floor_gate.py -q -> 74 passed

## INFERENCES
- The pre-patch anti_peak blind spot was an observability persistence defect, not a missing anti-peak scoring mechanism.
- The dominant persistence failure mode was shape mismatch between where anti_peak truth was produced and what compact journal retention preserved.
- The vol-adjusted deny path was a second independent observability gap: even perfect shadow retention could not prove anti-flat or anti-fomo blocking if the blocked event never carried anti_peak in the first place.
- The explicit flat contract reduces audit ambiguity because disabled, insufficient-data, within-band, anti-flat-triggered, and anti-fomo-triggered cases are now directly legible without reconstructing nested aliases.
- Because legacy aliases remain in place, the change is low-risk for downstream consumers that still read the old nested shape.

## ASSUMPTIONS
- Existing downstream forensic or BI consumers either ignore unknown additive fields or continue reading the legacy alias shape.
- EVT:GATE_CHAIN_TRACE consumers can tolerate the new optional anti_peak_observability field.
- No hidden out-of-repo log shippers depend on anti_peak_observability being absent from compact fragments.

## UNKNOWNS
- No post-patch runtime session has yet been observed, so durable live-log proof is still missing.
- No evidence was gathered for every possible TRADE_INTENT_REJECTED producer in the repo; this patch covers the touched StrategyGateway reject path and the observed low-vol DecisionMaking reject path.
- No downstream external consumer inventory was executed during this repair, so compatibility is inferred from additive contract shape rather than proven end-to-end.

## Current anti-peak computation path
- Aurora computes anti-peak observability in apps/reference/domains/strategies/runtimes/aurora/decision.py via AuroraDecisionMixin._build_anti_peak_observability.
- The builder reads active or disabled vol-gate config truth, price_motion-derived normalized motion, scoring result fields, admission_pre_shield, final score, and shield breakdown context.
- Vol-adjusted anti-flat and anti-fomo gating in apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py now attaches the same anti_peak block to blocked-event details using the live result, live feature snapshot, and price-motion provenance.
- StrategyGateway and DecisionMaking now forward existing anti_peak truth into rejection artifacts instead of dropping it.

## Current persistence gap root cause
- Anti_peak truth was previously produced in some Aurora paths but not normalized into a single operator-facing contract.
- Compact shadow journal retention in apps/reference/telemetry/shadow_journal.py preserved top-level anti_peak blocks but did not hoist nested scoring or details anti_peak payloads.
- Some blocked or rejected events either omitted anti_peak entirely or relied on paths that did not naturally surface it at the persisted fragment level.
- Result: runtime truth existed in-process, but inspected durable artifacts could still show zero anti_peak coverage.

## Added anti_peak_observability contract
- Canonical top-level fields added include:
  - enabled
  - gate_disabled
  - motion_classification
  - missing_inputs
  - active_config
  - disabled_config_snapshot
  - anti_fomo_sigma
  - anti_flat_sigma
  - window_sec
  - anti_fomo_sigma_value_source
  - anti_flat_sigma_value_source
  - window_sec_value_source
  - motion_norm_sigma
  - score_before_shields
  - score_after_shields
  - final_score
  - signal_threshold
  - danger_zone_applied
  - context_shield_applied
  - attenuated_below_threshold
  - consumed_by_gate
  - source
  - ready
  - reason
- The contract is explicit for disabled and insufficient-data cases. It does not invent neutral defaults.
- Legacy alias sections remain present only for compatibility and migration.

## Runtime surfaces updated
- EVT:STRATEGY_SIGNAL_PRODUCED now carries canonical anti_peak under scoring.anti_peak_observability.
- EVT:STRATEGY_DECISION_BLOCKED now carries anti_peak in details.anti_peak_observability on the anti-flat and anti-fomo deny path.
- EVT:TRADE_INTENT_REJECTED now carries anti_peak in details.anti_peak_observability when available from the incoming strategy signal or low-vol strategy trace.
- EVT:QUADRATIC_DECISION_TRACE continues to carry anti_peak at top level, now with the canonical flat fields added.
- EVT:DECISION_TRACE_EMITTED continues to receive anti_peak through trace context and now persists it reliably in compact journal fragments.
- EVT:GATE_CHAIN_TRACE can now copy anti_peak to a top-level field when the originating strategy signal already has it.

## Schema / registry changes
- Updated additively:
  - apps/reference/domains/decision_making/intent/schemas/quadratic_decision_trace_v1.json
  - schemas/decision_trace_emitted_v1.json
  - schemas/strategy_signal_produced_v1.json
  - apps/reference/domains/decision_making/intent/schemas/str_decision_blocked_v1.json
  - schemas/trade_intent_rejected_v1.json
  - apps/reference/domains/decision_making/intent/schemas/gate_chain_trace_v1.json
- anti_peak_observability definitions were loosened to additionalProperties true where necessary to preserve additive compatibility.
- No new event types were created. No registry updates were required.

## Shadow journal retention behavior
- build_payload_fragment now preserves anti_peak_observability for the touched decision surfaces even when the source payload stores it under scoring or details instead of top-level.
- This is event-aware retention, not a broad global payload expansion.
- The compact journal still remains selective; the repair only hoists the anti_peak block required for operator auditability.

## Tests added and validation output
- Added or expanded focused persistence tests for:
  - canonical top-level anti_peak fields on signal and trace paths
  - disabled-config truth persistence
  - insufficient-motion-data classification without fabricated neutral defaults
  - TRADE_INTENT_REJECTED anti_peak persistence via StrategyGateway reject flow
  - shadow journal hoisting from scoring and details
  - anti-flat blocked-event anti_peak emission with provenance and consumed_by_gate truth
- Validation results:
  - Focused anti-peak slice: 22 passed
  - Adjacent anti-peak contract slice: 74 passed
- One neighboring expectation was updated from attenuated_below_threshold = null to explicit false because the new contract records non-triggered attenuation as a real observed state instead of leaving it implicit.

## Legacy / technical debt classification
- motion
- score_path
- danger_zone_shield
- context_shield
- system_stress
- classification

These nested sections are migration aliases, not the canonical SSOT for future observability consumption.

## Behavior-change statement
- This repair changes observability shape and persistence coverage only.
- It does not change Aurora entry scoring, threshold selection, gate thresholds, config semantics, or decision outcomes.
- Operators should now see anti_peak truth in persisted decision artifacts where the previous runtime showed zero coverage.

## Residual risks
- Runtime proof is still pending. The patch is tested, but no post-patch live or replay log sample was captured in this task.
- Some downstream readers may continue preferring legacy nested aliases; that is compatible now, but it prolongs dual-shape support.
- Optional gate-chain propagation is code-tested only indirectly through touched paths, not yet proven with fresh runtime artifacts.

## Whether a short runtime is required
Yes.

A short runtime is required before claiming runtime-complete repair, because the patch changes persisted decision artifacts and compact journal retention behavior. The minimum credible follow-up is a short fresh run that emits at least one signal and one blocked or rejected decision after the patch boundary, then confirms non-zero anti_peak coverage in the durable artifacts.

## Minimal safe verdict
ANTI_PEAK_OBSERVABILITY_PATCHED_AND_TESTED
