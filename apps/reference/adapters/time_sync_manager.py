"""
Centralized Time Synchronization Manager for Binance API.

Manages server time offset with caching, background sync, and proper error handling.
Addresses -1021 timestamp errors by maintaining fresh server time offset.

Key features:
- Single source of truth for time offset
- Cache validation before signing requests
- Async sync with /fapi/v1/time endpoint
- Background periodic sync task
- Thread-safe for sync contexts (WS thread)
- Explicit "TIME_SYNC_FAILED" error on sync failure

Usage:
    manager = TimeSyncManager(config, http_client)
    await manager.start()  # Start background sync

    # Before signing request:
    timestamp = await manager.get_timestamp()  # Returns timestamp or raises

    # On -1021 error:
    await manager.force_sync()
    timestamp = await manager.get_timestamp()
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from apps.reference.config_adapter import TimeSyncConfig, resolve_time_sync_config

LOG = logging.getLogger(__name__)


class TimeSyncError(Exception):
    """Raised when time synchronization fails and request cannot proceed."""

    def __init__(self, message: str, last_offset_ms: Optional[int] = None):
        super().__init__(message)
        self.last_offset_ms = last_offset_ms


@dataclass
class TimeSyncState:
    """Internal state for time synchronization."""
    offset_ms: int = 0
    last_sync_monotonic: float = 0.0
    last_sync_timestamp: float = 0.0
    initialized: bool = False
    last_drift_warning_bucket: Optional[int] = None
    consecutive_failures: int = 0


class TimeSyncManager:
    """
    Centralized manager for Binance server time synchronization.

    Provides:
    - Cached time offset with TTL validation
    - Async sync with GET /fapi/v1/time
    - Background periodic sync task
    - Thread-safe sync for WS contexts
    - Explicit failure handling (TIME_SYNC_FAILED)
    """

    def __init__(
        self,
        config: Any = None,
        http_client: Optional[httpx.AsyncClient] = None,
        base_url: str = "https://fapi.binance.com",
        is_testnet: bool = True,
    ):
        """
        Initialize TimeSyncManager.

        Args:
            config: Configuration object with adapter.time_sync section
            http_client: Shared httpx.AsyncClient (optional, created if not provided)
            base_url: Binance API base URL
            is_testnet: Whether running on testnet (affects recvWindow default)
        """
        self._config = resolve_time_sync_config(config)
        self._http_client = http_client
        self._owns_client = http_client is None
        self._base_url = base_url.rstrip("/")
        self._is_testnet = is_testnet

        # State
        self._state = TimeSyncState()

        # Locks
        self._async_lock: Optional[asyncio.Lock] = None
        self._thread_lock = threading.Lock()

        # Background task
        self._background_task: Optional[asyncio.Task] = None
        self._running = False

        LOG.info(
            f"[TimeSyncManager] Initialized: testnet={is_testnet}, "
            f"interval={self._config.interval_sec}s, cache_valid={self._config.cache_valid_sec}s, "
            f"recvWindow={self._config.get_recv_window(is_testnet)}ms"
        )

    @property
    def config(self) -> TimeSyncConfig:
        """Get the time sync configuration."""
        return self._config

    @property
    def offset_ms(self) -> int:
        """Get current time offset in milliseconds."""
        return self._state.offset_ms

    @property
    def is_initialized(self) -> bool:
        """Check if time has been synced at least once."""
        return self._state.initialized

    @property
    def recv_window_ms(self) -> int:
        """Get appropriate recvWindow based on environment."""
        return self._config.get_recv_window(self._is_testnet)

    def is_cache_valid(self) -> bool:
        """Check if cached offset is still valid."""
        return self._config.is_offset_valid(
            self._state.last_sync_monotonic,
            time.monotonic()
        )

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        """
        Set the HTTP client for async sync operations.

        Call this after lazy initialization of httpx.AsyncClient in the adapter.
        """
        self._http_client = client
        self._owns_client = False  # Adapter owns the client
        LOG.debug("[TimeSyncManager] HTTP client set from adapter")

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            # Use sync_timeout_sec from config for all timeout values
            timeout = self._config.sync_timeout_sec
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=timeout, read=timeout, write=timeout, pool=timeout)
            )
            self._owns_client = True
        return self._http_client

    async def _ensure_async_lock(self) -> asyncio.Lock:
        """Lazy initialization of async lock."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    async def start(self) -> None:
        """
        Start the background time sync task.

        Performs initial sync and starts periodic background sync.
        """
        if self._running:
            LOG.warning("[TimeSyncManager] Already running")
            return

        self._running = True

        # Initial sync
        try:
            await self.sync(force=True)
            LOG.info(
                f"[TimeSyncManager] Initial sync complete: offset={self._state.offset_ms}ms"
            )
        except TimeSyncError as e:
            LOG.warning(f"[TimeSyncManager] Initial sync failed: {e}")

        # Start background task
        self._background_task = asyncio.create_task(
            self._background_sync_loop())
        LOG.info(
            f"[TimeSyncManager] Background sync task started "
            f"(interval={self._config.interval_sec}s)"
        )

    async def stop(self) -> None:
        """Stop the background sync task and clean up."""
        self._running = False

        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            LOG.info("[TimeSyncManager] Background sync task stopped")

        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def sync(self, force: bool = False) -> bool:
        """
        Synchronize time with Binance server.

        Args:
            force: If True, bypass cache validation

        Returns:
            True if sync successful, False otherwise

        Note: Does not raise - use get_timestamp() for strict validation.
        """
        # Quick cache check
        if not force and self.is_cache_valid():
            return True

        lock = await self._ensure_async_lock()

        # If lock is held by another task, wait or return cached
        if lock.locked() and not force:
            if self.is_cache_valid():
                return True

        async with lock:
            # Double-check after acquiring lock
            if not force and self.is_cache_valid():
                return True

            return await self._do_sync()

    async def force_sync(self) -> bool:
        """
        Force immediate time sync, invalidating cache.

        Returns:
            True if sync successful, False otherwise
        """
        return await self.sync(force=True)

    async def _do_sync(self) -> bool:
        """
        Perform actual time sync with retry.

        Returns:
            True if sync successful, False otherwise
        """
        # Use config values instead of hardcoded
        max_attempts = self._config.sync_max_attempts
        backoff_base = self._config.sync_backoff_base_sec
        timeout = self._config.sync_timeout_sec

        for attempt in range(1, max_attempts + 1):
            try:
                client = await self._ensure_client()
                url = f"{self._base_url}/fapi/v1/time"

                t0 = time.time() * 1000
                response = await client.get(url, timeout=timeout)
                t1 = time.time() * 1000

                response.raise_for_status()
                data = response.json()
                server_time = int(data["serverTime"])

                # Calculate offset with latency compensation
                latency = (t1 - t0) / 2
                estimated_server_time = server_time + latency
                new_offset = int(estimated_server_time - t1)

                # Check for material drift change
                old_offset = self._state.offset_ms
                if self._state.initialized:
                    if self._config.should_warn_drift_change(old_offset, new_offset):
                        LOG.warning(
                            f"[TimeSyncManager] Drift changed materially: "
                            f"{old_offset}ms -> {new_offset}ms "
                            f"(delta={new_offset - old_offset}ms)"
                        )
                    elif self._config.should_warn_drift(new_offset):
                        LOG.info(
                            f"[TimeSyncManager] Time drift: {new_offset}ms")

                # Update state
                self._state.offset_ms = new_offset
                self._state.last_sync_monotonic = time.monotonic()
                self._state.last_sync_timestamp = time.time()
                self._state.initialized = True
                self._state.consecutive_failures = 0

                LOG.info(
                    f"[TimeSyncManager] Sync success: offset={new_offset}ms, "
                    f"latency={latency:.1f}ms, attempt={attempt}, server_time={server_time}"
                )
                return True

            except Exception as e:
                self._state.consecutive_failures += 1

                if attempt < max_attempts:
                    wait_time = backoff_base * (2 ** (attempt - 1))
                    LOG.debug(
                        f"[TimeSyncManager] Sync attempt {attempt} failed: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    LOG.error(
                        f"[TimeSyncManager] Sync failed after {max_attempts} attempts: {e}"
                    )
                    return False

        return False

    async def get_timestamp(self) -> int:
        """
        Get current timestamp for request signing.

        Validates cache, performs sync if needed, and returns timestamp.
        Raises TimeSyncError if sync fails and cache is stale.

        Returns:
            Current timestamp in milliseconds (local_time + offset)

        Raises:
            TimeSyncError: If sync failed and cache is invalid
        """
        # Try sync if cache is invalid
        if not self.is_cache_valid():
            success = await self.sync()
            if not success:
                # Check if we can use stale cache with warning
                if self._state.initialized:
                    time_since_sync = time.time() - self._state.last_sync_timestamp
                    if time_since_sync < self._config.stale_cache_grace_period_sec:
                        LOG.warning(
                            f"[TimeSyncManager] Using stale offset "
                            f"(age={time_since_sync:.0f}s): {self._state.offset_ms}ms"
                        )
                    else:
                        raise TimeSyncError(
                            f"TIME_SYNC_FAILED: Cache expired ({time_since_sync:.0f}s old), "
                            f"sync failed. Cannot sign request.",
                            last_offset_ms=self._state.offset_ms
                        )
                else:
                    raise TimeSyncError(
                        "TIME_SYNC_FAILED: Never synced successfully. Cannot sign request.",
                        last_offset_ms=None
                    )

        # Check hard limit
        if self._config.exceeds_hard_limit(self._state.offset_ms):
            LOG.error(
                f"[TimeSyncManager] Drift exceeds hard limit: "
                f"{self._state.offset_ms}ms > {self._config.max_drift_hard_limit_ms}ms"
            )
            raise TimeSyncError(
                f"TIME_SYNC_FAILED: Drift {self._state.offset_ms}ms exceeds "
                f"hard limit {self._config.max_drift_hard_limit_ms}ms",
                last_offset_ms=self._state.offset_ms
            )

        return int(time.time() * 1000) + self._state.offset_ms

    def get_timestamp_sync(self) -> int:
        """
        Synchronous version of get_timestamp for WS thread context.

        Uses cached offset without async sync capability.
        Should only be used in WS thread where async is not available.

        Returns:
            Current timestamp in milliseconds (local_time + offset)

        Raises:
            TimeSyncError: If never initialized
        """
        if not self._state.initialized:
            raise TimeSyncError(
                "TIME_SYNC_FAILED: Never synced (sync context). Cannot sign request.",
                last_offset_ms=None
            )

        return int(time.time() * 1000) + self._state.offset_ms

    def sync_blocking(self, force: bool = False) -> bool:
        """
        Blocking time sync for sync contexts (WS thread).

        Uses requests library for blocking HTTP call.
        Thread-safe with separate lock from async operations.

        Args:
            force: If True, bypass cache validation

        Returns:
            True if sync successful, False otherwise
        """
        import requests as sync_requests

        # Quick cache check
        if not force and self.is_cache_valid():
            return True

        with self._thread_lock:
            # Double-check after acquiring lock
            if not force and self.is_cache_valid():
                return True

            # Use config values instead of hardcoded
            max_attempts = self._config.sync_max_attempts
            backoff_base = self._config.sync_backoff_base_sec
            timeout = self._config.sync_timeout_sec

            for attempt in range(1, max_attempts + 1):
                try:
                    url = f"{self._base_url}/fapi/v1/time"

                    t0 = time.time() * 1000
                    response = sync_requests.get(url, timeout=timeout)
                    t1 = time.time() * 1000

                    response.raise_for_status()
                    data = response.json()
                    server_time = int(data["serverTime"])

                    # Calculate offset with latency compensation
                    latency = (t1 - t0) / 2
                    estimated_server_time = server_time + latency
                    new_offset = int(estimated_server_time - t1)

                    # Update state
                    self._state.offset_ms = new_offset
                    self._state.last_sync_monotonic = time.monotonic()
                    self._state.last_sync_timestamp = time.time()
                    self._state.initialized = True
                    self._state.consecutive_failures = 0

                    LOG.debug(
                        f"[TimeSyncManager] Blocking sync success: offset={new_offset}ms"
                    )
                    return True

                except Exception as e:
                    self._state.consecutive_failures += 1

                    if attempt < max_attempts:
                        wait_time = backoff_base * (2 ** (attempt - 1))
                        LOG.debug(
                            f"[TimeSyncManager] Blocking sync attempt {attempt} failed: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        LOG.error(
                            f"[TimeSyncManager] Blocking sync failed after {max_attempts} attempts: {e}"
                        )
                        return False

            return False

    async def _background_sync_loop(self) -> None:
        """Background task for periodic time sync."""
        LOG.info(
            f"[TimeSyncManager] Background sync loop started "
            f"(interval={self._config.interval_sec}s)"
        )

        while self._running:
            try:
                await asyncio.sleep(self._config.interval_sec)
                if self._running:
                    await self.sync()
            except asyncio.CancelledError:
                LOG.info("[TimeSyncManager] Background sync loop cancelled")
                break
            except Exception as e:
                LOG.warning(f"[TimeSyncManager] Background sync error: {e}")
                # Continue loop even on error

    def get_state_summary(self) -> dict:
        """Get current state for debugging/monitoring."""
        return {
            "offset_ms": self._state.offset_ms,
            "initialized": self._state.initialized,
            "cache_valid": self.is_cache_valid(),
            "last_sync_timestamp": self._state.last_sync_timestamp,
            "time_since_sync_sec": time.time() - self._state.last_sync_timestamp
            if self._state.last_sync_timestamp > 0
            else None,
            "consecutive_failures": self._state.consecutive_failures,
            "recv_window_ms": self.recv_window_ms,
            "is_testnet": self._is_testnet,
        }
