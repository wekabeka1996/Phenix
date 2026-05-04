from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse

from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    record_failure_outcome,
)
from apps.reference.telemetry.metrics import inc_neocortex_async_forced_stop


def parse_tcp_endpoint(endpoint: str) -> Tuple[str, int]:
    """Parse tcp://host:port endpoint and return host, port."""

    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp":
        raise ValueError(f"Unsupported endpoint scheme: {endpoint}")
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Invalid endpoint: {endpoint}")
    return parsed.hostname, int(parsed.port)


@dataclass(frozen=True)
class ShadowTapDeliveryFailure:
    failure_class: str
    phase: str
    error_type: str
    error_message: str
    endpoint: str
    attempt: int = 0


def _classify_shadow_tap_delivery_failure(
    exc: BaseException,
    *,
    phase: str,
    endpoint: str,
    attempt: int = 0,
) -> ShadowTapDeliveryFailure:
    error_type = type(exc).__name__
    error_message = str(exc) or error_type
    normalized_phase = str(phase).lower()

    failure_class = "unknown"
    if isinstance(exc, socket.timeout):
        failure_class = "timeout"
    elif isinstance(exc, ConnectionRefusedError):
        failure_class = (
            "endpoint_unavailable"
            if normalized_phase in {"startup", "probe", "connect"}
            else "send_failed"
        )
    elif isinstance(exc, (BrokenPipeError, ConnectionResetError)):
        failure_class = "send_failed"
    elif isinstance(exc, OSError):
        errno = getattr(exc, "errno", None)
        if errno in {110, 10060}:
            failure_class = "timeout"
        elif errno in {111, 61, 10061}:
            failure_class = (
                "endpoint_unavailable"
                if normalized_phase in {"startup", "probe", "connect"}
                else "send_failed"
            )
        elif normalized_phase == "send":
            failure_class = "send_failed"
        elif normalized_phase in {"startup", "probe", "connect"}:
            failure_class = "connect_failed"
        else:
            failure_class = "unknown"
    elif normalized_phase == "queue":
        failure_class = "queue_overflow"

    return ShadowTapDeliveryFailure(
        failure_class=failure_class,
        phase=normalized_phase,
        error_type=error_type,
        error_message=error_message,
        endpoint=str(endpoint),
        attempt=int(attempt),
    )


class JsonlTcpServer:
    """Line-delimited JSON TCP server with threaded connection handling."""

    def __init__(
        self,
        endpoint: str,
        handler: Callable[[dict[str, Any]], None],
        *,
        stop_timeout_ms: int,
        logger: Optional[logging.Logger] = None,
        name: str = "jsonl_tcp_server",
    ) -> None:
        self.endpoint = endpoint
        self.handler = handler
        self.logger = logger or logging.getLogger(name)
        self.name = name
        self._stop_timeout_ms = int(stop_timeout_ms)
        if self._stop_timeout_ms < 1:
            raise ValueError("stop_timeout_ms must be >= 1")

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._state_lock = threading.Lock()
        self._handler_threads: set[threading.Thread] = set()
        self._active_connections: set[socket.socket] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._serve_loop, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._close_listening_socket()
        self._close_active_connections()

        deadline = time.monotonic() + (self._stop_timeout_ms / 1000.0)
        server_alive = self._join_thread_until_deadline(self._thread, deadline)
        if self._thread is not None and not self._thread.is_alive():
            self._thread = None

        handler_alive_count = 0
        for thread in self._snapshot_handler_threads():
            if self._join_thread_until_deadline(thread, deadline):
                handler_alive_count += 1
            else:
                with self._state_lock:
                    self._handler_threads.discard(thread)

        if server_alive or handler_alive_count > 0:
            self._record_unclean_shutdown(
                message="JSONL TCP server shutdown left owned threads alive",
                detail={
                    "server_thread_alive": server_alive,
                    "handler_threads_alive": handler_alive_count,
                },
            )

    def _record_unclean_shutdown(self, *, message: str, detail: object) -> None:
        inc_neocortex_async_forced_stop(
            component=self.name,
            reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN.value,
        )
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            FailureReasonCode.UNCLEAN_SHUTDOWN,
            location="domains/shadow_telemetry/ipc.py:JsonlTcpServer.stop",
            message=message,
            detail=detail,
        )
        self.logger.warning("%s: %s", self.name, message)

    def _join_thread_until_deadline(
        self,
        thread: threading.Thread | None,
        deadline: float,
    ) -> bool:
        if thread is None or not thread.is_alive():
            return False
        remaining = max(0.0, deadline - time.monotonic())
        thread.join(timeout=remaining)
        return thread.is_alive()

    def _snapshot_handler_threads(self) -> list[threading.Thread]:
        with self._state_lock:
            return list(self._handler_threads)

    def _close_listening_socket(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _close_active_connections(self) -> None:
        with self._state_lock:
            connections = list(self._active_connections)
        for conn in connections:
            try:
                conn.close()
            except OSError:
                pass

    def _serve_loop(self) -> None:
        srv: socket.socket | None = None
        try:
            host, port = parse_tcp_endpoint(self.endpoint)
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((host, port))
            srv.listen(64)
            srv.settimeout(1.0)
            self._socket = srv
            self.logger.info("%s listening on %s", self.name, self.endpoint)

            while not self._stop_event.is_set():
                try:
                    conn, _addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_event.is_set():
                        break
                    continue

                thread = threading.Thread(
                    target=self._handle_conn_thread,
                    args=(conn,),
                    name=f"{self.name}-handler",
                    daemon=True,
                )
                with self._state_lock:
                    self._handler_threads.add(thread)
                thread.start()
        except Exception as exc:
            if not self._stop_event.is_set():
                record_failure_outcome(
                    FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                    FailureReasonCode.HANDLER_FAILURE,
                    location="domains/shadow_telemetry/ipc.py:JsonlTcpServer._serve_loop",
                    message="JSONL TCP server loop failed",
                    detail=type(exc).__name__,
                )
                self.logger.exception(
                    "%s serve loop failed", self.name, exc_info=exc)
        finally:
            if srv is not None:
                try:
                    srv.close()
                except Exception:
                    pass
            self._socket = None

    def _handle_conn_thread(self, conn: socket.socket) -> None:
        current_thread = threading.current_thread()
        with self._state_lock:
            self._active_connections.add(conn)
        try:
            self._handle_conn(conn)
        except Exception as exc:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                FailureReasonCode.HANDLER_FAILURE,
                location="domains/shadow_telemetry/ipc.py:JsonlTcpServer._handle_conn_thread",
                message="JSONL TCP connection handler failed",
                detail=type(exc).__name__,
            )
            self.logger.exception(
                "%s connection handler failed", self.name, exc_info=exc)
        finally:
            with self._state_lock:
                self._active_connections.discard(conn)
                self._handler_threads.discard(current_thread)
            try:
                conn.close()
            except OSError:
                pass

    def _handle_conn(self, conn: socket.socket) -> None:
        with conn:
            try:
                stream = conn.makefile("r", encoding="utf-8")
            except Exception:
                return
            with stream:
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except (TypeError, ValueError) as exc:
                        self.logger.warning(
                            "%s failed to parse line: %s", self.name, exc)
                        continue

                    if not isinstance(payload, dict):
                        continue

                    try:
                        self.handler(payload)
                    except Exception as exc:
                        record_failure_outcome(
                            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                            FailureReasonCode.HANDLER_FAILURE,
                            location="domains/shadow_telemetry/ipc.py:JsonlTcpServer._handle_conn",
                            message="JSONL TCP server handler raised",
                            detail=type(exc).__name__,
                        )
                        self.logger.exception(
                            "%s handler raised", self.name, exc_info=exc)


class JsonlTcpQueueClient:
    """Bounded async-ish sender for JSONL payloads to a TCP endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        queue_maxsize: int,
        overflow_policy: str,
        stop_timeout_ms: int,
        logger: Optional[logging.Logger] = None,
        name: str = "jsonl_tcp_client",
        failure_reporter: Optional[Callable[[ShadowTapDeliveryFailure], None]] = None,
    ) -> None:
        self.endpoint = endpoint
        self.queue_maxsize = max(1, int(queue_maxsize))
        self.overflow_policy = str(overflow_policy)
        self._stop_timeout_ms = int(stop_timeout_ms)
        if self._stop_timeout_ms < 1:
            raise ValueError("stop_timeout_ms must be >= 1")
        self.logger = logger or logging.getLogger(name)
        self.name = name
        self._failure_reporter = failure_reporter

        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue(
            maxsize=self.queue_maxsize)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._sock_lock = threading.Lock()
        self._delivery_state_lock = threading.Lock()
        self._last_delivery_failure: Optional[ShadowTapDeliveryFailure] = None
        self._delivery_failure_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        deadline = time.monotonic() + (self._stop_timeout_ms / 1000.0)
        self.wait_until_idle(timeout_sec=self._stop_timeout_ms / 1000.0)
        self._close_socket()

        worker_alive = self._join_thread_until_deadline(self._thread, deadline)
        if self._thread is not None and not self._thread.is_alive():
            self._thread = None

        unfinished = self._unfinished_queue_items()
        if worker_alive or unfinished > 0:
            self._record_unclean_shutdown(
                detail={
                    "worker_thread_alive": worker_alive,
                    "unfinished_queue_items": unfinished,
                    "queue_depth": self.queue_depth(),
                }
            )

    def queue_depth(self) -> int:
        return int(self._queue.qsize())

    def has_delivery_failure(self) -> bool:
        with self._delivery_state_lock:
            return self._last_delivery_failure is not None

    def last_delivery_failure(self) -> Optional[ShadowTapDeliveryFailure]:
        with self._delivery_state_lock:
            return self._last_delivery_failure

    def delivery_failure_count(self) -> int:
        with self._delivery_state_lock:
            return int(self._delivery_failure_count)

    def mark_delivery_failure(self, failure: ShadowTapDeliveryFailure) -> None:
        with self._delivery_state_lock:
            self._delivery_failure_count += 1
            self._last_delivery_failure = failure

    def probe_endpoint(self, timeout_sec: float = 0.25) -> Optional[ShadowTapDeliveryFailure]:
        try:
            host, port = parse_tcp_endpoint(self.endpoint)
            with socket.create_connection((host, port), timeout=timeout_sec):
                return None
        except Exception as exc:
            return _classify_shadow_tap_delivery_failure(
                exc,
                phase="startup",
                endpoint=self.endpoint,
            )

    def wait_until_idle(self, timeout_sec: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_sec))
        while time.monotonic() < deadline:
            if self._unfinished_queue_items() == 0:
                return True
            time.sleep(0.01)
        return self._unfinished_queue_items() == 0

    def _unfinished_queue_items(self) -> int:
        return int(getattr(self._queue, "unfinished_tasks", 0))

    def _join_thread_until_deadline(
        self,
        thread: threading.Thread | None,
        deadline: float,
    ) -> bool:
        if thread is None or not thread.is_alive():
            return False
        remaining = max(0.0, deadline - time.monotonic())
        thread.join(timeout=remaining)
        return thread.is_alive()

    def _record_unclean_shutdown(self, *, detail: object) -> None:
        inc_neocortex_async_forced_stop(
            component=self.name,
            reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN.value,
        )
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            FailureReasonCode.UNCLEAN_SHUTDOWN,
            location="domains/shadow_telemetry/ipc.py:JsonlTcpQueueClient.stop",
            message="JSONL TCP queue client shutdown incomplete",
            detail=detail,
        )
        self.logger.warning("%s shutdown incomplete: %s", self.name, detail)

    def enqueue(self, payload: dict[str, Any]) -> bool:
        if self._stop_event.is_set():
            return False
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            if self.overflow_policy == "drop_oldest":
                try:
                    _ = self._queue.get_nowait()
                except queue.Empty:
                    return False
                try:
                    self._queue.put_nowait(payload)
                    return True
                except queue.Full:
                    return False
            return False

    def _worker(self) -> None:
        while True:
            try:
                payload = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    return
                continue

            try:
                line = json.dumps(payload, separators=(
                    ",", ":"), ensure_ascii=True) + "\n"
                failure = self._send_line(line.encode("utf-8"))
                if failure is not None:
                    self._record_delivery_failure(failure)
            except Exception as exc:
                failure = _classify_shadow_tap_delivery_failure(
                    exc,
                    phase="worker",
                    endpoint=self.endpoint,
                )
                self._record_delivery_failure(failure)
            finally:
                self._queue.task_done()

    def _record_delivery_failure(self, failure: ShadowTapDeliveryFailure) -> None:
        self.mark_delivery_failure(failure)

        reporter = self._failure_reporter
        if reporter is not None:
            try:
                reporter(failure)
                return
            except Exception as exc:
                self.logger.debug(
                    "%s delivery failure reporter raised; falling back to generic logging: %s",
                    self.name,
                    exc,
                )

        reason_code = {
            "timeout": FailureReasonCode.BRIDGE_TIMEOUT,
        }.get(
            failure.failure_class,
            FailureReasonCode.BRIDGE_UNAVAILABLE if failure.failure_class in {
                "endpoint_unavailable",
                "connect_failed",
                "send_failed",
                "queue_overflow",
            } else FailureReasonCode.HANDLER_FAILURE,
        )
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            reason_code,
            location="domains/shadow_telemetry/ipc.py:JsonlTcpQueueClient._worker",
            message="JSONL TCP queue client failed to deliver payload",
            detail={
                "endpoint": self.endpoint,
                "failure_class": failure.failure_class,
                "phase": failure.phase,
                "error_type": failure.error_type,
                "error_message": failure.error_message,
            },
        )
        self.logger.warning(
            "%s failed to deliver payload to %s [failure_class=%s phase=%s error=%s: %s]",
            self.name,
            self.endpoint,
            failure.failure_class,
            failure.phase,
            failure.error_type,
            failure.error_message,
        )

    def _send_line(self, data: bytes) -> Optional[ShadowTapDeliveryFailure]:
        for _attempt in (1, 2):
            with self._sock_lock:
                if self._sock is None:
                    connect_failure = self._connect_locked()
                    if connect_failure is not None:
                        connect_failure = ShadowTapDeliveryFailure(
                            failure_class=connect_failure.failure_class,
                            phase="connect",
                            error_type=connect_failure.error_type,
                            error_message=connect_failure.error_message,
                            endpoint=connect_failure.endpoint,
                            attempt=_attempt,
                        )
                        if _attempt == 2:
                            return connect_failure
                        continue
                try:
                    assert self._sock is not None
                    self._sock.sendall(data)
                    return None
                except Exception as exc:
                    self._close_socket_locked()
                    failure = _classify_shadow_tap_delivery_failure(
                        exc,
                        phase="send",
                        endpoint=self.endpoint,
                        attempt=_attempt,
                    )
                    if _attempt == 2:
                        return failure
                    continue
        return ShadowTapDeliveryFailure(
            failure_class="unknown",
            phase="send",
            error_type="RuntimeError",
            error_message="shadow tap delivery failed without exception",
            endpoint=self.endpoint,
        )

    def _connect_locked(self) -> Optional[ShadowTapDeliveryFailure]:
        try:
            host, port = parse_tcp_endpoint(self.endpoint)
            sock = socket.create_connection((host, port), timeout=1.5)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = sock
            return None
        except Exception as exc:
            self._sock = None
            return _classify_shadow_tap_delivery_failure(
                exc,
                phase="connect",
                endpoint=self.endpoint,
            )

    def _close_socket(self) -> None:
        with self._sock_lock:
            self._close_socket_locked()

    def _close_socket_locked(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
