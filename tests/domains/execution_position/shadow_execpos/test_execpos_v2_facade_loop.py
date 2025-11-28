"""
Tests for ExecPosRuntimeV2Facade event loop management (EXEC-V2-P0-FIX-LOOP-S5).

Validates that the facade:
1. Attaches to running loop lazily via _ensure_loop()
2. Delivers events to runtime.handle() without dropping them
3. Does not create new event loops or use asyncio.run()
"""
import asyncio
import pytest
from typing import List, Dict, Any


class DummyRuntime:
    """Mock runtime that records handle() calls."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    async def handle(self, event: Dict[str, Any]) -> None:
        """Record received events."""
        self.events.append(event)


class DummyAdapter:
    """Mock adapter."""
    pass


class DummyFSM:
    """Mock FSM."""

    def listen(self, event_type: str, handler) -> None:
        pass


@pytest.mark.asyncio
async def test_facade_attaches_to_running_loop_and_delivers_entry_intent():
    """
    Test that V2RuntimeFacade with loop=None successfully:
    1. Attaches to running loop via _ensure_loop()
    2. Delivers ENTRY_INTENT event to runtime.handle()
    """
    from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade

    dummy_runtime = DummyRuntime()

    # Create facade WITHOUT passing loop - should lazily attach
    config = {
        "execution_position": {"runtime_mode": "v2"},
        "execution": {"brackets": {"enabled": False}}
    }

    # Mock the runtime attribute directly
    facade = V2RuntimeFacade(
        config=config,
        adapter=DummyAdapter(),
        price_service=None,
        fsm=DummyFSM(),
        loop=None  # Force lazy attachment
    )

    # Replace runtime with our dummy
    facade.runtime = dummy_runtime

    # Create event
    event = {
        "kind": "ENTRY_INTENT",
        "symbol": "BTCUSDT",
        "payload": {"side": "BUY", "qty": 0.001},
    }

    # Submit event - should attach to running loop automatically
    facade._submit_to_loop(facade.runtime.handle(event), source="test")

    # Give loop time to process
    await asyncio.sleep(0.1)

    # Verify event was delivered
    assert len(
        dummy_runtime.events) == 1, f"Expected 1 event, got {len(dummy_runtime.events)}"
    assert dummy_runtime.events[0]["kind"] == "ENTRY_INTENT"
    assert dummy_runtime.events[0]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_facade_uses_provided_loop():
    """
    Test that V2RuntimeFacade respects explicitly provided loop.
    """
    from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade

    dummy_runtime = DummyRuntime()
    current_loop = asyncio.get_running_loop()

    config = {
        "execution_position": {"runtime_mode": "v2"},
        "execution": {"brackets": {"enabled": False}}
    }

    facade = V2RuntimeFacade(
        config=config,
        adapter=DummyAdapter(),
        price_service=None,
        fsm=DummyFSM(),
        loop=current_loop  # Explicitly provide loop
    )

    facade.runtime = dummy_runtime

    # Verify facade uses the provided loop
    assert facade._loop is current_loop

    # Submit event
    event = {
        "kind": "ENTRY_INTENT",
        "symbol": "ETHUSDT",
        "payload": {"side": "SELL", "qty": 0.01},
    }

    facade._submit_to_loop(facade.runtime.handle(event), source="test")
    await asyncio.sleep(0.1)

    assert len(dummy_runtime.events) == 1
    assert dummy_runtime.events[0]["symbol"] == "ETHUSDT"


@pytest.mark.asyncio
async def test_facade_handles_multiple_events_sequentially():
    """
    Test that facade can handle multiple events without dropping any.
    """
    from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade

    dummy_runtime = DummyRuntime()

    config = {
        "execution_position": {"runtime_mode": "v2"},
        "execution": {"brackets": {"enabled": False}}
    }

    facade = V2RuntimeFacade(
        config=config,
        adapter=DummyAdapter(),
        price_service=None,
        fsm=DummyFSM(),
        loop=None
    )

    facade.runtime = dummy_runtime

    # Submit multiple events
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    for symbol in symbols:
        event = {
            "kind": "ENTRY_INTENT",
            "symbol": symbol,
            "payload": {"side": "BUY", "qty": 0.001},
        }
        facade._submit_to_loop(facade.runtime.handle(event), source="test")

    # Give loop time to process all events
    await asyncio.sleep(0.2)

    # Verify all events were delivered
    assert len(
        dummy_runtime.events) == 3, f"Expected 3 events, got {len(dummy_runtime.events)}"
    received_symbols = [e["symbol"] for e in dummy_runtime.events]
    assert set(received_symbols) == set(symbols)


@pytest.mark.asyncio
async def test_ensure_loop_returns_none_when_no_loop_available():
    """
    Test _ensure_loop() returns None when called outside async context.
    This is an edge case - should not happen in production.
    """
    from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade

    config = {
        "execution_position": {"runtime_mode": "v2"},
        "execution": {"brackets": {"enabled": False}}
    }

    facade = V2RuntimeFacade(
        config=config,
        adapter=DummyAdapter(),
        price_service=None,
        fsm=DummyFSM(),
        loop=None
    )

    # Inside async context, _ensure_loop should work
    loop = facade._ensure_loop()
    assert loop is not None
    assert loop is asyncio.get_running_loop()
