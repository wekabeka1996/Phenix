from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.flows.close.close_executor import (
    CloseExecutor,
)
from apps.reference.domains.execution_position.flows.close.close_submission_adapter import (
    CloseSubmissionPayload,
)
from apps.reference.domains.execution_position.flows.close.fsm_close import (
    CloseFlowFSM,
)
from apps.reference.domains.execution_position.telemetry.close_shadow_comparison import (
    BOUNDARY_KEYS,
    BRIDGE_KEYS,
    SUBMISSION_KEYS,
    TRUTH_GATE_KEYS,
    compare_close_projections,
)
from apps.reference.telemetry.shadow_journal import ShadowCriticalEventJournal
from vfoundation.core.protocol import Message


def _cmd_close_message(
    *,
    rid: str,
    symbol: str,
    qty: str | None = None,
    idempotent_key: str | None = None,
    reason: str = "manual_close",
) -> Message:
    payload: dict[str, object] = {
        "symbol": symbol,
        "reason": reason,
    }
    if qty is not None:
        payload["qty"] = qty
    if idempotent_key is not None:
        payload["idempotent_key"] = idempotent_key
    return Message(
        op="CMD",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld=payload,
        why=reason,
    )


def _dec_close_message(
    *,
    rid: str,
    symbol: str,
    idempotent_key: str = "idem-1",
    qty: str | None = None,
) -> Message:
    payload: dict[str, object] = {
        "symbol": symbol,
        "idempotent_key": idempotent_key,
    }
    if qty is not None:
        payload["qty"] = qty
    return Message(
        op="DEC",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld=payload,
        data_ref=[],
    )


def _comparison_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        if record.get("record_type") == "comparison":
            records.append(record)
    return records


def _make_executor_harness(
    *,
    journal_path: Path,
    position_amt: Decimal | str = Decimal("0.10"),
) -> tuple[CloseExecutor, SimpleNamespace, SimpleNamespace, SimpleNamespace, ShadowCriticalEventJournal]:
    place_close = AsyncMock(return_value={"status": "NEW"})
    adapter = SimpleNamespace(
        get_open_positions=AsyncMock(
            return_value=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": str(position_amt),
                }
            ]
        ),
        get_open_orders=AsyncMock(return_value=[]),
        place_market_reduce_only=place_close,
    )
    order_guardian = SimpleNamespace(
        cleanup_before_close=AsyncMock(return_value=0),
        cleanup_orphans=AsyncMock(return_value=0),
        cleanup_other_brackets_for_symbol=AsyncMock(return_value=0),
        reconcile_symbol=AsyncMock(return_value=None),
    )
    fsm = SimpleNamespace(
        adapter=adapter,
        config=SimpleNamespace(
            domains=SimpleNamespace(
                execution_position=SimpleNamespace(
                    order_lifecycle=SimpleNamespace(
                        fill_settlement_delay_ms=0,
                        position_close_cleanup_delay_ms=0,
                    )
                )
            )
        ),
        manage_flows={},
        _symbol_brackets={},
        order_guardian=order_guardian,
        _clear_symbol_brackets=MagicMock(),
        _persist_restore_artifact_snapshot=MagicMock(),
        _emit_position_policy_close_request_state=MagicMock(),
        _emit_observability_event=MagicMock(),
        _orphan_metrics={"errors": 0, "reconcile_cancelled": 0},
        _is_unknown_order_error=MagicMock(return_value=False),
        _is_cancel_success_response=MagicMock(return_value=True),
        _cancel_status_str=MagicMock(return_value="CANCELED"),
    )
    journal = ShadowCriticalEventJournal(path=str(journal_path))
    fsm._shadow_journal = journal
    return CloseExecutor(fsm), fsm, adapter, order_guardian, journal


@pytest.mark.parametrize("qty, expected_partial", [(None, False), ("0.04", True)])
def test_close_flow_shadow_bridge_records_match_for_full_and_partial_close(
    tmp_path: Path,
    qty: str | None,
    expected_partial: bool,
) -> None:
    journal_path = tmp_path / f"bridge_{qty or 'full'}.jsonl"
    flow = CloseFlowFSM()
    flow.set_shadow_journal(ShadowCriticalEventJournal(path=str(journal_path)))
    msg = _cmd_close_message(
        rid="RID-CLOSE-BRIDGE",
        symbol="BTCUSDT",
        qty=qty,
        idempotent_key="idem-bridge-1",
    )

    result = flow.handle(msg)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    records = _comparison_records(journal_path)
    comparison = next(
        record["payload_fragment"]["comparison"]
        for record in records
        if record["event_name"] == "EVT:CLOSE_SHADOW_BRIDGE"
    )
    assert comparison["stage"] == "bridge"
    assert comparison["comparison_outcome"] == "match"
    assert comparison["comparison_classification"] is None
    assert comparison["comparison_keys"] == list(BRIDGE_KEYS)
    assert comparison["context"]["source"] == "CloseFlowFSM"
    assert result.pld["symbol"] == "BTCUSDT"
    assert result.pld.get("qty") == qty
    if expected_partial:
        assert result.pld["qty"] == "0.04"


@pytest.mark.parametrize(
    "requested_qty, expected_partial",
    [(None, False), (Decimal("0.04"), True)],
)
@pytest.mark.asyncio
async def test_close_submission_shadow_records_match_for_full_and_partial_close(
    tmp_path: Path,
    requested_qty: Decimal | None,
    expected_partial: bool,
) -> None:
    executor, _, _, _, _ = _make_executor_harness(
        journal_path=tmp_path / f"submission_{requested_qty or 'full'}.jsonl",
        position_amt=Decimal("0.10"),
    )
    decision = _dec_close_message(
        rid="RID-CLOSE-SUBMISSION",
        symbol="BTCUSDT",
        idempotent_key="idem-submission-1",
    )

    submission = executor._build_close_submission(
        decision=decision,
        symbol="BTCUSDT",
        position_amt=Decimal("0.10"),
        requested_qty=requested_qty,
    )

    assert submission is not None
    assert submission.partial_close is expected_partial
    assert submission.symbol == "BTCUSDT"

    records = _comparison_records(
        tmp_path / f"submission_{requested_qty or 'full'}.jsonl"
    )
    comparison = next(
        record["payload_fragment"]["comparison"]
        for record in records
        if record["event_name"] == "EVT:CLOSE_SHADOW_SUBMISSION"
    )
    assert comparison["stage"] == "submission"
    assert comparison["comparison_outcome"] == "match"
    assert comparison["comparison_classification"] is None
    assert comparison["comparison_keys"] == list(SUBMISSION_KEYS)
    assert comparison["context"]["source"] == "CloseExecutor"
    assert comparison["context"]["requested_qty"] == (
        None if requested_qty is None else "0.04"
    )


@pytest.mark.asyncio
async def test_close_submission_invalid_qty_records_shadow_reject(
    tmp_path: Path,
) -> None:
    executor, _, _, _, _ = _make_executor_harness(
        journal_path=tmp_path / "invalid_qty.jsonl",
        position_amt=Decimal("0.10"),
    )
    decision = _dec_close_message(
        rid="RID-CLOSE-INVALID-QTY",
        symbol="BTCUSDT",
        qty="abc",
        idempotent_key="idem-invalid-1",
    )

    requested_qty, rejected = executor._parse_requested_close_qty(
        decision=decision,
        symbol="BTCUSDT",
    )

    assert requested_qty is None
    assert rejected is True
    records = _comparison_records(tmp_path / "invalid_qty.jsonl")
    comparison = next(
        record["payload_fragment"]["comparison"]
        for record in records
        if record["event_name"] == "EVT:CLOSE_SHADOW_SUBMISSION_REJECT"
    )
    assert comparison["stage"] == "submission_reject"
    assert comparison["comparison_outcome"] == "reject"
    assert comparison["comparison_classification"] is None


def test_shadow_mismatch_classifications_are_explicit() -> None:
    payload_divergence = compare_close_projections(
        stage="submission",
        incumbent={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.1",
            "partial_close": False,
            "client_order_id": "CLOSE-BTCUSDT-1",
            "idempotent_key": "idem-1",
        },
        shadow={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.1",
            "partial_close": False,
            "client_order_id": "CLOSE-BTCUSDT-1",
            "idempotent_key": "idem-1",
        },
        comparison_keys=SUBMISSION_KEYS,
        validation_keys=("validation_classification", "reject_reason", "reason", "idempotent_key"),
    )
    assert payload_divergence.comparison_outcome == "mismatch"
    assert payload_divergence.comparison_classification == "payload_divergence"

    state_divergence = compare_close_projections(
        stage="bridge",
        incumbent={
            "state": "OPENED",
            "position_active": True,
            "last_close_reason": None,
            "last_close_qty": None,
            "last_close_symbol": None,
        },
        shadow={
            "state": "FLAT",
            "position_active": False,
            "last_close_reason": None,
            "last_close_qty": None,
            "last_close_symbol": None,
        },
        comparison_keys=(
            "state",
            "position_active",
            "last_close_reason",
            "last_close_qty",
            "last_close_symbol",
        ),
        state_keys=(
            "state",
            "position_active",
            "last_close_reason",
            "last_close_qty",
            "last_close_symbol",
        ),
    )
    assert state_divergence.comparison_outcome == "mismatch"
    assert state_divergence.comparison_classification == "state_divergence"

    validation_divergence = compare_close_projections(
        stage="submission",
        incumbent={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.1",
            "partial_close": False,
            "client_order_id": "CLOSE-BTCUSDT-1",
            "idempotent_key": "idem-1",
        },
        shadow={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.1",
            "partial_close": False,
            "client_order_id": "CLOSE-BTCUSDT-1",
            "idempotent_key": "idem-2",
        },
        comparison_keys=SUBMISSION_KEYS,
        validation_keys=("validation_classification", "reject_reason", "reason", "idempotent_key"),
    )
    assert validation_divergence.comparison_outcome == "mismatch"
    assert validation_divergence.comparison_classification == "validation_divergence"

    comparison_unavailable = compare_close_projections(
        stage="submission",
        incumbent=None,
        shadow={
            "symbol": "BTCUSDT",
        },
        comparison_keys=SUBMISSION_KEYS,
    )
    assert comparison_unavailable.comparison_outcome == "unavailable"
    assert comparison_unavailable.comparison_classification == "comparison_unavailable"

    shadow_failure = compare_close_projections(
        stage="submission",
        incumbent={
            "symbol": "BTCUSDT",
        },
        shadow={
            "symbol": "BTCUSDT",
        },
        comparison_keys=SUBMISSION_KEYS,
        instrumentation_failure="shadow boom",
    )
    assert shadow_failure.comparison_outcome == "failure"
    assert shadow_failure.comparison_classification == "shadow_instrumentation_failure"


@pytest.mark.asyncio
async def test_close_submit_boundary_shadow_comparison_is_telemetry_only(
    tmp_path: Path,
) -> None:
    executor, fsm, adapter, order_guardian, _ = _make_executor_harness(
        journal_path=tmp_path / "boundary.jsonl",
        position_amt=Decimal("0.10"),
    )
    manage_flow = SimpleNamespace(
        _closing_position=False,
        _closing_position_ts=0.0,
        set_bracket_ids=MagicMock(),
    )
    fsm.manage_flows["BTCUSDT"] = manage_flow
    decision = _dec_close_message(
        rid="RID-CLOSE-BOUNDARY",
        symbol="BTCUSDT",
        idempotent_key="idem-boundary-1",
    )
    submission = CloseSubmissionPayload.from_dec_close(
        symbol="BTCUSDT",
        position_amt=Decimal("0.10"),
        requested_qty=None,
        idempotent_key="idem-boundary-1",
    )

    with patch(
        "apps.reference.domains.execution_position.flows.close.close_executor.order_logger.write"
    ) as mock_write:
        response = await executor._submit_close_order(
            decision=decision,
            submission=submission,
        )

    assert response == {"status": "NEW"}
    assert adapter.place_market_reduce_only.await_count == 1
    assert mock_write.call_count == 2
    written_event_types = [call.args[0]["event_type"] for call in mock_write.call_args_list]
    assert written_event_types == ["ORDER_INTENT", "ORDER_PLACED"]
    manage_flow.set_bracket_ids.assert_not_called()
    order_guardian.cleanup_before_close.assert_not_called()
    order_guardian.cleanup_orphans.assert_not_called()
    order_guardian.reconcile_symbol.assert_not_called()
    order_guardian.cleanup_other_brackets_for_symbol.assert_not_called()

    records = _comparison_records(tmp_path / "boundary.jsonl")
    comparison = next(
        record["payload_fragment"]["comparison"]
        for record in records
        if record["event_name"] == "EVT:CLOSE_SHADOW_SUBMIT_BOUNDARY"
    )
    assert comparison["stage"] == "submit_boundary"
    assert comparison["comparison_outcome"] == "match"
    assert comparison["comparison_classification"] is None
    assert comparison["comparison_keys"] == list(BOUNDARY_KEYS)


@pytest.mark.asyncio
async def test_shadow_instrumentation_failure_does_not_block_adapter(
    tmp_path: Path,
) -> None:
    executor, _, adapter, order_guardian, journal = _make_executor_harness(
        journal_path=tmp_path / "failure.jsonl",
        position_amt=Decimal("0.10"),
    )
    manage_flow = SimpleNamespace(
        _closing_position=False,
        _closing_position_ts=0.0,
        set_bracket_ids=MagicMock(),
    )
    executor._fsm.manage_flows["BTCUSDT"] = manage_flow
    journal.record_comparison = MagicMock(side_effect=RuntimeError("shadow boom"))
    decision = _dec_close_message(
        rid="RID-CLOSE-FAILURE",
        symbol="BTCUSDT",
        idempotent_key="idem-failure-1",
    )
    submission = CloseSubmissionPayload.from_dec_close(
        symbol="BTCUSDT",
        position_amt=Decimal("0.10"),
        requested_qty=None,
        idempotent_key="idem-failure-1",
    )

    with patch(
        "apps.reference.domains.execution_position.flows.close.close_executor.order_logger.write"
    ) as mock_write:
        await executor._submit_close_order(
            decision=decision,
            submission=submission,
        )

    assert adapter.place_market_reduce_only.await_count == 1
    assert mock_write.call_count == 2
    event_types = [call.args[0]["event_type"] for call in mock_write.call_args_list]
    assert event_types == ["ORDER_INTENT", "ORDER_PLACED"]
    manage_flow.set_bracket_ids.assert_not_called()
    order_guardian.cleanup_before_close.assert_not_called()
    order_guardian.cleanup_orphans.assert_not_called()
    order_guardian.reconcile_symbol.assert_not_called()
    order_guardian.cleanup_other_brackets_for_symbol.assert_not_called()


@pytest.mark.asyncio
async def test_zero_position_truth_gate_records_shadow_reject_and_skips_later_lifecycle(
    tmp_path: Path,
) -> None:
    executor, fsm, adapter, order_guardian, _ = _make_executor_harness(
        journal_path=tmp_path / "truth_gate.jsonl",
        position_amt=Decimal("0"),
    )
    manage_flow = SimpleNamespace(
        _closing_position=False,
        _closing_position_ts=0.0,
        set_bracket_ids=MagicMock(),
    )
    fsm.manage_flows["BTCUSDT"] = manage_flow
    decision = _dec_close_message(
        rid="RID-CLOSE-FLAT",
        symbol="BTCUSDT",
        idempotent_key="idem-flat-1",
    )
    decision.pld["policy_context"] = {
        "policy_source": "position_policy_sidecar",
        "symbol": "BTCUSDT",
        "source_trace_id": "trace-flat-1",
    }

    await executor.execute_close(decision)

    adapter.place_market_reduce_only.assert_not_awaited()
    order_guardian.cleanup_before_close.assert_not_awaited()
    order_guardian.cleanup_orphans.assert_not_awaited()
    order_guardian.reconcile_symbol.assert_not_awaited()
    order_guardian.cleanup_other_brackets_for_symbol.assert_not_awaited()
    manage_flow.set_bracket_ids.assert_not_called()
    assert manage_flow._closing_position is False
    assert manage_flow._closing_position_ts == 0.0
    fsm._emit_position_policy_close_request_state.assert_called_once()

    records = _comparison_records(tmp_path / "truth_gate.jsonl")
    comparison = next(
        record["payload_fragment"]["comparison"]
        for record in records
        if record["event_name"] == "EVT:CLOSE_SHADOW_TRUTH_GATE"
    )
    assert comparison["stage"] == "truth_gate"
    assert comparison["comparison_outcome"] == "reject"
    assert comparison["comparison_classification"] is None


def test_missing_idempotent_key_comparison_classifies_as_validation_divergence() -> None:
    comparison = compare_close_projections(
        stage="submission",
        incumbent={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.1",
            "partial_close": False,
            "client_order_id": "CLOSE-BTCUSDT-1",
            "idempotent_key": "idem-1",
        },
        shadow={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.1",
            "partial_close": False,
            "client_order_id": "CLOSE-BTCUSDT-1",
        },
        comparison_keys=SUBMISSION_KEYS,
        validation_keys=(
            "validation_classification",
            "reject_reason",
            "reason",
            "idempotent_key",
        ),
    )
    assert comparison.comparison_outcome == "mismatch"
    assert comparison.comparison_classification == "validation_divergence"
    assert "idempotent_key" in comparison.mismatch_fields
