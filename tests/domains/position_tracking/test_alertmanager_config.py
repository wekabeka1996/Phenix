"""AlertManager config validation tests for PositionTracking."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.reference.domains.position_tracking.position_tracking import PositionTracking


@pytest.fixture
def base_position_tracking_config() -> dict:
    return {
        "risk_budgets": {"BTCUSDT": {"max_position_size_usd": 10000}},
        "instruments": {"BTCUSDT": {"min_qty": 0.001}},
        "alerting": {
            "dedup_window_s": 45,
            "risk_threshold_pct": 7.5,
            "wal_threshold_mb": 12,
        },
        "alerts": {
            "thresholds": {"cb_active_sec": 90}
        },
    }


@pytest.fixture
def mock_fsm():
    fsm = MagicMock()
    fsm.listen = MagicMock()
    fsm.emit = MagicMock()
    return fsm


def test_alertmanager_config_accepts_numeric_values(mock_fsm, base_position_tracking_config):
    tracker = PositionTracking(
        fsm=mock_fsm, config=base_position_tracking_config)

    assert tracker.alert_manager is not None
    assert tracker.alert_manager.deduplication_window_sec == 45.0
    assert tracker.alert_manager.risk_gate_threshold == 7.5
    assert tracker.alert_manager.wal_size_threshold_mb == 12.0
    assert tracker.alert_manager.config["alerts"]["thresholds"]["cb_active_sec"] == 90


def test_alertmanager_config_rejects_non_numeric_values(mock_fsm, base_position_tracking_config):
    bad_value = MagicMock()
    base_position_tracking_config["alerting"]["dedup_window_s"] = bad_value

    with pytest.raises(ValueError):
        PositionTracking(fsm=mock_fsm, config=base_position_tracking_config)
