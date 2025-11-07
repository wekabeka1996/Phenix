# apps/reference/orchestrator/utils_event_bus.py
"""
Simple event bus implementation for local use when FSMCore is not available.
"""

from typing import Dict, List, Callable, Any, Optional
import logging

logger = logging.getLogger(__name__)


class LocalBus:
    """
    Simple event bus for local event handling.
    Used as fallback when FSMCore is not available.
    """

    def __init__(self) -> None:
        self.listeners: Dict[str, List[Callable]] = {}

    def listen(self, event_name: str, callback: Callable) -> None:
        """Register an event listener."""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)
        logger.debug(f"Registered listener for {event_name}")

    def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None) -> None:
        """Emit an event to all registered listeners."""
        if event_name in self.listeners:
            # Create a Message-like object for compatibility
            message = {
                'rid': payload.get('rid', ''),
                'pld': payload,
                'data_ref': data_ref or [],
                'op': event_name.split(':')[0] if ':' in event_name else 'EVT',
                'verb': event_name.split(':')[1] if ':' in event_name else event_name
            }
            for callback in self.listeners[event_name]:
                try:
                    callback(message)
                except Exception as e:
                    logger.error(
                        f"Error in event listener for {event_name}: {e}")
        else:
            logger.debug(f"No listeners for event {event_name}")
