# MD_AMR Package D.2-PRE Entry Anchor Persistence Report

## Current Anchor Lifecycle

Before this change, md_amr captured `entry_anchor` only in handler-local in-memory state. The anchor was set on entry and cleared on full close or drift-to-flat, but restart-holdover scenarios lost the target-side anchor payload because no strategy-local persistence surface existed. Package C.4 then behaved correctly and fail-closed: when anchor-derived inputs were absent after restart, `context_validity` degraded to `UNKNOWN` / `MISSING_CONTEXT`.

After this change, the lifecycle is split by ownership boundary:

- md_amr persists strategy-local `entry_target_price` in a narrow md_amr-owned artifact.
- md_amr reconstructs `entry_price` only from execution-position portfolio truth.
- md_amr restores `_entry_anchor` only when both persisted target and execution entry price are available.
- md_amr clears both in-memory and persisted anchor state on flat transitions.
- md_amr keeps C.4 fail-closed behavior unchanged when restoration preconditions are not met.

## Chosen Persistence / Reconstruction Design

The implemented design is a narrow mixed persistence-plus-reconstruction fix.

- Persisted: `entry_target_price`, plus minimal audit fields needed to trace the stored anchor record.
- Reconstructed: `entry_price`, sourced from execution-position truth at restore time.
- Not changed: execution-position restore contracts, startup analytics restore payload shape, md_amr scoring formulas, threshold tuning, promotion behavior, or broader restart architecture.

This keeps ownership coherent. `entry_target_price` is strategy-local and not reconstructable from execution truth, so md_amr owns its persistence. `entry_price` is execution truth and is therefore reconstructed from the canonical execution-position state rather than promoted into md_amr-owned restart truth.

## Files Changed

- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/decision_making/md_amr_entry_anchor_artifact.py
- apps/reference/config_models.py
- config/aurora/strategies/md_amr.yaml
- tests/config/test_md_amr_package_d2_pre_entry_anchor_config_contract.py
- tests/domains/decision_making/test_md_amr_entry_anchor_persistence.py
- tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py
- tests/domains/decision_making/test_md_amr_package_c4_handler_contract.py
- tests/domains/decision_making/test_md_amr_tf_sec_guard.py
- tests/domains/decision_making/test_md_amr_silence_observability.py

## Diagnostics Added

The handler now emits explicit runtime markers around the new seam:

- artifact load and persistence activity
- anchor capture on entry
- anchor restore on restart-holdover recovery
- anchor clear on flat transitions
- unavailable-anchor diagnostics when persisted target is missing
- unavailable-anchor diagnostics when execution entry price is unavailable
- explicit C.4 fallback logging when restoration cannot satisfy context-validity inputs

These diagnostics make the new restart boundary observable without widening execution-position ownership.

## Validation Evidence

Focused D.2-PRE validation passed:

- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_md_amr_package_d2_pre_entry_anchor_config_contract.py tests/domains/decision_making/test_md_amr_entry_anchor_persistence.py tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py tests/domains/decision_making/test_md_amr_package_c4_handler_contract.py tests/domains/decision_making/test_md_amr_tf_sec_guard.py tests/domains/decision_making/test_md_amr_silence_observability.py -q`
- Result: 33 passed

Broader md_amr regression slice passed after compatibility hardening for object-created clean-start fixtures:

- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/feature_engineering/test_md_amr_package_a_exit_semantics.py tests/domains/feature_engineering/test_md_amr_package_b_hold_calibration.py tests/domains/feature_engineering/test_md_amr_package_c1_progress.py tests/domains/feature_engineering/test_md_amr_package_c2_setup_quality.py tests/domains/feature_engineering/test_md_amr_package_c3_hold_quality.py tests/domains/feature_engineering/test_md_amr_package_c4_context_validity.py tests/domains/decision_making/test_md_amr_clean_start_upgrade.py tests/bootstrap/test_runtime_analytics_restore.py tests/bootstrap/test_startup_hydration_planner.py -q`
- Result: 77 passed

Compatibility note proven during validation:

- legacy clean-start tests instantiate `MDAMRHandler` via `object.__new__` and skip `__init__`
- new helper methods were hardened to self-initialize local anchor maps and skip cfg-dependent restore work when `_cfg` is absent
- after that hardening, the clean-start regression file passed and the broader slice returned 77/77 green

## What Is Proven

- md_amr now has a narrow strategy-local persistence surface for entry-anchor restart state.
- restart-holdover restoration can repopulate `_entry_anchor` when persisted target data and execution entry price are both available.
- when those preconditions are absent, the handler remains fail-closed and does not fabricate anchor state.
- production YAML and typed config contracts expose the new persistence setting explicitly.
- existing C.3 and C.4 handler-contract slices remain green.
- clean-start and startup-hydration regression slices remain green after the change.

## What Remains Unproven

- live runtime proof from an actual restart-holdover production session was not collected in this task.
- long-window operational behavior of the new artifact under repeated restart cycles was not exercised beyond tests.
- broader repository-wide regression outside the md_amr, startup-hydration, and focused package boundary was not run.
- this task does not prove D.2 itself; it proves the stated D.2 precondition defect has been addressed narrowly.

## Operational Risks

- the new artifact is strategy-local state, so corruption or manual deletion of the file can still force the expected fail-closed UNKNOWN path after restart.
- restore depends on execution-position truth being available; if execution truth arrives late, anchor restoration is deferred until the relevant portfolio update path runs.
- tests proved contract compatibility for `object.__new__`-style handler fixtures, but future helper additions in md_amr can regress that compatibility if they assume `__init__` state is always present.

## Readiness for D.2 Re-Attempt

The requested D.2-PRE precondition is now addressed narrowly and with evidence. The change persists only the strategy-local part of anchor state, reconstructs only the execution-owned part from canonical truth, preserves C.4 fail-closed semantics, and clears the previously failing clean-start regression slice.

That is sufficient to re-attempt D.2 without bundling a broader restart redesign. The remaining uncertainty is runtime proof depth, not an unresolved contract gap in the precondition fix itself.

## Final Verdict

D.2 PRECONDITION FIXED — READY FOR D.2 RE-ATTEMPT
