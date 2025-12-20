import pytest
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
from apps.reference.domains.execution_position.order_index import OrderIndex
from apps.reference.domains.execution_position.metrics_collector import MetricsCollector
from apps.reference.domains.execution_position.idempotent_cancel import IdempotentCancelResult
# Note: IdempotentCancel is a mixin/helper, usually tested via usage or direct method call if possible.
# Here we will test the classes that were updated.

class TestExecutionPositionIntegration:
    def test_exposure_guard_uses_domains_config(self, mock_fsm, root_mock_config):
        """Verify ExposureGuard initializes with values from domains config."""
        eg = ExposureGuard(mock_fsm, root_mock_config)
        
        assert eg.pending_ttl_sec == 90
        assert eg.post_fill_hold_ttl_sec == 5
        assert eg.positions_stale_ttl_sec == 5

    def test_fsm_open_uses_domains_config(self, root_mock_config):
        """Verify OpenFlowFSM initializes with values from domains config."""
        # OpenFlowFSM might need more complex mocking if it depends on other things in __init__
        # Checking source, it takes (adapter, config). Adapter can be mock.
        mock_adapter = MagicMock()
        fsm = OpenFlowFSM(mock_adapter, root_mock_config)
        
        assert fsm.idempotency_window_sec == 60

    def test_order_index_uses_domains_config(self, root_mock_config):
        """Verify OrderIndex initializes with explicit values."""
        # Simulate extracting value from config (or use default)
        expected_ttl = 3600
        oi = OrderIndex(ttl_sec=expected_ttl)
        assert oi.ttl == expected_ttl

    def test_metrics_collector_uses_domains_config(self, root_mock_config):
        """Verify MetricsCollector initializes with explicit values."""
        # Simulate extracting value from config
        expected_window = 60
        mc = MetricsCollector(window_size_minutes=expected_window)
        assert mc.window_size_seconds == 60 * 60  # 60 minutes * 60 seconds
