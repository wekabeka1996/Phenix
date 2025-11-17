import sys
import asyncio


# On Windows, several async libraries (Tornado) expect the SelectorEventLoop.
# This test suite sometimes uses Tornado's AsyncIOMainLoop and proxies the
# running loop; ensure we set the policy early in the test process so plugins
# initialize correctly.
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        # If the policy is not available on the platform, ignore silently.
        pass
"""Pytest configuration for vfoundation tests."""

import sys
import pytest
from pathlib import Path

# Add project root, apps and vfoundation to path for imports BEFORE any tests run
project_root = Path(__file__).parent
apps_root = project_root / "apps"
# CRITICAL: vfoundation package root (where vfoundation/ module lives)
vfoundation_package_root = project_root / "vfoundation"
vfoundation_apps_root = project_root / "vfoundation" / "apps"


aurora_root = project_root / "aurora"

# Add to sys.path only once at the beginning
# NOTE: apps_root MUST come before vfoundation paths to use updated FSM implementations
for root_path in [
    project_root,
    apps_root,
    vfoundation_package_root,
    vfoundation_apps_root,
    aurora_root,
]:
    if str(root_path) not in sys.path:
        sys.path.insert(0, str(root_path))


def pytest_collection_modifyitems(config, items):
    """
    Reorder tests to run test_fsm_shadow_roundtrip FIRST.

    This ensures it runs before other tests cache the apps/ version of FSM modules.
    """
    shadow_tests = []
    other_tests = []

    for item in items:
        if "test_fsm_shadow_roundtrip.py" in str(item.fspath):
            shadow_tests.append(item)
        else:
            other_tests.append(item)

    # Shadow tests first, then everything else
    items[:] = shadow_tests + other_tests


def pytest_configure(config):
    """
    Force correct sys.path order BEFORE pytest starts collecting tests.

    This ensures apps/ is prioritized over vfoundation/apps for updated implementations.
    """
    # Ensure apps paths come BEFORE vfoundation paths for updated implementations
    vf_apps = str(vfoundation_apps_root)
    vf_pkg = str(vfoundation_package_root)
    apps = str(apps_root)

    # Remove all occurrences
    for path in [vf_apps, vf_pkg, apps, project_root]:
        while path in sys.path:
            sys.path.remove(path)

    # Re-add in correct order: project root first, then apps, then vfoundation
    sys.path.insert(0, vf_pkg)
    sys.path.insert(0, vf_apps)
    sys.path.insert(0, apps)
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session", autouse=True)
def cleanup_background_tasks():
    """Ensure all background tasks are cleaned up after test session."""
    yield
    # Force cleanup of any asyncio tasks or threads
    import asyncio
    import threading

    # Cancel any pending asyncio tasks
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
    except RuntimeError:
        pass

    # Log active threads for debugging
    active_threads = threading.enumerate()
    if len(active_threads) > 1:  # Main thread always exists
        print(
            f"\nWarning: {len(active_threads)} threads still active at test end")
        for thread in active_threads:
            if thread != threading.main_thread():
                print(f"   - {thread.name} (daemon={thread.daemon})")


@pytest.fixture(scope="function", autouse=True)
def reset_singletons():
    """Reset singleton instances between tests to prevent state leakage."""
    yield
    # Clear any cached singletons or global state
    # This prevents test interference


@pytest.fixture(scope="function", autouse=True)
def fix_event_loop():
    """Fix event loop for Windows Tornado compatibility."""
    import sys
    import asyncio
    if sys.platform.startswith("win"):
        try:
            # Force SelectorEventLoop for Tornado compatibility
            asyncio.set_event_loop_policy(
                asyncio.WindowsSelectorEventLoopPolicy())
            # Create a new event loop for this test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception:
            pass
    yield
    # Cleanup
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
    except Exception:
        pass
