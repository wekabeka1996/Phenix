from __future__ import annotations

import json
import logging
import queue
import socket
import threading
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse


def parse_tcp_endpoint(endpoint: str) -> Tuple[str, int]:
    """Parse tcp://host:port endpoint and return host, port."""

    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp":
        raise ValueError(f"Unsupported endpoint scheme: {endpoint}")
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Invalid endpoint: {endpoint}")
    return parsed.hostname, int(parsed.port)


class JsonlTcpServer:
    """Line-delimited JSON TCP server with threaded connection handling."""

    def __init__(
        self,
        endpoint: str,
        handler: Callable[[dict[str, Any]], None],
        *,
        logger: Optional[logging.Logger] = None,
        name: str = "jsonl_tcp_server",
    ) -> None:
        self.endpoint = endpoint
        self.handler = handler
        self.logger = logger or logging.getLogger(name)
        self.name = name

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve_loop, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _serve_loop(self) -> None:
        host, port = parse_tcp_endpoint(self.endpoint)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(64)
        srv.settimeout(1.0)
        self._socket = srv
        self.logger.info("%s listening on %s", self.name, self.endpoint)

        try:
            while not self._stop_event.is_set():
                try:
                    conn, _addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_event.is_set():
                        break
                    continue
                t = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
                t.start()
        finally:
            try:
                srv.close()
            except Exception:
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
                        if isinstance(payload, dict):
                            self.handler(payload)
                    except Exception as e:
                        self.logger.warning("%s failed to parse line: %s", self.name, e)


class JsonlTcpQueueClient:
    """Bounded async-ish sender for JSONL payloads to a TCP endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        queue_maxsize: int,
        overflow_policy: str,
        logger: Optional[logging.Logger] = None,
        name: str = "jsonl_tcp_client",
    ) -> None:
        self.endpoint = endpoint
        self.queue_maxsize = max(1, int(queue_maxsize))
        self.overflow_policy = str(overflow_policy)
        self.logger = logger or logging.getLogger(name)
        self.name = name

        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=self.queue_maxsize)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._sock_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._close_socket()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def queue_depth(self) -> int:
        return int(self._queue.qsize())

    def enqueue(self, payload: dict[str, Any]) -> bool:
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
        while not self._stop_event.is_set():
            try:
                payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            line = json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n"
            ok = self._send_line(line.encode("utf-8"))
            if not ok:
                self.logger.warning("%s failed to deliver payload to %s", self.name, self.endpoint)

    def _send_line(self, data: bytes) -> bool:
        for _attempt in (1, 2):
            with self._sock_lock:
                if self._sock is None and not self._connect_locked():
                    continue
                try:
                    assert self._sock is not None
                    self._sock.sendall(data)
                    return True
                except Exception:
                    self._close_socket_locked()
        return False

    def _connect_locked(self) -> bool:
        try:
            host, port = parse_tcp_endpoint(self.endpoint)
            sock = socket.create_connection((host, port), timeout=1.5)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = sock
            return True
        except Exception:
            self._sock = None
            return False

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
