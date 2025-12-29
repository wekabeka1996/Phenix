"""Pytest configuration for shadow_execpos tests.

This conftest ensures all ExecPosRuntimeV2 instances use ExecutionService
instead of ExecutorPool to prevent real HTTP calls during tests.
"""

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import (
    ExecPosRuntimeV2,
)


# Store original __init__ for patching
_original_init = ExecPosRuntimeV2.__init__


def _patched_init(self, *args, **kwargs):
    """Patched __init__ that sets _use_executor_pool=False after creation."""
    _original_init(self, *args, **kwargs)
    # CRITICAL: Disable ExecutorPool to prevent real HTTP calls in tests
    # Tests should mock execution_service instead
    self._use_executor_pool = False


@pytest.fixture(autouse=True)
def disable_executor_pool_for_all_tests(monkeypatch):
    """Autouse fixture that patches ExecPosRuntimeV2 to disable ExecutorPool.

    Without this, tests that mock execution_service will still route through
    ExecutorPool, causing real HTTP calls and failures like:
    "Request URL is missing an 'http://' or 'https://' protocol"
    """
    monkeypatch.setattr(ExecPosRuntimeV2, "__init__", _patched_init)
    yield


@pytest.fixture
def use_executor_pool_enabled(monkeypatch):
    """Fixture to explicitly enable ExecutorPool for specific tests.

    Use this fixture when you want to test ExecutorPool integration:

        def test_with_executor_pool(use_executor_pool_enabled):
            # This test will use ExecutorPool
            pass
    """
    monkeypatch.setattr(ExecPosRuntimeV2, "__init__", _original_init)
    yield
