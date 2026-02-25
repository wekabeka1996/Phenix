"""
AlertManager framework — alert hook registry and dispatch.

Provides:
- AlertLevel: severity enum
- Alert: alert data container
- AlertHook: ABC for alert handlers
- AlertManager: registry + dispatcher

Constitution §10: alerts must be routable to multiple sinks (log, webhook, metrics).
All hooks are fire-and-forget (errors suppressed, logged).
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels (ascending)."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    """Alert data container."""
    level: AlertLevel
    title: str
    message: str
    rid: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.title) > 120:
            raise ValueError(f"Alert title must be ≤120 chars, got {len(self.title)}")


class AlertHook(ABC):
    """Abstract base class for alert handlers."""

    @abstractmethod
    def on_alert(self, alert: Alert) -> None:
        """Handle an alert. Must not raise — errors should be logged internally."""
        ...


class InMemoryAlertHook(AlertHook):
    """
    In-memory alert hook — stores alerts for test inspection.
    Thread-safe.
    """

    def __init__(self) -> None:
        self._alerts: List[Alert] = []
        self._lock = threading.Lock()

    def on_alert(self, alert: Alert) -> None:
        """Append alert to internal list."""
        with self._lock:
            self._alerts.append(alert)

    @property
    def alerts(self) -> List[Alert]:
        """Thread-safe snapshot of stored alerts."""
        with self._lock:
            return list(self._alerts)

    def clear(self) -> None:
        """Clear stored alerts."""
        with self._lock:
            self._alerts.clear()


class AlertManager:
    """
    Alert manager — registry of AlertHook instances, dispatches alerts.

    Thread-safe: register/fire may be called from multiple threads.
    Hook errors are caught and logged (fire-and-forget policy).

    Args:
        min_level: Minimum AlertLevel to dispatch. Alerts below this level
                   are silently dropped. Defaults to INFO (all alerts).
    """

    def __init__(self, min_level: AlertLevel = AlertLevel.INFO) -> None:
        self.min_level = min_level
        self._hooks: List[AlertHook] = []
        self._lock = threading.Lock()
        self._fired_total: int = 0
        self._error_total: int = 0

    def register(self, hook: AlertHook) -> None:
        """Register an alert hook. Thread-safe."""
        with self._lock:
            self._hooks.append(hook)

    def fire(self, alert: Alert) -> None:
        """
        Dispatch alert to all registered hooks if level >= min_level.

        Thread-safe. Hook errors do NOT propagate — they are logged.
        """
        levels = list(AlertLevel)
        if levels.index(alert.level) < levels.index(self.min_level):
            return  # below minimum level threshold

        with self._lock:
            hooks = list(self._hooks)
            self._fired_total += 1

        for hook in hooks:
            try:
                hook.on_alert(alert)
            except Exception as exc:
                with self._lock:
                    self._error_total += 1
                logger.error("AlertHook %s raised: %s", type(hook).__name__, exc)

    @property
    def fired_total(self) -> int:
        """Total number of alerts dispatched (above min_level)."""
        return self._fired_total

    @property
    def error_total(self) -> int:
        """Total number of hook errors suppressed."""
        return self._error_total

    def hook_count(self) -> int:
        """Number of registered hooks."""
        with self._lock:
            return len(self._hooks)
