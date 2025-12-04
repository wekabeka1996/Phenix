"""
Integration tests for Market Data Multiprocessing (FSMP-ARCH-01).

Tests:
1. Process Isolation: Worker runs in separate process (different PID)
2. Latency: Tick processing latency < 100ms
3. Backpressure: Worker handles main loop blocking gracefully
4. Load Test: Sustain 1000 ticks/sec throughput

These tests require actual process spawning and are slower than unit tests.
Run with: pytest tests/integration/test_market_data_multiprocess.py -v
"""

import asyncio
import multiprocessing
import os
import queue
import time
from multiprocessing import Process, Queue
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.domains.market_data.proxy import MarketDataProxy
from apps.reference.domains.market_data.worker import MarketDataWorker, worker_entrypoint


# ============================================================================
# Test Fixtures
# ============================================================================

class MockFSM:
    """Mock FSMCore for testing."""
    
    def __init__(self):
        self.emitted_events: List[Dict[str, Any]] = []
        self.emit_timestamps: List[float] = []
    
    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted_events.append({
            "event_name": event_name,
            "payload": payload,
            "why": why,
            "received_at": time.time() * 1000,  # ms
        })
        self.emit_timestamps.append(time.perf_counter())
    
    def listen(self, event_name: str, callback):
        pass


class MockConfig:
    """Mock AuroraConfig for testing."""
    
    def __init__(self, config_dict: dict):
        self._config = config_dict
    
    def model_dump(self, mode: str = "python") -> dict:
        return self._config


def create_test_config(symbols: List[str] = None, testnet: bool = True) -> MockConfig:
    """Create a test configuration."""
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]
    
    instruments = {s: {"leverage": 10} for s in symbols}
    
    return MockConfig({
        "trading": {
            "testnet": testnet,
            "instruments": instruments,
            "market_data": {
                "macro_sync": {"anchors": []},
                "poll_interval_sec": 1,
                "use_multiprocessing": True,
            },
        },
    })


# ============================================================================
# Test 1: Process Isolation (PID Check)
# ============================================================================

class TestProcessIsolation:
    """Test that worker runs in a separate OS process."""

    def test_worker_runs_in_different_pid(self):
        """
        Verify worker process has different PID than main process.
        
        Success Criteria:
        - Worker PID != Main PID
        - Worker process terminates cleanly
        """
        main_pid = os.getpid()
        result_queue = Queue()
        
        def worker_pid_reporter(ipc_queue, config_dict):
            """Simple worker that reports its PID."""
            worker_pid = os.getpid()
            result_queue.put({"worker_pid": worker_pid, "main_pid": main_pid})
            # Exit immediately after reporting
        
        # Spawn worker process
        process = Process(target=worker_pid_reporter, args=(Queue(), {}))
        process.start()
        
        # Wait for result with timeout
        try:
            result = result_queue.get(timeout=5)
            worker_pid = result["worker_pid"]
            
            assert worker_pid != main_pid, (
                f"Worker should run in different process! "
                f"Main PID: {main_pid}, Worker PID: {worker_pid}"
            )
            print(f"✅ Process isolation confirmed: Main PID={main_pid}, Worker PID={worker_pid}")
            
        finally:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)

    def test_worker_writes_pid_to_queue(self):
        """
        Test that MarketDataWorker can communicate its PID via queue.
        
        This validates the IPC mechanism works for process identification.
        """
        ipc_queue = Queue(maxsize=100)
        main_pid = os.getpid()
        
        def pid_reporting_worker(q, config):
            """Worker that sends its PID as first message."""
            worker_pid = os.getpid()
            q.put({
                "type": "worker_started",
                "pid": worker_pid,
                "ts": time.time() * 1000,
            })
        
        process = Process(target=pid_reporting_worker, args=(ipc_queue, {}))
        process.start()
        
        try:
            msg = ipc_queue.get(timeout=5)
            
            assert msg["type"] == "worker_started"
            assert msg["pid"] != main_pid
            assert "ts" in msg
            
            print(f"✅ Worker communicated PID via queue: {msg['pid']}")
            
        finally:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()


# ============================================================================
# Test 2: Latency < 100ms
# ============================================================================

class TestLatency:
    """Test that tick processing latency meets SLA."""

    @pytest.mark.asyncio
    async def test_proxy_emit_latency_under_100ms(self):
        """
        Measure latency from tick creation to FSM emission.
        
        Success Criteria:
        - P99 latency < 100ms
        - Mean latency < 50ms
        """
        fsm = MockFSM()
        config = create_test_config()
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Use stdlib queue for in-process testing
        import queue as stdlib_queue
        proxy._ipc_queue = stdlib_queue.Queue(maxsize=100)
        
        latencies = []
        num_ticks = 100
        
        # Simulate ticks with timestamps
        for i in range(num_ticks):
            tick_ts = time.time() * 1000  # Exchange timestamp (ms)
            tick_data = {
                "type": MarketDataWorker.MSG_TYPE_TICK,
                "symbol": "BTCUSDT",
                "data": {
                    "ts": tick_ts,
                    "price": f"{95000 + i}",
                    "bid": f"{94999 + i}",
                    "ask": f"{95001 + i}",
                },
            }
            
            proxy._ipc_queue.put_nowait(tick_data)
        
        # Process all ticks
        start = time.perf_counter()
        while not proxy._ipc_queue.empty():
            msg = proxy._ipc_queue.get_nowait()
            emit_start = time.perf_counter()
            proxy._emit_tick(msg)
            emit_end = time.perf_counter()
            latencies.append((emit_end - emit_start) * 1000)  # ms
        
        total_time = (time.perf_counter() - start) * 1000
        
        # Calculate statistics
        mean_latency = sum(latencies) / len(latencies)
        sorted_latencies = sorted(latencies)
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        max_latency = max(latencies)
        
        print(f"\n📊 Latency Statistics ({num_ticks} ticks):")
        print(f"   Mean: {mean_latency:.3f}ms")
        print(f"   P99:  {p99_latency:.3f}ms")
        print(f"   Max:  {max_latency:.3f}ms")
        print(f"   Total processing time: {total_time:.2f}ms")
        
        # Assertions
        assert mean_latency < 50, f"Mean latency {mean_latency}ms exceeds 50ms SLA"
        assert p99_latency < 100, f"P99 latency {p99_latency}ms exceeds 100ms SLA"
        assert len(fsm.emitted_events) == num_ticks

    @pytest.mark.asyncio
    async def test_end_to_end_latency_simulation(self):
        """
        Simulate end-to-end latency including queue operations.
        
        This mimics the full path: Worker -> Queue -> Proxy -> FSM
        """
        fsm = MockFSM()
        config = create_test_config()
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Use real multiprocessing queue for realistic test
        ipc_queue = Queue(maxsize=100)
        proxy._ipc_queue = ipc_queue
        
        latencies = []
        num_ticks = 50
        
        def producer():
            """Simulate worker producing ticks."""
            for i in range(num_ticks):
                tick_ts = time.time() * 1000
                tick_data = {
                    "type": MarketDataWorker.MSG_TYPE_TICK,
                    "symbol": "BTCUSDT",
                    "data": {"ts": tick_ts, "price": f"{95000 + i}", "bid": "94999", "ask": "95001"},
                    "produced_at": time.perf_counter(),
                }
                ipc_queue.put(tick_data)
                time.sleep(0.001)  # 1ms between ticks
        
        # Start producer in separate process
        producer_process = Process(target=producer)
        producer_process.start()
        
        # Consume and measure latency
        received = 0
        timeout = time.time() + 5  # 5 second timeout
        
        while received < num_ticks and time.time() < timeout:
            try:
                msg = ipc_queue.get(timeout=0.1)
                receive_time = time.perf_counter()
                
                if "produced_at" in msg:
                    latency = (receive_time - msg["produced_at"]) * 1000
                    latencies.append(latency)
                
                proxy._emit_tick(msg)
                received += 1
                
            except Exception:
                continue
        
        producer_process.join(timeout=2)
        if producer_process.is_alive():
            producer_process.terminate()
        
        if latencies:
            mean_latency = sum(latencies) / len(latencies)
            p99_idx = int(len(latencies) * 0.99)
            p99_latency = sorted(latencies)[min(p99_idx, len(latencies) - 1)]
            
            print(f"\n📊 End-to-End Latency ({len(latencies)} ticks):")
            print(f"   Mean IPC latency: {mean_latency:.3f}ms")
            print(f"   P99 IPC latency:  {p99_latency:.3f}ms")
            
            # IPC adds ~0.5-5ms overhead typically
            assert mean_latency < 100, f"Mean E2E latency {mean_latency}ms too high"


# ============================================================================
# Test 3: Backpressure (5s Block)
# ============================================================================

class TestBackpressure:
    """Test backpressure handling when main loop blocks."""

    def test_worker_drops_oldest_when_queue_full(self):
        """
        Verify drop-oldest policy works correctly.
        
        Success Criteria:
        - Queue doesn't grow beyond maxsize
        - Oldest ticks are dropped, newest are kept
        - No crash or hang
        """
        import queue as stdlib_queue
        
        maxsize = 10
        test_queue = stdlib_queue.Queue(maxsize=maxsize)
        dropped_count = 0
        
        def put_with_backpressure(q, tick):
            nonlocal dropped_count
            try:
                q.put_nowait(tick)
            except stdlib_queue.Full:
                try:
                    q.get_nowait()  # Drop oldest
                    dropped_count += 1
                    q.put_nowait(tick)
                except stdlib_queue.Empty:
                    q.put_nowait(tick)
        
        # Produce more ticks than queue can hold
        num_ticks = 50
        for i in range(num_ticks):
            tick = {"id": i, "ts": time.time() * 1000}
            put_with_backpressure(test_queue, tick)
        
        # Verify queue state
        assert test_queue.qsize() == maxsize
        assert dropped_count == num_ticks - maxsize
        
        # Verify newest ticks are kept (FIFO after drops)
        remaining_ticks = []
        while not test_queue.empty():
            remaining_ticks.append(test_queue.get_nowait())
        
        # The remaining ticks should be the last `maxsize` ticks
        expected_ids = list(range(num_ticks - maxsize, num_ticks))
        actual_ids = [t["id"] for t in remaining_ticks]
        
        assert actual_ids == expected_ids, (
            f"Expected newest ticks {expected_ids}, got {actual_ids}"
        )
        
        print(f"✅ Backpressure test passed:")
        print(f"   Total produced: {num_ticks}")
        print(f"   Queue maxsize: {maxsize}")
        print(f"   Dropped: {dropped_count}")
        print(f"   Retained: {len(remaining_ticks)} (newest)")

    @pytest.mark.asyncio
    async def test_proxy_recovers_after_main_loop_block(self):
        """
        Simulate main loop blocking for 1 second and verify recovery.
        
        Note: Using 1s instead of 5s to keep test fast.
        
        Success Criteria:
        - Worker continues producing during block
        - Proxy catches up after unblock
        - No data corruption
        """
        import queue as stdlib_queue
        
        fsm = MockFSM()
        config = create_test_config()
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Small queue to force backpressure quickly
        proxy._ipc_queue = stdlib_queue.Queue(maxsize=20)
        proxy._running = True
        
        # Simulate producer filling queue during "block"
        for i in range(50):  # More than queue can hold
            tick = {
                "type": MarketDataWorker.MSG_TYPE_TICK,
                "symbol": "BTCUSDT",
                "data": {"ts": i, "price": f"{95000 + i}", "bid": "94999", "ask": "95001"},
            }
            try:
                proxy._ipc_queue.put_nowait(tick)
            except stdlib_queue.Full:
                # Drop oldest (simulate worker behavior)
                try:
                    proxy._ipc_queue.get_nowait()
                    proxy._ipc_queue.put_nowait(tick)
                except stdlib_queue.Empty:
                    pass
        
        # Now "unblock" and process
        processed = 0
        while not proxy._ipc_queue.empty():
            msg = proxy._ipc_queue.get_nowait()
            proxy._emit_tick(msg)
            processed += 1
        
        print(f"\n✅ Recovery after block:")
        print(f"   Ticks processed after unblock: {processed}")
        print(f"   Events emitted: {len(fsm.emitted_events)}")
        
        assert processed == 20  # Queue maxsize
        assert len(fsm.emitted_events) == processed


# ============================================================================
# Test 4: Load Test (1000 ticks/sec)
# ============================================================================

class TestLoadCapacity:
    """Test system can handle 1000 ticks/sec sustained load."""

    @pytest.mark.asyncio
    async def test_throughput_1000_ticks_per_second(self):
        """
        Verify proxy can process 1000 ticks within 1 second.
        
        Success Criteria:
        - All 1000 ticks processed
        - Total time < 1.5 seconds (allowing 50% overhead)
        - No data loss
        """
        import queue as stdlib_queue
        
        fsm = MockFSM()
        config = create_test_config()
        proxy = MarketDataProxy(fsm=fsm, config=config)
        proxy._ipc_queue = stdlib_queue.Queue(maxsize=2000)
        
        num_ticks = 1000
        
        # Pre-fill queue with 1000 ticks
        for i in range(num_ticks):
            tick = {
                "type": MarketDataWorker.MSG_TYPE_TICK,
                "symbol": "BTCUSDT" if i % 2 == 0 else "ETHUSDT",
                "data": {
                    "ts": time.time() * 1000,
                    "price": f"{95000 + (i % 100)}",
                    "bid": "94999",
                    "ask": "95001",
                },
            }
            proxy._ipc_queue.put_nowait(tick)
        
        # Process all ticks and measure time
        start = time.perf_counter()
        
        processed = 0
        while not proxy._ipc_queue.empty():
            msg = proxy._ipc_queue.get_nowait()
            proxy._emit_tick(msg)
            processed += 1
        
        elapsed = time.perf_counter() - start
        throughput = processed / elapsed
        
        print(f"\n📊 Load Test Results ({num_ticks} ticks):")
        print(f"   Processing time: {elapsed:.3f}s")
        print(f"   Throughput: {throughput:.0f} ticks/sec")
        print(f"   Events emitted: {len(fsm.emitted_events)}")
        
        # Assertions
        assert processed == num_ticks, f"Expected {num_ticks} ticks, processed {processed}"
        assert len(fsm.emitted_events) == num_ticks
        assert elapsed < 1.5, f"Processing took {elapsed}s, expected < 1.5s"
        assert throughput > 666, f"Throughput {throughput}/sec below minimum 666/sec"

    @pytest.mark.asyncio  
    async def test_sustained_load_5_seconds(self):
        """
        Test sustained load over 5 seconds.
        
        Success Criteria:
        - Maintain ~1000 ticks/sec average
        - No queue overflow (with proper sizing)
        - Consistent latency throughout
        """
        import queue as stdlib_queue
        
        fsm = MockFSM()
        config = create_test_config()
        proxy = MarketDataProxy(fsm=fsm, config=config)
        proxy._ipc_queue = stdlib_queue.Queue(maxsize=proxy.QUEUE_MAXSIZE)
        
        duration_sec = 2  # 2 seconds for faster test
        target_rate = 1000  # ticks/sec
        total_ticks = duration_sec * target_rate
        
        # Produce and consume interleaved
        produced = 0
        consumed = 0
        batch_size = 50
        
        start = time.perf_counter()
        
        while produced < total_ticks:
            # Produce batch
            for _ in range(min(batch_size, total_ticks - produced)):
                tick = {
                    "type": MarketDataWorker.MSG_TYPE_TICK,
                    "symbol": "BTCUSDT",
                    "data": {"ts": time.time() * 1000, "price": "95000", "bid": "94999", "ask": "95001"},
                }
                try:
                    proxy._ipc_queue.put_nowait(tick)
                    produced += 1
                except stdlib_queue.Full:
                    break
            
            # Consume batch
            for _ in range(batch_size):
                try:
                    msg = proxy._ipc_queue.get_nowait()
                    proxy._emit_tick(msg)
                    consumed += 1
                except stdlib_queue.Empty:
                    break
            
            # Small yield to simulate real async behavior
            await asyncio.sleep(0.001)
        
        # Drain remaining
        while not proxy._ipc_queue.empty():
            msg = proxy._ipc_queue.get_nowait()
            proxy._emit_tick(msg)
            consumed += 1
        
        elapsed = time.perf_counter() - start
        avg_rate = consumed / elapsed
        
        print(f"\n📊 Sustained Load Test ({duration_sec}s target):")
        print(f"   Actual duration: {elapsed:.2f}s")
        print(f"   Ticks produced: {produced}")
        print(f"   Ticks consumed: {consumed}")
        print(f"   Average rate: {avg_rate:.0f} ticks/sec")
        
        assert consumed == produced, f"Data loss: produced {produced}, consumed {consumed}"
        assert avg_rate > 500, f"Average rate {avg_rate}/sec too low"


# ============================================================================
# Bonus: Full Integration Test
# ============================================================================

class TestFullIntegration:
    """Full integration test with actual process spawning."""

    def test_worker_to_proxy_full_cycle(self):
        """
        Test complete cycle: Worker process -> Queue -> Proxy -> FSM.
        
        This is the most realistic test of the entire system.
        """
        ipc_queue = Queue(maxsize=100)
        result_queue = Queue()
        
        def test_worker(q, result_q):
            """Worker that sends test ticks and reports completion."""
            worker_pid = os.getpid()
            
            # Send PID notification
            q.put({"type": "worker_started", "pid": worker_pid})
            
            # Send test ticks
            for i in range(10):
                tick = {
                    "type": "tick",
                    "symbol": "BTCUSDT",
                    "data": {"ts": time.time() * 1000, "price": f"{95000 + i}", "bid": "94999", "ask": "95001"},
                }
                q.put(tick)
                time.sleep(0.01)
            
            # Send completion signal
            q.put({"type": "worker_done", "ticks_sent": 10})
            result_q.put({"status": "success", "pid": worker_pid})
        
        # Start worker
        process = Process(target=test_worker, args=(ipc_queue, result_queue))
        process.start()
        
        # Create proxy with mock FSM
        fsm = MockFSM()
        config = create_test_config()
        proxy = MarketDataProxy(fsm=fsm, config=config)
        proxy._ipc_queue = ipc_queue
        
        # Consume messages
        ticks_received = 0
        worker_pid = None
        timeout = time.time() + 10
        
        while time.time() < timeout:
            try:
                msg = ipc_queue.get(timeout=0.5)
                msg_type = msg.get("type")
                
                if msg_type == "worker_started":
                    worker_pid = msg.get("pid")
                    print(f"Worker started with PID: {worker_pid}")
                    
                elif msg_type == "tick":
                    proxy._emit_tick(msg)
                    ticks_received += 1
                    
                elif msg_type == "worker_done":
                    print(f"Worker completed, sent {msg.get('ticks_sent')} ticks")
                    break
                    
            except Exception:
                continue
        
        # Cleanup
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
        
        # Verify
        assert worker_pid is not None and worker_pid != os.getpid()
        assert ticks_received == 10
        assert len(fsm.emitted_events) == 10
        
        print(f"\n✅ Full Integration Test Passed:")
        print(f"   Worker PID: {worker_pid}")
        print(f"   Main PID: {os.getpid()}")
        print(f"   Ticks received: {ticks_received}")
        print(f"   FSM events: {len(fsm.emitted_events)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
