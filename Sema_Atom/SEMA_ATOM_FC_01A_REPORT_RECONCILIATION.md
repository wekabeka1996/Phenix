# SEMA_ATOM_FC_01A_REPORT_RECONCILIATION

## Verdict
FC_01A_RECONCILED_WITH_RESIDUALS

## Scope
- Artifact-only reconciliation of the existing FC_01 outputs after the accepted incomplete guard patch.
- No new data collection, no runtime modification, and no baseline SAF mutation.

## Inputs Read
- aurora_forward_slice_2026-05-08_2026-05-09.saf.jsonl
- SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT.md
- SEMA_ATOM_FORWARD_COLLECTION_INDEX.json
- C:\Users\user\Music\Phenix\logs\order_log_v1.jsonl

## Atom Reconciliation
- atoms_created: 43
- accepted_atoms_created: 0
- rejected_atoms_created: 43
- diagnostics_only_atoms_created: 0
- atoms_created_reconciliation_ok: True

## Accepted Incomplete Inspection
- accepted close events found: 1
- accepted contracts completed: 0
- MFE/MAE computed: 1
- inspected_lifecycle_id: aurora_BTCUSDT_1778207102724
- inspected_pnl_status: unresolved
- inspected_realized_pnl_net: null
- inspected_fees: null
- inspected_close_price: null
- ACCEPTED_INCOMPLETE_TRAINABLE_ATOM_DEFECT: FALSE
- unresolved accepted close did not produce a trainable ACCEPTED atom.
- handling mode: incomplete bucket / excluded from trainable SAF corpus.

## Metric Semantics Clarification
- `accepted close events found = 1` counts the raw `POSITION_CLOSED` row in the window.
- `accepted contracts completed = 0` because the row was incomplete on terminal economics and therefore not trainable.
- `MFE/MAE computed = 1` is still possible because replay only requires symbol, side, entry_price, entry_ts_ms, and close_ts_ms.
- After the patch, replay evidence can still exist for forensic reporting while the unresolved accepted close stays outside the trainable SAF corpus.

## Time Window Semantics
- `--from` is inclusive at 2026-05-08T00:00:00Z.
- `--to` is inclusive by day, implemented as exclusive next-midnight bound.
- window_start_ts_ms: 1778198400000 (2026-05-08T00:00:00+00:00)
- window_end_ts_ms_exclusive: 1778371200000 (2026-05-10T00:00:00+00:00)
- time_window_ambiguity_detected: False
- The end timestamp corresponds to 2026-05-10T00:00:00Z because the collector includes the full UTC day 2026-05-09 and then uses the next midnight as the exclusive boundary.

## Recorder Coverage Impact
- recorder_dates_missing: ["2026-05-09"]
- latest_rejected_event_ts: 1778226002146 (2026-05-08T07:40:02.146000+00:00)
- latest_replay_future_ts: 1778229899999 (2026-05-08T08:44:59.999000+00:00)
- missing_t30_horizons: 0
- missing_t60_horizons: 0
- cross_day_t30_horizons_into_2026_05_09: 0
- cross_day_t60_horizons_into_2026_05_09: 0
- The missing `2026-05-09` recorder directory did not affect any actual rejected T+30/T+60 evaluation in this slice.
- No late 2026-05-08 replay horizon was truncated by the missing next-day recorder folder.

## Index Reconciliation
- index_atoms_created: 43
- index_accepted_atoms_created: 0
- index_rejected_atoms_created: 43
- index_diagnostics_only_atoms_created: 0
- index_incomplete_accepted_missing_realized_pnl_net: 1

## Final Assessment
- The accepted incomplete guard is now effective: unresolved accepted economics no longer enter the trainable SAF corpus.
- Residuals remain from the requested window extending beyond recorder day coverage, but they did not create the original accepted-atom blocker.
