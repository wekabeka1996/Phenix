"""
Tests for ExecPosAsyncManager
=============================
"""
import pytest
import asyncio
import logging
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.shadow_execpos.async_manager import ExecPosAsyncManager

@pytest.fixture
def manager():
    mgr = ExecPosAsyncManager()
    return mgr

@pytest.mark.asyncio
async def test_submit_coroutine(manager):
    """Verify submitting a simple coroutine works and is tracked."""
    
    async def simple_job():
        await asyncio.sleep(0.01)
        return "done"
        
    # Set the current loop
    loop = asyncio.get_running_loop()
    print(f"DEBUG: Loop is {loop}")
    manager.set_async_loop(loop)
    
    task = manager.submit(simple_job())
    print(f"DEBUG: Task is {task}")
    assert task is not None
    assert task in manager._bg_tasks
    
    await task
    assert task.result() == "done"
    
    # Allow callback to run
    await asyncio.sleep(0.01)
    assert task not in manager._bg_tasks

@pytest.mark.asyncio
async def test_submit_callable(manager):
    """Verify submitting a callable returning a coroutine."""
    
    async def job():
        return "called"
        
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)
    
    task = manager.submit(job)
    assert task is not None
    await task
    assert task.result() == "called"

@pytest.mark.asyncio
async def test_exception_logging(manager, caplog):
    """Verify exceptions in background tasks are logged."""
    
    async def failing_job():
        raise ValueError("Boom")
        
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)
    
    with caplog.at_level(logging.ERROR):
        task = manager.submit(failing_job(), label="fail_test")
        assert task is not None
        
        # Wait for task to fail
        try:
            await task
        except ValueError:
            pass
            
        # Allow callback to run
        await asyncio.sleep(0.01)
        
        assert "SHADOW_EXEC_POS_BG_TASK_FAILED" in caplog.text
        assert "Boom" in caplog.text
        assert "fail_test" in caplog.text

@pytest.mark.asyncio
async def test_shutdown(manager):
    """Verify shutdown cancels tasks."""
    
    async def long_job():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass
            
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)
    
    task = manager.submit(long_job())
    assert task in manager._bg_tasks
    
    # We can't easily test the blocking shutdown from within the async loop 
    # because the implementation avoids blocking if running_loop is loop.
    # But we can call it and verify it cancels.
    
    manager.shutdown_background_tasks(timeout=0.1)
    
    await asyncio.sleep(0.01)
    assert task.cancelled() or task.done()
    assert len(manager._bg_tasks) == 0
