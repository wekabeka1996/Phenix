import time

from apps.reference.config_loader import ConfigLoader
from apps.reference.telemetry.alerts import AlertManager, AlertLevel, AlertType


def test_alert_manager_uses_config_ssot_not_env(monkeypatch):
    monkeypatch.setenv("AURORA_ALERTS_RISK_GATE_PCT", "1")
    monkeypatch.setenv("AURORA_ALERTS_DEDUP_WINDOW_SEC", "1")

    config = ConfigLoader().load_config()
    manager = AlertManager(config)

    # Must come from Pydantic config defaults, not env overrides
    assert manager.risk_gate_threshold == 80
    assert manager.deduplication_window_sec == 300


def test_recent_alerts_prunes_old_and_caps_size(monkeypatch):
    config = ConfigLoader().load_config()
    manager = AlertManager(config)

    manager.deduplication_window_sec = 1
    manager.recent_alerts_max_keys = 3

    now = time.time()
    manager.recent_alerts = {
        "k_old_1": now - 10,
        "k_old_2": now - 20,
        "k_new_1": now,
    }

    manager._prune_recent_alerts()
    assert "k_old_1" not in manager.recent_alerts
    assert "k_old_2" not in manager.recent_alerts
    assert "k_new_1" in manager.recent_alerts

    for idx in range(10):
        manager.raise_alert(
            level=AlertLevel.WARNING,
            alert_type=AlertType.SYSTEM_HEALTH,
            title=f"health_{idx}",
            message="test",
        )

    assert len(manager.recent_alerts) <= 3
