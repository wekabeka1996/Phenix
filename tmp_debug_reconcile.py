import asyncio
from unittest.mock import AsyncMock, MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM


async def run():
    mock_config = {
        "trading": {
            "execution": {
                "manage": {
                }
            }
        }
    }

    class DummyFSMCore:
        pass
    fsm_core = DummyFSMCore()
    fsm = ExecPosFSM(mock_config, fsm_core, shadow_mode=True)

    # Replace adapter
    adapter = MagicMock()
    adapter.get_open_orders = AsyncMock(return_value=[])
    adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter = adapter

    # Replace order_guardian with real instance or mocked
    from apps.reference.services.order_guardian import OrderGuardian
    guardian = OrderGuardian(adapter=adapter, poll_interval_ms=0)
    guardian.cleanup_orphans = AsyncMock()
    fsm.order_guardian = guardian

    await fsm.sync_open_orders_and_positions()
    print('cleanup_orphans called count', guardian.cleanup_orphans.call_count)

asyncio.run(run())
