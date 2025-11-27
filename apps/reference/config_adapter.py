"""Centralized resolver for adapter timeout/retry configuration.

Provides normalized dataclasses for HTTP timeouts, retry policies, WebSocket
reconnection settings, and time synchronization settings.
Consumers should rely on this module instead of reaching
into raw configuration structures.

Configuration is read from: config/domains/execution.yaml -> adapter section
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple, Type

import httpx
import httpcore


def _pluck(node: Any, key: str, default: Any = None) -> Any:
    """Safely extract a key/attribute from dicts or objects."""
    if node is None:
        return default
    if isinstance(node, Mapping):
        return node.get(key, default)
    if hasattr(node, key):
        try:
            return getattr(node, key)
        except AttributeError:
            return default
    return default


def _coerce_float(value: Any, fallback: float) -> float:
    """Safely convert value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    """Safely convert value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_bool(value: Any, fallback: bool) -> bool:
    """Safely convert value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


# =============================================================================
# TIMEOUT CONFIGURATION
# =============================================================================

@dataclass
class TimeoutConfig:
    """
    Timeout configuration for HTTP adapter requests.

    All values in seconds. Use higher values for testnet.
    """
    connect: float = 10.0
    read: float = 30.0
    write: float = 10.0
    pool: float = 10.0

    def to_httpx_timeout(self) -> httpx.Timeout:
        """Convert to httpx.Timeout object."""
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )

    @classmethod
    def testnet_defaults(cls) -> "TimeoutConfig":
        """Conservative timeouts for testnet (often slow/unreliable)."""
        return cls(connect=10.0, read=30.0, write=10.0, pool=10.0)

    @classmethod
    def live_defaults(cls) -> "TimeoutConfig":
        """Tighter timeouts for live API (more responsive)."""
        return cls(connect=5.0, read=10.0, write=5.0, pool=5.0)

    @classmethod
    def from_config(cls, cfg: Any) -> "TimeoutConfig":
        """
        Build TimeoutConfig from configuration (backward-compatible method).

        Supports multiple config formats:
        - config_v2.domains.execution.adapter.timeouts
        - adapter.timeouts (flat dict)
        - rest_timeout_sec (legacy)
        """
        if cfg is None:
            is_testnet = os.environ.get(
                "USE_TESTNET", "1") in ("1", "true", "True")
            return cls.testnet_defaults() if is_testnet else cls.live_defaults()

        # Try config_v2.domains.execution.adapter.timeouts
        config_v2 = _pluck(cfg, "config_v2")
        if config_v2:
            domains = _pluck(config_v2, "domains", {})
            if isinstance(domains, dict):
                execution = domains.get("execution", {})
            else:
                execution = _pluck(domains, "execution", {})

            if isinstance(execution, dict):
                adapter_cfg = execution.get("adapter", {})
            else:
                adapter_cfg = _pluck(execution, "adapter", {})

            if isinstance(adapter_cfg, dict) and adapter_cfg.get("timeouts"):
                timeouts = adapter_cfg["timeouts"]
                return cls(
                    connect=_coerce_float(timeouts.get("connect"), 10.0),
                    read=_coerce_float(timeouts.get("read"), 30.0),
                    write=_coerce_float(timeouts.get("write"), 10.0),
                    pool=_coerce_float(timeouts.get("pool"), 10.0),
                )

        # Try direct adapter.timeouts (dict config)
        if isinstance(cfg, dict):
            adapter_cfg = cfg.get("adapter", {})
            if isinstance(adapter_cfg, dict) and adapter_cfg.get("timeouts"):
                timeouts = adapter_cfg["timeouts"]
                return cls(
                    connect=_coerce_float(timeouts.get("connect"), 10.0),
                    read=_coerce_float(timeouts.get("read"), 30.0),
                    write=_coerce_float(timeouts.get("write"), 10.0),
                    pool=_coerce_float(timeouts.get("pool"), 10.0),
                )

            # Legacy: rest_timeout_sec
            if "rest_timeout_sec" in cfg:
                rest_timeout = _coerce_float(cfg.get("rest_timeout_sec"), 30.0)
                return cls(
                    connect=10.0,
                    read=rest_timeout,
                    write=10.0,
                    pool=10.0,
                )

        # Fallback to environment defaults
        is_testnet = os.environ.get(
            "USE_TESTNET", "1") in ("1", "true", "True")
        return cls.testnet_defaults() if is_testnet else cls.live_defaults()


@dataclass
class RetryConfig:
    """
    Retry configuration with exponential backoff.
    """
    max_retries: int = 3
    initial_backoff_sec: float = 0.5
    max_backoff_sec: float = 8.0
    backoff_multiplier: float = 2.0
    retry_on_timeout: bool = True
    retry_on_network: bool = True

    def get_backoff_delays(self) -> List[float]:
        """Calculate backoff delays for all retry attempts."""
        delays = []
        delay = self.initial_backoff_sec
        for _ in range(self.max_retries):
            delays.append(min(delay, self.max_backoff_sec))
            delay *= self.backoff_multiplier
        return delays

    @classmethod
    def from_config(cls, cfg: Any) -> "RetryConfig":
        """
        Build RetryConfig from configuration (backward-compatible method).

        Supports multiple config formats:
        - config_v2.domains.execution.adapter.retry
        - adapter.retry (flat dict)
        - brackets.retry (legacy)
        """
        if cfg is None:
            return cls()

        # Try config_v2.domains.execution.adapter.retry
        config_v2 = _pluck(cfg, "config_v2")
        if config_v2:
            domains = _pluck(config_v2, "domains", {})
            if isinstance(domains, dict):
                execution = domains.get("execution", {})
            else:
                execution = _pluck(domains, "execution", {})

            if isinstance(execution, dict):
                adapter_cfg = execution.get("adapter", {})
            else:
                adapter_cfg = _pluck(execution, "adapter", {})

            if isinstance(adapter_cfg, dict) and adapter_cfg.get("retry"):
                retry = adapter_cfg["retry"]
                return cls(
                    max_retries=_coerce_int(retry.get("max_retries"), 3),
                    initial_backoff_sec=_coerce_float(
                        retry.get("initial_backoff_sec"), 0.5),
                    max_backoff_sec=_coerce_float(
                        retry.get("max_backoff_sec"), 8.0),
                    backoff_multiplier=_coerce_float(
                        retry.get("backoff_multiplier"), 2.0),
                    retry_on_timeout=_coerce_bool(
                        retry.get("retry_on_timeout"), True),
                    retry_on_network=_coerce_bool(
                        retry.get("retry_on_network"), True),
                )

        # Try direct adapter.retry (dict config)
        if isinstance(cfg, dict):
            adapter_cfg = cfg.get("adapter", {})
            if isinstance(adapter_cfg, dict) and adapter_cfg.get("retry"):
                retry = adapter_cfg["retry"]
                return cls(
                    max_retries=_coerce_int(retry.get("max_retries"), 3),
                    initial_backoff_sec=_coerce_float(
                        retry.get("initial_backoff_sec"), 0.5),
                    max_backoff_sec=_coerce_float(
                        retry.get("max_backoff_sec"), 8.0),
                    backoff_multiplier=_coerce_float(
                        retry.get("backoff_multiplier"), 2.0),
                    retry_on_timeout=_coerce_bool(
                        retry.get("retry_on_timeout"), True),
                    retry_on_network=_coerce_bool(
                        retry.get("retry_on_network"), True),
                )

            # Legacy: brackets.retry
            brackets = cfg.get("brackets", {})
            if isinstance(brackets, dict) and brackets.get("retry"):
                legacy = brackets["retry"]
                max_attempts = _coerce_int(legacy.get("max_attempts"), 3)
                backoff_ms = legacy.get("backoff_ms", [500])
                initial_backoff = _coerce_float(
                    backoff_ms[0], 500.0) / 1000.0 if backoff_ms else 0.5
                return cls(
                    max_retries=max_attempts,
                    initial_backoff_sec=initial_backoff,
                )

        return cls()


@dataclass
class Error1021RetryConfig:
    """
    Retry configuration specifically for -1021 timestamp errors.

    These errors require special handling: force time sync before retry,
    rebuild signature with fresh timestamp.
    """
    max_retries: int = 2
    backoff_base_sec: float = 0.3
    backoff_multiplier: float = 2.0
    force_sync_before_retry: bool = True

    def get_backoff_delays(self) -> List[float]:
        """Calculate backoff delays for -1021 retry attempts."""
        delays = []
        delay = self.backoff_base_sec
        for _ in range(self.max_retries):
            delays.append(delay)
            delay *= self.backoff_multiplier
        return delays

    @classmethod
    def from_config(cls, cfg: Any) -> "Error1021RetryConfig":
        """Build from adapter.time_sync.error_1021 config section."""
        if cfg is None:
            return cls()

        adapter_cfg = _get_adapter_config_internal(cfg)
        time_sync = adapter_cfg.get("time_sync", {}) if isinstance(
            adapter_cfg, dict) else {}
        error_1021 = time_sync.get("error_1021", {}) if isinstance(
            time_sync, dict) else {}

        if error_1021:
            return cls(
                max_retries=_coerce_int(error_1021.get("max_retries"), 2),
                backoff_base_sec=_coerce_float(
                    error_1021.get("backoff_base_sec"), 0.3),
                backoff_multiplier=_coerce_float(
                    error_1021.get("backoff_multiplier"), 2.0),
                force_sync_before_retry=_coerce_bool(
                    error_1021.get("force_sync_before_retry"), True),
            )

        return cls()


@dataclass
class TimeSyncConfig:
    """
    Time synchronization configuration for Binance API.

    Addresses -1021 timestamp errors by maintaining fresh server time offset.
    Uses different recvWindow values for mainnet vs testnet.
    """
    # recvWindow per environment (ms)
    # Mainnet: strict 5s to prevent replay attacks
    # Testnet: relaxed 60s to handle high latency and timestamp drift
    recv_window_mainnet_ms: int = 5000
    recv_window_testnet_ms: int = 60000  # Increased from 20000 to handle testnet instability

    # Sync schedule
    interval_sec: float = 30.0
    cache_valid_sec: float = 35.0  # Must be > interval_sec to prevent stale cache

    # Drift monitoring thresholds (ms)
    max_drift_warn_ms: int = 500
    max_drift_change_warn_ms: int = 10000
    max_drift_hard_limit_ms: int = 60000

    # Sync retry configuration (previously hardcoded in TimeSyncManager)
    sync_max_attempts: int = 5
    sync_backoff_base_sec: float = 0.5
    sync_timeout_sec: float = 10.0

    # Stale cache grace period (seconds) - allows using old offset if sync fails
    stale_cache_grace_period_sec: float = 300.0  # 5 minutes

    # Error -1021 specific retry config
    error_1021: Error1021RetryConfig = field(
        default_factory=Error1021RetryConfig)

    def get_recv_window(self, is_testnet: bool) -> int:
        """Get appropriate recvWindow based on environment."""
        return self.recv_window_testnet_ms if is_testnet else self.recv_window_mainnet_ms

    def is_offset_valid(self, last_sync_monotonic: float, current_monotonic: float) -> bool:
        """Check if cached offset is still valid."""
        return (current_monotonic - last_sync_monotonic) < self.cache_valid_sec

    def should_warn_drift(self, drift_ms: float) -> bool:
        """Check if drift exceeds warning threshold."""
        return abs(drift_ms) > self.max_drift_warn_ms

    def should_warn_drift_change(self, old_drift_ms: float, new_drift_ms: float) -> bool:
        """Check if drift change exceeds warning threshold."""
        return abs(new_drift_ms - old_drift_ms) > self.max_drift_change_warn_ms

    def exceeds_hard_limit(self, drift_ms: float) -> bool:
        """Check if drift exceeds hard limit (should reject request)."""
        return abs(drift_ms) > self.max_drift_hard_limit_ms

    @classmethod
    def testnet_defaults(cls) -> "TimeSyncConfig":
        """Conservative defaults for testnet (higher latency)."""
        return cls(
            recv_window_mainnet_ms=5000,
            recv_window_testnet_ms=60000,  # 60s for testnet high latency
            interval_sec=30.0,
            cache_valid_sec=35.0,  # 5s buffer over interval to avoid stale cache before next sync
            max_drift_warn_ms=500,
            max_drift_change_warn_ms=10000,
            max_drift_hard_limit_ms=60000,
            sync_max_attempts=5,
            sync_backoff_base_sec=0.5,
            sync_timeout_sec=10.0,
        )

    @classmethod
    def mainnet_defaults(cls) -> "TimeSyncConfig":
        """Tighter defaults for mainnet (lower latency expected)."""
        return cls(
            recv_window_mainnet_ms=5000,
            recv_window_testnet_ms=60000,  # Same as testnet for consistency
            interval_sec=60.0,  # Less frequent sync on mainnet
            cache_valid_sec=65.0,  # 5s buffer over interval
            max_drift_warn_ms=200,
            max_drift_change_warn_ms=5000,
            max_drift_hard_limit_ms=30000,
            sync_max_attempts=5,
            sync_backoff_base_sec=0.5,
            sync_timeout_sec=10.0,
        )

    @classmethod
    def from_config(cls, cfg: Any) -> "TimeSyncConfig":
        """
        Build TimeSyncConfig from configuration.

        Looks in: adapter.time_sync section of execution domain config.
        """
        if cfg is None:
            is_testnet = os.environ.get(
                "USE_TESTNET", "1") in ("1", "true", "True")
            return cls.testnet_defaults() if is_testnet else cls.mainnet_defaults()

        adapter_cfg = _get_adapter_config_internal(cfg)
        time_sync = adapter_cfg.get("time_sync", {}) if isinstance(
            adapter_cfg, dict) else {}

        if time_sync:
            error_1021_cfg = time_sync.get("error_1021", {})
            error_1021 = Error1021RetryConfig(
                max_retries=_coerce_int(error_1021_cfg.get("max_retries"), 2),
                backoff_base_sec=_coerce_float(
                    error_1021_cfg.get("backoff_base_sec"), 0.3),
                backoff_multiplier=_coerce_float(
                    error_1021_cfg.get("backoff_multiplier"), 2.0),
                force_sync_before_retry=_coerce_bool(
                    error_1021_cfg.get("force_sync_before_retry"), True),
            ) if error_1021_cfg else Error1021RetryConfig()

            return cls(
                recv_window_mainnet_ms=_coerce_int(
                    time_sync.get("recv_window_mainnet_ms"), 5000),
                recv_window_testnet_ms=_coerce_int(
                    time_sync.get("recv_window_testnet_ms"), 60000),  # Testnet: 60s for high latency
                interval_sec=_coerce_float(
                    time_sync.get("interval_sec"), 30.0),
                cache_valid_sec=_coerce_float(
                    time_sync.get("cache_valid_sec"), 35.0),  # > interval_sec
                max_drift_warn_ms=_coerce_int(
                    time_sync.get("max_drift_warn_ms"), 500),
                max_drift_change_warn_ms=_coerce_int(
                    time_sync.get("max_drift_change_warn_ms"), 10000),
                max_drift_hard_limit_ms=_coerce_int(
                    time_sync.get("max_drift_hard_limit_ms"), 60000),
                sync_max_attempts=_coerce_int(
                    time_sync.get("sync_max_attempts"), 5),
                sync_backoff_base_sec=_coerce_float(
                    time_sync.get("sync_backoff_base_sec"), 0.5),
                sync_timeout_sec=_coerce_float(
                    time_sync.get("sync_timeout_sec"), 10.0),
                error_1021=error_1021,
            )

        # Fallback to environment-based defaults
        is_testnet = os.environ.get(
            "USE_TESTNET", "1") in ("1", "true", "True")
        return cls.testnet_defaults() if is_testnet else cls.mainnet_defaults()


def _get_adapter_config_internal(cfg: Any) -> dict:
    """
    Internal helper to extract adapter config from config object.
    Used by dataclass from_config methods that can't call module-level functions.
    """
    if cfg is None:
        return {}

    # Try config_v2.domains.execution.adapter path
    config_v2 = _pluck(cfg, "config_v2")
    if config_v2:
        domains = _pluck(config_v2, "domains", {})
        if isinstance(domains, dict):
            execution = domains.get("execution", {})
        else:
            execution = _pluck(domains, "execution", {})

        if isinstance(execution, dict):
            return execution.get("adapter", {})
        return _pluck(execution, "adapter", {})

    # Try direct adapter path (for dict configs)
    if isinstance(cfg, dict):
        return cfg.get("adapter", {})

    return {}


@dataclass
class WebSocketReconnectConfig:
    """
    Configuration for WebSocket reconnection with exponential backoff.
    """
    initial_delay_sec: float = 1.0
    # Max 1 minute (was 30, matches ws_max_reconnect_delay)
    max_delay_sec: float = 60.0
    multiplier: float = 2.0
    reset_after_success: bool = True
    # 45 minutes (45*60) for USER_DATA_STREAM
    listen_key_keepalive_sec: int = 2700

    def get_next_delay(self, current_delay: float) -> float:
        """Calculate next delay with exponential backoff, capped at max."""
        return min(current_delay * self.multiplier, self.max_delay_sec)

    @classmethod
    def from_config(cls, cfg: Any) -> "WebSocketReconnectConfig":
        """
        Build WebSocketReconnectConfig from configuration (backward-compatible method).

        Supports multiple config formats:
        - config_v2.domains.execution.adapter.websocket
        - adapter.websocket (flat dict)
        """
        if cfg is None:
            return cls()

        # Try config_v2.domains.execution.adapter.websocket
        config_v2 = _pluck(cfg, "config_v2")
        if config_v2:
            domains = _pluck(config_v2, "domains", {})
            if isinstance(domains, dict):
                execution = domains.get("execution", {})
            else:
                execution = _pluck(domains, "execution", {})

            if isinstance(execution, dict):
                adapter_cfg = execution.get("adapter", {})
            else:
                adapter_cfg = _pluck(execution, "adapter", {})

            if isinstance(adapter_cfg, dict) and adapter_cfg.get("websocket"):
                ws = adapter_cfg["websocket"]
                return cls(
                    initial_delay_sec=_coerce_float(
                        ws.get("initial_delay_sec"), 1.0),
                    max_delay_sec=_coerce_float(ws.get("max_delay_sec"), 60.0),
                    multiplier=_coerce_float(ws.get("multiplier"), 2.0),
                    reset_after_success=_coerce_bool(
                        ws.get("reset_after_success"), True),
                    listen_key_keepalive_sec=_coerce_int(
                        ws.get("listen_key_keepalive_sec"), 2700),
                )

        # Try direct adapter.websocket (dict config)
        if isinstance(cfg, dict):
            adapter_cfg = cfg.get("adapter", {})
            if isinstance(adapter_cfg, dict) and adapter_cfg.get("websocket"):
                ws = adapter_cfg["websocket"]
                return cls(
                    initial_delay_sec=_coerce_float(
                        ws.get("initial_delay_sec"), 1.0),
                    max_delay_sec=_coerce_float(ws.get("max_delay_sec"), 60.0),
                    multiplier=_coerce_float(ws.get("multiplier"), 2.0),
                    reset_after_success=_coerce_bool(
                        ws.get("reset_after_success"), True),
                    listen_key_keepalive_sec=_coerce_int(
                        ws.get("listen_key_keepalive_sec"), 2700),
                )

        return cls()


@dataclass
class OpenOrdersConfig:
    """
    Configuration for get_open_orders query with retry.
    """
    max_attempts: int = 3
    backoff_ms: Tuple[int, ...] = (200, 500)
    fallback_reason: str = "API_ORDERS_FAILED"

    @classmethod
    def from_config(cls, cfg: Any) -> "OpenOrdersConfig":
        """Build from adapter.open_orders config section."""
        if cfg is None:
            return cls()

        adapter_cfg = _get_adapter_config_internal(cfg)
        open_orders = adapter_cfg.get("open_orders", {}) if isinstance(
            adapter_cfg, dict) else {}

        if open_orders:
            backoff = open_orders.get("backoff_ms", [200, 500])
            if isinstance(backoff, list):
                backoff = tuple(backoff)
            return cls(
                max_attempts=_coerce_int(open_orders.get("max_attempts"), 3),
                backoff_ms=backoff,
                fallback_reason=open_orders.get(
                    "fallback_reason", "API_ORDERS_FAILED"),
            )

        return cls()


# =============================================================================
# EXCEPTION TUPLES FOR ERROR CLASSIFICATION
# =============================================================================

TIMEOUT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.TimeoutException,
    httpcore.ReadTimeout,
    httpcore.ConnectTimeout,
    httpcore.WriteTimeout,
    httpcore.PoolTimeout,
)

NETWORK_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpcore.ConnectError,
    httpcore.RemoteProtocolError,
    ConnectionError,
    OSError,
)


# =============================================================================
# RESOLVER FUNCTIONS
# =============================================================================

def _get_adapter_config(cfg: Any) -> dict:
    """
    Extract adapter config from config object.

    Looks in: config_v2.domains.execution.adapter OR config_v2.domains['execution']['adapter']
    """
    if cfg is None:
        return {}

    # Try config_v2.domains.execution.adapter path
    config_v2 = _pluck(cfg, "config_v2")
    if config_v2:
        domains = _pluck(config_v2, "domains", {})
        if isinstance(domains, dict):
            execution = domains.get("execution", {})
        else:
            execution = _pluck(domains, "execution", {})

        if isinstance(execution, dict):
            return execution.get("adapter", {})
        return _pluck(execution, "adapter", {})

    # Try direct adapter path (for dict configs)
    if isinstance(cfg, dict):
        return cfg.get("adapter", {})

    return {}


def resolve_timeout_config(cfg: Any) -> TimeoutConfig:
    """
    Resolve TimeoutConfig from configuration.

    Args:
        cfg: AuroraConfig, dict with config_v2.domains.execution.adapter, or TimeoutConfig

    Returns:
        TimeoutConfig with values from YAML or defaults
    """
    # If already a TimeoutConfig, return as-is
    if isinstance(cfg, TimeoutConfig):
        return cfg

    adapter_cfg = _get_adapter_config(cfg)
    timeouts = adapter_cfg.get("timeouts", {}) if isinstance(
        adapter_cfg, dict) else {}

    if timeouts:
        return TimeoutConfig(
            connect=_coerce_float(timeouts.get("connect"), 10.0),
            read=_coerce_float(timeouts.get("read"), 30.0),
            write=_coerce_float(timeouts.get("write"), 10.0),
            pool=_coerce_float(timeouts.get("pool"), 10.0),
        )

    # Fallback to environment-based defaults
    is_testnet = os.environ.get("USE_TESTNET", "1") in ("1", "true", "True")
    return TimeoutConfig.testnet_defaults() if is_testnet else TimeoutConfig.live_defaults()


def resolve_retry_config(cfg: Any) -> RetryConfig:
    """
    Resolve RetryConfig from configuration.

    Args:
        cfg: AuroraConfig, dict with config_v2.domains.execution.adapter, or RetryConfig

    Returns:
        RetryConfig with values from YAML or defaults
    """
    # If already a RetryConfig, return as-is
    if isinstance(cfg, RetryConfig):
        return cfg

    adapter_cfg = _get_adapter_config(cfg)
    retry = adapter_cfg.get("retry", {}) if isinstance(
        adapter_cfg, dict) else {}

    if retry:
        return RetryConfig(
            max_retries=_coerce_int(retry.get("max_retries"), 3),
            initial_backoff_sec=_coerce_float(
                retry.get("initial_backoff_sec"), 0.5),
            max_backoff_sec=_coerce_float(retry.get("max_backoff_sec"), 8.0),
            backoff_multiplier=_coerce_float(
                retry.get("backoff_multiplier"), 2.0),
            retry_on_timeout=_coerce_bool(retry.get("retry_on_timeout"), True),
            retry_on_network=_coerce_bool(retry.get("retry_on_network"), True),
        )

    return RetryConfig()


def resolve_websocket_reconnect_config(cfg: Any) -> WebSocketReconnectConfig:
    """
    Resolve WebSocketReconnectConfig from configuration.

    Args:
        cfg: AuroraConfig, dict with config_v2.domains.execution.adapter, or WebSocketReconnectConfig

    Returns:
        WebSocketReconnectConfig with values from YAML or defaults
    """
    # If already a WebSocketReconnectConfig, return as-is
    if isinstance(cfg, WebSocketReconnectConfig):
        return cfg

    adapter_cfg = _get_adapter_config(cfg)
    ws = adapter_cfg.get("websocket", {}) if isinstance(
        adapter_cfg, dict) else {}

    if ws:
        return WebSocketReconnectConfig(
            initial_delay_sec=_coerce_float(ws.get("initial_delay_sec"), 1.0),
            max_delay_sec=_coerce_float(ws.get("max_delay_sec"), 30.0),
            multiplier=_coerce_float(ws.get("multiplier"), 2.0),
            reset_after_success=_coerce_bool(
                ws.get("reset_after_success"), True),
            listen_key_keepalive_sec=_coerce_int(
                ws.get("listen_key_keepalive_sec"), 2700),
        )

    return WebSocketReconnectConfig()


def resolve_time_sync_config(cfg: Any) -> TimeSyncConfig:
    """
    Resolve TimeSyncConfig from configuration.

    Args:
        cfg: AuroraConfig, dict with config_v2.domains.execution.adapter, or TimeSyncConfig

    Returns:
        TimeSyncConfig with values from YAML or defaults
    """
    # If already a TimeSyncConfig, return as-is
    if isinstance(cfg, TimeSyncConfig):
        return cfg

    adapter_cfg = _get_adapter_config(cfg)
    time_sync = adapter_cfg.get("time_sync", {}) if isinstance(
        adapter_cfg, dict) else {}

    if time_sync:
        error_1021_cfg = time_sync.get("error_1021", {})
        error_1021 = Error1021RetryConfig(
            max_retries=_coerce_int(error_1021_cfg.get("max_retries"), 2),
            backoff_base_sec=_coerce_float(
                error_1021_cfg.get("backoff_base_sec"), 0.3),
            backoff_multiplier=_coerce_float(
                error_1021_cfg.get("backoff_multiplier"), 2.0),
            force_sync_before_retry=_coerce_bool(
                error_1021_cfg.get("force_sync_before_retry"), True),
        ) if error_1021_cfg else Error1021RetryConfig()

        return TimeSyncConfig(
            recv_window_mainnet_ms=_coerce_int(
                time_sync.get("recv_window_mainnet_ms"), 5000),
            recv_window_testnet_ms=_coerce_int(
                time_sync.get("recv_window_testnet_ms"), 60000),  # 60s for testnet
            interval_sec=_coerce_float(time_sync.get("interval_sec"), 30.0),
            cache_valid_sec=_coerce_float(
                time_sync.get("cache_valid_sec"), 35.0),  # > interval_sec
            max_drift_warn_ms=_coerce_int(
                time_sync.get("max_drift_warn_ms"), 500),
            max_drift_change_warn_ms=_coerce_int(
                time_sync.get("max_drift_change_warn_ms"), 10000),
            max_drift_hard_limit_ms=_coerce_int(
                time_sync.get("max_drift_hard_limit_ms"), 60000),
            sync_max_attempts=_coerce_int(
                time_sync.get("sync_max_attempts"), 5),
            sync_backoff_base_sec=_coerce_float(
                time_sync.get("sync_backoff_base_sec"), 0.5),
            sync_timeout_sec=_coerce_float(
                time_sync.get("sync_timeout_sec"), 10.0),
            stale_cache_grace_period_sec=_coerce_float(
                time_sync.get("stale_cache_grace_period_sec"), 300.0),
            error_1021=error_1021,
        )

    # Fallback to environment-based defaults
    is_testnet = os.environ.get("USE_TESTNET", "1") in ("1", "true", "True")
    return TimeSyncConfig.testnet_defaults() if is_testnet else TimeSyncConfig.mainnet_defaults()


def resolve_open_orders_config(cfg: Any) -> OpenOrdersConfig:
    """
    Resolve OpenOrdersConfig from configuration.

    Args:
        cfg: AuroraConfig, dict with config_v2.domains.execution.adapter, or OpenOrdersConfig

    Returns:
        OpenOrdersConfig with values from YAML or defaults
    """
    # If already an OpenOrdersConfig, return as-is
    if isinstance(cfg, OpenOrdersConfig):
        return cfg

    adapter_cfg = _get_adapter_config(cfg)
    open_orders = adapter_cfg.get("open_orders", {}) if isinstance(
        adapter_cfg, dict) else {}

    if open_orders:
        backoff = open_orders.get("backoff_ms", [200, 500])
        if isinstance(backoff, list):
            backoff = tuple(backoff)
        return OpenOrdersConfig(
            max_attempts=_coerce_int(open_orders.get("max_attempts"), 3),
            backoff_ms=backoff,
            fallback_reason=open_orders.get(
                "fallback_reason", "API_ORDERS_FAILED"),
        )

    return OpenOrdersConfig()
