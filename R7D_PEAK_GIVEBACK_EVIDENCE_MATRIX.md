# R7D Peak-Giveback Evidence Matrix

Observation window: 2026-04-25T23:00:46.264Z to 2026-04-26T09:27:22.675Z

Note:

- The latest window contains only one primary rid-bearing evaluated lifecycle.
- Most remaining Sidecar rows are suppressions with no active lifecycle and no usable rid; they are summarized in the report but not expanded as separate lifecycle rows here.

| lifecycle/rid | symbol | side | first timestamp | last timestamp | evaluated rows | economics present? | first arm timestamp | max peak_edge_usd | max giveback_pct | threshold met? | recommendation emitted? | close request emitted? | downstream close observed? | case classification | anomaly flag | notes |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_BNBUSDT_1777136102246 | BNBUSDT | SELL | 2026-04-25T23:00:47.445Z | 2026-04-26T05:17:12.453Z | 296 | No. All 296 evaluated rows had `mark_price=null`, `unrealized_pnl_usdt=null`, `unrealized_pnl_pct=null` | Not observable | Not observable | Not observable | Not observable | No | No | No sidecar provenance found in order log, shadow journal, or execution-domain logs | CASE F — Still unobservable | Yes | Latest-window evaluated lifecycle. `peak_giveback_snapshot` absent on every row. Suppressions before and around evaluation were `features_snapshot_missing_or_stale` and `regime_snapshot_missing_or_stale`. |
| aurora_BNBUSDT_1777136102246:SL | BNBUSDT | SELL | 2026-04-26T05:17:12.497Z | 2026-04-26T09:28:49.493Z | 0 | No | Not applicable | Not observable | Not observable | Not observable | No | No | No sidecar provenance found downstream | CASE E — Suppressed safely | Yes | Auxiliary rid path after fill ingress. All observed rows were `POSITION_POLICY_SIDECAR_SUPPRESSED` with `manage_flow_has_no_active_lifecycle`. Existing validator flags this fill-ingress candidate as `became_candidate_but_never_evaluated`. |

## Non-Rid Suppression Summary

| bucket | count | notes |
| --- | ---: | --- |
| `no_manage_flow_for_symbol` | 42,054 | Generic safe suppression on symbols without active lifecycle |
| `features_snapshot_missing_or_stale` | 3,462 | Generic fail-closed stale-input suppression |
| `regime_snapshot_missing_or_stale` | 462 | Generic fail-closed stale-input suppression |

## Matrix Reading

- No row in this matrix proves arm, below-trigger, or threshold-met state.
- No row in this matrix proves runtime-loaded peak-giveback config.
- No row in this matrix proves downstream close routing from Sidecar provenance.
- The matrix therefore supports `PEAK_GIVEBACK_RUNTIME_NOT_PROVEN`, not `QUIET_BUT_OBSERVABLE`.
