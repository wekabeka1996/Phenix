"""
Diagnostic script to measure FSM event chain execution time.
Run this to identify which listener is slow.
"""
import time
import functools
from typing import Callable, Any

# Patch to measure listener execution time
_original_callbacks = {}

def timing_wrapper(name: str, original_func: Callable) -> Callable:
    """Wrap a function to measure its execution time."""
    @functools.wraps(original_func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = original_func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 10:  # Log if > 10ms
            print(f"⏱️  SLOW: {name} took {elapsed_ms:.1f}ms")
        return result
    return wrapper

def patch_fsm_emit(fsm):
    """Patch FSM.emit to measure each listener's execution time."""
    original_emit = fsm.emit
    
    def timed_emit(event_name: str, payload, why: str, data_ref=None):
        print(f"\n📤 emit({event_name})")
        start_total = time.perf_counter()
        
        if event_name in fsm.listeners:
            for i, callback in enumerate(fsm.listeners[event_name]):
                cb_name = f"{callback.__module__}.{callback.__qualname__}"
                start = time.perf_counter()
                try:
                    from vfoundation.core.fsm_core import Message
                    message = Message(
                        op="EVT",
                        verb=event_name.split(":")[1],
                        src="fsm_core",
                        dst="any",
                        pld=payload,
                        why=why,
                        data_ref=data_ref or [],
                    )
                    callback(message)
                except Exception as e:
                    print(f"  ❌ {cb_name}: {e}")
                elapsed_ms = (time.perf_counter() - start) * 1000
                status = "🔴" if elapsed_ms > 50 else "🟡" if elapsed_ms > 10 else "🟢"
                print(f"  {status} [{i}] {cb_name}: {elapsed_ms:.1f}ms")
        
        total_ms = (time.perf_counter() - start_total) * 1000
        print(f"  📊 Total: {total_ms:.1f}ms\n")
    
    fsm.emit = timed_emit
    return fsm


if __name__ == "__main__":
    print("=== FSM Event Chain Timing Diagnostic ===")
    print("Import this module and call patch_fsm_emit(fsm) to enable timing.")
    print("Then emit events normally and check console output.")
