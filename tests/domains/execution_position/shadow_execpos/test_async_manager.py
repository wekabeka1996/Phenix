"""
Tests for ExecPosAsyncManager
=============================

Tests the minimal async loop manager for ExecPos domain.
"""
import pytest
import asyncio

from apps.reference.domains.execution_position.shadow_execpos.async_manager import ExecPosAsyncManager


@pytest.fixture
def manager():
    mgr = ExecPosAsyncManager()
    return mgr


def test_init_no_loop(manager):
    """Verify manager starts with no loop set."""
    assert manager._loop is None


@pytest.mark.asyncio
async def test_set_and_get_loop(manager):
    """Verify set_async_loop stores the loop and get_async_loop retrieves it."""
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)

    assert manager._loop is loop
    assert manager.get_async_loop() is loop


@pytest.mark.asyncio
async def test_get_loop_fallback_to_running(manager):
    """Verify get_async_loop falls back to running loop when no loop set."""
    running_loop = asyncio.get_running_loop()

    # No loop explicitly set
    assert manager._loop is None

    # Should return the running loop
    resolved = manager.get_async_loop()
    assert resolved is running_loop


@pytest.mark.asyncio
async def test_get_loop_prefers_explicit(manager):
    """Verify explicitly set loop takes precedence over running loop."""
    running_loop = asyncio.get_running_loop()

    # Create a new loop (but don't run it)
    explicit_loop = asyncio.new_event_loop()
    try:
        manager.set_async_loop(explicit_loop)

        # Should return the explicit loop, not the running one
        resolved = manager.get_async_loop()
        assert resolved is explicit_loop
        assert resolved is not running_loop
    finally:
        explicit_loop.close()


@pytest.mark.asyncio
async def test_get_loop_ignores_closed(manager):
    """Verify closed loop is ignored and fallback is used."""
    running_loop = asyncio.get_running_loop()

    # Create and close a loop
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()

    manager.set_async_loop(closed_loop)

    # Should fall back to running loop since explicit is closed
    resolved = manager.get_async_loop()
    assert resolved is running_loop


@pytest.mark.asyncio
async def test_clear(manager):
    """Verify clear() removes the stored loop."""
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)

    assert manager._loop is loop

    manager.clear()

    assert manager._loop is None


def test_get_loop_no_running_loop():
    """Verify get_async_loop handles case when no loop is running."""
    manager = ExecPosAsyncManager()

    # In a sync context with no running loop, should try get_event_loop
    # This may return a loop or None depending on Python version and context
    result = manager.get_async_loop()
    # Just verify it doesn't raise
    assert result is None or isinstance(result, asyncio.AbstractEventLoop)
