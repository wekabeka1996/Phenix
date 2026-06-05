from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import threading
import time
from typing import Any, Callable

from vfoundation.core.fsm_emit_compat import emit_compat
from vfoundation.core.protocol import Message
from vfoundation.core import FSMCore


class RetryScheduler:
    """
    Reliable retry scheduler for EVT:INTENT_DEFERRED events.

    TASK24.E: Hardening contracts:
    - Scheduler-owned attempt counter (SSOT)
    - Bounded retries by config
    - Fail-fast without a running loop (no pending leaks)
    - emit_compat-only emission
    """

    def __init__(
        self,
        fsm: FSMCore,
        logger: logging.Logger | None = None,
        default_max_attempts: int = 5,
        min_retry_delay_ms: int = 500,
        backoff_factor: float = 2.0,
        jitter_ms: int = 0,
        on_no_loop: Callable[[], None] | None = None,
    ):
        self.fsm = fsm
        self.logger = logger or logging.getLogger("RetryScheduler")
        self.default_max_attempts = default_max_attempts
        self.min_retry_delay_ms = min_retry_delay_ms
        self.backoff_factor = float(backoff_factor)
        self.jitter_ms = int(jitter_ms)

        if self.backoff_factor < 1.0:
            raise ValueError("RetryScheduler.backoff_factor must be >= 1.0")
        if self.jitter_ms < 0:
            raise ValueError("RetryScheduler.jitter_ms must be >= 0")

        self._pending: dict[str, dict[str, Any]] = {}
        self._attempts: dict[str, int] = {}
        self._attempts_payload_hash: dict[str, str] = {}
        self._retry_tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_no_loop = on_no_loop or (lambda: None)

        self.logger.info(
            "RetryScheduler initialized (max_attempts=%d, min_delay_ms=%d, backoff=%.3f, jitter_ms=%d)",
            default_max_attempts,
            min_retry_delay_ms,
            self.backoff_factor,
            self.jitter_ms,
        )

    def _inc_no_loop_metric(self) -> None:
        try:
            self._on_no_loop()
        except Exception as exc:
            self.logger.debug("RetryScheduler no-loop callback failed: %r", exc)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        if loop is None or not loop.is_running():
            self._inc_no_loop_metric()
            raise RuntimeError("RetryScheduler.bind_loop requires a running asyncio loop")
        self._loop = loop
        with self._lock:
            pending_keys = list(self._pending.keys())
        for retry_key in pending_keys:
            next_allowed_ts = int(self._pending.get(retry_key, {}).get("next_allowed_ts", 0))
            if next_allowed_ts > 0:
                self._schedule_retry(retry_key, next_allowed_ts)

    def register_deferred(self, deferred_payload: dict[str, Any]) -> bool:
        if self._loop is None or not self._loop.is_running():
            # Fail-closed: do not raise; drop intent and increment metric.
            self._inc_no_loop_metric()
            return False

        loop_thread_id = getattr(self._loop, "_thread_id", None)
        if loop_thread_id is not None and loop_thread_id != threading.get_ident():
            # TASK47-FIX: Support off-loop thread registration via call_soon_threadsafe.
            # This is critical for strategies running in background threads (e.g. MeanReversion).
            self.logger.info("RetryScheduler: off-loop thread registration for %s; scheduling via call_soon_threadsafe", deferred_payload.get("retry_key"))
            self._loop.call_soon_threadsafe(self.register_deferred, deferred_payload)
            return True

        retry_key = deferred_payload.get("retry_key")
        if not retry_key:
            self.logger.warning("RetryScheduler: deferred_payload missing retry_key, ignoring")
            return False

        symbol = deferred_payload.get("symbol", "UNKNOWN")
        reason = deferred_payload.get("reason", "unknown")
        next_allowed_ts = int(deferred_payload.get("next_allowed_ts", 0) or 0)
        requested_max_attempts = int(deferred_payload.get("max_attempts", self.default_max_attempts) or self.default_max_attempts)
        max_attempts = min(requested_max_attempts, int(self.default_max_attempts))
        original_event = deferred_payload.get("original_event")
        if not isinstance(original_event, dict):
            self.logger.warning("RetryScheduler: deferred_payload missing/invalid original_event for %s", retry_key)
            return False

        event_name = original_event.get("event_name")
        payload_min = original_event.get("payload_min")
        if not event_name or not isinstance(payload_min, dict):
            self.logger.warning("RetryScheduler: %s has invalid original_event shape", retry_key)
            return False

        try:
            original_event_json = json.dumps(original_event, sort_keys=True, default=str, separators=(",", ":"))
        except Exception:
            original_event_json = str(original_event)
        payload_hash = hashlib.sha256(original_event_json.encode("utf-8")).hexdigest()

        with self._lock:
            prev_hash = self._attempts_payload_hash.get(retry_key)
            if prev_hash is not None and prev_hash != payload_hash:
                self._attempts[retry_key] = 0
            self._attempts_payload_hash[retry_key] = payload_hash

            self._pending[retry_key] = {
                "retry_key": retry_key,
                "symbol": symbol,
                "reason": reason,
                "next_allowed_ts": next_allowed_ts,
                "max_attempts": max_attempts,
                "original_event": original_event,
                "why_chain": deferred_payload.get("why_chain", []),
                "created_ts": int(deferred_payload.get("created_ts", int(time.time() * 1000))),
                "payload_hash": payload_hash,
            }

            last_attempt = int(self._attempts.get(retry_key, 0) or 0)
            next_attempt = last_attempt + 1
            self.logger.info(
                "RetryScheduler: Registered %s (symbol=%s, reason=%s, next_attempt=%d/%d, next_ts=%d)",
                retry_key,
                symbol,
                reason,
                next_attempt,
                max_attempts,
                next_allowed_ts,
            )

        self._schedule_retry(retry_key, next_allowed_ts)
        return True

    def _schedule_retry(self, retry_key: str, next_allowed_ts: int) -> None:
        if retry_key in self._retry_tasks:
            old_future = self._retry_tasks.pop(retry_key)
            try:
                old_future.cancel()
            except Exception:
                pass

        if self._loop is None or not self._loop.is_running():
            self._inc_no_loop_metric()
            # Fail-closed: do not raise; clear pending to avoid zombies.
            with self._lock:
                self._pending.pop(retry_key, None)
            return

        loop_thread_id = getattr(self._loop, "_thread_id", None)
        if loop_thread_id is not None and loop_thread_id != threading.get_ident():
            self._inc_no_loop_metric()
            self.logger.error("RetryScheduler._schedule_retry called off-loop thread; dropping %s", retry_key)
            with self._lock:
                self._pending.pop(retry_key, None)
            return

        with self._lock:
            pending = self._pending.get(retry_key)
            last_attempt = int(self._attempts.get(retry_key, 0) or 0)

        if not pending:
            return

        max_attempts = int(pending.get("max_attempts", self.default_max_attempts) or self.default_max_attempts)
        next_attempt = last_attempt + 1
        now_ms = int(time.time() * 1000)

        base_delay_ms = max(0, int(next_allowed_ts) - now_ms)
        backoff_delay_ms = int(self.min_retry_delay_ms * (self.backoff_factor ** max(next_attempt - 1, 0)))
        delay_ms = max(base_delay_ms, backoff_delay_ms)
        if self.jitter_ms > 0:
            delay_ms += random.randint(0, self.jitter_ms)

        async def _do_retry():
            delay_sec = max(0.0, delay_ms / 1000.0)
            self.logger.debug(
                "RetryScheduler: %s sleeping %.2fs before retry (attempt=%d/%d)",
                retry_key,
                delay_sec,
                next_attempt,
                max_attempts,
            )
            if delay_sec > 0:
                await asyncio.sleep(delay_sec)
            await self._execute_retry(retry_key)

        task = self._loop.create_task(_do_retry())
        self._retry_tasks[retry_key] = task

        def _observe_task_result(done_task: asyncio.Task[None]) -> None:
            try:
                done_task.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self.logger.error("RetryScheduler: Task for %s failed: %r", retry_key, exc)
                with self._lock:
                    self._pending.pop(retry_key, None)
                self._retry_tasks.pop(retry_key, None)

        task.add_done_callback(_observe_task_result)

    async def _execute_retry(self, retry_key: str) -> None:
        with self._lock:
            pending = self._pending.get(retry_key)
            if not pending:
                self.logger.debug("RetryScheduler: %s no longer pending, skip retry", retry_key)
                return

            max_attempts = int(pending.get("max_attempts", self.default_max_attempts) or self.default_max_attempts)
            symbol = pending.get("symbol", "UNKNOWN")
            original_event = pending.get("original_event", {}) or {}
            why_chain = pending.get("why_chain", []) or []
            created_ts = int(pending.get("created_ts", 0) or 0)
            original_reason = pending.get("reason", "unknown")

            last_attempt = int(self._attempts.get(retry_key, 0) or 0)
            attempt = last_attempt + 1
            self._attempts[retry_key] = attempt

            self._pending.pop(retry_key, None)
            self._retry_tasks.pop(retry_key, None)

        if attempt > max_attempts:
            await self._drop_intent(
                retry_key=retry_key,
                symbol=symbol,
                drop_reason="MAX_ATTEMPTS_EXCEEDED",
                original_reason=original_reason,
                attempt=attempt,
                max_attempts=max_attempts,
                original_event=original_event,
                why_chain=list(why_chain) + ["max_attempts_exceeded"],
                created_ts=created_ts,
            )
            with self._lock:
                self._attempts.pop(retry_key, None)
                self._attempts_payload_hash.pop(retry_key, None)
            return

        event_name = original_event.get("event_name", "")
        payload_min = original_event.get("payload_min", {})

        if not event_name or not payload_min:
            self.logger.error("RetryScheduler: %s has invalid original_event, dropping", retry_key)
            await self._drop_intent(
                retry_key=retry_key,
                symbol=symbol,
                drop_reason="STALE_INTENT",
                original_reason=original_reason,
                attempt=attempt,
                max_attempts=max_attempts,
                original_event=original_event,
                why_chain=list(why_chain) + ["invalid_original_event"],
                created_ts=created_ts,
            )
            with self._lock:
                self._attempts.pop(retry_key, None)
                self._attempts_payload_hash.pop(retry_key, None)
            return

        if ":" in event_name:
            op, verb = event_name.split(":", 1)
        else:
            op, verb = "EVT", event_name

        retry_msg = Message(
            op=op,
            verb=verb,
            src="retry_scheduler",
            dst="*",
            rid=payload_min.get("rid", f"retry_{retry_key}_{attempt}"),
            pld=payload_min,
            why=f"retry_attempt_{attempt}_of_{max_attempts}",
        )

        self.logger.info(
            "RetryScheduler: Re-emitting %s for %s (attempt %d/%d)",
            event_name,
            symbol,
            attempt,
            max_attempts,
        )

        await emit_compat(self.fsm, retry_msg, logger=self.logger)

    async def _drop_intent(
        self,
        retry_key: str,
        symbol: str,
        drop_reason: str,
        original_reason: str,
        attempt: int,
        max_attempts: int,
        original_event: dict,
        why_chain: list,
        created_ts: int,
    ) -> None:
        dropped_ts = int(time.time() * 1000)

        drop_payload = {
            "retry_key": retry_key,
            "symbol": symbol,
            "drop_reason": drop_reason,
            "original_reason": original_reason,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "original_event": original_event,
            "why_chain": why_chain,
            "created_ts": created_ts,
            "dropped_ts": dropped_ts,
        }

        drop_msg = Message(
            op="EVT",
            verb="INTENT_DROPPED",
            src="retry_scheduler",
            dst="*",
            rid=f"drop_{retry_key}",
            pld=drop_payload,
            why=f"dropped_{drop_reason}",
        )

        self.logger.warning(
            "RetryScheduler: Dropping %s (reason=%s, attempts=%d/%d)",
            retry_key,
            drop_reason,
            attempt,
            max_attempts,
        )

        await emit_compat(self.fsm, drop_msg, logger=self.logger)

    def cancel_pending(self, retry_key: str) -> bool:
        with self._lock:
            if retry_key not in self._pending:
                return False

            pending = self._pending.pop(retry_key)
            _symbol = pending.get("symbol", "UNKNOWN")
            self._attempts.pop(retry_key, None)
            self._attempts_payload_hash.pop(retry_key, None)

        if retry_key in self._retry_tasks:
            task = self._retry_tasks.pop(retry_key)
            if not task.done():
                task.cancel()

        return True

    def clear_all_pending(self, emit_dropped: bool = True, drop_reason: str = "RESTART_NO_PERSISTENCE") -> int:
        with self._lock:
            pending_copy = dict(self._pending)
            self._pending.clear()
            attempts_copy = dict(self._attempts)
            self._attempts.clear()
            self._attempts_payload_hash.clear()

            for task in self._retry_tasks.values():
                if not task.done():
                    task.cancel()
            self._retry_tasks.clear()

        if not pending_copy:
            return 0

        if emit_dropped:
            if self._loop is None or not self._loop.is_running():
                self._inc_no_loop_metric()
                # Fail-closed: cannot emit without loop; just clear state.
                return len(pending_copy)

            loop_thread_id = getattr(self._loop, "_thread_id", None)
            if loop_thread_id is not None and loop_thread_id != threading.get_ident():
                self._inc_no_loop_metric()
                # Fail-closed: avoid cross-thread scheduling in restricted runtime.
                return len(pending_copy)

            dropped_ts = int(time.time() * 1000)
            for retry_key, pending in pending_copy.items():
                attempt = int(attempts_copy.get(retry_key, 0) or 0)
                drop_payload = {
                    "retry_key": retry_key,
                    "symbol": pending.get("symbol", "UNKNOWN"),
                    "drop_reason": drop_reason,
                    "original_reason": pending.get("reason", "unknown"),
                    "attempt": attempt,
                    "max_attempts": pending.get("max_attempts", self.default_max_attempts),
                    "original_event": pending.get("original_event", {}),
                    "why_chain": pending.get("why_chain", []) + [drop_reason.lower()],
                    "created_ts": pending.get("created_ts", 0),
                    "dropped_ts": dropped_ts,
                }
                drop_msg = Message(
                    op="EVT",
                    verb="INTENT_DROPPED",
                    src="retry_scheduler",
                    dst="*",
                    rid=f"drop_{retry_key}",
                    pld=drop_payload,
                    why=f"dropped_{drop_reason}",
                )
                self._loop.create_task(emit_compat(self.fsm, drop_msg, logger=self.logger))

        return len(pending_copy)

    def get_pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def get_pending_for_symbol(self, symbol: str) -> list[str]:
        with self._lock:
            return [k for k, v in self._pending.items() if v.get("symbol") == symbol]
