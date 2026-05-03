"""
FSM Core - Event Bus for FSM Applications

Provides a simple event-driven communication system for FSM components.
"""

from typing import Dict, List, Callable, Any, Optional
import logging
import threading
from .protocol import Message
from apps.reference.domains.execution_position.contract_layer.terminal_order_contracts import (
    normalize_terminal_order_event_payload,
)
from apps.reference.domains.execution_position.contract_layer.trade_intent_reject_contracts import (
    normalize_trade_intent_rejected_payload,
)
from apps.reference.domains.execution_position.contract_layer.trade_executed_contracts import (
    normalize_trade_executed_payload,
)


class InvalidMessagePayloadError(ValueError):
    """Raised when a message payload fails JSON schema validation."""
    pass


class FSMCore:
    """
    Simple FSM core interface for event-driven applications.

    Acts as an event bus that allows components to emit and listen for events.
    """

    _emit_compat_mode = "message"

    def __init__(self) -> None:
        """Initialize the FSM core with empty listeners registry."""
        self.listeners: Dict[str, List[Callable]] = {}
        self.domains: Dict[str, Any] = {}  # Domain registry
        # Module logger for structured logging
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()

    def listen(self, event_name: str, callback: Callable) -> None:
        """
        Register an event listener.

        Args:
            event_name: Name of the event to listen for (e.g., "EVT:TRADE_INTENT_PROPOSED")
            callback: Function to call when event is emitted
        """
        with self._lock:
            if event_name not in self.listeners:
                self.listeners[event_name] = []
            self.listeners[event_name].append(callback)

    def emit(
        self,
        event_name: Any,
        payload: Optional[Dict[str, Any]] = None,
        why: str = "",
        data_ref: Optional[List[str]] = None,
        rid: Optional[str] = None,
    ) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event_name: Name of the event to emit
            payload: Event payload data
            why: Reason for emitting the event
            data_ref: Optional WHY chain data reference
            rid: Optional request ID to pass through for envelope-level traceability.
                 If None, Message generates a new UUID (backward-compatible).
        """
        # Compatibility: allow emit(Message(...)) from legacy bridges/helpers.
        if isinstance(event_name, Message):
            msg = event_name
            event_name = f"{msg.op}:{msg.verb}"
            payload = dict(msg.pld or {})
            if not why:
                why = msg.why or ""
            if data_ref is None:
                data_ref = list(msg.data_ref or [])
            if rid is None:
                rid = msg.rid

        if not isinstance(event_name, str):
            raise TypeError(f"event_name must be str or Message, got {type(event_name).__name__}")

        if payload is None:
            payload = {}
        elif event_name in ("EVT:ORDER_REJECTED", "EVT:ORDER_STATE_CHANGED") and isinstance(payload, dict):
            payload = normalize_terminal_order_event_payload(
                event_name,
                payload,
                fallback_rid=rid,
            )
        elif event_name == "EVT:TRADE_INTENT_REJECTED" and isinstance(payload, dict):
            payload = normalize_trade_intent_rejected_payload(
                payload,
                fallback_rid=rid,
            )
        elif event_name == "EVT:TRADE_EXECUTED" and isinstance(payload, dict):
            payload = normalize_trade_executed_payload(
                payload,
                fallback_rid=rid,
                order_index=getattr(self, "order_index", None),
            )

        # Phase 14C: Message Schema Validation (Fail-Fast)
        try:
            from .schema_registry import get_global_registry
            from jsonschema.exceptions import ValidationError

            registry = get_global_registry()
            if registry:
                parts = event_name.split(":", 1)
                if len(parts) == 2:
                    op, verb = parts
                    validator = registry.get_validator(op, verb)
                    if validator:
                        validator.validate(payload)
                    elif registry.is_schema_missing(op, verb):
                        self.logger.warning(
                            "DEPRECATION: Emitting %s without JSON Schema validation. "
                            "Please define a schema in verb_registry_v1.yaml.", event_name
                        )
        except Exception as e:
            from jsonschema.exceptions import ValidationError
            if isinstance(e, ValidationError):
                self.logger.error("Payload validation failed for %s: %s", event_name, e.message)
                raise InvalidMessagePayloadError(f"Payload validation failed for {event_name}: {e.message}") from e
            else:
                self.logger.error("Schema validation system error for %s: %s", event_name, e)

        with self._lock:
            callbacks = list(self.listeners.get(event_name, []))

        shadow_journal = getattr(self, "_shadow_journal", None)
        if shadow_journal is not None:
            try:
                shadow_journal.record_bus_emit(
                    event_name=event_name,
                    payload=payload,
                    why=why,
                    data_ref=data_ref,
                    rid=rid,
                )
            except Exception as e:
                self.logger.error("Shadow journal emit capture failed for %s: %s", event_name, e)

        hardening = getattr(self, "_execution_truth_hardening", None)
        if hardening is not None and event_name == "EVT:TRADE_EXECUTED":
            try:
                decision = hardening.evaluate_trade_executed(
                    payload,
                    order_index=getattr(self, "order_index", None),
                )
                why_l = (why or "").lower()
                if why.startswith("WS_") or "websocket" in why_l:
                    source_component = "binance_ws_client"
                    source_path = "websocket:user_data_stream"
                    event_origin_type = "websocket"
                elif "polling" in why_l or "watchdog" in why_l:
                    source_component = "execution_position.watchdog"
                    source_path = "watchdog:rest_poll"
                    event_origin_type = "watchdog"
                else:
                    source_component = "vfoundation.fsm_core"
                    source_path = "execution:trade_executed_dedupe"
                    event_origin_type = "execution"

                if shadow_journal is not None and decision.degraded_identity:
                    notes = [decision.identity_quality]
                    if decision.trade_id_present:
                        notes.append("trade_id_included_in_shared_key")
                    for field in decision.missing_fields:
                        notes.append(f"missing_{field}")
                    shadow_journal.record_transition(
                        event_name="HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED",
                        source_component=source_component,
                        source_path=source_path,
                        event_origin_type=event_origin_type,
                        truth_owner="FSMCore",
                        payload=payload,
                        rid=rid,
                        notes=notes,
                    )

                if shadow_journal is not None and decision.warm_state_miss:
                    shadow_journal.record_transition(
                        event_name="HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_MISS",
                        source_component=source_component,
                        source_path=source_path,
                        event_origin_type=event_origin_type,
                        truth_owner="FSMCore",
                        payload=payload,
                        rid=rid,
                        notes=[
                            "terminal_identity_cache_exact_identity_not_seeded",
                            f"fill_key={decision.key}",
                            decision.identity_quality,
                        ],
                    )

                if decision.suppress:
                    if shadow_journal is not None:
                        if decision.warm_state_hit:
                            shadow_journal.record_transition(
                                event_name="HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_HIT",
                                source_component=source_component,
                                source_path=source_path,
                                event_origin_type=event_origin_type,
                                truth_owner="FSMCore",
                                payload=payload,
                                rid=rid,
                                notes=[
                                    "restart_seeded_terminal_identity_cache_hit",
                                    f"fill_key={decision.key}",
                                    decision.identity_quality,
                                ],
                            )
                        shadow_journal.record_transition(
                            event_name="HARDENING:TRADE_EXECUTED_SUPPRESSED",
                            source_component=source_component,
                            source_path=source_path,
                            event_origin_type=event_origin_type,
                            truth_owner="FSMCore",
                            payload=payload,
                            rid=rid,
                            notes=[
                                decision.reason,
                                f"fill_key={decision.key}",
                                decision.identity_quality,
                                "exact_identity" if decision.exact_identity else "non_exact_identity",
                                "cache_seed_hit" if decision.warm_state_hit else "process_local_hit",
                                *[f"missing_{field}" for field in decision.missing_fields],
                            ],
                        )
                    self.logger.warning(
                        "Suppressed duplicate EVT:TRADE_EXECUTED: %s (%s)",
                        decision.reason,
                        decision.key,
                    )
                    return
            except Exception as e:
                self.logger.exception("TRADE_EXECUTED hardening failed open for %s: %s", event_name, e)

        if callbacks:
            # Build Message kwargs — pass rid through if provided
            msg_kwargs: Dict[str, Any] = dict(
                op="EVT",
                verb=event_name.split(":")[1],  # Extract verb from EVT:VERB
                src="fsm_core",
                dst="any",
                pld=payload,
                why=why,
                data_ref=data_ref or [],
            )
            if rid is not None:
                msg_kwargs["rid"] = rid
            message = Message(**msg_kwargs)

            # Call all listeners
            for callback in callbacks:
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
        with self._lock:
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
