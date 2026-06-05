"""
Tests for CMD:EXTERNAL_OPEN_REQUEST_V1 listener wiring in ExecPosFSM.

Proves: LISTENER_NOT_REGISTERED break (FORENSIC_REPORT_LLM_INTENT_PATH.md)
is fixed — the event reaches IntentRouter.on_external_open_request().
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from vfoundation.core.protocol import Message


# ---------------------------------------------------------------------------
# Dispatching bus: actually routes emit → registered listeners
# ---------------------------------------------------------------------------
class _DispatchingBus:
    def __init__(self):
        self.listeners: dict[str, list] = {}
        self.events: list[tuple[str, dict, str | None, object]] = []

    def listen(self, topic: str, handler) -> None:
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic: str, payload=None, why=None, data_ref=None,
             **kwargs) -> None:
        payload_dict = payload or {}
        self.events.append((topic, payload_dict, why, data_ref))
        for handler in self.listeners.get(topic, []):
            msg = Message(
                op=topic.split(":")[0] if ":" in topic else "EVT",
                verb=topic.split(":", 1)[1] if ":" in topic else topic,
                src="test",
                dst="execution_position",
                rid=payload_dict.get("rid", "test-rid"),
                pld=payload_dict,
                why=why,
                data_ref=data_ref if data_ref is not None else [],
            )
            handler(msg)


def _make_fsm_with_dispatching_bus():
    """Build ExecPosFSM with a bus that actually dispatches to listeners."""
    from tests.domains.execution_position.conftest import fsm_config
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    cfg = fsm_config.__wrapped__() if hasattr(fsm_config, "__wrapped__") else fsm_config()
    bus = _DispatchingBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.is_duplicate.return_value = False
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)
        fsm.order_guardian = mock_guardian
    return fsm, bus, cfg


# ---------------------------------------------------------------------------
# Test 1: Listener registration exists
# ---------------------------------------------------------------------------
def test_external_open_request_listener_registered():
    """CMD:EXTERNAL_OPEN_REQUEST_V1 must have a registered listener on the bus."""
    _fsm, bus, _ = _make_fsm_with_dispatching_bus()
    assert "CMD:EXTERNAL_OPEN_REQUEST_V1" in bus.listeners, (
        "LISTENER_NOT_REGISTERED: CMD:EXTERNAL_OPEN_REQUEST_V1 has no consumer"
    )
    assert len(bus.listeners["CMD:EXTERNAL_OPEN_REQUEST_V1"]) == 1


# ---------------------------------------------------------------------------
# Test 2: Dispatched event reaches on_external_open_request (reject path)
# ---------------------------------------------------------------------------
def test_external_open_request_reaches_intent_router_gate_reject():
    """
    Emit CMD:EXTERNAL_OPEN_REQUEST_V1 with missing intent_id.
    Proves the handler IS invoked and rejects at GATE 1.
    """
    fsm, bus, _ = _make_fsm_with_dispatching_bus()

    bus.emit("CMD:EXTERNAL_OPEN_REQUEST_V1", {
        "rid": "rid-test-001",
        "symbol": "1000PEPEUSDT",
        "side": "SELL",
        "qty": "1.5",
        "source": "external_llm",
        "order_type": "LIMIT",
        "tif": "GTC",
        "price": "0.003406",
        # intent_id deliberately missing → GATE 1 reject
    }, why="test_gate_reject")

    # The rejection event must appear on the bus
    reject_events = [
        (t, p) for t, p, w, d in bus.events
        if t == "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1"
    ]
    assert len(reject_events) == 1, (
        f"Expected 1 rejection event, got {len(reject_events)}. "
        f"All events: {[t for t, *_ in bus.events]}"
    )
    assert reject_events[0][1]["reason_code"] == "NRR-EXT-MISSING-INTENT-ID"


# ---------------------------------------------------------------------------
# Test 3: Dispatched event reaches CMD:OPEN on success path
# ---------------------------------------------------------------------------
def test_external_open_request_reaches_cmd_open():
    """
    Emit CMD:EXTERNAL_OPEN_REQUEST_V1 with valid payload.
    Proves the handler invokes fsm.handle() with CMD:OPEN.
    """
    fsm, bus, cfg = _make_fsm_with_dispatching_bus()

    # Set up config for GATE 6 (valid_for_ms fallback)
    cfg.strategies.llm_microstructure.pending_entry_ttl_ms = 30000

    # Intercept handle() to capture the CMD:OPEN
    captured_cmds = []
    original_handle = fsm.handle

    def _capturing_handle(cmd: Message) -> Message:
        captured_cmds.append(cmd)
        return Message(
            op="DEC", verb="OPEN", src="execution_position",
            dst="execution_position", rid=cmd.rid,
            pld={"symbol": cmd.pld.get("symbol")},
            why="OPEN_OK", data_ref=cmd.data_ref,
        )

    fsm.handle = _capturing_handle

    bus.emit("CMD:EXTERNAL_OPEN_REQUEST_V1", {
        "rid": "rid-test-002",
        "intent_id": "intent-abc-123",
        "symbol": "1000PEPEUSDT",
        "side": "SELL",
        "qty": "1.5",
        "source": "external_llm",
        "order_type": "LIMIT",
        "tif": "GTC",
        "price": "0.003406",
        "valid_for_ms": 30000,
        "idempotent_key": "idem-ext-001",
    }, why="test_success_path")

    # CMD:OPEN must have been built and passed to handle()
    assert len(captured_cmds) == 1, (
        f"Expected 1 CMD:OPEN, got {len(captured_cmds)}"
    )
    cmd = captured_cmds[0]
    assert cmd.op == "CMD"
    assert cmd.verb == "OPEN"
    assert cmd.rid == "rid-test-002"
    assert cmd.pld["symbol"] == "1000PEPEUSDT"
    assert cmd.pld["side"] == "SELL"
    assert cmd.pld["strategy"] == "llm_microstructure"
    assert cmd.pld["metadata"]["source"] == "external_llm"
    assert cmd.pld["metadata"]["source_intent_id"] == "intent-abc-123"

    # No reject events must be present
    reject_events = [
        t for t, *_ in bus.events
        if t == "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1"
    ]
    assert reject_events == [], f"Unexpected rejections: {reject_events}"


# ---------------------------------------------------------------------------
# Test 4: Source provenance preserved — no fallback to DM path
# ---------------------------------------------------------------------------
def test_external_open_request_does_not_use_dm_reject_verb():
    """
    On gate failure, the reject verb must be EXTERNAL_OPEN_REQUEST_REJECTED_V1,
    NOT EVT:TRADE_INTENT_REJECTED (which belongs to decision_making path).
    """
    fsm, bus, _ = _make_fsm_with_dispatching_bus()

    bus.emit("CMD:EXTERNAL_OPEN_REQUEST_V1", {
        "rid": "rid-test-003",
        "intent_id": "intent-xyz",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.01",
        "source": "wrong_source",  # GATE 2 fail
        "order_type": "LIMIT",
        "tif": "GTC",
        "price": "50000",
    }, why="test_provenance")

    dm_rejects = [t for t, *_ in bus.events if t == "EVT:TRADE_INTENT_REJECTED"]
    ext_rejects = [t for t, *_ in bus.events if t == "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1"]

    assert dm_rejects == [], "Must NOT emit DM-path reject verb"
    assert len(ext_rejects) == 1, "Must emit external-specific reject verb"
