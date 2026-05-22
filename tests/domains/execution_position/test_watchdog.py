import json
import pytest
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

import jsonschema

from apps.reference.domains.execution_position.adapters.watchdog import (
    WATCHDOG_ORDER_STATE_CHANGED_WAL_WHY,
    OrderTimeoutWatchdog,
    OrderTimeoutType,
    OrderDeadline,
)
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from apps.reference.core.time import get_clock
from vfoundation.core.fsm_core import FSMCore
from vfoundation.dr import wal


@pytest.fixture
def watchdog():
    wd = OrderTimeoutWatchdog(
        config={"ack_ttl_ms": 1000, "fill_ttl_ms": 5000,
                "check_interval_ms": 100, "rps_limit": 5}
    )
    return wd


def test_watchdog_init_and_start_stop(watchdog):
    assert watchdog.ack_ttl_ms == 1000
    assert watchdog.fill_ttl_ms == 5000
    assert not watchdog._started

    # Start without loop should be deferred safely
    watchdog.start()
    assert not watchdog._started

    # Late start without loop should be deferred
    watchdog.ensure_started()
    assert not watchdog._started

    # Stop should be safe
    watchdog.stop()


@pytest.mark.asyncio
async def test_watchdog_start_with_loop(watchdog):
    watchdog.start()
    assert watchdog._started
    assert watchdog._watchdog_task is not None

    watchdog.stop()
    assert not watchdog._started
    await asyncio.sleep(0)  # let task cancel


@pytest.mark.asyncio
async def test_watchdog_disable(watchdog):
    watchdog.disable()
    assert not watchdog._enabled
    watchdog.start()
    assert not watchdog._started


def test_watchdog_track_and_ack(watchdog):
    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000

        watchdog.track_order_placed("o1", "c1", "BTCUSDT")
        assert "o1" in watchdog.pending_orders

        deadline = watchdog.pending_orders["o1"]
        assert deadline.timeout_type == OrderTimeoutType.ACK_TIMEOUT
        assert deadline.deadline_ms == 11000  # 10000 + 1000

        # Ack it
        watchdog.on_order_ack("o1")
        assert "o1" not in watchdog.pending_orders
        assert "o1" in watchdog.acked_orders

        ack_deadline = watchdog.acked_orders["o1"]
        assert ack_deadline.timeout_type == OrderTimeoutType.FILL_TIMEOUT
        assert ack_deadline.deadline_ms == 15000  # 10000 + 5000


def test_watchdog_track_override_ttl(watchdog):
    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000
        watchdog.track_order_placed(
            "o1", "c1", "BTCUSDT", fill_ttl_override_ms=20000)
        watchdog.on_order_ack("o1")
        # 10000 + 20000
        assert watchdog.acked_orders["o1"].deadline_ms == 30000


def test_watchdog_on_fill(watchdog):
    watchdog.pending_orders["o1"] = OrderDeadline(
        "o1", "c1", "BTCUSDT", 0, OrderTimeoutType.ACK_TIMEOUT)
    watchdog.acked_orders["o2"] = OrderDeadline(
        "o2", "c2", "BTCUSDT", 0, OrderTimeoutType.FILL_TIMEOUT)

    watchdog._poll_meta["o1"] = {}

    # Fill pending
    watchdog.on_order_fill("o1")
    assert "o1" not in watchdog.pending_orders
    assert "o1" not in watchdog._poll_meta

    # Fill acked
    watchdog.on_order_fill("o2")
    assert "o2" not in watchdog.acked_orders


def test_watchdog_on_cancel(watchdog):
    watchdog.pending_orders["o1"] = OrderDeadline(
        "o1", "c1", "BTCUSDT", 0, OrderTimeoutType.ACK_TIMEOUT)
    watchdog._poll_meta["o1"] = {}

    watchdog.on_order_cancel("o1")
    assert "o1" not in watchdog.pending_orders
    assert "o1" not in watchdog._poll_meta


@pytest.mark.asyncio
async def test_watchdog_timeout_handling(watchdog):
    cb = MagicMock()
    watchdog.on_timeout_callback = cb

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 20000

        # pending o1 expired at 10000
        watchdog.pending_orders["o1"] = OrderDeadline(
            "o1", "c1", "BTC", 10000, OrderTimeoutType.ACK_TIMEOUT)

        # acked o2 not expired at 30000
        watchdog.acked_orders["o2"] = OrderDeadline(
            "o2", "c2", "ETH", 30000, OrderTimeoutType.FILL_TIMEOUT)

        await watchdog._check_timeouts()

        # o1 should be removed
        assert "o1" not in watchdog.pending_orders
        assert "o2" in watchdog.acked_orders

        assert watchdog.timeout_count == 1
        cb.assert_called_once()
        assert cb.call_args[0][0].order_id == "o1"


@pytest.mark.asyncio
async def test_poll_order_statuses_filled(watchdog):
    get_order_fn = AsyncMock(return_value={
                             "status": "FILLED", "executedQty": "1.0", "avgPrice": "50000", "clientOrderId": "c1", "side": "BUY"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)

    watchdog.pending_orders["o1"] = OrderDeadline(
        "o1", "c1", "BTC", 30000, OrderTimeoutType.ACK_TIMEOUT, rid="rid-o1", side="BUY"
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000

        # Poll should happen because next_poll_at is 0
        await watchdog._poll_order_statuses()

        get_order_fn.assert_called_once_with("BTC", "o1")
        emit_fn.assert_called_once_with("EVT:TRADE_EXECUTED", {
            "orderId": "o1",
            "exchangeOrderId": "o1",
            "symbol": "BTC",
            "side": "buy",
            "quantity": "1.0",
            "qty": "1.0",
            "price": "50000",
            "status": "FILLED",
            "clientOrderId": "c1",
            "client_order_id": "c1",
            "rid": "rid-o1",
            "ts": 10000,
            "ts_ms": 10000,
            "venue": "binance",
        })

        # Should mark handled
        assert "o1" not in watchdog.pending_orders
        assert watchdog._poll_meta["o1"]["terminal"] is True


@pytest.mark.asyncio
async def test_poll_order_statuses_filled_without_emit_hook_keeps_tracking_for_retry(watchdog, caplog):
    get_order_fn = AsyncMock(return_value={
                             "status": "FILLED", "executedQty": "1.0", "avgPrice": "50000", "clientOrderId": "c1", "side": "BUY"})
    watchdog.set_hooks(get_order_fn, None)

    watchdog.acked_orders["o1"] = OrderDeadline(
        "o1", "c1", "BTC", 30000, OrderTimeoutType.FILL_TIMEOUT, rid="rid-o1", side="BUY"
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000

        with caplog.at_level("ERROR"):
            await watchdog._poll_order_statuses()

    assert "WATCHDOG_RECOVERED_FILL_CANONICAL_EMIT_FAILED" in caplog.text
    assert "o1" in watchdog.acked_orders
    assert watchdog._poll_meta["o1"]["attempts"] == 1
    assert watchdog._poll_meta["o1"].get("terminal") is not True


@pytest.mark.asyncio
async def test_poll_order_statuses_cancelled(watchdog):
    get_order_fn = AsyncMock(
        return_value={"status": "CANCELED", "clientOrderId": "c1"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)

    watchdog.acked_orders["o2"] = OrderDeadline(
        "o2", "c1", "BTC", 30000, OrderTimeoutType.FILL_TIMEOUT)

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000

        await watchdog._poll_order_statuses()

        emit_fn.assert_called_once_with("EVT:ORDER_STATE_CHANGED", {
            "orderId": "o2",
            "symbol": "BTC",
            "status": "CANCELED",
            "client_order_id": "c1",
            "rid": None,
            "clientOrderId": "c1",
            "order_id": "o2",
            "event_ts_ms": 10000,
            "ts_ms": 10000,
            "terminal_non_fill": True,
            "terminal_state_kind": "CANCELED",
            "identity_quality": "order_identity_exact",
            "canonical_identity_key": "evt:order_state_changed:symbol=BTC:order_id=o2:client_order_id=c1:terminal_state=CANCELED",
            "compatibility_aliases_retained": True,
        })

        assert "o2" not in watchdog.acked_orders
        assert watchdog._poll_meta["o2"]["terminal"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "terminal_state_kind", "test_id"),
    [
        ("CANCELED", "CANCELED", "cancelled"),
        ("REJECTED", "REJECTED", "rejected"),
        ("EXPIRED", "EXPIRED", "expired"),
    ],
    ids=lambda item: item if isinstance(item, str) else None,
)
async def test_poll_order_statuses_order_state_changed_writes_wal_before_emit(
    watchdog,
    status,
    terminal_state_kind,
    test_id,
):
    del test_id
    get_order_fn = AsyncMock(
        return_value={"status": status, "clientOrderId": "c1"})
    sequence = []
    wal_records = []

    async def emit_fn(event_name, payload):
        sequence.append(("emit", event_name, payload))

    def wal_append(record):
        sequence.append(("wal", record))
        wal_records.append(record)
        return "hash-1"

    watchdog.set_hooks(get_order_fn, emit_fn)
    watchdog.acked_orders["o2"] = OrderDeadline(
        "o2",
        "c1",
        "BTC",
        30000,
        OrderTimeoutType.FILL_TIMEOUT,
        rid="rid-o2",
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock, patch(
        "vfoundation.dr.wal.append", side_effect=wal_append
    ):
        mock_clock.return_value.now_ms.return_value = 10000

        await watchdog._poll_order_statuses()

    assert [step[0] for step in sequence] == ["wal", "emit"]
    assert len(wal_records) == 1
    wal_record = wal_records[0]
    assert wal_record["op"] == "EVT"
    assert wal_record["verb"] == "ORDER_STATE_CHANGED"
    assert wal_record["src"] == "execution_position"
    assert wal_record["dst"] == "monitoring"
    assert wal_record["rid"] == "rid-o2"
    assert wal_record["why"] == WATCHDOG_ORDER_STATE_CHANGED_WAL_WHY
    assert wal_record["pld"]["status"] == status
    assert wal_record["pld"]["symbol"] == "BTC"
    assert wal_record["pld"]["order_id"] == "o2"
    assert wal_record["pld"]["client_order_id"] == "c1"
    assert wal_record["pld"]["terminal_state_kind"] == terminal_state_kind

    emit_step = sequence[1]
    assert emit_step[1] == "EVT:ORDER_STATE_CHANGED"
    assert emit_step[2] == wal_record["pld"]
    assert "o2" not in watchdog.acked_orders
    assert watchdog._poll_meta["o2"]["terminal"] is True


@pytest.mark.asyncio
async def test_poll_order_statuses_order_state_changed_controlled_runtime_induction_writes_real_wal_and_shadow(
    watchdog,
    tmp_path,
):
    bus = FSMCore()
    shadow_path = tmp_path / "shadow_watchdog_controlled.jsonl"
    attach_shadow_journal(
        bus,
        SimpleNamespace(
            observability=SimpleNamespace(
                shadow_journal=SimpleNamespace(
                    enabled=True,
                    path=str(shadow_path),
                    schema_version="1.0.0",
                    instrumentation_version="1.0.0",
                    critical_events=list(DEFAULT_CRITICAL_EVENTS),
                )
            )
        ),
    )

    status_specs = [
        ("o-cancel", "c-cancel", "rid-cancel", "CANCELED", 10000),
        ("o-reject", "c-reject", "rid-reject", "REJECTED", 11000),
        ("o-expire", "c-expire", "rid-expire", "EXPIRED", 12000),
    ]
    rid_by_order_id = {order_id: rid for order_id,
                       _, rid, _, _ in status_specs}
    status_by_order_id = {
        order_id: {"status": status, "clientOrderId": client_order_id}
        for order_id, client_order_id, _, status, _ in status_specs
    }
    emitted = []

    async def emit_fn(event_name, payload):
        emitted.append((event_name, payload))
        bus.emit(
            event_name,
            payload,
            why=WATCHDOG_ORDER_STATE_CHANGED_WAL_WHY,
            rid=rid_by_order_id[payload["order_id"]],
        )

    watchdog.set_hooks(
        AsyncMock(side_effect=lambda symbol,
                  order_id: status_by_order_id[order_id]),
        emit_fn,
    )

    schema = json.loads(
        Path(
            "apps/reference/domains/execution_position/schemas/order_state_changed_v1.json"
        ).read_text(encoding="utf-8")
    )

    for order_id, client_order_id, rid, _, now_ms in status_specs:
        watchdog.acked_orders[order_id] = OrderDeadline(
            order_id,
            client_order_id,
            "BTCUSDT",
            30000,
            OrderTimeoutType.FILL_TIMEOUT,
            rid=rid,
        )

        with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
            mock_clock.return_value.now_ms.return_value = now_ms
            await watchdog._poll_order_statuses()

        assert order_id not in watchdog.acked_orders
        assert watchdog._poll_meta[order_id]["terminal"] is True

    wal_records = wal.read_all()
    assert len(wal_records) == 3
    assert wal.verify_chain(wal_records) is True
    assert wal_records[1]["_prev"] == wal_records[0]["_hash"]
    assert wal_records[2]["_prev"] == wal_records[1]["_hash"]

    seen_statuses = set()
    for record in wal_records:
        payload = record["pld"]
        seen_statuses.add(payload["status"])

        assert record["op"] == "EVT"
        assert record["verb"] == "ORDER_STATE_CHANGED"
        assert record["src"] == "execution_position"
        assert record["dst"] == "monitoring"
        assert record["why"] == WATCHDOG_ORDER_STATE_CHANGED_WAL_WHY
        assert record["rid"] == rid_by_order_id[payload["order_id"]]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["status"] in {"CANCELED", "REJECTED", "EXPIRED"}
        assert payload["order_id"]
        assert payload["client_order_id"]
        assert payload["canonical_identity_key"]
        assert payload["terminal_non_fill"] is True
        assert payload["compatibility_aliases_retained"] is True
        jsonschema.validate(payload, schema)

        assert record["_writer_pid"]
        assert record["_writer_process_name"]
        assert record["_writer_host"]
        assert record["_writer_lock_mode"]
        assert record["_wal_writer_version"] == "P11_B4_ATTRIBUTION_V1"

    assert seen_statuses == {"CANCELED", "REJECTED", "EXPIRED"}
    assert [event_name for event_name, _ in emitted] == [
        "EVT:ORDER_STATE_CHANGED",
        "EVT:ORDER_STATE_CHANGED",
        "EVT:ORDER_STATE_CHANGED",
    ]

    with shadow_path.open("r", encoding="utf-8") as fh:
        shadow_records = [json.loads(line) for line in fh if line.strip()]

    shadow_events = [
        record
        for record in shadow_records
        if record.get("event_name") == "EVT:ORDER_STATE_CHANGED"
    ]
    assert len(shadow_events) == 3

    for wal_record in wal_records:
        payload = wal_record["pld"]
        matches = [
            shadow_record
            for shadow_record in shadow_events
            if shadow_record.get("rid") == wal_record["rid"]
            and shadow_record.get("source_component") == "execution_position.watchdog"
            and shadow_record.get("event_origin_type") == "watchdog"
            and (shadow_record.get("payload_fragment") or {}).get("canonical_identity_key")
            == payload["canonical_identity_key"]
        ]
        assert len(matches) == 1
        fragment = matches[0]["payload_fragment"]
        assert fragment["status"] == payload["status"]
        assert fragment["terminal_non_fill"] is True
        assert fragment["terminal_state_kind"] == payload["terminal_state_kind"]


@pytest.mark.asyncio
async def test_poll_order_statuses_order_state_changed_logs_wal_append_failure_and_still_emits(
    watchdog,
    caplog,
):
    get_order_fn = AsyncMock(
        return_value={"status": "CANCELED", "clientOrderId": "c1"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)
    watchdog.acked_orders["o2"] = OrderDeadline(
        "o2",
        "c1",
        "BTC",
        30000,
        OrderTimeoutType.FILL_TIMEOUT,
        rid="rid-o2",
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock, patch(
        "vfoundation.dr.wal.append", return_value=None
    ):
        mock_clock.return_value.now_ms.return_value = 10000
        with caplog.at_level("WARNING"):
            await watchdog._poll_order_statuses()

    emit_fn.assert_called_once_with(
        "EVT:ORDER_STATE_CHANGED",
        {
            "orderId": "o2",
            "symbol": "BTC",
            "status": "CANCELED",
            "client_order_id": "c1",
            "rid": None,
            "clientOrderId": "c1",
            "order_id": "o2",
            "event_ts_ms": 10000,
            "ts_ms": 10000,
            "terminal_non_fill": True,
            "terminal_state_kind": "CANCELED",
            "identity_quality": "order_identity_exact",
            "canonical_identity_key": "evt:order_state_changed:symbol=BTC:order_id=o2:client_order_id=c1:terminal_state=CANCELED",
            "compatibility_aliases_retained": True,
        },
    )
    assert "WATCHDOG_ORDER_STATE_CHANGED_WAL_APPEND_FAILED" in caplog.text
    assert "symbol=BTC" in caplog.text
    assert "order_id=o2" in caplog.text
    assert "status=CANCELED" in caplog.text
    assert "rid=rid-o2" in caplog.text


@pytest.mark.asyncio
async def test_poll_order_statuses_backoff(watchdog):
    get_order_fn = AsyncMock(return_value={"status": "NEW"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)

    watchdog.pending_orders["o1"] = OrderDeadline(
        "o1", "c1", "BTC", 30000, OrderTimeoutType.ACK_TIMEOUT)

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000

        await watchdog._poll_order_statuses()

        assert watchdog._poll_meta["o1"]["attempts"] == 1
        assert watchdog._poll_meta["o1"]["backoff_ms"] == 2000
        assert watchdog._poll_meta["o1"]["next_poll_at"] == 12000

        # Immediate second poll should be skipped due to backoff
        get_order_fn.reset_mock()
        await watchdog._poll_order_statuses()
        assert get_order_fn.call_count == 0


@pytest.mark.asyncio
async def test_poll_order_statuses_rps_limit(watchdog):
    get_order_fn = AsyncMock(return_value={"status": "NEW"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)

    # We set rps_limit = 2 for tracking
    watchdog._rps_limit = 2

    watchdog.pending_orders["o1"] = OrderDeadline(
        "o1", "c1", "BTC", 30000, OrderTimeoutType.ACK_TIMEOUT)
    watchdog.pending_orders["o2"] = OrderDeadline(
        "o2", "c2", "ETH", 30000, OrderTimeoutType.ACK_TIMEOUT)
    watchdog.pending_orders["o3"] = OrderDeadline(
        "o3", "c3", "LTC", 30000, OrderTimeoutType.ACK_TIMEOUT)

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10500  # within same second

        await watchdog._poll_order_statuses()

        # Only 2 out of 3 should have been polled
        assert get_order_fn.call_count == 2
        assert watchdog._rps_throttle_hits == 1
