"""
Local event bus for ExecPosFSM when global FSM is not available.

Provides a simple pub-sub mechanism for internal event routing.
"""

import logging
from typing import Callable, Dict, List, Any


LOG = logging.getLogger(__name__)


class LocalBus:
    """Simple local event bus for intra-domain communication."""

    def __init__(self):
        """Initialize the event bus with an empty listeners dict."""
        self._listeners: Dict[str, List[Callable]] = {}

    def listen(self, event: str, callback: Callable) -> None:
        """
        Register a callback for an event.

        Args:
            event: Event name (e.g., "EVT:ORDER_ACK")
            callback: Callable to invoke when event is emitted
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(self, event: str, payload: Any = None) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event: Event name
            payload: Event payload (typically a dict or Message)
        """
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    if payload is not None:
                        callback(payload)
                    else:
                        callback()
                except Exception as e:
                    # Log error but continue processing other listeners
                    LOG.warning(
                        "EXEC_POS_LOCALBUS_LISTENER_ERROR",
                        extra={
                            "event": event,
                            "error": str(e),
                            "why": "localbus_emit",
                        },
                    )

    def unlisten(self, event: str, callback: Callable) -> None:
        """
        Unregister a callback for an event.

        Args:
            event: Event name
            callback: Callable to remove
        """
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass  # Callback not registered
