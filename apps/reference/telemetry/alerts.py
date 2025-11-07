"""
Alert Manager for Phenix v1.

Provides alerting capabilities for critical system events:
- Risk gate violations (>80%)
- Circuit breaker active
- WAL size thresholds
- Other critical system alerts

Supports Slack notifications and structured logging.
"""

import time
import logging
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

try:
    import requests  # type: ignore
except ImportError:
    requests = None


class AlertLevel(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Alert types for categorization."""
    RISK_GATE = "risk_gate"
    CIRCUIT_BREAKER = "circuit_breaker"
    WAL_SIZE = "wal_size"
    SYSTEM_HEALTH = "system_health"
    TRADE_EXECUTION = "trade_execution"


@dataclass
class Alert:
    """Alert data structure."""
    alert_id: str
    level: AlertLevel
    alert_type: AlertType
    title: str
    message: str
    details: Dict[str, Any]
    timestamp: float
    resolved: bool = False
    resolved_at: Optional[float] = None


class AlertManager:
    """
    Manages system alerts with deduplication, escalation, and notifications.

    Features:
    - Alert deduplication (same alert within time window)
    - Slack notifications
    - Structured logging
    - Alert resolution tracking
    """

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # Alert configuration
        alert_config = config.get("alerts", {})
        self.slack_webhook_url = alert_config.get("slack_webhook_url")
        self.deduplication_window_sec = alert_config.get(
            "deduplication_window_sec", 300)  # 5 min
        self.max_alerts_per_hour = alert_config.get("max_alerts_per_hour", 10)

        # State
        self.active_alerts: Dict[str, Alert] = {}
        # alert_key -> last_timestamp
        self.recent_alerts: Dict[str, float] = {}
        self.alert_count_this_hour = 0
        self.hour_start_time = time.time()

        # Thresholds
        thresholds = alert_config.get("thresholds", {})
        self.risk_gate_threshold = thresholds.get("risk_gate_percent", 80)
        self.wal_size_threshold_mb = thresholds.get("wal_size_mb", 500)
        self.cb_active_threshold_sec = thresholds.get("cb_active_sec", 60)

        self.logger.info(
            f"AlertManager initialized: slack={bool(self.slack_webhook_url)}, "
            f"dedup_window={self.deduplication_window_sec}s, "
            f"risk_threshold={self.risk_gate_threshold}%, "
            f"wal_threshold={self.wal_size_threshold_mb}MB"
        )

    def _get_alert_key(self, alert_type: AlertType, title: str) -> str:
        """Generate deduplication key for alert."""
        return f"{alert_type.value}:{title}"

    def _should_deduplicate(self, alert_key: str) -> bool:
        """Check if alert should be deduplicated."""
        now = time.time()
        last_alert_time = self.recent_alerts.get(alert_key, 0)
        return (now - last_alert_time) < self.deduplication_window_sec

    def _should_rate_limit(self) -> bool:
        """Check if we're rate limited."""
        now = time.time()

        # Reset counter if hour has passed
        if now - self.hour_start_time >= 3600:
            self.alert_count_this_hour = 0
            self.hour_start_time = now

        return self.alert_count_this_hour >= self.max_alerts_per_hour

    def _send_slack_notification(self, alert: Alert) -> None:
        """Send alert to Slack if configured."""
        if not self.slack_webhook_url or not requests:
            return

        try:
            # Format Slack message
            color = {
                AlertLevel.INFO: "good",
                AlertLevel.WARNING: "warning",
                AlertLevel.ERROR: "danger",
                AlertLevel.CRITICAL: "danger"
            }.get(alert.level, "warning")

            slack_payload = {
                "attachments": [{
                    "color": color,
                    "title": f"🚨 {alert.title}",
                    "text": alert.message,
                    "fields": [
                        {"title": "Type", "value": alert.alert_type.value, "short": True},
                        {"title": "Level", "value": alert.level.value, "short": True},
                        {"title": "Time", "value": time.strftime(
                            "%H:%M:%S", time.localtime(alert.timestamp)), "short": True}
                    ],
                    "footer": "Phenix Alert Manager",
                    "ts": int(alert.timestamp)
                }]
            }

            # Add details if present
            if alert.details:
                details_text = "\n".join(
                    f"• {k}: {v}" for k, v in alert.details.items())
                slack_payload["attachments"][0]["fields"].append({  # type: ignore
                    "title": "Details",
                    "value": details_text,
                    "short": False
                })

            response = requests.post(
                self.slack_webhook_url,
                json=slack_payload,
                timeout=5
            )
            response.raise_for_status()

            self.logger.info(
                f"✅ Slack notification sent for alert {alert.alert_id}")

        except Exception as e:
            self.logger.error(f"❌ Failed to send Slack notification: {e}")

    def _log_alert(self, alert: Alert) -> None:
        """Log alert to structured logger."""
        log_data = {
            "alert_id": alert.alert_id,
            "level": alert.level.value,
            "type": alert.alert_type.value,
            "title": alert.title,
            "message": alert.message,
            "details": alert.details,
            "timestamp": alert.timestamp,
            "resolved": alert.resolved
        }

        if alert.resolved and alert.resolved_at:
            log_data["resolved_at"] = alert.resolved_at

        # Log with appropriate level
        log_method = {
            AlertLevel.INFO: self.logger.info,
            AlertLevel.WARNING: self.logger.warning,
            AlertLevel.ERROR: self.logger.error,
            AlertLevel.CRITICAL: self.logger.critical
        }.get(alert.level, self.logger.warning)

        log_method(f"ALERT: {alert.title} - {alert.message}", extra=log_data)

    def raise_alert(
        self,
        level: AlertLevel,
        alert_type: AlertType,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Raise a new alert.

        Returns alert_id if alert was created, None if deduplicated or rate limited.
        """
        alert_key = self._get_alert_key(alert_type, title)

        # Check deduplication
        if self._should_deduplicate(alert_key):
            self.logger.debug(f"Alert deduplicated: {title}")
            return None

        # Check rate limiting
        if self._should_rate_limit():
            self.logger.warning(f"Alert rate limited: {title}")
            return None

        # Create alert
        alert_id = f"{alert_type.value}_{int(time.time())}_{hash(title) % 1000}"
        alert = Alert(
            alert_id=alert_id,
            level=level,
            alert_type=alert_type,
            title=title,
            message=message,
            details=details or {},
            timestamp=time.time()
        )

        # Store alert
        self.active_alerts[alert_id] = alert
        self.recent_alerts[alert_key] = alert.timestamp
        self.alert_count_this_hour += 1

        # Send notifications
        self._send_slack_notification(alert)
        self._log_alert(alert)

        self.logger.info(f"🚨 Alert raised: {title} ({alert_id})")
        return alert_id

    def resolve_alert(self, alert_id: str, resolution_note: str = "") -> bool:
        """
        Resolve an active alert.

        Returns True if alert was resolved, False if not found.
        """
        if alert_id not in self.active_alerts:
            return False

        alert = self.active_alerts[alert_id]
        alert.resolved = True
        alert.resolved_at = time.time()
        alert.details["resolution_note"] = resolution_note

        # Send resolution notification
        self._send_slack_notification(alert)
        self._log_alert(alert)

        # Remove from active alerts
        del self.active_alerts[alert_id]

        self.logger.info(f"✅ Alert resolved: {alert.title} ({alert_id})")
        return True

    def check_risk_gate(self, risk_gate_percent: float) -> None:
        """Check risk gate threshold and raise alert if exceeded."""
        if risk_gate_percent > self.risk_gate_threshold:
            self.raise_alert(
                level=AlertLevel.CRITICAL,
                alert_type=AlertType.RISK_GATE,
                title="Risk Gate Violation",
                message=f"Risk gate at {risk_gate_percent:.1f}% exceeds threshold {self.risk_gate_threshold}%",
                details={
                    "current_percent": risk_gate_percent,
                    "threshold_percent": self.risk_gate_threshold
                }
            )

    def check_circuit_breaker(self, cb_active: bool, cb_duration_sec: float) -> None:
        """Check circuit breaker status and raise alert if active too long."""
        if cb_active and cb_duration_sec > self.cb_active_threshold_sec:
            self.raise_alert(
                level=AlertLevel.ERROR,
                alert_type=AlertType.CIRCUIT_BREAKER,
                title="Circuit Breaker Active",
                message=f"Circuit breaker has been active for {cb_duration_sec:.0f}s",
                details={
                    "active_duration_sec": cb_duration_sec,
                    "threshold_sec": self.cb_active_threshold_sec
                }
            )

    def check_wal_size(self, wal_size_mb: float) -> None:
        """Check WAL size and raise alert if exceeds threshold."""
        if wal_size_mb > self.wal_size_threshold_mb:
            self.raise_alert(
                level=AlertLevel.WARNING,
                alert_type=AlertType.WAL_SIZE,
                title="WAL Size Threshold Exceeded",
                message=f"WAL size {wal_size_mb:.1f}MB exceeds threshold {self.wal_size_threshold_mb}MB",
                details={
                    "current_size_mb": wal_size_mb,
                    "threshold_mb": self.wal_size_threshold_mb
                }
            )

    def get_active_alerts(self) -> Dict[str, Alert]:
        """Get all active (unresolved) alerts."""
        return self.active_alerts.copy()

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        return {
            "active_alerts": len(self.active_alerts),
            "alerts_this_hour": self.alert_count_this_hour,
            "recent_alert_keys": list(self.recent_alerts.keys())
        }
