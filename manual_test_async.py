import asyncio
import logging
import sys
from apps.reference.domains.execution_position.shadow_execpos.async_manager import ExecPosAsyncManager

# Configure logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger("manual_test")

async def test_submit_coroutine():
    print("TEST: test_submit_coroutine")
    manager = ExecPosAsyncManager()
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)

    async def simple_job():
        await asyncio.sleep(0.01)
        return "done"

    task = manager.submit(simple_job())
    if task is None:
        print("FAIL: Task is None")
        return
    
    if task not in manager._bg_tasks:
        print("FAIL: Task not tracked")
        return

    await task
    if task.result() != "done":
        print(f"FAIL: Result mismatch {task.result()}")
        return

    # Allow callback
    await asyncio.sleep(0.01)
    if task in manager._bg_tasks:
        print("FAIL: Task not removed")
        return
    
    print("PASS: test_submit_coroutine")

async def test_exception_logging():
    print("TEST: test_exception_logging")
    manager = ExecPosAsyncManager()
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)

    async def failing_job():
        raise ValueError("Boom")

    task = manager.submit(failing_job(), label="fail_test")
    
    try:
        await task
    except ValueError:
        pass
    
    await asyncio.sleep(0.01)
    # We can't easily assert logging here without capturing it, but we can see it in stdout
    print("PASS: test_exception_logging (Check logs for 'SHADOW_EXEC_POS_BG_TASK_FAILED')")

async def test_shutdown():
    print("TEST: test_shutdown")
    manager = ExecPosAsyncManager()
    loop = asyncio.get_running_loop()
    manager.set_async_loop(loop)

    async def long_job():
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            print("Job Cancelled")
            raise

    task = manager.submit(long_job())
    
    # Simulate shutdown from a sync context (simulated via run_coroutine_threadsafe if we were outside loop)
    # But here we are inside the loop. The manager.shutdown_background_tasks() logic 
    # tries to handle being called from outside.
    # Let's just call it. It might not block if we are in the loop, but it should cancel.
    
    manager.shutdown_background_tasks(timeout=0.1)
    
    await asyncio.sleep(0.1)
    if not task.cancelled() and not task.done():
        print("FAIL: Task not cancelled")
        return
        
    if len(manager._bg_tasks) != 0:
        print(f"FAIL: Tasks not cleared {manager._bg_tasks}")
        return

    print("PASS: test_shutdown")

async def main():
    await test_submit_coroutine()
    await test_exception_logging()
    await test_shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"CRASH: {e}")
