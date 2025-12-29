#!/usr/bin/env python3
"""
System Performance Benchmark Script
Diagnoses slowdowns in the trading system
"""
import asyncio
import time
import threading
import statistics
from typing import List, Dict, Any

# Benchmark results storage
results: Dict[str, Any] = {}


def benchmark_sync(name: str, iterations: int = 100):
    """Decorator for sync benchmarks"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                func(*args, **kwargs)
                times.append((time.perf_counter() - start) * 1000)  # ms

            results[name] = {
                "avg_ms": statistics.mean(times),
                "min_ms": min(times),
                "max_ms": max(times),
                "p95_ms": sorted(times)[int(len(times) * 0.95)],
                "iterations": iterations,
            }
            return results[name]
        return wrapper
    return decorator


def benchmark_async(name: str, iterations: int = 100):
    """Decorator for async benchmarks"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                await func(*args, **kwargs)
                times.append((time.perf_counter() - start) * 1000)  # ms

            results[name] = {
                "avg_ms": statistics.mean(times),
                "min_ms": min(times),
                "max_ms": max(times),
                "p95_ms": sorted(times)[int(len(times) * 0.95)],
                "iterations": iterations,
            }
            return results[name]
        return wrapper
    return decorator


# ============ BENCHMARKS ============

@benchmark_sync("threading.Lock", iterations=10000)
def bench_threading_lock():
    """Benchmark threading.Lock acquisition"""
    lock = threading.Lock()
    with lock:
        pass


@benchmark_sync("time.time()", iterations=10000)
def bench_time_time():
    """Benchmark time.time() call"""
    _ = time.time()


@benchmark_sync("time.monotonic()", iterations=10000)
def bench_time_monotonic():
    """Benchmark time.monotonic() call"""
    _ = time.monotonic()


@benchmark_sync("dict_access", iterations=10000)
def bench_dict_access():
    """Benchmark dict access"""
    d = {"key": "value", "key2": 123, "key3": [1, 2, 3]}
    _ = d.get("key")
    _ = d.get("missing", "default")


@benchmark_sync("json_dumps", iterations=1000)
def bench_json_dumps():
    """Benchmark JSON serialization"""
    import json
    data = {
        "symbol": "BTCUSDT",
        "price": 90000.0,
        "quantity": 0.001,
        "timestamp": time.time(),
        "nested": {"a": 1, "b": 2, "c": [1, 2, 3]},
    }
    _ = json.dumps(data)


@benchmark_sync("hmac_sign", iterations=1000)
def bench_hmac_sign():
    """Benchmark HMAC signing (used in API requests)"""
    import hmac
    import hashlib
    secret = b"test_secret_key_for_benchmark"
    message = b"timestamp=1234567890&symbol=BTCUSDT&side=BUY&quantity=0.001"
    _ = hmac.new(secret, message, hashlib.sha256).hexdigest()


async def bench_asyncio_sleep():
    """Benchmark asyncio.sleep overhead"""
    times = []
    for _ in range(100):
        start = time.perf_counter()
        await asyncio.sleep(0)
        times.append((time.perf_counter() - start) * 1000)

    results["asyncio.sleep(0)"] = {
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "p95_ms": sorted(times)[int(len(times) * 0.95)],
        "iterations": 100,
    }


async def bench_asyncio_lock():
    """Benchmark asyncio.Lock acquisition"""
    lock = asyncio.Lock()
    times = []
    for _ in range(1000):
        start = time.perf_counter()
        async with lock:
            pass
        times.append((time.perf_counter() - start) * 1000)

    results["asyncio.Lock"] = {
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "p95_ms": sorted(times)[int(len(times) * 0.95)],
        "iterations": 1000,
    }


async def bench_httpx_client_create():
    """Benchmark httpx client creation"""
    import httpx
    times = []
    for _ in range(50):
        start = time.perf_counter()
        client = httpx.AsyncClient(timeout=30.0)
        times.append((time.perf_counter() - start) * 1000)
        await client.aclose()

    results["httpx.AsyncClient()"] = {
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "p95_ms": sorted(times)[int(len(times) * 0.95)],
        "iterations": 50,
    }


async def bench_binance_time_api():
    """Benchmark Binance time API (network latency)"""
    import httpx

    times_testnet = []
    times_prod = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Testnet
        for _ in range(5):
            start = time.perf_counter()
            try:
                r = await client.get("https://testnet.binancefuture.com/fapi/v1/time")
                r.raise_for_status()
                times_testnet.append((time.perf_counter() - start) * 1000)
            except Exception as e:
                times_testnet.append(float('inf'))

        # Production
        for _ in range(5):
            start = time.perf_counter()
            try:
                r = await client.get("https://fapi.binance.com/fapi/v1/time")
                r.raise_for_status()
                times_prod.append((time.perf_counter() - start) * 1000)
            except Exception as e:
                times_prod.append(float('inf'))

    valid_testnet = [t for t in times_testnet if t != float('inf')]
    valid_prod = [t for t in times_prod if t != float('inf')]

    if valid_testnet:
        results["Binance_Testnet_/time"] = {
            "avg_ms": statistics.mean(valid_testnet),
            "min_ms": min(valid_testnet),
            "max_ms": max(valid_testnet),
            "p95_ms": sorted(valid_testnet)[-1],
            "iterations": len(valid_testnet),
        }

    if valid_prod:
        results["Binance_Prod_/time"] = {
            "avg_ms": statistics.mean(valid_prod),
            "min_ms": min(valid_prod),
            "max_ms": max(valid_prod),
            "p95_ms": sorted(valid_prod)[-1],
            "iterations": len(valid_prod),
        }


def bench_import_times():
    """Measure import times for key modules"""
    import importlib
    import sys

    modules = [
        "apps.reference.adapters.binance_adapter",
        "apps.reference.domains.execution_position.shadow_execpos.runtime",
        "apps.reference.domains.market_data.market_data_connector",
        "apps.reference.domains.decision_making.decision_making",
    ]

    for mod_name in modules:
        # Remove from cache if present
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        start = time.perf_counter()
        try:
            importlib.import_module(mod_name)
            elapsed_ms = (time.perf_counter() - start) * 1000
            results[f"import_{mod_name.split('.')[-1]}"] = {
                "avg_ms": elapsed_ms,
                "min_ms": elapsed_ms,
                "max_ms": elapsed_ms,
                "p95_ms": elapsed_ms,
                "iterations": 1,
            }
        except Exception as e:
            results[f"import_{mod_name.split('.')[-1]}"] = {"error": str(e)}


def print_results():
    """Print benchmark results in a formatted table"""
    print("\n" + "=" * 80)
    print("🚀 SYSTEM PERFORMANCE BENCHMARK RESULTS")
    print("=" * 80)

    # Categorize results
    fast = []      # < 0.1 ms
    normal = []    # 0.1 - 10 ms
    slow = []      # 10 - 100 ms
    very_slow = [] # > 100 ms
    errors = []

    for name, data in sorted(results.items()):
        if "error" in data:
            errors.append((name, data))
        elif data["avg_ms"] < 0.1:
            fast.append((name, data))
        elif data["avg_ms"] < 10:
            normal.append((name, data))
        elif data["avg_ms"] < 100:
            slow.append((name, data))
        else:
            very_slow.append((name, data))

    def print_category(title: str, emoji: str, items: list):
        if not items:
            return
        print(f"\n{emoji} {title}:")
        print("-" * 70)
        print(f"{'Name':<35} {'Avg':>10} {'Min':>10} {'Max':>10} {'P95':>10}")
        print("-" * 70)
        for name, data in items:
            print(f"{name:<35} {data['avg_ms']:>9.3f}ms {data['min_ms']:>9.3f}ms {data['max_ms']:>9.3f}ms {data['p95_ms']:>9.3f}ms")

    print_category("FAST (< 0.1ms)", "✅", fast)
    print_category("NORMAL (0.1-10ms)", "🟡", normal)
    print_category("SLOW (10-100ms)", "🟠", slow)
    print_category("VERY SLOW (> 100ms)", "🔴", very_slow)

    if errors:
        print(f"\n❌ ERRORS:")
        print("-" * 70)
        for name, data in errors:
            print(f"{name}: {data['error']}")

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    total_benchmarks = len(results)
    print(f"Total benchmarks: {total_benchmarks}")
    print(f"  ✅ Fast: {len(fast)}")
    print(f"  🟡 Normal: {len(normal)}")
    print(f"  🟠 Slow: {len(slow)}")
    print(f"  🔴 Very Slow: {len(very_slow)}")
    print(f"  ❌ Errors: {len(errors)}")

    # Diagnose issues
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSIS")
    print("=" * 80)

    issues = []

    # Check network latency
    testnet_data = results.get("Binance_Testnet_/time", {})
    prod_data = results.get("Binance_Prod_/time", {})

    if testnet_data.get("avg_ms", 0) > 500:
        issues.append(f"⚠️ Testnet API дуже повільний: {testnet_data['avg_ms']:.0f}ms (норма < 300ms)")

    if prod_data.get("avg_ms", 0) > 300:
        issues.append(f"⚠️ Production API повільний: {prod_data['avg_ms']:.0f}ms (норма < 200ms)")

    # Check import times
    for name, data in results.items():
        if name.startswith("import_") and data.get("avg_ms", 0) > 1000:
            issues.append(f"⚠️ Імпорт {name} занадто довгий: {data['avg_ms']:.0f}ms")

    # Check async overhead
    async_lock = results.get("asyncio.Lock", {})
    thread_lock = results.get("threading.Lock", {})

    if async_lock.get("avg_ms", 0) > 0.1:
        issues.append(f"⚠️ asyncio.Lock повільний: {async_lock['avg_ms']:.3f}ms")

    if not issues:
        print("✅ Основні компоненти працюють нормально!")
        print("   Якщо система все ще повільна, проблема може бути в:")
        print("   - WebSocket reconnects")
        print("   - Database queries")
        print("   - Event loop blocking")
    else:
        for issue in issues:
            print(issue)


async def main():
    print("🔧 Starting System Performance Benchmark...")
    print("   This will take about 30 seconds...\n")

    # Sync benchmarks
    print("Running sync benchmarks...")
    bench_threading_lock()
    bench_time_time()
    bench_time_monotonic()
    bench_dict_access()
    bench_json_dumps()
    bench_hmac_sign()

    # Async benchmarks
    print("Running async benchmarks...")
    await bench_asyncio_sleep()
    await bench_asyncio_lock()
    await bench_httpx_client_create()

    # Network benchmarks
    print("Running network benchmarks (Binance API)...")
    await bench_binance_time_api()

    # Import benchmarks
    print("Running import benchmarks...")
    bench_import_times()

    # Print results
    print_results()


if __name__ == "__main__":
    asyncio.run(main())
