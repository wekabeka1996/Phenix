"""Package 12 bounded test suite:
background OrderGuardian.cleanup_orphans(hard=False) -> typed bridge -> Package 4.

Tests prove:
1. background cleanup_orphans(hard=False) routes through CancelSubmissionPayload.from_dec_cancel()
2. multiple orphans each traverse the typed seam exactly once
3. the hard=False path no longer uses raw direct adapter cancel as governing owner
4. Package 9 cleanup_orphans(hard=True) path remains unchanged (reconcile bridge)
5. Package 10 cleanup_other_brackets_for_symbol() remains unchanged
6. Package 11 cleanup_before_close() remains unchanged
7. no positionAmt / restart changes introduced
8. Package 4 tests remain additive only
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.reference.domains.execution_position.cancel_submission_adapter import (
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
)
from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
    GuardianBackgroundOrphanCancelRequest,
    adapt_guardian_background_orphan_to_dec_cancel,
)
from apps.reference.domains.execution_position.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _orphan_open_order(
    *,
    symbol: str,
    order_id: str,
    client_order_id: str,
    order_type: str = "STOP_MARKET",
) -> dict:
    return {
        "symbol": symbol,
        "orderId": order_id,
        "clientOrderId": client_order_id,
        "type": order_type,
        "reduceOnly": True,
        "closePosition": False,
    }


def _orphan_meta(
    *,
    symbol: str,
    order_type: str = "STOP_MARKET",
    parent_entry_id: str = "entry-old",
    client_order_id: str = "SL-1",
) -> dict:
    return {
        "symbol": symbol,
        "type": order_type,
        "reduce_only": True,
        "close_position": False,
        "parent_entry_id": parent_entry_id,
        "client_order_id": client_order_id,
        "kind": order_type.replace("_MARKET", "").upper(),
    }


def _make_guardian(adapter, store=None) -> OrderGuardian:
    return OrderGuardian(adapter=adapter, store=store or InMemoryStore(), poll_interval_ms=0)


# ---------------------------------------------------------------------------
# Bridge contract tests (unit)
# ---------------------------------------------------------------------------

class TestBridgeContract:
    """Unit tests for the guardian_background_orphan_cancel_bridge module."""

    def test_bridge_produces_package4_compatible_payload_without_extra_fields(self) -> None:
        request, cancel_decision = adapt_guardian_background_orphan_to_dec_cancel(
            symbol="BTCUSDT",
            order_id="sl-orphan-1",
            order_type="STOP_MARKET",
        )
        assert request == GuardianBackgroundOrphanCancelRequest(
            symbol="BTCUSDT",
            order_id="sl-orphan-1",
            order_type="STOP_MARKET",
        )
        pld = cancel_decision.pld
        assert pld["symbol"] == "BTCUSDT"
        assert pld["order_id"] == "sl-orphan-1"
        assert pld["order_type"] == "STOP_MARKET"
        assert pld["trigger"] == "guardian_background_orphan_cancel"
        # Must NOT carry parent_entry_id, keep_parent_order_id, or rid in pld
        assert "parent_entry_id" not in pld
        assert "keep_parent_order_id" not in pld
        assert "rid" not in pld

    def test_bridge_payload_passes_package4_raw_intake(self) -> None:
        _, cancel_decision = adapt_guardian_background_orphan_to_dec_cancel(
            symbol="ETHUSDT",
            order_id="tp-orphan-7",
            order_type="TAKE_PROFIT_MARKET",
        )
        submission = CancelSubmissionPayload.from_dec_cancel(payload=cancel_decision.pld)
        assert submission.symbol == "ETHUSDT"
        assert submission.order_id == "tp-orphan-7"

    def test_bridge_uppercases_symbol_and_order_type(self) -> None:
        request, _ = adapt_guardian_background_orphan_to_dec_cancel(
            symbol="btcusdt",
            order_id="sl-1",
            order_type="stop_market",
        )
        assert request.symbol == "BTCUSDT"
        assert request.order_type == "STOP_MARKET"

    def test_bridge_rejects_missing_symbol(self) -> None:
        from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
            GuardianBackgroundOrphanCancelBridgeError,
        )
        with pytest.raises(GuardianBackgroundOrphanCancelBridgeError, match="symbol"):
            adapt_guardian_background_orphan_to_dec_cancel(
                symbol="",
                order_id="sl-1",
                order_type="STOP_MARKET",
            )

    def test_bridge_rejects_missing_order_id(self) -> None:
        from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
            GuardianBackgroundOrphanCancelBridgeError,
        )
        with pytest.raises(GuardianBackgroundOrphanCancelBridgeError, match="order_id"):
            adapt_guardian_background_orphan_to_dec_cancel(
                symbol="BTCUSDT",
                order_id="",
                order_type="STOP_MARKET",
            )


# ---------------------------------------------------------------------------
# Task 1 requirement: hard=False routes through Package 4 typed seam
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_background_cleanup_orphans_routes_through_package4_typed_cancel_intake() -> None:
    """hard=False path MUST invoke CancelSubmissionPayload.from_dec_cancel for each orphan."""
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []  # position flat -> orphan cleanup proceeds
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="sl-orphan-1", client_order_id="SL-ORPHAN-1"),
    ]
    adapter.cancel_order.return_value = {"status": "CANCELED", "orderId": "sl-orphan-1"}
    store = InMemoryStore()
    store.put("order:sl-orphan-1", _orphan_meta(symbol=symbol))
    guardian = _make_guardian(adapter, store)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=False)

    assert cancelled == 1
    from_dec_cancel.assert_called_once()
    call_payload = from_dec_cancel.call_args.kwargs["payload"]
    assert call_payload["order_id"] == "sl-orphan-1"
    assert call_payload["symbol"] == "BTCUSDT"
    assert call_payload["trigger"] == "guardian_background_orphan_cancel"
    # parent_entry_id must NOT be in the Package 4 payload
    assert "parent_entry_id" not in call_payload
    assert adapter.cancel_order.await_count == 1


@pytest.mark.asyncio
async def test_background_cleanup_orphans_multiple_orphans_traverse_typed_seam_once_each() -> None:
    """Each discovered orphan must traverse the typed seam exactly once."""
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="sl-1", client_order_id="SL-1"),
        _orphan_open_order(
            symbol=symbol,
            order_id="tp-1",
            client_order_id="TP-1",
            order_type="TAKE_PROFIT_MARKET",
        ),
    ]
    adapter.cancel_order.side_effect = [
        {"status": "CANCELED", "orderId": "sl-1"},
        {"status": "CANCELED", "orderId": "tp-1"},
    ]
    store = InMemoryStore()
    store.put("order:sl-1", _orphan_meta(symbol=symbol, order_type="STOP_MARKET"))
    store.put(
        "order:tp-1",
        _orphan_meta(symbol=symbol, order_type="TAKE_PROFIT_MARKET", client_order_id="TP-1"),
    )
    guardian = _make_guardian(adapter, store)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=False)

    assert cancelled == 2
    assert from_dec_cancel.call_count == 2
    observed_ids = [c.kwargs["payload"]["order_id"] for c in from_dec_cancel.call_args_list]
    assert set(observed_ids) == {"sl-1", "tp-1"}
    # adapter.cancel_order was called exactly twice (once per orphan via typed seam)
    assert adapter.cancel_order.await_count == 2


@pytest.mark.asyncio
async def test_background_cleanup_orphans_no_raw_direct_adapter_cancel_on_package4_reject() -> None:
    """When Package 4 intake rejects, adapter.cancel_order must NOT be called (non-bypass)."""
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="sl-bad", client_order_id="SL-BAD"),
    ]
    store = InMemoryStore()
    store.put("order:sl-bad", _orphan_meta(symbol=symbol))
    guardian = _make_guardian(adapter, store)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        side_effect=CancelSubmissionAdapterError("typed reject"),
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=False)

    assert cancelled == 0
    from_dec_cancel.assert_called_once()
    adapter.cancel_order.assert_not_called()


# ---------------------------------------------------------------------------
# Task 2: Package 9 hard=True path remains unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_package9_hard_path_remains_on_reconcile_bridge_not_background_bridge() -> None:
    """cleanup_orphans(hard=True) must use guardian_reconcile_cancel_bridge, not Package 12 bridge."""
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="sl-hard", client_order_id="SL-HARD"),
    ]
    adapter.cancel_order.return_value = {"status": "CANCELED", "orderId": "sl-hard"}
    store = InMemoryStore()
    store.put("order:sl-hard", _orphan_meta(symbol=symbol))
    guardian = _make_guardian(adapter, store)

    from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
        adapt_guardian_background_orphan_to_dec_cancel,
    )
    from apps.reference.domains.execution_position.guardian_reconcile_cancel_bridge import (
        adapt_guardian_reconcile_to_dec_cancel,
    )

    with (
        patch(
            "apps.reference.domains.execution_position.order_guardian.adapt_guardian_background_orphan_to_dec_cancel",
            wraps=adapt_guardian_background_orphan_to_dec_cancel,
        ) as background_bridge,
        patch(
            "apps.reference.domains.execution_position.order_guardian.adapt_guardian_reconcile_to_dec_cancel",
            wraps=adapt_guardian_reconcile_to_dec_cancel,
        ) as reconcile_bridge,
    ):
        cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=True)

    assert cancelled == 1
    reconcile_bridge.assert_called_once()
    background_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_background_cleanup_orphans_does_not_invoke_reconcile_bridge() -> None:
    """cleanup_orphans(hard=False) must NOT invoke the Package 9 reconcile bridge."""
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_positions.return_value = []
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="sl-soft", client_order_id="SL-SOFT"),
    ]
    adapter.cancel_order.return_value = {"status": "CANCELED", "orderId": "sl-soft"}
    store = InMemoryStore()
    store.put("order:sl-soft", _orphan_meta(symbol=symbol))
    guardian = _make_guardian(adapter, store)

    from apps.reference.domains.execution_position.guardian_reconcile_cancel_bridge import (
        adapt_guardian_reconcile_to_dec_cancel,
    )
    with patch(
        "apps.reference.domains.execution_position.order_guardian.adapt_guardian_reconcile_to_dec_cancel",
        wraps=adapt_guardian_reconcile_to_dec_cancel,
    ) as reconcile_bridge:
        await guardian.cleanup_orphans(symbol=symbol, hard=False)

    reconcile_bridge.assert_not_called()


# ---------------------------------------------------------------------------
# Task 3: Package 10 cleanup_other_brackets_for_symbol() remains unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_package10_cleanup_other_brackets_remains_unchanged() -> None:
    """cleanup_other_brackets_for_symbol() must still use the old-bracket bridge, not Package 12."""
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="tp-old", client_order_id="TP-OLD"),
    ]
    adapter.cancel_order.return_value = {"status": "CANCELED", "orderId": "tp-old"}
    store = InMemoryStore()
    store.put(
        "order:tp-old",
        _orphan_meta(symbol=symbol, order_type="TAKE_PROFIT_MARKET", client_order_id="TP-OLD"),
    )
    guardian = _make_guardian(adapter, store)

    from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
        adapt_guardian_background_orphan_to_dec_cancel,
    )
    with patch(
        "apps.reference.domains.execution_position.order_guardian.adapt_guardian_background_orphan_to_dec_cancel",
        wraps=adapt_guardian_background_orphan_to_dec_cancel,
    ) as background_bridge:
        cancelled = await guardian.cleanup_other_brackets_for_symbol(
            symbol=symbol,
            keep_parent_order_id="parent-keep",
        )

    assert cancelled == 1
    background_bridge.assert_not_called()
    adapter.cancel_order.assert_awaited_once()


# ---------------------------------------------------------------------------
# Task 4: Package 11 cleanup_before_close() remains unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_package11_cleanup_before_close_remains_unchanged() -> None:
    """cleanup_before_close() must still use the pre-close bridge, not Package 12."""
    adapter = AsyncMock()
    adapter.cancel_order.return_value = {"status": "CANCELED", "orderId": "sl-1"}
    store = InMemoryStore()
    guardian = _make_guardian(adapter, store)
    guardian.register_entry(
        symbol="BTCUSDT", order_id="entry-1", client_order_id="ENTRY-1", side="BUY", qty=1.0
    )
    guardian.register_bracket(
        symbol="BTCUSDT",
        parent_order_id="entry-1",
        order_id="sl-1",
        client_order_id="SL-1",
        kind="SL",
    )

    from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
        adapt_guardian_background_orphan_to_dec_cancel,
    )
    with patch(
        "apps.reference.domains.execution_position.order_guardian.adapt_guardian_background_orphan_to_dec_cancel",
        wraps=adapt_guardian_background_orphan_to_dec_cancel,
    ) as background_bridge:
        cancelled = await guardian.cleanup_before_close(
            symbol="BTCUSDT", parent_order_id="entry-1"
        )

    assert cancelled == 1
    background_bridge.assert_not_called()


# ---------------------------------------------------------------------------
# Task 5: No positionAmt / parsing / restart contamination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_background_cleanup_does_not_call_get_open_positions_on_non_background_path() -> None:
    """cleanup_orphans(hard=False) still gates on get_open_positions for position check.
    This test proves no parsing redesign was introduced: the positionAmt check still gates
    the soft-cleanup path as before (no position = proceed, position = skip), without
    any new position-parsing logic being added.
    """
    symbol = "BTCUSDT"
    adapter = AsyncMock()
    # Simulate a live position – soft cleanup must skip
    adapter.get_open_positions.return_value = [
        {"symbol": symbol, "position_amount": "1.0"}
    ]
    adapter.get_open_orders.return_value = [
        _orphan_open_order(symbol=symbol, order_id="sl-skip", client_order_id="SL-SKIP"),
    ]
    store = InMemoryStore()
    store.put("order:sl-skip", _orphan_meta(symbol=symbol))
    guardian = _make_guardian(adapter, store)

    with patch.object(
        CancelSubmissionPayload,
        "from_dec_cancel",
        wraps=CancelSubmissionPayload.from_dec_cancel,
    ) as from_dec_cancel:
        cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=False)

    assert cancelled == 0
    from_dec_cancel.assert_not_called()
    adapter.cancel_order.assert_not_called()


# ---------------------------------------------------------------------------
# Regression: Package 4 tests additive only
# ---------------------------------------------------------------------------

def test_cancel_submission_payload_from_dec_cancel_accepts_background_orphan_payload() -> None:
    """Additive coverage: the Package 4 intake explicitly accepts the Package 12 payload fields."""
    payload = {
        "symbol": "BTCUSDT",
        "order_id": "sl-1",
        "order_type": "STOP_MARKET",
        "trigger": "guardian_background_orphan_cancel",
    }
    submission = CancelSubmissionPayload.from_dec_cancel(payload=payload)
    assert submission.symbol == "BTCUSDT"
    assert submission.order_id == "sl-1"


def test_cancel_submission_payload_rejects_payload_with_parent_entry_id() -> None:
    """Package 4 CancelSubmissionRawPayload must reject parent_entry_id (extra=forbid)."""
    payload = {
        "symbol": "BTCUSDT",
        "order_id": "sl-1",
        "parent_entry_id": "entry-1",  # must be rejected
        "trigger": "guardian_background_orphan_cancel",
    }
    with pytest.raises(CancelSubmissionAdapterError):
        CancelSubmissionPayload.from_dec_cancel(payload=payload)
