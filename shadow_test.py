
import sys
import os
import asyncio
import random
import time
import logging
from typing import Dict, Any
from unittest.mock import MagicMock

sys.path.append(os.getcwd())

from apps.reference.adapters.simulated_adapter import SimulatedAdapter
from vfoundation.core.protocol import Message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChaosSim")

class ChaosSimulatedAdapter(SimulatedAdapter):
    """
    Chaos Adapter for Stage 4 Shadow Test.
    Injects random errors and latency.
    """
    def __init__(self, error_rate: float = 0.1, latency_ms: int = 500):
        super().__init__(config={"latency_ms": latency_ms}) # Use base latency
        self.error_rate = error_rate
        logger.info(f"Initialized Chaos Adapter with Error Rate={error_rate}, Latency={latency_ms}ms")

    async def create_order(self, params: Any) -> Any:
        # Error Injection
        if random.random() < self.error_rate:
            logger.error("\u26A0 NETWORK ERROR INJECTED")
            raise ConnectionError("Simulated Network Error")
            
        return await super().create_order(params)

async def run_shadow_test():
    print("\n--- Stage 4: Integration 'Shadow Test' ---")
    adapter = ChaosSimulatedAdapter(error_rate=0.2, latency_ms=100) # 20% error rate
    
    total_orders = 50
    success = 0
    failures = 0
    start_time = time.time()
    
    print(f"Injecting {total_orders} orders...")
    
    from apps.reference.adapters.contract import ExchangeOrderParams
    
    for i in range(total_orders):
        params = ExchangeOrderParams(
            client_order_id=f"test_{i}",
            symbol="BTCUSDT",
            side="BUY",
            quantity="1.0",
            price="50000",
            order_type="LIMIT"
        )
        try:
            await adapter.create_order(params)
            success += 1
            print(f"Order {i+1}: Success")
        except Exception as e:
            failures += 1
            print(f"Order {i+1}: FAILED ({e})")
            
        # Small delay between orders
        await asyncio.sleep(0.01)
            
    duration = time.time() - start_time
    print(f"\nResults: Total={total_orders}, Success={success}, Failures={failures}")
    print(f"Error Rate Actual: {failures/total_orders:.2f} (Target: 0.2)")
    print(f"Total Duration: {duration:.2f}s")
    
    if failures > 0:
        print("System demonstrates vulnerability to network errors (Exceptions raised to Orchestrator).")
        print("Verdict: Verify if Orchestrator has retry logic for these exceptions.")
    else:
        print("Strange: No failures occurred (Bad Random?)")

if __name__ == "__main__":
    asyncio.run(run_shadow_test())
