# AGENT_REPORT_V1

## Executive Summary
A3 canonical decision ledger restoration is closed in current scope: the canonical ledger now writes explicit decision-time seed revisions, appends final terminal revisions for the same decision_id and rid, exposes accepted unresolved decisions as a separate builder category, and preserves null close or PnL fields for unresolved rows.

## Proven Facts
- Canonical row contract now carries explicit revision_status, outcome_status, terminal_status, and dataset_visibility fields.
- Accepted decision seed rows serialize as revision_status=SEED_PENDING_OUTCOME and outcome_status=UNRESOLVED_ACCEPTED.
- Rejected decision-terminal rows serialize as revision_status=DECISION_TERMINAL and outcome_status=NOT_APPLICABLE.
- Final close-backed rows serialize as revision_status=OUTCOME_FINAL and outcome_status=REALIZED.
- Accepted unresolved rows do not emit synthetic realized_pnl_net, realized_pnl_gross, fees, close_reason, or close_ts_ms values; those fields stayed null in runtime evidence.
- The realized outcome builder now exposes accepted_unresolved_rows separately and does not route those rows into rejected_rows or realized_rows.
- The realized outcome builder collapses duplicate decision ledger revisions by latest appended row for the same rid using timestamp plus line-order tie-break, and the real sink seed-plus-final sequence resolves to a single final realized row.
- Broad nearby validation passed: 33 tests passed across the touched contract, sink, and builder files.

## Inferred Findings
- The canonical ledger is now usable as the proof surface for decision to outcome joins without requiring in-place mutation of prior JSONL rows.
- Explicit revision_status plus outcome_status closes the ambiguity between pending accepted decisions, decision-terminal rejects, and realized final outcomes.
- Backfilling missing snapshot observation timestamps from request_ts_ms is necessary to preserve trainable visibility for non-trace decision-terminal rows when the upstream snapshot omits its own event timestamp.

## Contradictions / Evidence Gaps
- No live production runtime was exercised in this task; proof is local test and local scratch runtime only.
- Latest-row collapse still keys on rid at the builder seam; this report does not prove decision_id-first collapse for cross-decision rid collision edge cases.

## Root Cause Candidates
- The original canonical ledger lacked explicit revision semantics, so accepted seed rows and final rows shared the same surface without an explicit state marker.
- The realized outcome builder treated all no-close decisions as rejected_rows, which collapsed accepted unresolved decisions into the wrong category.
- Shadow decision snapshots could omit their own observation timestamp, causing legitimate decision-terminal rows to downgrade to diagnostics_only unless the sink backfilled causal observation time from request_ts_ms or event_ts_ms.

## Operational Risk
- Correctness
- Observability Gap

## Files / Areas Touched
- apps/reference/domains/neocortex/contracts/decision_outcome_ledger.py
- apps/reference/domains/neocortex/logic/ledger/decision_outcome_ledger.py
- calibrators/datasets/builders/realized_outcome_builder.py
- tests/domains/neocortex/contract/test_decision_outcome_ledger_contract.py
- tests/domains/shadow_telemetry/test_decision_ledger_join.py
- tests/calibrators/test_realized_outcome_builder.py

## Validation Performed
- Narrow A3 validation:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/neocortex/contract/test_decision_outcome_ledger_contract.py tests/domains/shadow_telemetry/test_decision_ledger_join.py::test_decision_trace_accept_seed_emits_unresolved_row_before_terminal_event tests/domains/shadow_telemetry/test_decision_ledger_join.py::test_decision_trace_reject_seed_emits_vetoed_row_without_terminal_event tests/calibrators/test_realized_outcome_builder.py::test_builder_exposes_accepted_unresolved_separately_from_rejections_and_final_rows tests/calibrators/test_realized_outcome_builder.py::test_sink_seed_then_terminal_revision_builder_collapses_to_latest_final_row tests/calibrators/test_realized_outcome_builder.py::test_builder_uses_latest_appended_decision_row_revision_for_duplicate_rid -q
13 passed in 2.86s
```

- Broader touched-surface validation:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/neocortex/contract/test_decision_outcome_ledger_contract.py tests/domains/shadow_telemetry/test_decision_ledger_join.py tests/calibrators/test_realized_outcome_builder.py -q
33 passed in 9.57s
```

- Runtime evidence collection:

```text
PYTHONPATH=<repo-root> c:/Users/user/Music/Phenix/.venv/Scripts/python.exe scratch/a3_report_samples/generate_a3_evidence.py
```

## Sample Rows
Accepted seed then final revision from one real sink sequence:

```json
[
  {
    "decision_id": "decision-evidence-accepted-1",
    "rid": "RID-EVIDENCE-ACCEPTED-1",
    "revision_status": "SEED_PENDING_OUTCOME",
    "outcome_status": "UNRESOLVED_ACCEPTED",
    "terminal_status": "INVALID_FOR_DATASET",
    "dataset_visibility": "diagnostics_only",
    "invalid_reason_code": "OUTCOME_UNRESOLVED",
    "accepted_or_rejected": "ACCEPTED",
    "execution_outcome": "PENDING_TIMEOUT",
    "realized_pnl_net": null,
    "realized_pnl_gross": null,
    "fees": null,
    "close_reason": null,
    "close_ts_ms": null,
    "intent_id": "LIFE:decision-evidence-accepted-1",
    "cycle_key": "ENTRY:BTCUSDT:300:1700000000000"
  },
  {
    "decision_id": "decision-evidence-accepted-1",
    "rid": "RID-EVIDENCE-ACCEPTED-1",
    "revision_status": "OUTCOME_FINAL",
    "outcome_status": "REALIZED",
    "terminal_status": "EXECUTED_AND_CLOSED",
    "dataset_visibility": "trainable",
    "invalid_reason_code": null,
    "accepted_or_rejected": "ACCEPTED",
    "execution_outcome": "EXECUTED",
    "realized_pnl_net": 1.8,
    "realized_pnl_gross": 2.0,
    "fees": 0.2,
    "close_reason": "TP_HIT",
    "close_ts_ms": 1714568600000,
    "intent_id": "LIFE:decision-evidence-accepted-1",
    "cycle_key": "ENTRY:BTCUSDT:300:1700000000000"
  }
]
```

Rejected decision-terminal row from one real sink sequence:

```json
{
  "decision_id": "decision-evidence-rejected-1",
  "rid": "RID-EVIDENCE-REJECTED-1",
  "revision_status": "DECISION_TERMINAL",
  "outcome_status": "NOT_APPLICABLE",
  "terminal_status": "VETOED",
  "dataset_visibility": "trainable",
  "invalid_reason_code": null,
  "accepted_or_rejected": "REJECTED",
  "execution_outcome": "FSM_BLOCKED",
  "realized_pnl_net": null,
  "realized_pnl_gross": null,
  "fees": null,
  "close_reason": null,
  "close_ts_ms": null,
  "intent_id": "LIFE:decision-evidence-rejected-1",
  "cycle_key": "ENTRY:BTCUSDT:300:1700000000000"
}
```

Accepted unresolved builder category sample:

```json
{
  "summary": {
    "rows_emitted": 0,
    "accepted_unresolved_rows": 1
  },
  "accepted_unresolved_row": {
    "reason": "ACCEPTED_UNRESOLVED",
    "decision_id": "dec_unresolved_1",
    "rid": "rid_unresolved_1",
    "lifecycle_id": "lc_unresolved_1",
    "terminal_status": "INVALID_FOR_DATASET",
    "outcome_status": "UNRESOLVED_ACCEPTED",
    "revision_status": "SEED_PENDING_OUTCOME",
    "accepted_or_rejected": "ACCEPTED",
    "dataset_visibility": "diagnostics_only",
    "invalid_reason_code": "OUTCOME_UNRESOLVED",
    "realized_pnl_net": null,
    "fees": null,
    "close_reason": null,
    "close_ts_ms": null
  },
  "rejected_rows": []
}
```

## Residual Risk
- The builder collapse proof is local and keyed by rid; cross-decision rid alias collisions remain outside the evidence scope of this report.
- The accepted_unresolved category is exposed in builder result, manifest, quality report, and JSONL artifact, but downstream consumers beyond the realized outcome builder were not audited in this task.

## What Remains Unproven
- Live runtime durability across restarts and log rotation for mixed seed plus final revision streams.
- End-to-end consumption of accepted_unresolved_rows by every downstream reporting or training pipeline outside the realized outcome builder.
- Behavior under malformed or duplicated decision_id and rid combinations beyond the covered latest-row tie-break path.

## Minimal Safe Verdict
Within the current A3 scope, canonical decision ledger restoration is complete and evidenced: decision-time accepted and rejected rows are explicit, unresolved accepted decisions are category-separated, final outcome collapse is proven on real appended sink output, and unresolved rows do not synthesize close or economics fields.
