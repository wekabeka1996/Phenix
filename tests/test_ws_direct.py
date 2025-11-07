#!/usr/bin/env python3
"""
Direct WebSocket test to see what the API is actually sending
"""
import asyncio
import websockets
import json
import pytest


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires running WebSocket server on localhost:8000")
async def test_ws():
    uri = "ws://localhost:8000/ws"
    print(f"Connecting to {uri}...")

    async with websockets.connect(uri) as websocket:
        print("✓ Connected!")

        # Receive initial message
        msg = await websocket.recv()
        data = json.loads(msg)
        print(f"\n[Initial] Received: {json.dumps(data, indent=2)}")

        # Receive 3 metrics updates
        for i in range(3):
            msg = await websocket.recv()
            data = json.loads(msg)
            print(f"\n[Update {i+1}] Received: {json.dumps(data, indent=2)}")

            if data.get('type') == 'metrics_update':
                print("✓ Metrics data received successfully!")
                exp = data.get('exposure', {})
                ord = data.get('orders', {})
                print(f"  Equity: {exp.get('equity_usd')} USD")
                print(f"  Positions: {exp.get('positions_usd')} USD")
                print(f"  Orders Placed: {ord.get('placed_total')}")
                print(f"  Orders Filled: {ord.get('filled_total')}")

if __name__ == "__main__":
    asyncio.run(test_ws())
