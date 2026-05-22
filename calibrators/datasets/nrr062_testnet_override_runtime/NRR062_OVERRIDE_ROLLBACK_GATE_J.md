# NRR062_OVERRIDE_ROLLBACK_GATE_J

| condition | value | interpretation |
| --- | --- | --- |
| verdict | NO_ROLLBACK_SIGNAL_SAMPLE_GATE_REACHED_KEEP_TESTNET_ONLY | no rollback trigger fired, but Package J adds an adverse close |
| override_observed | True | runtime override cohort exists |
| boundary_leak_detected | False | no leakage observed in retained J surface |
| override_outside_testnet_hybrid | False | no live or production leakage |
| realized_positive | False | Package J-only realized override net |
| current_total_realized_positive | True | combined I+J net remains positive |
| sl_or_adverse_close_dominates | False | current total sample is not loss-dominant |
| j_window_negative_close_observed | True | Package J contributes one canonical loss |
| sample_gate_reached_current_total | True | I+J reaches 31 admitted override rids and 5 canonical closes |
| sample_size_sufficient_for_promotion | False | sample gate reached is not promotion-grade |
| objective_rows_preserve_override_token | false | still raw-log-only truth |
| decision_ledger_preserves_override_token | false | still raw-log-only truth |
| sidecar_authority_changed | False | no authority change in scope |
| production_scope_changed | False | no rollout widening |

Recommended action: Keep the Package G override unchanged in hybrid_live_data_testnet_exec only; do not promote, do not tune thresholds, and run a short post-sample-gate stability review because Package J adds one canonical override loss while the cumulative I+J sample only just reaches the 31 admitted / 5 canonical-close gate.
