# AGENT_REPORT_V1

## Executive Summary
A4 authoritative lifecycle stats ledger proving slice is complete for execution-owned append-only telemetry. The ledger contract, append seams, proof tests, and sample rows are now explicit. Sidecar reader cutover is not implemented yet and remains a deferred residual. Execution behavior did not change; this work is telemetry/ledger only.

## Proven Facts
- The canonical default ledger path is logs/execution_lifecycle_stats_v1.jsonl.
- The canonical row schema version is execution_lifecycle_stats_v1 and the record kind is execution_lifecycle_stats.
- The canonical owner recorded in each row is execution_position.
- Lifecycle rows are keyed by lifecycle_id, with entry_rid preserved as the causal join key.
- The ledger is append-only and does not overwrite prior rows.
- Provisional rows are appended on entry fill, open portfolio updates, and close-request transitions.
- Final rows are appended on authoritative close detection from execution_position.
- Path stats are computed in the execution-owned ledger, not reconstructed later from sidecar snapshots.
- Close-request transitions are appended from PositionPolicyMediator using source CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST.
- FINAL rows preserve path stats and use authoritative close truth for gross_pnl, fees, and net_pnl when pnl_status is resolved.
- Unresolved or incomplete close accounting now fails closed in the ledger: gross_pnl, fees, and net_pnl remain null instead of being synthesized.
- Workspace search under apps/reference/domains/execution_position/** found no lifecycle_stats_ref or lifecycle_stats_source fields.
- Workspace search under apps/reference/domains/execution_position/sidecar/** found only write-side ExecutionLifecycleStatsLedger references inside position_policy_mediator.py; no sidecar reader surfaced.
- Execution behavior did not change. No order-routing, fill-handling, close-submission, or adapter logic was changed for business behavior. The change is telemetry/ledger only.

## Canonical Ledger Contract

Ledger path:

logs/execution_lifecycle_stats_v1.jsonl

Canonical row schema fields, in dataclass order:

1. record_kind
2. schema_version
3. owner
4. row_status
5. provisional_status
6. provenance_source
7. recorded_ts_ms
8. lifecycle_id
9. entry_rid
10. symbol
11. side
12. entry_ts_ms
13. entry_price
14. qty
15. best_price_in_trade_direction
16. worst_price_against_trade
17. mfe_usdt
18. mae_usdt
19. mfe_bps
20. mae_bps
21. first_positive_pnl_ts_ms
22. peak_edge_usd
23. peak_giveback_usd
24. peak_giveback_pct
25. current_unrealized_at_close_request
26. close_ts_ms
27. close_actor
28. close_reason
29. gross_pnl
30. fees
31. net_pnl

Join keys:

- lifecycle_id: primary lifecycle ledger key.
- entry_rid: causal join key back to the authoritative entry fill / lifecycle start.

Authoritative append seams:

- Entry fill seed: execution_position event handler on final entry fill.
- Open provisional update: execution_position event handler on EVT:PORTFOLIO_STATE_UPDATED.
- Close-request transition: position policy mediator after typed close command emission.
- Final close: execution_position event handler on position-close detection using authoritative close truth.

No post-hoc reconstruction rule:

Path stats are appended at the owning execution seams above. They are not rebuilt later from sidecar recommendation snapshots, score payloads, or advisory shadow telemetry.

## Sample Rows

Open provisional sample row:

```json
{
  "record_kind": "execution_lifecycle_stats",
  "schema_version": "execution_lifecycle_stats_v1",
  "owner": "execution_position",
  "row_status": "PROVISIONAL",
  "provisional_status": "open_live",
  "provenance_source": "portfolio_state_updated",
  "recorded_ts_ms": 1700000000999,
  "lifecycle_id": "life-report-1",
  "entry_rid": "entry-report-1",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entry_ts_ms": 1700000000000,
  "entry_price": 100.0,
  "qty": 2.0,
  "best_price_in_trade_direction": 104.0,
  "worst_price_against_trade": 100.0,
  "mfe_usdt": 8.0,
  "mae_usdt": 0.0,
  "mfe_bps": 400.0,
  "mae_bps": 0.0,
  "first_positive_pnl_ts_ms": 1700000000200,
  "peak_edge_usd": 8.0,
  "peak_giveback_usd": 0.0,
  "peak_giveback_pct": 0.0,
  "current_unrealized_at_close_request": null,
  "close_ts_ms": null,
  "close_actor": null,
  "close_reason": null,
  "gross_pnl": null,
  "fees": 0.15,
  "net_pnl": null
}
```

Close-request transition sample row:

```json
{
  "record_kind": "execution_lifecycle_stats",
  "schema_version": "execution_lifecycle_stats_v1",
  "owner": "execution_position",
  "row_status": "PROVISIONAL",
  "provisional_status": "close_requested",
  "provenance_source": "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST",
  "recorded_ts_ms": 1700000000999,
  "lifecycle_id": "life-report-1",
  "entry_rid": "entry-report-1",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entry_ts_ms": 1700000000000,
  "entry_price": 100.0,
  "qty": 2.0,
  "best_price_in_trade_direction": 104.0,
  "worst_price_against_trade": 100.0,
  "mfe_usdt": 8.0,
  "mae_usdt": 0.0,
  "mfe_bps": 400.0,
  "mae_bps": 0.0,
  "first_positive_pnl_ts_ms": 1700000000200,
  "peak_edge_usd": 8.0,
  "peak_giveback_usd": 0.0,
  "peak_giveback_pct": 0.0,
  "current_unrealized_at_close_request": 4.5,
  "close_ts_ms": null,
  "close_actor": "POSITION_POLICY_SIDECAR",
  "close_reason": null,
  "gross_pnl": null,
  "fees": 0.15,
  "net_pnl": null
}
```

Closed FINAL sample row:

```json
{
  "record_kind": "execution_lifecycle_stats",
  "schema_version": "execution_lifecycle_stats_v1",
  "owner": "execution_position",
  "row_status": "FINAL",
  "provisional_status": null,
  "provenance_source": "position_closed",
  "recorded_ts_ms": 1700000000999,
  "lifecycle_id": "life-report-1",
  "entry_rid": "entry-report-1",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entry_ts_ms": 1700000000000,
  "entry_price": 100.0,
  "qty": 2.0,
  "best_price_in_trade_direction": 104.0,
  "worst_price_against_trade": 100.0,
  "mfe_usdt": 8.0,
  "mae_usdt": 0.0,
  "mfe_bps": 400.0,
  "mae_bps": 0.0,
  "first_positive_pnl_ts_ms": 1700000000200,
  "peak_edge_usd": 8.0,
  "peak_giveback_usd": 0.0,
  "peak_giveback_pct": 0.0,
  "current_unrealized_at_close_request": 4.5,
  "close_ts_ms": 1700000000500,
  "close_actor": "EXECUTION_POSITION",
  "close_reason": "TP_HIT",
  "gross_pnl": 5.0,
  "fees": 0.4,
  "net_pnl": 4.6
}
```

## Inferred Findings
- The authoritative lifecycle stats surface now has a minimal but complete proof chain from entry to final close.
- Sidecar can request close transitions into the ledger, but it does not yet consume the ledger as a reader.
- The unresolved close-accounting defect was local to FINAL row materialization and is now fail-closed.

## Contradictions / Evidence Gaps
- There is no current evidence of sidecar reading lifecycle stats rows or carrying lifecycle_stats_ref / lifecycle_stats_source payload fields.
- This task did not collect live runtime JSONL from production-like trading sessions; evidence is from deterministic focused tests and deterministic sample-row harnesses.

## Root Cause Candidates
- A4 was previously incomplete because the proof artifact was missing and the unresolved-close path still allowed partial fee leakage into FINAL telemetry rows.
- Sidecar reader cutover was planned later than the execution-owned write-side proof and remains outside the completed A4 proving slice.

## Operational Risk
Observability Gap

## Files / Areas Touched
- apps/reference/domains/execution_position/telemetry/lifecycle_stats_ledger.py
- apps/reference/domains/execution_position/orchestration/event_handlers.py
- apps/reference/domains/execution_position/sidecar/position_policy_mediator.py
- tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py
- tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py
- tests/domains/execution_position/test_close_producer_bridge_package6.py
- A4_AUTHORITATIVE_LIFECYCLE_STATS_LEDGER_REPORT.md

## Validation Performed
Focused test proofs by requirement:

- Entry fill creates provisional row:
  tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_seed_entry_writes_initial_provisional_row
  tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_on_order_fill_seeds_execution_owned_lifecycle_stats
- Portfolio update updates MFE/MAE/peak/giveback side-aware:
  tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_open_update_computes_path_stats_and_first_positive_pnl
  tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_short_side_update_computes_side_aware_mfe_mae_and_giveback
- first_positive_pnl_ts_ms captured:
  tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_open_update_computes_path_stats_and_first_positive_pnl
- Close-request transition appended from mediator:
  tests/domains/execution_position/test_close_producer_bridge_package6.py::test_position_policy_mediator_path_reaches_typed_close_bridge
- FINAL row appends gross/fees/net from authoritative close truth:
  tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_position_close_finalizes_lifecycle_stats_before_cache_cleanup
- Unresolved / incomplete close accounting does not synthesize pnl/fees:
  tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_position_close_with_unresolved_accounting_does_not_synthesize_pnl_or_fees

Final focused pytest command:

```text
& "c:/Users/user/Music/Phenix/.venv/Scripts/python.exe" -m pytest tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py tests/domains/execution_position/test_close_producer_bridge_package6.py::test_position_policy_mediator_path_reaches_typed_close_bridge
```

Final focused pytest output:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\user\Music\Phenix\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\user\Music\Phenix
configfile: pytest.ini
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_seed_entry_writes_initial_provisional_row PASSED [ 10%]
tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_open_update_computes_path_stats_and_first_positive_pnl PASSED [ 20%]
tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_duplicate_provisional_state_is_not_reappended PASSED [ 30%]
tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_short_side_update_computes_side_aware_mfe_mae_and_giveback PASSED [ 40%]
tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py::test_close_request_and_finalize_preserve_path_stats_and_emit_final_row PASSED [ 50%]
tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_on_order_fill_seeds_execution_owned_lifecycle_stats PASSED [ 60%]
tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_on_portfolio_state_updated_updates_provisional_path_stats PASSED [ 70%]
tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_position_close_finalizes_lifecycle_stats_before_cache_cleanup PASSED [ 80%]
tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py::test_position_close_with_unresolved_accounting_does_not_synthesize_pnl_or_fees PASSED [ 90%]
tests/domains/execution_position/test_close_producer_bridge_package6.py::test_position_policy_mediator_path_reaches_typed_close_bridge PASSED [100%]

============================= 10 passed in 2.59s =============================
```

Deterministic sample-row harness:

- Generated canonical field order and the three representative rows shown above from the ledger implementation itself.
- Sample harness used the default ledger contract and deterministic timestamps; it did not depend on sidecar snapshots for path-stat reconstruction.

## Residual Risk
- Sidecar reader cutover is deferred. Consumers that need lifecycle stats still do not receive a dedicated lifecycle_stats_ref or lifecycle_stats_source field from sidecar payloads.
- This report proves append semantics and contract shape, not long-horizon retention, rotation, or production replay across restarts.

## What Remains Unproven
- No production-runtime sample log from a live session was captured in this task.
- No sidecar reader integration exists yet, so there is no reader-side payload contract or reader-side test to present.

## Minimal Safe Verdict
A4 authoritative lifecycle stats ledger is complete for the execution-owned write path and proof artifact requirements. Sidecar reader cutover is not complete and must be tracked as a deferred residual. Execution behavior remains unchanged; this delivery is telemetry/ledger only.
