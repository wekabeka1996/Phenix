from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.config_loader import get_config
import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath('.'))


async def test_order_guardian_initialization():
    """Test OrderGuardian initialization and polling startup."""
    print("=== TESTING OrderGuardian Initialization ===")

    try:
        # Load config
        config = get_config()

        print("✅ Config loaded successfully")

        # Create FSM instance (this should initialize OrderGuardian)
        fsm = ExecPosFSM(config, None, shadow_mode=False)

        print("✅ ExecPosFSM created")

        # Check if OrderGuardian was initialized
        if hasattr(fsm, 'order_guardian') and fsm.order_guardian:
            print("✅ OrderGuardian initialized")

            # Debug config reading
            print(f"Config type: {type(config)}")
            if hasattr(config, 'execution'):
                print(f"Config has execution: {hasattr(config, 'execution')}")
                if hasattr(config.execution, 'order_guardian'):
                    print(
                        f"Config.execution has order_guardian: {hasattr(config.execution, 'order_guardian')}")
                    if hasattr(config.execution.order_guardian, 'poll_interval_ms'):
                        print(
                            f"Config.execution.order_guardian.poll_interval_ms: {config.execution.order_guardian.poll_interval_ms}")
                elif isinstance(config.execution, dict):
                    print(f"Config.execution as dict: {config.execution}")
                    if 'order_guardian' in config.execution:
                        print(
                            f"Config.execution['order_guardian']: {config.execution['order_guardian']}")

            # Check OrderGuardian initialization details
            print(f"OrderGuardian type: {type(fsm.order_guardian)}")
            print(
                f"OrderGuardian has _impl: {hasattr(fsm.order_guardian, '_impl')}")
            if hasattr(fsm.order_guardian, '_impl'):
                impl = fsm.order_guardian._impl
                print(f"_impl type: {type(impl)}")
                print(
                    f"_impl has poll_interval_ms: {hasattr(impl, 'poll_interval_ms')}")
                if hasattr(impl, 'poll_interval_ms'):
                    print(f"_impl poll_interval_ms: {impl.poll_interval_ms}")

            # Check poll interval
            if hasattr(fsm.order_guardian, 'poll_interval_ms'):
                poll_interval = fsm.order_guardian.poll_interval_ms
                print(f"✅ OrderGuardian poll_interval_ms: {poll_interval}")

                if poll_interval == 5000:
                    print("✅ SUCCESS: poll_interval_ms correctly set to 5000ms")
                    return True
                else:
                    print(
                        f"❌ FAIL: poll_interval_ms is {poll_interval}, expected 5000")
                    return False
            elif hasattr(fsm.order_guardian, '_impl') and hasattr(fsm.order_guardian._impl, 'poll_interval_ms'):
                poll_interval = fsm.order_guardian._impl.poll_interval_ms
                print(
                    f"✅ OrderGuardian._impl.poll_interval_ms: {poll_interval}")

                if poll_interval == 5000:
                    print("✅ SUCCESS: poll_interval_ms correctly set to 5000ms")

                    # Check if polling task was started
                    # Give a small delay for the task to be created
                    await asyncio.sleep(0.1)

                    if hasattr(fsm.order_guardian, '_impl'):
                        impl = fsm.order_guardian._impl
                        if hasattr(impl, '_poller_task') and impl._poller_task is not None:
                            print("✅ OrderGuardian polling task started")
                            return True
                        else:
                            print("❌ FAIL: OrderGuardian polling task not started")
                            return False
                    else:
                        if hasattr(fsm.order_guardian, '_poller_task') and fsm.order_guardian._poller_task is not None:
                            print("✅ OrderGuardian polling task started")
                            return True
                        else:
                            print("❌ FAIL: OrderGuardian polling task not started")
                            return False
                else:
                    print(
                        f"❌ FAIL: poll_interval_ms is {poll_interval}, expected 5000")
                    return False
            else:
                print("❌ FAIL: OrderGuardian has no poll_interval_ms attribute")
                return False

        else:
            print("❌ FAIL: OrderGuardian not initialized")
            return False

    except Exception as e:
        print(f"❌ ERROR during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_order_guardian_initialization())
    if success:
        print("\n🎉 TEST PASSED: OrderGuardian initialization successful")
        sys.exit(0)
    else:
        print("\n💥 TEST FAILED: OrderGuardian initialization issues")
        sys.exit(1)
