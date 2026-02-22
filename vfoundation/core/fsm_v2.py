"""
FSMv2 — Stateful domain FSM engine with guards and transition tables.

Additive extension: Does NOT replace FSMCore (event bus). Instead, FSMv2
can be wired into FSMCore listeners to enforce state transitions formally.

Usage:
    fsm = FSMv2("order_lifecycle")
    fsm.register_state("IDLE")
    fsm.register_state("PENDING")
    fsm.register_state("PLACED")
    fsm.register_state("FILLED", terminal=True)
    fsm.register_state("CANCELLED", terminal=True)

    fsm.register_transition("IDLE", "CMD:OPEN", "PENDING", guard=lambda m: m.pld.get("qty", 0) > 0)
    fsm.register_transition("PENDING", "EVT:ORDER_PLACED", "PLACED")
    fsm.register_transition("PLACED", "EVT:ORDER_FILL", "FILLED")
    fsm.register_transition("PLACED", "CMD:CANCEL", "CANCELLED")

    result = fsm.handle("my_key", msg)  # Returns (new_state, response_msg | None)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .protocol import Message

LOG = logging.getLogger(__name__)

# Constitution v2.2 limits
MAX_STATES_PER_FSM = 20
MAX_VERBS_PER_DOMAIN = 12


@dataclass
class TransitionRule:
    """A single allowed transition in the FSM."""

    from_state: str
    event: str  # "OP:VERB" format, e.g. "CMD:OPEN"
    to_state: str
    guard: Optional[Callable[[Message], bool]] = None
    action: Optional[Callable[[Message], Optional[Message]]] = None


@dataclass
class StateInfo:
    """Metadata about a registered state."""

    name: str
    terminal: bool = False
    on_enter: Optional[Callable[[str, str, Message], None]] = None  # (key, state, msg)
    on_exit: Optional[Callable[[str, str, Message], None]] = None


class FSMv2:
    """
    Stateful FSM engine with guards, transition tables, and per-key state tracking.

    Thread-safe. Designed to coexist with FSMCore event bus.

    Invariants (Constitution v2.2 §3):
        - Max 20 states per FSM
        - Fail-closed: unregistered transitions → ERR:NO_TRANSITION
        - why is mandatory on every Message
        - Audit: all transitions logged
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._states: Dict[str, StateInfo] = {}
        self._transitions: List[TransitionRule] = []
        self._initial_state: Optional[str] = None
        self._state_store: Dict[str, str] = {}  # key → current state
        self._lock = threading.RLock()

        # Metrics
        self.metrics = _FSMv2Metrics()

    # ── State registration ───────────────────────────────────────────

    def register_state(
        self,
        name: str,
        *,
        terminal: bool = False,
        initial: bool = False,
        on_enter: Optional[Callable[[str, str, Message], None]] = None,
        on_exit: Optional[Callable[[str, str, Message], None]] = None,
    ) -> None:
        """
        Register a state in this FSM.

        Args:
            name: State name (e.g. "IDLE", "PENDING", "FILLED")
            terminal: If True, no transitions out of this state are allowed
            initial: If True, this is the initial state for new keys
            on_enter: Callback(key, state, msg) called on state entry
            on_exit: Callback(key, state, msg) called on state exit
        """
        if len(self._states) >= MAX_STATES_PER_FSM:
            raise ValueError(
                f"FSM '{self.name}' already has {MAX_STATES_PER_FSM} states "
                f"(Constitution §3: max {MAX_STATES_PER_FSM})"
            )
        if name in self._states:
            raise ValueError(f"State '{name}' already registered in FSM '{self.name}'")

        self._states[name] = StateInfo(
            name=name, terminal=terminal, on_enter=on_enter, on_exit=on_exit
        )
        if initial:
            if self._initial_state is not None:
                raise ValueError(
                    f"FSM '{self.name}' already has initial state '{self._initial_state}'"
                )
            self._initial_state = name

    # ── Transition registration ──────────────────────────────────────

    def register_transition(
        self,
        from_state: str,
        event: str,
        to_state: str,
        *,
        guard: Optional[Callable[[Message], bool]] = None,
        action: Optional[Callable[[Message], Optional[Message]]] = None,
    ) -> None:
        """
        Register a transition rule.

        Args:
            from_state: Source state name
            event: Event string in "OP:VERB" format (e.g. "CMD:OPEN")
            to_state: Target state name
            guard: Optional predicate — transition only fires if guard(msg) is True
            action: Optional side-effect — called after transition, may return response Message
        """
        if from_state not in self._states:
            raise ValueError(f"Unknown from_state '{from_state}' in FSM '{self.name}'")
        if to_state not in self._states:
            raise ValueError(f"Unknown to_state '{to_state}' in FSM '{self.name}'")
        if self._states[from_state].terminal:
            raise ValueError(
                f"Cannot register transition from terminal state '{from_state}'"
            )

        self._transitions.append(
            TransitionRule(
                from_state=from_state,
                event=event,
                to_state=to_state,
                guard=guard,
                action=action,
            )
        )

    # ── State query ──────────────────────────────────────────────────

    def get_state(self, key: str) -> Optional[str]:
        """Get current state for a key, or None if key not tracked."""
        with self._lock:
            return self._state_store.get(key)

    def set_state(self, key: str, state: str) -> None:
        """Force-set state for a key (for recovery/snapshots)."""
        if state not in self._states:
            raise ValueError(f"Unknown state '{state}' in FSM '{self.name}'")
        with self._lock:
            self._state_store[key] = state

    def tracked_keys(self) -> Set[str]:
        """Return set of all tracked keys."""
        with self._lock:
            return set(self._state_store.keys())

    # ── Core: handle ─────────────────────────────────────────────────

    def handle(self, key: str, msg: Message) -> Tuple[str, Optional[Message]]:
        """
        Process an event for a given key. Returns (new_state, optional_response).

        Fail-closed: if no matching transition → ERR:NO_TRANSITION.

        Args:
            key: Entity key (e.g. order_id, position_id)
            msg: Incoming message with op+verb

        Returns:
            (new_state, response_message_or_None)
        """
        event = f"{msg.op}:{msg.verb}"

        with self._lock:
            # Initialize state if key is new
            if key not in self._state_store:
                if self._initial_state is None:
                    self.metrics.errors += 1
                    return self._err(
                        msg, "NO_INITIAL_STATE",
                        f"FSM '{self.name}' has no initial state for key '{key}'"
                    )
                self._state_store[key] = self._initial_state

            current = self._state_store[key]

            # Find matching transition
            matching = [
                t for t in self._transitions
                if t.from_state == current and t.event == event
            ]

            if not matching:
                self.metrics.rejected += 1
                LOG.warning(
                    "FSMv2[%s] NO_TRANSITION key=%s state=%s event=%s",
                    self.name, key, current, event,
                )
                return current, self._err_msg(
                    msg, "NO_TRANSITION",
                    f"no transition from '{current}' on '{event}'"
                )

            # Evaluate guards
            selected: Optional[TransitionRule] = None
            for rule in matching:
                if rule.guard is None or rule.guard(msg):
                    selected = rule
                    break

            if selected is None:
                self.metrics.guard_rejected += 1
                LOG.info(
                    "FSMv2[%s] GUARD_REJECTED key=%s state=%s event=%s",
                    self.name, key, current, event,
                )
                return current, self._err_msg(
                    msg, "GUARD_REJECTED",
                    f"guard blocked transition from '{current}' on '{event}'"
                )

            # Execute transition
            old_state = current
            new_state = selected.to_state

            # on_exit callback
            exit_cb = self._states[old_state].on_exit
            if exit_cb:
                try:
                    exit_cb(key, old_state, msg)
                except Exception as e:
                    LOG.exception("FSMv2[%s] on_exit error: %s", self.name, e)

            # Update state
            self._state_store[key] = new_state

            # on_enter callback
            enter_cb = self._states[new_state].on_enter
            if enter_cb:
                try:
                    enter_cb(key, new_state, msg)
                except Exception as e:
                    LOG.exception("FSMv2[%s] on_enter error: %s", self.name, e)

            self.metrics.transitions += 1
            LOG.debug(
                "FSMv2[%s] TRANSITION key=%s %s → %s on %s",
                self.name, key, old_state, new_state, event,
            )

            # Execute action
            response: Optional[Message] = None
            if selected.action:
                try:
                    response = selected.action(msg)
                except Exception as e:
                    LOG.exception("FSMv2[%s] action error: %s", self.name, e)
                    self.metrics.errors += 1

            return new_state, response

    # ── Introspection ────────────────────────────────────────────────

    def get_transition_table(self) -> List[Dict[str, str]]:
        """Return a human-readable transition table."""
        return [
            {
                "from": t.from_state,
                "event": t.event,
                "to": t.to_state,
                "guarded": t.guard is not None,
            }
            for t in self._transitions
        ]

    def get_registered_states(self) -> List[str]:
        """Return list of registered state names."""
        return list(self._states.keys())

    def snapshot(self) -> Dict[str, str]:
        """Return a copy of the full state store (for DR snapshots)."""
        with self._lock:
            return dict(self._state_store)

    def restore(self, state_store: Dict[str, str]) -> None:
        """Restore state store from a DR snapshot."""
        for state in state_store.values():
            if state not in self._states:
                raise ValueError(f"Unknown state '{state}' in snapshot")
        with self._lock:
            self._state_store = dict(state_store)

    # ── Private helpers ──────────────────────────────────────────────

    def _err(
        self, msg: Message, verb: str, why: str
    ) -> Tuple[str, Optional[Message]]:
        return "", self._err_msg(msg, verb, why)

    def _err_msg(self, msg: Message, verb: str, why: str) -> Message:
        return Message(
            op="ERR",
            verb=verb,
            src=f"fsmv2:{self.name}",
            dst=msg.src,
            rid=msg.rid,
            why=why,
        )


@dataclass
class _FSMv2Metrics:
    transitions: int = 0
    rejected: int = 0
    guard_rejected: int = 0
    errors: int = 0
