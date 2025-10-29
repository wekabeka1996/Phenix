"""
FSM Core - Event Bus for FSM Applications

Provides a simple event-driven communication system for FSM components.
"""
from typing import Dict, List, Callable, Any
import logging
from .protocol import Message


class FSMCore:
    """
    Simple FSM core interface for event-driven applications.

    Acts as an event bus that allows components to emit and listen for events.
    """

    def __init__(self) -> None:
        """Initialize the FSM core with empty listeners registry."""
        self.listeners: Dict[str, List[Callable]] = {}
        self.domains: Dict[str, Any] = {}  # Domain registry
        # Module logger for structured logging
        self.logger = logging.getLogger(__name__)

    def listen(self, event_name: str, callback: Callable) -> None:
        """
        Register an event listener.

        Args:
            event_name: Name of the event to listen for (e.g., "EVT:TRADE_INTENT_PROPOSED")
            callback: Function to call when event is emitted
        """
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload: Dict[str, Any], why: str) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event_name: Name of the event to emit
            payload: Event payload data
            why: Reason for emitting the event
        """
        if event_name in self.listeners:
            # Create Message object
            message = Message(
                op="EVT",
                verb=event_name.split(":")[1],  # Extract verb from EVT:VERB
                src="fsm_core",
                dst="any",
                pld=payload,
                why=why
            )

            # Call all listeners
            for callback in self.listeners[event_name]:
                try:
                    callback(message)
                except Exception as e:
                    # Log full stack trace and context for debugging
                    # Include exception message in the log to make errors easily searchable
                    self.logger.exception(
                        "CRITICAL: Unhandled exception in listener for event '%s': %s",
                        event_name,
                        str(e),
                    )

    def remove_listener(self, event_name: str, callback: Callable) -> None:
        """
        Remove an event listener.

        Args:
            event_name: Name of the event
            callback: The callback function to remove
        """
        if event_name in self.listeners:
            try:
                self.listeners[event_name].remove(callback)
                if not self.listeners[event_name]:
                    del self.listeners[event_name]
            except ValueError:
                pass  # Callback not found, ignore

    def register_domain(self, name: str, domain_instance: Any) -> None:
        """
        Register a domain instance in the FSM core.

        Args:
            name: Name of the domain
            domain_instance: The domain instance to register
        """
        self.domains[name] = domain_instance
        self.logger.info(f"Domain '{name}' registered in FSM core")

    def get_domain(self, name: str) -> Any:
        """
        Retrieve a registered domain instance.

        Args:
            name: Name of the domain

        Returns:
            Domain instance or None if not found
        """
        return self.domains.get(name)