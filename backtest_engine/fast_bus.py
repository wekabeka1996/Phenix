"""
BacktestFastBus — Phase 4: Fast-Path / Bypass EventBus

Drop-in replacement for FSMCore used EXCLUSIVELY during backtest runs (turbo_mode="phase4").
Eliminates overhead from:
  - JSON Schema validation (not needed in controlled backtest data)
  - threading.RLock acquire/release (single-threaded backtest loop)
  - Message() dataclass allocation (skipped entirely)
  - dict copy for payload (passed by reference)

Equivalence contract:
  - Same listener registry interface (listen, emit, remove_listener, register_domain, get_domain)
  - Payload is passed as-is (dict), exactly like FSMCore in non-strict mode
  - No WAL writes in fast-path; WAL is not needed for backtest transactional integrity
  - On exception in callback, logs and continues (same behavior as FSMCore)

Design decisions:
  - `emit()` is a tight inner loop, no try/except around the callback in the happy path
  - `listen()` / `remove_listener()` are called at startup only — not perf-critical
  - `register_domain()` / `get_domain()` are pass-through for interface parity

Usage:
    from backtest_engine.fast_bus import BacktestFastBus
    fast_bus = BacktestFastBus()
    # copy listeners from existing FSMCore
    fast_bus.copy_from(fsm)
    # or pass as event_bus directly if building engine fresh
"""

import logging
from typing import Any, Callable, Dict, List, Optional

LOG = logging.getLogger(__name__)


class BacktestFastBus:
    """
    Ultra-lightweight event bus for single-threaded backtest replay.
    
    API surface is compatible with FSMCore so it can be passed as `event_bus`
    to BacktestEngine without any other changes at call sites.
    """

    __slots__ = ("listeners", "domains", "_listeners_cache")

    def __init__(self) -> None:
        # We use plain dicts; no RLock needed (single-threaded).
        self.listeners: Dict[str, List[Callable]] = {}
        self.domains: Dict[str, Any] = {}
        # Snapshot cache: rebuilt on each `listen()` / `remove_listener()` to
        # avoid repeated list() copy inside the hot-path `emit()`.
        self._listeners_cache: Dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # Registration API
    # ------------------------------------------------------------------

    def listen(self, event_name: str, callback: Callable) -> None:
        """Register a callback for an event (called at startup only)."""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)
        # Invalidate snapshot cache
        self._listeners_cache.pop(event_name, None)

    def remove_listener(self, event_name: str, callback: Callable) -> None:
        """Unregister a callback (called rarely)."""
        if event_name in self.listeners:
            try:
                self.listeners[event_name].remove(callback)
                self._listeners_cache.pop(event_name, None)
                if not self.listeners[event_name]:
                    del self.listeners[event_name]
            except ValueError:
                pass

    def register_domain(self, name: str, domain_instance: Any) -> None:
        """Register a domain instance (interface parity with FSMCore)."""
        self.domains[name] = domain_instance

    def get_domain(self, name: str) -> Any:
        """Retrieve a registered domain instance."""
        return self.domains.get(name)

    # ------------------------------------------------------------------
    # Emit — hot path
    # ------------------------------------------------------------------

    def emit(
        self,
        event_name: Any,
        payload: Optional[Dict[str, Any]] = None,
        why: str = "",
        data_ref: Optional[List[str]] = None,
        rid: Optional[str] = None,
    ) -> None:
        """
        Emit event directly to registered callbacks.

        NO schema validation, NO Message allocation, NO lock.
        Payload dict is passed directly to each callback as the first arg,
        mimicking how FSMCore callbacks receive `message.pld` via the
        on_bar_closed / on_tick handler signatures.

        NOTE: For compatibility with handlers that expect `Message`, we pass
        a thin `_FakeMessage` wrapper. This avoids touching all handler
        implementations while still bypassing the heavy Message dataclass
        path. The `_FakeMessage` is a simple object with `.pld`, `.why`,
        and `.rid` — all the attributes handler code actually accesses.
        """
        if payload is None:
            payload = {}

        # Fast-path cache lookup
        cbs = self._listeners_cache.get(event_name)
        if cbs is None:
            raw = self.listeners.get(event_name)
            if not raw:
                return
            cbs = tuple(raw)
            self._listeners_cache[event_name] = cbs

        msg = _FakeMessage(pld=payload, why=why, rid=rid, event_name=event_name)

        for callback in cbs:
            try:
                callback(msg)
            except Exception as exc:
                LOG.exception(
                    "BacktestFastBus: unhandled exception in listener for '%s': %s",
                    event_name,
                    exc,
                )

    def copy_from(self, fsm_core: Any) -> None:
        """
        Copy listener registry from an existing FSMCore into this bus.
        
        Call AFTER all domains have registered their listeners on `fsm_core`,
        then swap out `engine.event_bus = fast_bus` for the hot loop.
        """
        for event_name, cbs in fsm_core.listeners.items():
            self.listeners[event_name] = list(cbs)
            self._listeners_cache.pop(event_name, None)

        # Copy domain registry too
        for name, domain in fsm_core.domains.items():
            self.domains[name] = domain

        LOG.info(
            "BacktestFastBus: copied %d event subscriptions and %d domains from FSMCore.",
            len(self.listeners),
            len(self.domains),
        )


class _FakeMessage:
    """
    Thin wrapper that mimics the Message dataclass interface used by
    FSMCore handlers. Handlers typically access `.pld`, `.why`, `.rid`.
    
    We skip the full Message dataclass allocation (UUID generation,
    dataclass overhead, dict copy) while maintaining handler compatibility.
    """
    __slots__ = ("pld", "why", "rid", "op", "verb")

    def __init__(
        self,
        pld: Dict[str, Any],
        why: str = "",
        rid: Optional[str] = None,
        event_name: str = "",
    ) -> None:
        self.pld = pld
        self.why = why
        self.rid = rid
        # Some handlers access msg.op / msg.verb
        parts = event_name.split(":", 1)
        self.op = parts[0] if parts else ""
        self.verb = parts[1] if len(parts) > 1 else event_name
