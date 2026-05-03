"""Phase 6 Package 4 — cancel submission seam closure tests.

Seam: ``DEC:CANCEL_ORDER -> adapter cancellation``.

These tests prove that the typed :class:`CancelSubmissionPayload` is the
single runtime normalization owner of the cancel-submission intake, that the
untyped dual-key glue path no longer governs, and that downstream
``ExecPosFSM._cancel_order`` / ``IdempotentCancelHelper`` / adapter
ownership remains untouched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.guardian.cancel_submission_adapter import (
    CANCEL_SUBMISSION_CONTRACT,
    CANCEL_SUBMISSION_PATH,
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
    build_cancel_submission_trace_ref,
)
from apps.reference.domains.execution_position.flows.close.close_executor import CloseExecutor


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _dec_cancel_decision(
    *,
    symbol: str = "BTCUSDT",
    order_id: str | None = "123456",
    order_id_key: str = "order_id",
    rid: str = "RID-CANCEL-1",
    extras: dict[str, Any] | None = None,
    data_ref: list[str] | None = None,
) -> SimpleNamespace:
    pld: dict[str, Any] = {"symbol": symbol}
    if order_id is not None:
        pld[order_id_key] = order_id
    if extras:
        pld.update(extras)
    return SimpleNamespace(
        op="DEC",
        verb="CANCEL_ORDER",
        rid=rid,
        pld=pld,
        data_ref=list(data_ref or []),
    )


def _build_fsm_with_spy() -> tuple[SimpleNamespace, AsyncMock]:
    cancel_spy = AsyncMock(return_value={"status": "CANCELED"})
    fsm = SimpleNamespace(_cancel_order=cancel_spy)
    return fsm, cancel_spy


# ---------------------------------------------------------------------------
# Typed payload unit tests
# ---------------------------------------------------------------------------


class TestCancelSubmissionPayload:

    def test_accepts_canonical_payload(self) -> None:
        payload = CancelSubmissionPayload.from_dec_cancel(
            payload={"symbol": "BTCUSDT", "order_id": "42"}
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.order_id == "42"

    def test_canonicalizes_orderid_alias(self) -> None:
        payload = CancelSubmissionPayload.from_dec_cancel(
            payload={"symbol": "ETHUSDT", "orderId": "99"}
        )
        # Typed instance exposes only the canonical field name.
        assert payload.order_id == "99"
        assert not hasattr(payload, "orderId")

    def test_prefers_canonical_over_alias_when_both_present(self) -> None:
        payload = CancelSubmissionPayload.from_dec_cancel(
            payload={"symbol": "BTCUSDT",
                     "order_id": "CANON", "orderId": "ALIAS"}
        )
        assert payload.order_id == "CANON"

    def test_accepts_bounded_raw_context_fields_and_returns_canonical_request(self) -> None:
        payload = CancelSubmissionPayload.from_dec_cancel(
            payload={
                "symbol": "BTCUSDT",
                "order_id": "42",
                "trigger": "DEC:CLOSE:reconcile",
                "order_type": "STOP_MARKET",
                "bracket_type": "SL",
                "keep_parent_order_id": "parent-1",
            }
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.order_id == "42"

    def test_rejects_unknown_raw_extra_field(self) -> None:
        with pytest.raises(CancelSubmissionAdapterError) as exc:
            CancelSubmissionPayload.from_dec_cancel(
                payload={
                    "symbol": "BTCUSDT",
                    "order_id": "42",
                    "unexpected_new_field": "boom",
                }
            )
        assert "unexpected_new_field" in str(exc.value)

    def test_rejects_missing_symbol(self) -> None:
        with pytest.raises(CancelSubmissionAdapterError) as exc:
            CancelSubmissionPayload.from_dec_cancel(payload={"order_id": "42"})
        assert "symbol" in str(exc.value)

    def test_rejects_missing_order_id(self) -> None:
        with pytest.raises(CancelSubmissionAdapterError) as exc:
            CancelSubmissionPayload.from_dec_cancel(
                payload={"symbol": "BTCUSDT"})
        assert "order_id" in str(exc.value)

    def test_rejects_empty_values(self) -> None:
        with pytest.raises(CancelSubmissionAdapterError):
            CancelSubmissionPayload.from_dec_cancel(
                payload={"symbol": "   ", "order_id": "42"}
            )
        with pytest.raises(CancelSubmissionAdapterError):
            CancelSubmissionPayload.from_dec_cancel(
                payload={"symbol": "BTCUSDT", "order_id": ""}
            )

    def test_rejects_non_mapping_payload(self) -> None:
        with pytest.raises(CancelSubmissionAdapterError):
            CancelSubmissionPayload.from_dec_cancel(
                payload=["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_model_is_extra_forbid(self) -> None:
        # Direct constructor must reject unknown keys (defense in depth
        # behind the classmethod).
        with pytest.raises(Exception):
            # type: ignore[call-arg]
            CancelSubmissionPayload(symbol="BTCUSDT", order_id="42", foo="bar")


class TestCancelSubmissionTraceRef:

    def test_success_trace_ref_shape(self) -> None:
        ref = build_cancel_submission_trace_ref(status="success")
        assert ref.startswith("obs://execution_position/cancel_submission?")
        assert f"contract={CANCEL_SUBMISSION_CONTRACT}" in ref
        assert "path=DEC%3ACANCEL_ORDER-%3Eadapter" in ref
        assert "status=success" in ref
        assert "reason=" not in ref

    def test_reject_trace_ref_shape(self) -> None:
        ref = build_cancel_submission_trace_ref(
            status="reject", reason="adapter_validation"
        )
        assert f"contract={CANCEL_SUBMISSION_CONTRACT}" in ref
        assert "status=reject" in ref
        assert "reason=adapter_validation" in ref


# ---------------------------------------------------------------------------
# Executor wiring tests
# ---------------------------------------------------------------------------


class TestCloseExecutorCancelIntake:

    @pytest.mark.asyncio
    async def test_canonical_payload_reaches_cancel_order_bridge(self) -> None:
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = _dec_cancel_decision(symbol="BTCUSDT", order_id="42")

        await executor.execute_cancel_order(decision)

        cancel_spy.assert_awaited_once_with("BTCUSDT", "42")
        # Success trace ref attached to the decision's data_ref.
        success_ref = build_cancel_submission_trace_ref(status="success")
        assert success_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_orderid_alias_canonicalized_at_seam(self) -> None:
        """The legacy ``orderId`` key must be canonicalized at the intake.

        This replaces the previous untyped dual-key glue: downstream
        ``_cancel_order`` must receive the canonical id.
        """
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = _dec_cancel_decision(
            symbol="ETHUSDT", order_id="99", order_id_key="orderId"
        )

        await executor.execute_cancel_order(decision)

        cancel_spy.assert_awaited_once_with("ETHUSDT", "99")

    @pytest.mark.asyncio
    async def test_missing_symbol_fails_closed_without_invoking_bridge(self) -> None:
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = SimpleNamespace(
            op="DEC", verb="CANCEL_ORDER", rid="RID-NOSYM",
            pld={"order_id": "42"}, data_ref=[],
        )

        await executor.execute_cancel_order(decision)

        cancel_spy.assert_not_awaited()
        reject_ref = build_cancel_submission_trace_ref(
            status="reject", reason="adapter_validation"
        )
        assert reject_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_missing_order_id_fails_closed_without_invoking_bridge(self) -> None:
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = SimpleNamespace(
            op="DEC", verb="CANCEL_ORDER", rid="RID-NOID",
            pld={"symbol": "BTCUSDT"}, data_ref=[],
        )

        await executor.execute_cancel_order(decision)

        cancel_spy.assert_not_awaited()
        reject_ref = build_cancel_submission_trace_ref(
            status="reject", reason="adapter_validation"
        )
        assert reject_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_empty_string_order_id_fails_closed(self) -> None:
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = _dec_cancel_decision(order_id="   ")

        await executor.execute_cancel_order(decision)

        cancel_spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_executor_routes_through_typed_payload_classmethod(self) -> None:
        """Non-bypass proof: every main cancel dispatch must construct the
        typed payload exactly once via ``from_dec_cancel``.
        """
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = _dec_cancel_decision()

        original = CancelSubmissionPayload.from_dec_cancel
        calls: list[Any] = []

        def _spy(*, payload):
            calls.append(payload)
            return original(payload=payload)

        with patch(
            "apps.reference.domains.execution_position.flows.close.close_executor."
            "CancelSubmissionPayload.from_dec_cancel",
            side_effect=_spy,
        ) as wrapped:
            await executor.execute_cancel_order(decision)

        assert wrapped.call_count == 1
        cancel_spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_bypass_across_representative_upstream_producers(self) -> None:
        """Representative upstream producers (trailing adjust, supersede,
        limit timeout) converge at the same typed intake.

        The seam chokepoint is exactly ``CloseExecutor.execute_cancel_order``,
        so proving 3 independently-constructed upstream shapes all traverse
        ``from_dec_cancel`` exactly once is the non-bypass guarantee.
        """
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)

        upstream_decisions = [
            # Trailing-adjust-style (fsm_manage._emit_cancel_order): orderId key.
            _dec_cancel_decision(
                symbol="BTCUSDT", order_id="TRAIL-1",
                order_id_key="orderId", rid="RID-TRAIL",
            ),
            # Supersede-style: canonical order_id.
            _dec_cancel_decision(
                symbol="ETHUSDT", order_id="SUPER-1", rid="RID-SUPER",
            ),
            # Limit-timeout-style: orderId key.
            _dec_cancel_decision(
                symbol="SOLUSDT", order_id="TIMEOUT-1",
                order_id_key="orderId", rid="RID-TIMEOUT",
            ),
        ]

        with patch(
            "apps.reference.domains.execution_position.flows.close.close_executor."
            "CancelSubmissionPayload.from_dec_cancel",
            wraps=CancelSubmissionPayload.from_dec_cancel,
        ) as wrapped:
            for dec in upstream_decisions:
                await executor.execute_cancel_order(dec)

        assert wrapped.call_count == len(upstream_decisions)
        assert cancel_spy.await_count == len(upstream_decisions)
        # All downstream calls canonicalized to (symbol, order_id) form.
        assert [c.args for c in cancel_spy.await_args_list] == [
            ("BTCUSDT", "TRAIL-1"),
            ("ETHUSDT", "SUPER-1"),
            ("SOLUSDT", "TIMEOUT-1"),
        ]


class TestCloseExecutorCancelTraces:

    @pytest.mark.asyncio
    async def test_success_trace_ref_logged_and_attached(self, caplog) -> None:
        fsm, _ = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = _dec_cancel_decision(rid="RID-SUCC")

        with caplog.at_level("INFO"):
            await executor.execute_cancel_order(decision)

        messages = "\n".join(caplog.messages)
        assert "CANCEL_SUBMISSION_SUCCESS" in messages
        assert f"contract={CANCEL_SUBMISSION_CONTRACT}" in messages
        success_ref = build_cancel_submission_trace_ref(status="success")
        assert success_ref in list(decision.data_ref)

    @pytest.mark.asyncio
    async def test_reject_trace_ref_logged_and_attached(self, caplog) -> None:
        fsm, cancel_spy = _build_fsm_with_spy()
        executor = CloseExecutor(fsm)
        decision = SimpleNamespace(
            op="DEC", verb="CANCEL_ORDER", rid="RID-REJ",
            pld={"symbol": "BTCUSDT"}, data_ref=[],
        )

        with caplog.at_level("ERROR"):
            await executor.execute_cancel_order(decision)

        messages = "\n".join(caplog.messages)
        assert "CANCEL_SUBMISSION_REJECT" in messages
        assert f"path={CANCEL_SUBMISSION_PATH}" in messages
        cancel_spy.assert_not_awaited()
        reject_ref = build_cancel_submission_trace_ref(
            status="reject", reason="adapter_validation"
        )
        assert reject_ref in list(decision.data_ref)


# ---------------------------------------------------------------------------
# Downstream ownership preservation (scope-discipline proof)
# ---------------------------------------------------------------------------


class TestDownstreamOwnershipUnchanged:
    """These tests assert that Phase 6 Package 4 did NOT touch downstream
    surfaces: ``ExecPosFSM._cancel_order``, ``IdempotentCancelHelper``, or
    the terminal outcome normalizer.
    """

    def test_idempotent_cancel_helper_unchanged(self) -> None:
        from apps.reference.domains.execution_position.guardian.idempotent_cancel import (
            IdempotentCancelHelper,
            IdempotentCancelResult,
        )

        # Public surface preserved.
        assert hasattr(IdempotentCancelHelper, "cancel_order_idempotent")
        assert hasattr(IdempotentCancelResult, "is_idempotent_success")

    def test_cancel_order_bridge_signature_unchanged(self) -> None:
        import inspect
        from apps.reference.domains.execution_position.fsm import ExecPosFSM

        sig = inspect.signature(ExecPosFSM._cancel_order)
        params = list(sig.parameters)
        assert params == ["self", "symbol", "order_id"]

    def test_terminal_order_contracts_unchanged(self) -> None:
        from apps.reference.domains.execution_position import terminal_order_contracts

        # Canonical public constants still exported.
        assert hasattr(terminal_order_contracts,
                       "TERMINAL_NON_FILL_STATUS_MAP")
        assert hasattr(terminal_order_contracts, "IDENTITY_EXACT")
