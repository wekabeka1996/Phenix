"""
Local event bus for ExecPosFSM when global FSM is not available.

Provides a simple pub-sub mechanism for internal event routing.
"""

import logging
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger(__name__)


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

    def emit(
        self,
        event: str,
        payload: Any = None,
        why: Optional[str] = None,
        data_ref: Optional[List[str]] = None
    ) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event: Event name
            payload: Event payload (typically a dict or Message)
            why: Optional reason/context (for compatibility with FSMCore)
            data_ref: Optional data references (for compatibility with FSMCore)
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
                    logger.error(f"[LocalBus] Error in callback for {event}: {e}", exc_info=True)

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
