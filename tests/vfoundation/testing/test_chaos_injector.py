"""Tests for ChaosInjector — Blueprint 12.1 context-manager fault injection."""
from __future__ import annotations

import pytest
from vfoundation.testing.chaos import ChaosInjector


class _DummyRouter:
    """Duck-typed target for inject_timeout tests."""

    def handle(self, msg: str) -> str:
        return f"handled:{msg}"


class _DummyAdapter:
    """Duck-typed target for inject_cb_open tests."""

    def place_order(self, symbol: str) -> str:
        return f"placed:{symbol}"


class _DummyStore:
    """Duck-typed target for inject_network_partition tests."""

    def reserve(self, key: str) -> str:
        return f"reserved:{key}"

    def confirm(self, key: str) -> str:
        return f"confirmed:{key}"

    def get(self, key: str) -> str:
        return f"got:{key}"


class TestChaosInjector:
    def test_inject_timeout_fires_at_probability_1(self) -> None:
        """probability=1.0 → always raises TimeoutError."""
        injector = ChaosInjector(seed=42)
        router = _DummyRouter()
        with injector.inject_timeout(router, probability=1.0):
            with pytest.raises(TimeoutError, match="injected timeout"):
                router.handle("test")

    def test_inject_timeout_never_fires_at_0(self) -> None:
        """probability=0.0 → never raises, original method works."""
        injector = ChaosInjector(seed=42)
        router = _DummyRouter()
        with injector.inject_timeout(router, probability=0.0):
            for _ in range(50):
                assert router.handle("ok") == "handled:ok"

    def test_inject_cb_open_raises(self) -> None:
        """CB_OPEN injection raises RuntimeError."""
        injector = ChaosInjector()
        adapter = _DummyAdapter()
        with injector.inject_cb_open(adapter):
            with pytest.raises(RuntimeError, match="CB_OPEN"):
                adapter.place_order("BTCUSDT")

    def test_inject_cb_open_restores_on_exit(self) -> None:
        """After exiting context, original method is restored."""
        injector = ChaosInjector()
        adapter = _DummyAdapter()
        with injector.inject_cb_open(adapter):
            pass  # just enter and exit
        assert adapter.place_order("ETH") == "placed:ETH"

    def test_inject_network_partition_raises(self) -> None:
        """Network partition raises ConnectionError on patched methods."""
        injector = ChaosInjector()
        store = _DummyStore()
        with injector.inject_network_partition(store):
            with pytest.raises(ConnectionError, match="network partition"):
                store.reserve("key1")
            with pytest.raises(ConnectionError):
                store.confirm("key1")
            with pytest.raises(ConnectionError):
                store.get("key1")

    def test_inject_network_partition_restores(self) -> None:
        """After exiting context, store methods work normally."""
        injector = ChaosInjector()
        store = _DummyStore()
        with injector.inject_network_partition(store):
            pass
        assert store.reserve("k") == "reserved:k"
        assert store.confirm("k") == "confirmed:k"
        assert store.get("k") == "got:k"

    def test_inject_random_failures_respects_seed(self) -> None:
        """Same seed produces same should_fail() sequence."""
        results_a = []
        results_b = []
        for results in [results_a, results_b]:
            inj = ChaosInjector(seed=99)
            with inj.inject_random_failures(rate=0.5) as ci:
                for _ in range(30):
                    results.append(ci.should_fail(0.5))
        assert results_a == results_b

    def test_inject_random_failures_rate_0(self) -> None:
        """rate=0.0 → should_fail never returns True."""
        injector = ChaosInjector(seed=42)
        with injector.inject_random_failures(rate=0.0) as ci:
            for _ in range(100):
                assert ci.should_fail(0.0) is False
