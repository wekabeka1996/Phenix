import time
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM
from apps.reference.config_models import AuroraConfig

def feed_opened_position(fsm: ExecPosFSM, symbol: str, side: str, qty: Decimal, entry_price: Decimal):
    """
    Simulates an open position in the FSM state.
    Ensures all 3 flows (Open, Manage, Close) are created for the symbol.
    """
    # Use internal set directly to avoid complex config mocks in _get_or_create_flows
    if symbol not in fsm.manage_flows:
        fsm.open_flows[symbol] = OpenFlowFSM(cooldown_sec=1.0, guard_enabled=True, config=fsm.config)
        fsm.manage_flows[symbol] = ManageFlowFSM(config=fsm.config)
        fsm.close_flows[symbol] = CloseFlowFSM()
    
    manage_flow = fsm.manage_flows[symbol]
    # Hydrate ManageFlowFSM with CORRECT keys from fsm_manage.py:1382
    manage_flow.hydrate({
        "qty": str(qty),
        "entry_price": str(entry_price),
        "side": side,
        "open_ts": time.time(),
        "sl_order_id": "sl_existing_123" # Mock that brackets are placed
    })

def collect_emits(bus: Any) -> List[Message]:
    """
    Returns list of messages emitted to the bus.
    Works with both scenario.FakeBus and conftest.FakeBus.
    """
    if hasattr(bus, "events"): # conftest.FakeBus
        msgs = []
        for topic, args, kwargs in bus.events:
            # In conftest.FakeBus, args[0] is often the topic, args[1] the message? 
            # Wait, conftest.py:30: def emit(self, topic, *args, **kwargs): self.events.append((topic, args, kwargs))
            # Usually: bus.emit("TOPIC", msg) -> events.append(("TOPIC", (msg,), {}))
            if args and isinstance(args[0], Message):
                msgs.append(args[0])
            elif "msg" in kwargs:
                msgs.append(kwargs["msg"])
        return msgs
    elif hasattr(bus, "emitted"): # scenario.FakeBus
        return [m for t, m in bus.emitted]
    return []

def get_last_emit_by_verb(bus: Any, verb: str) -> Optional[Message]:
    """Finds the last message with a specific verb."""
    msgs = collect_emits(bus)
    for m in reversed(msgs):
        if m.verb == verb:
            return m
    return None
