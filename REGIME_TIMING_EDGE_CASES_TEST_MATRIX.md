# Regime Timing Edge Cases Test Matrix

Targeted validation batch:

`c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/sim/test_regime_timing_edge_cases.py tests/runtime/test_task24_regime_detector_correctness.py tests/bootstrap/test_warmup_ssot_alignment.py tests/domains/regime_detector/test_regime_warmup_backfill.py tests/domains/test_dm_bar_ttl_preemit.py -q`

Result:

- 55 passed
- 0 failed
- Reproduced behaviors are pinned by passing deterministic tests. No intentionally failing tests were committed.

## Scenario Matrix

| Scenario | Concrete seam | Strategy path | Test coverage | Status | Verdict |
| --- | --- | --- | --- | --- | --- |
| One-bar delayed regime event: CMD for bar N arrives before EVT:REGIME_DETECTED(N) | FeatureEngineering injects `self.last_regime.get(symbol)` into CMD payload | Non-Aurora: MR | `tests/sim/test_regime_timing_edge_cases.py::test_mr_one_bar_delayed_regime_event_uses_previous_cached_cmd_regime` | REPRODUCED | Defect-risk timing seam: current bar can run on previous cached regime |
| Alternating stale/ready cadence | Detector stale gate uses `bar_ttl_ms` and emits `UNCERTAIN` on stale bars | Structural regime detector | `tests/sim/test_regime_timing_edge_cases.py::test_detector_alternating_stale_ready_cadence_is_explicit` | REPRODUCED | Contract-valid fail-closed behavior |
| Hysteresis-induced apparent missing regime | Detector hysteresis carry keeps stable regime until confirmation | Structural regime detector | `tests/sim/test_regime_timing_edge_cases.py::test_hysteresis_raw_regime_churn_can_look_missing_without_dropped_emission` | DISPROVEN as missing-event theory | Contract-valid; `UNCERTAIN` carry is not missing regime |
| Startup warmup boundary around required bars and import buffer | `regime_detector_required_bars()` vs `basis_import_buffer` startup plan | Startup / detector warmup | `tests/sim/test_regime_timing_edge_cases.py::test_startup_required_bars_boundary_becomes_ready_at_threshold_and_buffer_only_expands_plan` | DISPROVEN as post-ready cadence theory | Buffer expands startup import plan; it does not create every-other-bar loss after ready |
| Out-of-order delivery: CMD before FEATURES_CALCULATED | MR decisions are driven by CMD; FEATURES event is data-only compatibility hook | Non-Aurora: MR | `tests/sim/test_regime_timing_edge_cases.py::test_mr_cmd_before_features_event_does_not_reprocess_same_bar` | DISPROVEN | Contract-valid; late FEATURES event does not reprocess the same bar |
| Stale features fail-closed | Detector emits `UNCERTAIN` and records `stale_features` drop | Structural regime detector | `tests/runtime/test_task24_regime_detector_correctness.py::test_stale_data_sets_regime_uncertain`, `tests/runtime/test_task24_regime_detector_correctness.py::test_stale_features_do_not_update_buffers` | REPRODUCED | Contract-valid fail-closed behavior |
| Missing regime payload with cache fallback | Aurora fills missing feature regime fields from cached handler state | Aurora | `tests/sim/test_regime_timing_edge_cases.py::test_aurora_missing_regime_payload_uses_cached_previous_regime_with_traceable_ts` | REPRODUCED | Observability gap / defect-risk: traceable by old ts, but same-bar freshness is not explicit |
| Missing regime payload with no cache | Aurora liveness guard blocks when detector heartbeat never arrived | Aurora | `tests/sim/test_regime_timing_edge_cases.py::test_aurora_missing_regime_without_cache_blocks_with_canonical_reason` | REPRODUCED | Contract-valid fail-closed behavior |
| Cross-symbol backlog / queue lag | Per-symbol regime caches in FE bridge and handlers | Non-Aurora: MR | `tests/sim/test_regime_timing_edge_cases.py::test_mr_cross_symbol_delays_are_isolated_per_symbol` | DISPROVEN | Not reproduced; tested seam is symbol-isolated |
| Ancient bar / TTL mismatch near edge | `ReadinessGates.features_ready()` boundary semantics | Decision readiness | `tests/sim/test_regime_timing_edge_cases.py::test_bar_ttl_edge_is_inclusive_and_one_ms_over_fails_in_close_ts_mode`, `tests/domains/test_dm_bar_ttl_preemit.py::test_ancient_bar_rejected_even_in_received_mode` | REPRODUCED | Contract-valid boundary semantics |
| Duplicate or skipped regime events | Cache overwrite on duplicate; previous cache persists across skipped update | Non-Aurora: MR | `tests/sim/test_regime_timing_edge_cases.py::test_mr_duplicate_and_skipped_regime_events_replay_deterministically` | REPRODUCED | Deterministic current behavior; skipped update preserves stale regime until next EVT |

## Supporting Existing Tests

These existing tests were re-run because they close mandatory matrix edges already present in the repo:

- `tests/bootstrap/test_warmup_ssot_alignment.py::test_startup_warmup_plan_equals_canonical_plus_buffer`
- `tests/bootstrap/test_warmup_ssot_alignment.py::test_regime_detector_required_bars_formula`
- `tests/domains/regime_detector/test_regime_warmup_backfill.py::test_after_backfill_first_live_bar_triggers_sma_ready`
- `tests/domains/regime_detector/test_regime_warmup_backfill.py::test_without_backfill_first_live_bar_is_not_ready`
- `tests/runtime/test_task24_regime_detector_correctness.py::test_stale_data_sets_regime_uncertain`
- `tests/runtime/test_task24_regime_detector_correctness.py::test_stale_features_do_not_update_buffers`
- `tests/domains/test_dm_bar_ttl_preemit.py::test_bar_close_ts_mode`
- `tests/domains/test_dm_bar_ttl_preemit.py::test_bar_close_ts_mode_stale`
- `tests/domains/test_dm_bar_ttl_preemit.py::test_ancient_bar_rejected_even_in_received_mode`

## Invariant Coverage

Covered by the targeted pack:

- Missing detector heartbeat yields one canonical blocked outcome on Aurora, not mixed tradable/non-tradable results.
- Alternating stale bars are explicitly rejected as `UNCERTAIN` with `stale_features`, not silently reused.
- `UNCERTAIN` is treated as a present structural regime state and is distinct from missing heartbeat.
- Duplicate and skipped regime-event sequences replay deterministically.
- Cross-symbol delay did not reproduce cache contamination in the tested seam.

Partially covered but still worth hardening:

- Cached previous-bar regime reuse on Aurora is traceable via `regime_ts_ms < bar_close_ts`, but there is no explicit same-bar freshness marker.
- Delayed EVT on MR proves stale current-bar regime use is deterministic; the contract does not currently emit an explicit reason that the regime is previous-bar carry rather than same-bar truth.
