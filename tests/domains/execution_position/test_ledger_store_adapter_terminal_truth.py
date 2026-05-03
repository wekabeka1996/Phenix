from __future__ import annotations

from apps.reference.domains.execution_position.state.ledger_store_adapter import (
    LedgerStoreAdapter,
)
from apps.reference.domains.execution_position.state.order_ledger import (
    OrderLedger,
    OrderStatus,
)


def test_mark_order_terminal_updates_active_record() -> None:
    ledger = OrderLedger(":memory:")
    adapter = LedgerStoreAdapter(ledger)

    adapter.put(
        "order:2001",
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "client_order_id": "SL-2001",
            "kind": "SL",
            "status": "ACTIVE",
        },
    )

    before = ledger.get_order_by_order_id("2001")
    assert before is not None
    assert before.status == OrderStatus.ACTIVE

    changed = adapter.mark_order_terminal(
        order_id="2001",
        status="CANCELLED",
        reason="PRE_CHECK_NOT_FOUND",
        outcome_class="missing_order",
    )

    assert changed is True
    after = ledger.get_order_by_order_id("2001")
    assert after is not None
    assert after.status == OrderStatus.CANCELLED


def test_upsert_honors_terminal_status_and_client_fallback() -> None:
    ledger = OrderLedger(":memory:")
    adapter = LedgerStoreAdapter(ledger)

    adapter.put(
        "order:3001",
        {
            "symbol": "ETHUSDT",
            "side": "BUY",
            "type": "TAKE_PROFIT_MARKET",
            "client_order_id": "TP-3001",
            "kind": "TP",
            "status": "REJECTED",
        },
    )

    rec = ledger.get_order_by_order_id("3001")
    assert rec is not None
    assert rec.status == OrderStatus.REJECTED

    changed = adapter.mark_order_terminal(
        order_id="does-not-exist",
        client_order_id="TP-3001",
        status="EXPIRED",
        reason="cancel_reconcile",
        outcome_class="terminal_by_client",
    )

    assert changed is True
    rec_after = ledger.get_order_by_order_id("3001")
    assert rec_after is not None
    assert rec_after.status == OrderStatus.EXPIRED
