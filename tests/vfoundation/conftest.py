"""
Global test fixtures for tests/vfoundation suite.

Provides shared fixtures for all vfoundation tests, including
MockExecutionAdapter (moved from production code per Phase 9.3).
"""
from __future__ import annotations

import pytest

from tests.vfoundation.fixtures.mock_execution_adapter import MockExecutionAdapter
from vfoundation.core.adapters.execution_adapter import ExecutionMode


@pytest.fixture()
def mock_adapter_dry_run() -> MockExecutionAdapter:
    """MockExecutionAdapter in DRY_RUN mode. Suppress DeprecationWarning."""
    return MockExecutionAdapter(mode=ExecutionMode.DRY_RUN)


@pytest.fixture()
def mock_adapter_paper() -> MockExecutionAdapter:
    """MockExecutionAdapter in PAPER mode."""
    return MockExecutionAdapter(mode=ExecutionMode.PAPER)
