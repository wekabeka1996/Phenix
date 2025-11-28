# apps/reference/orchestrator/utils_event_bus.py
"""
Simple event bus implementation for local use when FSMCore is not available.

Provides a simple pub-sub mechanism for internal event routing with
Message-like object compatibility for FSMCore interoperability.
"""

from typing import Dict, List, Callable, Any, Optional
import logging

logger = logging.getLogger(__name__)


class LocalBus:
    """
    Simple event bus for local event handling.
    Used as fallback when FSMCore is not available.

    Provides listen/emit/unlisten interface compatible with FSMCore.
    """

    def __init__(self) -> None:
        """Initialize the event bus with an empty listeners dict."""
        self._listeners: Dict[str, List[Callable]] = {}

    def listen(self, event_name: str, callback: Callable) -> None:
        """
        Register a callback for an event.

        Args:
            event_name: Event name (e.g., "EVT:ORDER_ACK")
            callback: Callable to invoke when event is emitted
        """
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)
        logger.debug(f"Registered listener for {event_name}")

    def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None) -> None:
        """
        Emit an event to all registered listeners.

        Creates a Message-like dict for FSMCore compatibility.

        Args:
            event_name: Event name (e.g., "EVT:TRADE_EXECUTED")
            payload: Event payload dict
            why: Reason/context for the event
            data_ref: Optional data references
        """
        if event_name in self._listeners:
            # Create a Message-like object for compatibility
            message = {
                'rid': payload.get('rid', ''),
                'pld': payload,
                'data_ref': data_ref or [],
                'op': event_name.split(':')[0] if ':' in event_name else 'EVT',
                'verb': event_name.split(':')[1] if ':' in event_name else event_name,
                'why': why,
            }
            for callback in self._listeners[event_name]:
                try:
                    callback(message)
                except Exception as e:
                    logger.warning(
                        "LOCALBUS_LISTENER_ERROR",
                        extra={
                            "event": event_name,
                            "error": str(e),
                            "why": why,
                        },
                    )
        else:
            logger.debug(f"No listeners for event {event_name}")

    def unlisten(self, event_name: str, callback: Callable) -> None:
        """
        Unregister a callback for an event.

        Args:
            event_name: Event name
            callback: Callable to remove
        """
        if event_name in self._listeners:
            try:
                self._listeners[event_name].remove(callback)
                logger.debug(f"Unregistered listener for {event_name}")
            except ValueError:
                pass  # Callback not registered
