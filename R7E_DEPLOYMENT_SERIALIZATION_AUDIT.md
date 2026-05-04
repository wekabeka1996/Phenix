# R7E Deployment And Serialization Audit

## Problem Framing

R7E localizes why the original R7D runtime slice showed none of the additive R7C observability fields in raw trade_lifecycle evidence.

This package is bounded to deployment, transport, and persistence proof. It does not change peak-giveback business behavior, thresholds, close routing, or Sidecar design.

## FACTS

### Deployed-Build Identity Findings

- apps/reference/domains/execution_position/position_policy_sidecar.py on disk is R7C-capable and contains sidecar_config_snapshot, peak_giveback_snapshot, peak_giveback_state, null_reasons, and policy_source logic.
- Only one workspace copy of position_policy_sidecar.py exists.
- The active runtime command line is still -m apps.reference.main.
- Import resolution through the configured virtual environment resolves execution_position Sidecar and trade_lifecycle logger modules to the workspace tree.
- The current sidecar file LastWriteTimeUtc is 2026-04-26 09:10:46.
- The currently running matching processes were created at 2026-04-26 15:00:02 UTC and 2026-04-26 15:00:03 UTC, which is after the sidecar file timestamp rather than before it.

### Sidecar Payload Construction Findings

- PositionPolicySidecar.announce_mode_active constructs sidecar_config_snapshot before publish.
- PositionPolicySidecar._evaluate_symbol attaches peak_giveback_snapshot to non-mode Sidecar payloads before publish.
- PositionPolicySidecar._peak_giveback_snapshot constructs peak_giveback_state and null_reasons.
- PositionPolicySidecar._handle_peak_giveback_trigger stamps policy_source = position_policy_sidecar:peak_giveback for peak-giveback recommendation and close-request flows.
- PositionPolicyCloseRequest.to_payload emits event_type = POSITION_POLICY_SIDECAR_CLOSE_REQUESTED while the command topic remains CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST by design.

### Event Bus And Serializer Findings

- PositionPolicySidecar._publish first optionally emits dict(payload) onto the internal bus and then directly writes record = {"record_kind": "position_policy_sidecar", **payload} to append_trade_lifecycle_record.
- LocalBus.emit forwards payload unchanged to listeners and does not normalize, flatten, or allowlist fields.
- append_trade_lifecycle_record persists the full dict via json.dumps(record, ensure_ascii=False, default=str) with no projection layer.
- iter_trade_lifecycle_records can hide policy rows only at read time when include_policy_records is false; the raw JSONL line on disk is not rewritten or projected.
- A direct passthrough probe using append_trade_lifecycle_record preserved sidecar_config_snapshot, peak_giveback_snapshot, null_reasons, and policy_source unchanged in JSONL.

### Fresh Runtime Artifact Findings

- The current raw logs/trade_lifecycle.jsonl line 1 is a POSITION_POLICY_SIDECAR_MODE_ACTIVE row that already contains sidecar_config_snapshot.
- The next fresh BNBUSDT Sidecar rows in the same file contain peak_giveback_snapshot, peak_giveback_state, and explicit null_reasons in raw JSONL.
- Those fresh raw rows are written by the currently running post-R7C processes, not by the historical pre-restart slice that R7D inspected.

## INFERENCES

- The earlier absence of R7C fields in the R7D slice was not caused by serializer loss, event-bus stripping, or missing source construction.
- The smallest explanation consistent with both the historical absence and the current post-restart presence is stale runtime build: the earlier process slice was running pre-R7C code, and the restarted slice is running R7C-capable code.
- There is no evidence of an event-name or writer-filter mismatch on the raw trade_lifecycle path. The distinction between CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST and event_type POSITION_POLICY_SIDECAR_CLOSE_REQUESTED is intentional and normalized by the close-request object and mediator.
- The current deployment gap is operationally resolved for raw trade_lifecycle observability because the restarted runtime now writes the expected additive fields.

## ASSUMPTIONS

- The current trade_lifecycle.jsonl leading rows belong to the present restarted runtime slice rather than to a manually injected offline replay. This is consistent with the mode-active row shape and current live process timestamps, but there is no startup build fingerprint in logs to make that attribution self-identifying.

## UNKNOWNS

- Startup logs still do not expose a git SHA, build ID, or source fingerprint, so deployment identity remains indirect rather than banner-based.
- One matching process still reports ExecutablePath = C:/Python314/python.exe despite the exact .venv command line. Current evidence does not show that this changes module resolution or payload shape, but the discrepancy remains operationally odd.

## Requested Cause Matrix

### 1. Runtime Host Not Running The R7C Build

Status: supported as the historical root cause for the missing-field slice.

Mechanism:

- the original slice lacked the additive fields
- the current source and writer path prove the fields should persist
- the restarted slice now emits those fields in raw JSONL

### 2. Wrong Entrypoint, Wrong Working Tree, Or Wrong Venv

Status: not supported.

Reason:

- command line remains -m apps.reference.main
- import resolution still points at workspace modules
- the current runtime emits the exact R7C fields expected from this tree

### 3. Sidecar Does Not Construct The New Fields At Runtime

Status: disproven.

Reason:

- construction is present in current source
- fresh runtime rows now show the constructed fields on disk

### 4. Event Bus Or Payload Adapter Stripping The Fields

Status: disproven for raw trade_lifecycle.

Reason:

- _publish writes directly after bus emit
- LocalBus is pass-through
- fresh raw JSONL contains the fields

### 5. trade_lifecycle Writer Or Serializer Dropping Additive Fields

Status: disproven.

Reason:

- writer is raw json.dumps
- direct passthrough probe preserved all additive fields
- fresh runtime raw JSONL now preserves them too

### 6. Another Concrete Wiring Issue

Status: no stronger competing explanation remains.

Reason:

- both historical and current evidence are fully explained by stale runtime deployment followed by restart onto the correct build

## Coverage Boundary

- Existing R7C tests prove schema shape and in-memory payload construction.
- Existing tests still do not include a focused end-to-end raw JSONL assertion for sidecar_config_snapshot, peak_giveback_snapshot, and null_reasons.
- That is an automation gap, not the cause of the historical runtime absence.

## Exact Root Cause Classification

STALE_RUNTIME_BUILD

## Smallest Safe Next Step

- No production code change is needed in this package.
- Treat the restart onto the verified build as the corrective action that resolved the observability gap.
- If future deployment forensics need to be cheaper, add a startup build fingerprint in a separate bounded package rather than changing Sidecar behavior here.
