"""Tests for Graceful Shutdown Contract — Phase 17.2."""
import asyncio

import pytest

from vfoundation.core.lifecycle import (
    LifecycleHook,
    LifecycleManager,
    ShutdownPhase,
)


class DummyHook(LifecycleHook):
    """Test hook that records shutdown calls."""

    def __init__(self, name: str, phase: ShutdownPhase, healthy: bool = True):
        self._name = name
        self._phase = phase
        self._healthy = healthy
        self.shutdown_called = False
        self.shutdown_order: int = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def shutdown_phase(self) -> ShutdownPhase:
        return self._phase

    async def shutdown(self, timeout_sec: float = 5.0) -> None:
        self.shutdown_called = True

    async def health_check(self) -> bool:
        return self._healthy


class SlowHook(LifecycleHook):
    """Hook that takes too long to shutdown."""

    @property
    def name(self) -> str:
        return "slow_hook"

    @property
    def shutdown_phase(self) -> ShutdownPhase:
        return ShutdownPhase.BACKGROUND

    async def shutdown(self, timeout_sec: float = 5.0) -> None:
        await asyncio.sleep(100)  # Will timeout

    async def health_check(self) -> bool:
        return True


class TestLifecycleManager:
    """Phase 17.2: LifecycleManager tests."""

    @pytest.mark.asyncio
    async def test_shutdown_order(self):
        """Hooks are shutdown in phase order (INGRESS first, NETWORKING last)."""
        mgr = LifecycleManager()
        net_hook = DummyHook("net", ShutdownPhase.NETWORKING)
        ingress_hook = DummyHook("ingress", ShutdownPhase.INGRESS)
        proc_hook = DummyHook("proc", ShutdownPhase.PROCESSING)

        # Register in reverse order
        mgr.register(net_hook)
        mgr.register(ingress_hook)
        mgr.register(proc_hook)

        order: list[str] = []
        orig_shutdown = DummyHook.shutdown

        async def tracking_shutdown(self_hook, timeout_sec=5.0):
            order.append(self_hook.name)
            await orig_shutdown(self_hook, timeout_sec)

        DummyHook.shutdown = tracking_shutdown  # type: ignore[assignment]
        try:
            results = await mgr.shutdown_all()
            assert order == ["ingress", "proc", "net"]
            assert all(v is None for v in results.values())
        finally:
            DummyHook.shutdown = orig_shutdown  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        """Second shutdown_all() returns empty dict without re-running hooks."""
        mgr = LifecycleManager()
        hook = DummyHook("test", ShutdownPhase.INGRESS)
        mgr.register(hook)

        results1 = await mgr.shutdown_all()
        assert "test" in results1
        results2 = await mgr.shutdown_all()
        assert results2 == {}

    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(self):
        """Slow hooks get timeout error instead of blocking forever."""
        mgr = LifecycleManager()
        mgr.register(SlowHook())
        results = await mgr.shutdown_all(timeout_sec=0.1)
        assert "slow_hook" in results
        assert "timeout" in results["slow_hook"]

    @pytest.mark.asyncio
    async def test_health_all_aggregation(self):
        """health_all() aggregates health from all hooks."""
        mgr = LifecycleManager()
        mgr.register(DummyHook("healthy", ShutdownPhase.INGRESS, healthy=True))
        mgr.register(DummyHook("unhealthy", ShutdownPhase.PROCESSING, healthy=False))

        health = await mgr.health_all()
        assert health["healthy"] is True
        assert health["unhealthy"] is False

    @pytest.mark.asyncio
    async def test_register_and_hooks_list(self):
        """register() adds hooks, hooks property returns them."""
        mgr = LifecycleManager()
        assert len(mgr.hooks) == 0
        mgr.register(DummyHook("a", ShutdownPhase.INGRESS))
        mgr.register(DummyHook("b", ShutdownPhase.NETWORKING))
        assert len(mgr.hooks) == 2


class StartupHook(LifecycleHook):
    """Test hook that records startup calls."""

    def __init__(self, name: str, phase: ShutdownPhase):
        self._name = name
        self._phase = phase
        self.startup_called = False
        self.startup_order_log: list = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def shutdown_phase(self) -> ShutdownPhase:
        return self._phase

    async def shutdown(self, timeout_sec: float = 5.0) -> None:
        pass

    async def on_startup(self) -> None:
        self.startup_called = True
        self.startup_order_log.append(self._name)


class SlowStartupHook(LifecycleHook):
    """Hook that takes too long to start."""

    @property
    def name(self) -> str:
        return "slow_starter"

    @property
    def shutdown_phase(self) -> ShutdownPhase:
        return ShutdownPhase.BACKGROUND

    async def shutdown(self, timeout_sec: float = 5.0) -> None:
        pass

    async def on_startup(self) -> None:
        await asyncio.sleep(100)


class TestStartupAll:
    """Blueprint 17.2: on_startup() + startup_all()."""

    @pytest.mark.asyncio
    async def test_startup_all_calls_hooks(self):
        """startup_all() calls on_startup() on all hooks."""
        mgr = LifecycleManager()
        h = StartupHook("test_hook", ShutdownPhase.INGRESS)
        mgr.register(h)
        started = await mgr.startup_all()
        assert h.startup_called is True
        assert "test_hook" in started

    @pytest.mark.asyncio
    async def test_startup_order_reverse_of_shutdown(self):
        """Startup order is reverse of shutdown order (NETWORKING first, INGRESS last)."""
        order: list[str] = []
        mgr = LifecycleManager()

        class OrderTracker(LifecycleHook):
            def __init__(self, name_: str, phase_: ShutdownPhase):
                self._n = name_
                self._p = phase_

            @property
            def name(self) -> str:
                return self._n

            @property
            def shutdown_phase(self) -> ShutdownPhase:
                return self._p

            async def shutdown(self, timeout_sec: float = 5.0) -> None:
                pass

            async def on_startup(self) -> None:
                order.append(self._n)

        mgr.register(OrderTracker("ingress", ShutdownPhase.INGRESS))
        mgr.register(OrderTracker("net", ShutdownPhase.NETWORKING))
        mgr.register(OrderTracker("proc", ShutdownPhase.PROCESSING))

        await mgr.startup_all()
        assert order == ["net", "proc", "ingress"]

    @pytest.mark.asyncio
    async def test_startup_timeout_handling(self):
        """Slow hooks are skipped with timeout, not included in result."""
        mgr = LifecycleManager()
        mgr.register(SlowStartupHook())
        started = await mgr.startup_all(timeout_sec=0.1)
        assert "slow_starter" not in started
