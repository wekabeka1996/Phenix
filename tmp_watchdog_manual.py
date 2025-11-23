import asyncio
from unittest.mock import AsyncMock, patch
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog


async def main():
    watchdog = OrderTimeoutWatchdog()
    watchdog.check_interval_ms = 10
    watchdog._check_timeouts = AsyncMock(
        side_effect=[Exception('Loop Error'), None, None, None])
    with patch('apps.reference.domains.execution_position.watchdog.LOG') as mock_log:
        watchdog.start()
        await asyncio.sleep(0.05)
        watchdog.stop()
        await asyncio.sleep(0.01)
        print('call_count', watchdog._check_timeouts.call_count)
        print('log_calls', mock_log.error.call_count)

if __name__ == '__main__':
    asyncio.run(main())
