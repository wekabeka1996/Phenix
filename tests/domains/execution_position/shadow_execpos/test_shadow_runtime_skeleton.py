"""
Tests for Shadow ExecPos Skeleton
=================================

Verifies the structural integrity and basic contract of the new modular architecture.
"""
import pytest
import asyncio
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import ExecutionStatus

@pytest.fixture
def mock_adapter():
    return MagicMock()

@pytest.fixture
def mock_price_service():
    return MagicMock()

@pytest.fixture
def runtime(mock_adapter, mock_price_service):
    config = {"mode": "test"}
    return ExecPosRuntimeV2(config, mock_adapter, mock_price_service)

@pytest.mark.asyncio
async def test_runtime_instantiation(runtime):
    """Verify the runtime initializes all components."""
    assert runtime.async_manager is not None
    assert runtime.execution_service is not None
    assert runtime.gatekeeper is not None
    assert runtime.watchdog is not None

@pytest.mark.asyncio
async def test_runtime_methods_no_error(runtime):
    """Verify basic lifecycle methods do not crash."""
    # Hydrate
    runtime.hydrate({"some": "state"})

    # Metrics
    metrics = runtime.get_metrics()
    assert isinstance(metrics, dict)
    assert metrics["status"] == "healthy"

    # Handle
    await runtime.handle({"type": "TEST_EVENT"})

    # Shutdown
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_async_manager_minimal():
    """Verify minimal AsyncManager methods."""
    from apps.reference.domains.execution_position.shadow_execpos.async_manager import ExecPosAsyncManager

    manager = ExecPosAsyncManager()
    loop = asyncio.get_running_loop()

    manager.set_async_loop(loop)
    assert manager.get_async_loop() == loop

    # Clear
    manager.clear()
    assert manager._loop is None

    # Should fall back to running loop
    assert manager.get_async_loop() == loop


def test_types_import():
    """Verify types can be imported and used."""
    status = ExecutionStatus.SUBMITTED
    assert status.value == "SUBMITTED"
