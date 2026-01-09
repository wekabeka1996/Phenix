# VF-DICT-FORENSIC-03 — Как сейчас валидятся op/verb/TTL/security (без YAML)
Дата: 2026-01-08

## Message contract (op/verb/ttl)
### vfoundation/core/protocol.py (фрагменты)
```py
from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
import time
import uuid

Op = Literal["ASK", "DEC", "CMD", "EVT", "UPD", "ERR"]
IntentType = Literal["INQUIRY", "COMMAND", "PROPOSAL", "OBSERVATION", "DECLARATION"]


def truncate_why(why_text: Optional[str], max_len: int = 80) -> Optional[str]:
    """Truncate why field to max_len to comply with Message validation.

    Usage in bridge: why = truncate_why(long_why_string)
    """
    if why_text is None:
        return None
    if len(why_text) <= max_len:
        return why_text
    return why_text[:max_len]


class Message(BaseModel):
    v: int = 1
    op: Op
    verb: str
    src: str
    dst: str | Literal["any"]
    rid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parent_span_id: Optional[str] = None
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    ttl_ms: int = 2000
    key: Optional[str] = None
    idempotent_key: Optional[str] = None  # New field for TTL-based idempotency
    pld: Dict[str, Any] = Field(default_factory=dict)
    why: Optional[str] = None
    why_explain_ref: Optional[str] = None
    intent: Optional[IntentType] = None  # Message intent classification (v2.2)
    data_ref: List[str] = Field(default_factory=list)
    sig: Optional[str] = None
    mode: str = "live"  # Domain-level trading mode: live, backtest, paper
    # Mode-specific validation rule identifier
    mode_contract: Optional[str] = None
    corr_id: Optional[str] = None  # Correlation ID for order lifecycle tracing
    oco_group_id: Optional[str] = None  # OCO group ID for entry + SL/TP orders
    # Parent client order ID for SL/TP orders
    parent_client_order_id: Optional[str] = None
    link_ack_id: Optional[str] = None  # Link to exchange ACK order_id
    link_fill_id: Optional[str] = None  # Link to fill order_id for correlation

    @field_validator("ttl_ms")
    @classmethod
    def _ttl_positive(cls, v: int) -> int:
        if v <= 0 or v > 30000:
            raise ValueError("ttl_ms out of allowed range (1..30000)")
        return v

    @field_validator("why")
    @classmethod
    def _why_len(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 80:
            raise ValueError("why must be <=80 chars")
        return v

    def is_expired(self) -> bool:
        return (int(time.time() * 1000) - self.ts) > self.ttl_ms
```

## Router enforcement (TTL + signature + NO_ROUTE)
### vfoundation/core/routing.py (фрагменты)
```py
from __future__ import annotations
from typing import Callable, Dict, Tuple, Optional
from .protocol import Message
from .retry_cb import RetryPolicy, CircuitBreaker
from ..dr.wal import append as wal_append
from ..obs.debug_api import record_router_timing, record_timeout
from ..security.signing_ed25519 import verify
import time
import json


class SimpleIdempotencyStore:
    """Simple in-memory idempotency store for Router."""

    def __init__(self) -> None:
        self._store: Dict[str, Message] = {}
        self._inflight: Dict[str, bool] = {}
        # Simple metrics for compatibility
        self.metrics = type(
            "Metrics",
            (),
            {
                "idem_reserve_total": {},
                "idem_confirm_total": {},
                "idem_release_total": {},
                "idem_conflict_total": 0,
                "idem_busy_total": 0,
                "idem_retries_total": 0,
                "idem_cb_open_total": 0,
                "idem_acquired": 0,
                "idem_dedup": 0,
            },
        )()

    def seen(self, key: str) -> bool:
        """Check if key has been seen."""
        return key in self._store

    def get(self, key: str) -> Message:
        """Get stored message for key."""
        return self._store[key]

    def remember(self, key: str, msg: Message) -> None:
        """Store message for key."""
        self._store[key] = msg

    def begin(self, key: str) -> Dict[str, bool]:
        """Begin processing for idempotent key."""
        if key in self._store:
            self.metrics.idem_dedup += 1
            return {"dedup": True}
        if key in self._inflight:
            return {"inflight": True}
        self._inflight[key] = True
        self.metrics.idem_acquired += 1
        return {"acquired": True}

    def get_if_done(self, key: str) -> Optional[Message]:
        """Get result if processing is done."""
        return self._store.get(key)

    def complete(self, key: str, result: Message) -> None:
        """Complete processing for key."""
        self._store[key] = result
        self._inflight.pop(key, None)


class Router:
    def __init__(self) -> None:
        self.handlers: Dict[Tuple[str, str], Callable[[Message], Message]] = {}
        self.idem = SimpleIdempotencyStore()
        self.cb = CircuitBreaker()

    def register(self, op: str, verb: str, handler: Callable[[Message], Message]) -> None:
        self.handlers[(op, verb)] = handler

    def get_idempotency_metrics(self) -> Dict[str, int]:
        """Get idempotency metrics from store"""
        metrics = self.idem.metrics
        return {
            "idem_reserve_total": sum(metrics.idem_reserve_total.values()),
            "idem_confirm_total": sum(metrics.idem_confirm_total.values()),
            "idem_release_total": sum(metrics.idem_release_total.values()),
            "idem_conflict_total": metrics.idem_conflict_total,
            "idem_busy_total": metrics.idem_busy_total,
            "idem_retries_total": metrics.idem_retries_total,
            "idem_cb_open_total": metrics.idem_cb_open_total,
            "idem_acquired": metrics.idem_acquired,
            "idem_dedup": metrics.idem_dedup,
        }

    def route(self, msg: Message) -> Message:
        start_time = time.time()

        try:
            # Input validation - check why field length
            if msg.why and len(msg.why) > 80:
                return self._error_response(msg, "WHY_TOO_LONG", "why field exceeds 80 chars")

            # Signature verification for high-risk operations (DEC, CMD)
            if msg.op in ["DEC", "CMD"]:
                if not msg.sig:
                    return self._error_response(
                        msg, "SIGNATURE_REQUIRED", "DEC/CMD ops require signature", status_code=401
                    )

                # Verify signature (stub implementation)
                # Create canonical payload for verification (exclude sig field)
                msg_dict = msg.model_dump(exclude={"sig"})
                payload = json.dumps(msg_dict, sort_keys=True).encode()

                try:
                    signature_bytes = bytes.fromhex(msg.sig)
                    if not verify(payload, signature_bytes):
                        return self._error_response(
                            msg,
                            "SIGNATURE_INVALID",
                            "signature verification failed",
                            status_code=401,
                        )
                except Exception as e:
                    return self._error_response(
                        msg, "SIGNATURE_ERROR", f"signature error: {str(e)[:40]}", status_code=401
                    )

            # Check message expiry
            if msg.is_expired():
                record_timeout()
                return self._error_response(msg, "TIMEOUT", "expired")

            # Single-flight idempotency with begin/complete API
            if msg.idempotent_key:
                # Try to begin processing
                status = self.idem.begin(msg.idempotent_key)

                if status.get("dedup"):
                    # Already completed - return cached result
                    cached_result = self.idem.get_if_done(msg.idempotent_key)
                    if cached_result:
                        # Add dedup marker to response (create new Message with updated pld)
                        updated_pld = {**cached_result.pld, "dedup": True}
                        result: Message = cached_result.model_copy(update={"pld": updated_pld})
                        return result

                if status.get("inflight"):
                    # Another request is processing - return inflight response
                    return self._inflight_response(msg)

                if status.get("over_cap"):
                    # Admission control: too many concurrent requests - return inflight response
                    return self._inflight_response(msg)

                # status.get("acquired") == True - proceed with processing

            # Legacy RID-based idempotency (kept for backward compatibility)
            if self.idem.seen(msg.rid):
                prev_msg: Message = self.idem.get(msg.rid)
                return prev_msg

            # Find handler
            handler = self.handlers.get((msg.op, msg.verb))
            if not handler:
                return self._error_response(msg, "NO_ROUTE", "no route")

            # Check circuit breaker
            if not self.cb.allow():
                return self._error_response(msg, "CB_OPEN", "circuit open")

            # Execute with retry policy
            policy = RetryPolicy()
            last_err: Optional[Message] = None

            for attempt in range(policy.retries + 1):
                try:
                    # Write to WAL before processing (fail-closed approach)
                    wal_record = {
                        "rid": msg.rid,
                        "op": msg.op,
                        "verb": msg.verb,
                        "src": msg.src,
                        "dst": msg.dst,
                        "ts": msg.ts,
                        "why": msg.why,
                        "attempt": attempt,
                    }
                    wal_append(wal_record)

                    # Execute handler
                    res = handler(msg)

```

## TTL profiles (код, не YAML)
```py
TTL_PROFILES = {
    "critical": 50,
    "fast": 200,
    "normal": 2000,
    "ml_slow": 10000,
    "background": 30000,
}
DEFAULT_PROFILE = "normal"
```

## Signature (ed25519)
```py
from __future__ import annotations
from typing import Tuple
from nacl.signing import SigningKey, VerifyKey
try:
    from nacl.exceptions import BadSignatureError  # type: ignore
except Exception:  # local shim fallback
    from nacl import BadSignatureError  # type: ignore
import hashlib
import os


def kms_seed() -> bytes:
    seed = os.getenv("VFOUNDATION_KMS_SEED", "demo-seed").encode()
    return hashlib.sha256(seed).digest()


def load_keys() -> Tuple[SigningKey, VerifyKey]:
    sk = SigningKey(kms_seed())
    vk = sk.verify_key
    return sk, vk


def sign(payload: bytes) -> bytes:
    sk, _ = load_keys()
    return sk.sign(payload).signature


def verify(payload: bytes, signature: bytes) -> bool:
    _, vk = load_keys()
    try:
        vk.verify(payload, signature)
        return True
    except BadSignatureError:
        return False
```

## FSMCore event naming
```py
"""
FSM Core - Event Bus for FSM Applications

Provides a simple event-driven communication system for FSM components.
"""

from typing import Dict, List, Callable, Any, Optional
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

    def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event_name: Name of the event to emit
            payload: Event payload data
            why: Reason for emitting the event
            data_ref: Optional WHY chain data reference
        """
        if event_name in self.listeners:
            # Create Message object
            message = Message(
                op="EVT",
                verb=event_name.split(":")[1],  # Extract verb from EVT:VERB
                src="fsm_core",
                dst="any",
                pld=payload,
                why=why,
                data_ref=data_ref or [],
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
```

## Мапа «политика → где живёт → поведение»
- `op` allowlist: `vfoundation/core/protocol.py` (Literal Op).
- `verb` allowlist: отсутствует как явный реестр; ограничение косвенно через Router handlers (NO_ROUTE).
- TTL range: `vfoundation/core/protocol.py` (`ttl_ms` 1..30000).
- TTL expiry: `vfoundation/core/routing.py` (`msg.is_expired()` → TIMEOUT).
- Signature required: `vfoundation/core/routing.py` (DEC/CMD require sig).
- Signature algorithm/keys: `vfoundation/security/signing_ed25519.py` (seed from env).

## Что я доказал фактами
- Сейчас enforcement реализован в коде vfoundation, без чтения глобальных/доменных словарей.
