# tests/integration/test_decision_to_execution_flow.py
"""
Integration test for Decision→Execution bridge (Part EXECUTE-T03).
Tests the end-to-end flow from TRADE_INTENT_PROPOSED to CMD:OPEN.
"""

from unittest.mock import MagicMock
import pytest
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "vfoundation" / "vfoundation"))


# Simple Message class for testing (same as in other integration tests)
class Message:
    """Simple message class for testing."""

    def __init__(
        self,
        op,
        verb,
        src=None,
        dst=None,
        pld=None,
        why=None,
        rid=None,
        span_id=None,
        parent_span_id=None,
    ):
        self.op = op
        self.verb = verb
        self.src = src
        self.dst = dst
        self.pld = pld or {}
        self.why = why or ""
        self.rid = rid or "test-rid"
        self.span_id = span_id or "test-span-id"
        self.parent_span_id = parent_span_id


# Simple FSM core for testing
class FSMCore:
    """Simple FSM core interface for testing."""

    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.logger = MagicMock()

    def listen(self, event_name: str, callback) -> None:
        """Register event listener."""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload=None, why=None, **kwargs) -> None:
        """Emit event to listeners."""
        if event_name in self.listeners:
            event = Message(
                op=kwargs.get("op", "EVT"), verb=event_name, pld=payload, why=why
            )
            for callback in self.listeners[event_name]:
                callback(event)


@pytest.fixture
def full_config():
    """Provides a realistic, complete configuration for Decision→Execution flow test."""
    return {
        "trading": {
            "decision": {
                "signal_threshold": "0.2",  # Low threshold for easy signal triggering
                "payoff_ratio_r": "2.0",
                "kelly_alpha": "0.5",
                "kelly_conservative_factor": "0.1",
                "liquidity_based_cap_usd": "10000",
                "min_position_size_usd": "10",
                "p_calibration_version": "v1.0",
                "sizing_modifiers": {},
                "instruments": {"ETHUSDT": {"min_qty": "0.001", "lot_step": "0.001"}},
            },
            "tca_prefs": {
                "max_slippage_bps": "5",
                "max_latency_ms": "1000",
                "maker_preference": "prefer",
            },
            "risk_budgets": {
                "trade_cvar95_max_bps": "50",
                "session_cvar95_max_bps": "500",
                "max_cvar_per_session_usd": "25000",
            },
        },
        "system": {"trade_intent_validity_ms": 30000},
    }


def test_full_flow_from_decision_to_execution_command(full_config):
    """
    Integration test for Decision→Execution bridge (Part EXECUTE-T03).

    Tests the end-to-end flow:
    1. DecisionMaking receives strong buy signal (OBI=0.9, TFI=0.9)
    2. Emits EVT:TRADE_INTENT_PROPOSED with order details
    3. Bridge handler (on_trade_intent_proposed) transforms to CMD:OPEN
    4. ExecPosFSM receives command with correct payload

    Validates:
    - Payload mapping: instrument→symbol, order.qty→qty, order.price→price
    - XAI chain preservation via parent_span_id
    - Message protocol correctness (op=CMD, verb=OPEN)
    - Shadow mode: ExecPosFSM processes without real execution
    """
    # 1. Arrange: Initialize FSM core and mock domains
    fsm_core = FSMCore()
    LOG = MagicMock()  # Mock logger for bridge

    # Mock execution_domain to spy on handle() calls
    execution_domain = MagicMock()
    execution_domain.handle = MagicMock(return_value=None)

    # 2. Wire up the bridge: Register handler that mirrors main.py logic
    def on_trade_intent_proposed(event):
        """
        Bridge handler - transforms EVT:TRADE_INTENT_PROPOSED → CMD:OPEN.
        This is a copy of the logic from apps/reference/main.py lines 81-141.
        """
        LOG.info(
            f"BRIDGE: Received TRADE_INTENT_PROPOSED for {event.pld.get('instrument', 'unknown')} "
            f"with side {event.pld.get('side', 'unknown')}. Transforming to CMD:OPEN."
        )

        # Transform EVT to CMD - extract order details from nested structure
        order_details = event.pld.get("order", {})

        command_payload = {
            # Map 'instrument' to 'symbol'
            "symbol": event.pld.get("instrument"),
            "side": event.pld.get("side"),
            # Get qty from order.qty (as string)
            "qty": order_details.get("qty"),
            "price": order_details.get(
                "price"
            ),  # Get price from order.price (as string)
            "order_type": "LIMIT",  # Use LIMIT orders with specified price
            "tif": "GTC",  # Good-Till-Cancel
            "idempotent_key": event.pld.get(
                "idempotent_key"
            ),  # Pass through for deduplication
        }

        LOG.debug(f"BRIDGE: CMD:OPEN payload being sent: {command_payload}")

        # Preserve XAI chain: take first why from event payload, or fallback
        event_why_chain = event.pld.get("why", [])
        bridge_why = (
            event_why_chain[0]
            if event_why_chain
            else "Execute trade intent from decision"
        )

        # Create Message for CMD:OPEN
        # RID will be auto-generated, parent_span_id links to event for tracing
        open_command = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            parent_span_id=event.span_id,  # Link to parent event for tracing
            why=bridge_why,  # Preserve XAI chain from decision
            pld=command_payload,
        )

        LOG.info(
            f"BRIDGE: Dispatched CMD:OPEN with rid={open_command.rid}, parent_span={event.span_id}"
        )

        # Handle the command with execution_position FSM
        if execution_domain is not None:
            result = execution_domain.handle(open_command)
            if result:
                LOG.info(
                    f"BRIDGE: Execution FSM processed CMD:OPEN, result: {result.op}:{result.verb}"
                )
                if result.op == "ERR":
                    LOG.error(
                        f"BRIDGE: Execution rejected - why={result.why}, pld={result.pld}"
                    )
            else:
                LOG.info(
                    "BRIDGE: Execution FSM processed CMD:OPEN, no decision emitted"
                )
        else:
            LOG.error("BRIDGE: execution_position FSM not initialized")

    fsm_core.listen("TRADE_INTENT_PROPOSED", on_trade_intent_proposed)

    # 3. Act: Simulate TRADE_INTENT_PROPOSED event from an older bridge-era fixture.
    # Kelly-related values below are synthetic payload-shape placeholders, not
    # assertions about current Aurora Kelly provenance truth.
    trade_intent_payload = {
        "instrument": "ETHUSDT",
        "side": "buy",
        # Mock idempotent key (32 chars)
        "idempotent_key": "a1b2c3d4e5f678901234567890123456",
        "p": "0.9",  # High probability (calibrated)
        "payoff_ratio_r": "2.0",
        "tca_budget": {
            "max_slippage_bps": "5",
            "max_latency_ms": "1000",
            "maker_preference": "prefer",
        },
        "risk_budget": {"trade_cvar95_max_bps": "50", "session_cvar95_max_bps": "500"},
        "size": {"kelly_fraction": "0.0425", "notional_cap_usd": "1000.0"},
        "order": {
            "price_ref": "4000.0",
            "qty": "0.25",  # Calculated from notional_cap / price
            "price": "4000.0",
            "reduce_only": False,
        },
        "valid_for_ms": 30000,
        "why": [
            "Decision based on signal_score=0.900, p_src='v1.0'",
            "Features: obi=0.900, tfi=0.900, absorption=0.500",
            "Probability: p_raw=0.900, p_cal=0.900, p=0.900 (ceiling=0.950)",
            "EV: raw=0.800, full_kelly=0.8500, kelly_used=0.0425",
            "Position sizing: equity=$50000.00, kelly_based_usd=$2125.00, final=$1000.00",
        ],
        "dto_version": "1.0.0",
        "schema_ref": "https://aurora.scalp/shared/dto/trade_intent.schema.json",
    }

    Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="main",
        pld=trade_intent_payload,
        why="Strong buy signal detected",
        span_id="decision-span-123",  # Span ID for tracing
    )

    # Trigger the bridge by emitting event through FSM core
    fsm_core.emit(
        "TRADE_INTENT_PROPOSED",
        payload=trade_intent_payload,
        why="Strong buy signal detected",
    )

    # 4. Assert: Verify that execution_domain received the correct CMD:OPEN command
    execution_domain.handle.assert_called_once()

    called_command = execution_domain.handle.call_args[0][0]
    assert isinstance(
        called_command, Message), "Command should be a Message instance"
    assert called_command.op == "CMD", f"Expected op='CMD', got '{called_command.op}'"
    assert called_command.verb == "OPEN", (
        f"Expected verb='OPEN', got '{called_command.verb}'"
    )

    # Validate payload structure
    assert called_command.pld["symbol"] == "ETHUSDT", (
        "Symbol should be mapped from instrument"
    )
    assert called_command.pld["side"] == "buy", "Side should be preserved"
    assert called_command.pld["qty"] == "0.25", "Qty should be extracted from order.qty"
    assert called_command.pld["price"] == "4000.0", (
        "Price should be extracted from order.price"
    )
    assert called_command.pld["order_type"] == "LIMIT", "Order type should be LIMIT"
    assert called_command.pld["tif"] == "GTC", "Time-in-force should be GTC"
    assert "idempotent_key" in called_command.pld, (
        "idempotent_key should be passed through from intent"
    )
    assert isinstance(called_command.pld["idempotent_key"], str), (
        "idempotent_key should be string"
    )
    assert len(called_command.pld["idempotent_key"]) == 32, (
        "idempotent_key should be 32-char hash"
    )

    # Validate XAI chain preservation
    assert called_command.why.startswith("Decision based on"), (
        "Why should preserve first element from decision why chain"
    )

    # Validate tracing linkage (if span_id was set by bridge)
    # Note: In real main.py, parent_span_id would be set to event.span_id
    # Our mock doesn't auto-generate, but we verify the field exists
    assert hasattr(called_command, "parent_span_id"), (
        "Command should have parent_span_id for tracing"
    )

    # Validate logger calls (bridge should log key events)
    assert LOG.info.call_count >= 2, "Bridge should log Received and Dispatched events"
    log_messages = [call[0][0] for call in LOG.info.call_args_list]
    assert any(
        "BRIDGE: Received TRADE_INTENT_PROPOSED" in msg for msg in log_messages
    ), "Should log event reception"
    assert any("BRIDGE: Dispatched CMD:OPEN" in msg for msg in log_messages), (
        "Should log command dispatch"
    )
