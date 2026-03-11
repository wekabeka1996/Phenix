"""Compatibility LocalBus for legacy alpha_search runtime imports."""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class LocalBus:
    """Simple local event bus compatible with legacy alpha_search runtime."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def listen(self, event: str, callback: Callable) -> None:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(
        self,
        event: Optional[str] = None,
        payload: Any = None,
        why: Optional[str] = None,
        data_ref: Optional[List[str]] = None,
        event_name: Optional[str] = None,
    ) -> None:
        target_event = event_name or event
        if not target_event:
            raise ValueError("LocalBus.emit requires 'event' or 'event_name'")

        wrapped_payload = payload
        if why is not None or data_ref is not None:
            wrapped_payload = {
                "pld": payload,
                "why": why,
                "data_ref": data_ref or [],
            }

        for callback in self._listeners.get(target_event, []):
            try:
                callback(wrapped_payload)
            except Exception as exc:
                logger.error(
                    "[LocalBus] Error in callback for %s: %s",
                    target_event,
                    exc,
                    exc_info=True,
                )

    def unlisten(self, event: str, callback: Callable) -> None:
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass
