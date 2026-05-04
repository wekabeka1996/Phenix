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

                # Verify signature
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

                    # Success path
                    self.cb.on_success()

                    # Remember results in both idempotency stores
                    self.idem.remember(msg.rid, res)

                    # Complete single-flight processing if using idempotent_key
                    if msg.idempotent_key:
                        self.idem.complete(msg.idempotent_key, res)

                    return res

                except Exception as e:
                    self.cb.on_failure()
                    error_msg = str(e)[:80] if str(e) else "handler_fail"
                    last_err = self._error_response(msg, "HANDLER_FAIL", error_msg)

                    # Wait before retry (except last attempt)
                    if attempt < policy.retries:
                        time.sleep(policy.backoff_ms(attempt) / 1000.0)

            return last_err if last_err else self._error_response(msg, "UNKNOWN", "unknown")

        finally:
            # Record timing for metrics
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            record_router_timing(duration_ms)

    def _error_response(self, msg: Message, verb: str, why: str, status_code: int = 400) -> Message:
        """Create standardized error response without WAL entry"""
        return Message(
            op="ERR",
            verb=verb,
            src="router",
            dst=msg.src,
            rid=msg.rid,
            why=why,
            pld={"status_code": status_code},
        )

    def _inflight_response(self, msg: Message) -> Message:
        """Create response for concurrent requests (single-flight)"""
        return Message(
            op="EVT",
            verb="INFLIGHT",
            src="router",
            dst=msg.src,
            rid=msg.rid,
            why="concurrent request processing",
            pld={"inflight": True, "retry_after_ms": 100},
        )
