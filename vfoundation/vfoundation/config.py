"""
Minimal ENV-based configuration for vFoundation.

Security and critical operational knobs only - no business logic parameters.
Fail-obvious dev defaults with warnings, no live-reload, no frameworks.
"""

from __future__ import annotations

import os
import pathlib
import warnings
from typing import List, Optional


class Config:
    """Central configuration loaded from ENV variables at module import time."""

    def __init__(self) -> None:
        # Security: RBAC tokens
        self.rbac_admin_tokens: List[str] = self._get_admin_tokens()
        self.signing_key: str = self._get_signing_key()

        # DR: WAL settings
        self.wal_dir: pathlib.Path = self._get_wal_dir()
        self.wal_lock_timeout_sec: float = self._get_float_env(
            "WAL_LOCK_TIMEOUT_SEC", 5.0, min_val=0.1, max_val=300.0
        )

        # Circuit Breaker
        self.cb_threshold: int = self._get_int_env("CB_THRESHOLD", 5, min_val=1, max_val=100)
        self.cb_cooldown_sec: float = self._get_float_env(
            "CB_COOLDOWN_SEC", 60.0, min_val=1.0, max_val=3600.0
        )

        # Idempotency
        self.idem_ttl_ms: int = self._get_int_env(
            "IDEM_TTL_MS", 600_000, min_val=1000, max_val=3600_000
        )
        self.idem_max_entries: int = self._get_int_env(
            "IDEM_MAX_ENTRIES", 10000, min_val=100, max_val=1_000_000
        )

        # Drift Monitor
        self.drift_time_window_sec: float = self._get_float_env(
            "DRIFT_TIME_WINDOW_SEC", 1.0, min_val=0.1, max_val=60.0
        )

        # Execution Adapter (FSMP-P2-T01)
        self.execution_mode: str = self._get_execution_mode()
        self.exchange_api_key: Optional[str] = self._get_optional_env("EXCHANGE_API_KEY")
        self.exchange_api_secret: Optional[str] = self._get_optional_env("EXCHANGE_API_SECRET")
        self.exchange_base_url: Optional[str] = self._get_optional_env("EXCHANGE_BASE_URL")
        self.exchange_ws_url: Optional[str] = self._get_optional_env("EXCHANGE_WS_URL")

        # Adapter timeouts (milliseconds)
        self.adapter_submit_timeout_ms: int = self._get_int_env(
            "ADAPTER_SUBMIT_TIMEOUT_MS", 200, min_val=10, max_val=5000
        )
        self.adapter_cancel_timeout_ms: int = self._get_int_env(
            "ADAPTER_CANCEL_TIMEOUT_MS", 200, min_val=10, max_val=5000
        )
        self.adapter_stream_timeout_ms: int = self._get_int_env(
            "ADAPTER_STREAM_TIMEOUT_MS", 5000, min_val=100, max_val=30000
        )

        # Adapter retry configuration
        self.adapter_retry_max_attempts: int = self._get_int_env(
            "ADAPTER_RETRY_MAX_ATTEMPTS", 3, min_val=1, max_val=10
        )
        self.adapter_retry_base_ms: int = self._get_int_env(
            "ADAPTER_RETRY_BASE_MS", 100, min_val=10, max_val=1000
        )
        self.adapter_retry_max_ms: int = self._get_int_env(
            "ADAPTER_RETRY_MAX_MS", 2000, min_val=100, max_val=10000
        )

        # Adapter Circuit Breaker
        self.adapter_cb_open_threshold: float = self._get_float_env(
            "ADAPTER_CB_OPEN_THRESHOLD", 0.5, min_val=0.1, max_val=1.0
        )
        self.adapter_cb_cooldown_ms: int = self._get_int_env(
            "ADAPTER_CB_COOLDOWN_MS", 5000, min_val=1000, max_val=60000
        )
        self.adapter_cb_half_open_probes: int = self._get_int_env(
            "ADAPTER_CB_HALF_OPEN_PROBES", 3, min_val=1, max_val=10
        )

        # Distributed Idempotency (FSMP-P2-T02)
        self.redis_url: str = self._get_redis_url()
        self.idemp_ttl_ms: int = self._get_int_env(
            "IDEMP_TTL_MS", 60_000, min_val=1000, max_val=3600_000
        )
        self.idemp_timeout_ms: int = self._get_int_env(
            "IDEMP_TIMEOUT_MS", 100, min_val=10, max_val=5000
        )
        self.idemp_retry_max_attempts: int = self._get_int_env(
            "IDEMP_RETRY_MAX_ATTEMPTS", 3, min_val=1, max_val=10
        )
        self.idemp_retry_base_ms: int = self._get_int_env(
            "IDEMP_RETRY_BASE_MS", 50, min_val=10, max_val=1000
        )
        self.idemp_retry_max_ms: int = self._get_int_env(
            "IDEMP_RETRY_MAX_MS", 1000, min_val=100, max_val=10000
        )
        self.idemp_cb_threshold: float = self._get_float_env(
            "IDEMP_CB_THRESHOLD", 0.6, min_val=0.1, max_val=1.0
        )
        self.idemp_cb_cooldown_ms: int = self._get_int_env(
            "IDEMP_CB_COOLDOWN_MS", 3000, min_val=1000, max_val=60000
        )
        self.idemp_cb_half_open_probes: int = self._get_int_env(
            "IDEMP_CB_HALF_OPEN_PROBES", 2, min_val=1, max_val=10
        )
        self.worker_id: str = self._get_worker_id()

    def _get_admin_tokens(self) -> List[str]:
        """Get RBAC admin tokens from ENV with dev-obvious default warning."""
        raw = os.getenv("RBAC_ADMIN_TOKENS", "")
        if not raw:
            # Fail-obvious dev default
            warnings.warn(
                "RBAC_ADMIN_TOKENS not set - using INSECURE dev default 'dev-admin-token'. "
                "Set RBAC_ADMIN_TOKENS env var in production!",
                stacklevel=2,
            )
            return ["dev-admin-token"]

        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        if not tokens:
            warnings.warn(
                "RBAC_ADMIN_TOKENS is empty - no admin access will be granted!", stacklevel=2
            )
        return tokens

    def _get_signing_key(self) -> str:
        """Get Ed25519 signing key from ENV with dev-obvious default warning."""
        key = os.getenv("SIGNING_KEY", "")
        if not key:
            # Fail-obvious dev default (64 hex chars for Ed25519)
            warnings.warn(
                "SIGNING_KEY not set - using INSECURE dev default. "
                "Set SIGNING_KEY env var in production!",
                stacklevel=2,
            )
            return "0" * 64  # Dev-obvious invalid key

        if len(key) != 64:
            warnings.warn(
                f"SIGNING_KEY should be 64 hex characters (got {len(key)}). "
                "Using provided value but signatures may fail.",
                stacklevel=2,
            )
        return key

    def _get_execution_mode(self) -> str:
        """Get execution mode from ENV with dry_run default."""
        mode = os.getenv("EXECUTION_MODE", "dry_run").lower()
        valid_modes = {"dry_run", "paper", "live"}

        if mode not in valid_modes:
            warnings.warn(
                f"EXECUTION_MODE='{mode}' invalid, using 'dry_run'. Valid modes: {valid_modes}",
                stacklevel=2,
            )
            return "dry_run"

        # Fail-obvious requirement for non-dry_run modes
        if mode in {"paper", "live"}:
            required = ["EXCHANGE_API_KEY", "EXCHANGE_API_SECRET", "EXCHANGE_BASE_URL"]
            missing = [k for k in required if not os.getenv(k)]
            if missing:
                raise RuntimeError(
                    f"EXECUTION_MODE={mode} requires ENV vars: {', '.join(missing)}. "
                    f"Set them or use EXECUTION_MODE=dry_run for testing."
                )

        return mode

    def _get_redis_url(self) -> str:
        """Get Redis URL from ENV with dev-obvious default."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return url

    def _get_worker_id(self) -> str:
        """Get worker ID from ENV with hostname default."""
        worker_id = os.getenv("WORKER_ID")
        if not worker_id:
            import socket

            hostname = socket.gethostname()
            import uuid

            worker_id = f"{hostname}-{uuid.uuid4().hex[:8]}"
            warnings.warn(
                f"WORKER_ID not set - using generated ID: {worker_id}. "
                "Set WORKER_ID env var for stable identification.",
                stacklevel=2,
            )
        return worker_id

    def _get_optional_env(self, key: str) -> Optional[str]:
        """Get optional ENV variable, return None if not set."""
        return os.getenv(key) or None

    def _get_wal_dir(self) -> pathlib.Path:
        """Get WAL directory from ENV or use default."""
        dir_str = os.getenv("WAL_DIR", "ops/wal")
        return pathlib.Path(dir_str)

    def _get_int_env(
        self, key: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None
    ) -> int:
        """Get integer from ENV with validation."""
        raw = os.getenv(key)
        if raw is None:
            return default

        try:
            value = int(raw)
        except ValueError:
            warnings.warn(
                f"{key}='{raw}' is not a valid integer, using default {default}", stacklevel=3
            )
            return default

        if min_val is not None and value < min_val:
            warnings.warn(f"{key}={value} is below minimum {min_val}, using minimum", stacklevel=3)
            return min_val

        if max_val is not None and value > max_val:
            warnings.warn(f"{key}={value} exceeds maximum {max_val}, using maximum", stacklevel=3)
            return max_val

        return value

    def _get_float_env(
        self,
        key: str,
        default: float,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> float:
        """Get float from ENV with validation."""
        raw = os.getenv(key)
        if raw is None:
            return default

        try:
            value = float(raw)
        except ValueError:
            warnings.warn(
                f"{key}='{raw}' is not a valid number, using default {default}", stacklevel=3
            )
            return default

        if min_val is not None and value < min_val:
            warnings.warn(f"{key}={value} is below minimum {min_val}, using minimum", stacklevel=3)
            return min_val

        if max_val is not None and value > max_val:
            warnings.warn(f"{key}={value} exceeds maximum {max_val}, using maximum", stacklevel=3)
            return max_val

        return value


# Singleton instance loaded at module import
config = Config()


def reload_config() -> None:
    """
    Reload configuration from ENV (useful for testing).

    Recreates Config and updates global singleton attributes in-place
    so existing references to `config` see updated values.

    WARNING: Not thread-safe. Only use in test setup or single-threaded context.
    """
    global config
    new_config = Config()

    # Update all attributes in-place to preserve existing references
    config.rbac_admin_tokens = new_config.rbac_admin_tokens
    config.signing_key = new_config.signing_key
    config.wal_dir = new_config.wal_dir
    config.wal_lock_timeout_sec = new_config.wal_lock_timeout_sec
    config.cb_threshold = new_config.cb_threshold
    config.cb_cooldown_sec = new_config.cb_cooldown_sec
    config.idem_ttl_ms = new_config.idem_ttl_ms
    config.idem_max_entries = new_config.idem_max_entries
    config.drift_time_window_sec = new_config.drift_time_window_sec

    # Adapter settings (FSMP-P2-T01)
    config.execution_mode = new_config.execution_mode
    config.exchange_api_key = new_config.exchange_api_key
    config.exchange_api_secret = new_config.exchange_api_secret
    config.exchange_base_url = new_config.exchange_base_url
    config.exchange_ws_url = new_config.exchange_ws_url
    config.adapter_submit_timeout_ms = new_config.adapter_submit_timeout_ms
    config.adapter_cancel_timeout_ms = new_config.adapter_cancel_timeout_ms
    config.adapter_stream_timeout_ms = new_config.adapter_stream_timeout_ms
    config.adapter_retry_max_attempts = new_config.adapter_retry_max_attempts
    config.adapter_retry_base_ms = new_config.adapter_retry_base_ms
    config.adapter_retry_max_ms = new_config.adapter_retry_max_ms
    config.adapter_cb_open_threshold = new_config.adapter_cb_open_threshold
    config.adapter_cb_cooldown_ms = new_config.adapter_cb_cooldown_ms
    config.adapter_cb_half_open_probes = new_config.adapter_cb_half_open_probes

    # Distributed idempotency (FSMP-P2-T02)
    config.redis_url = new_config.redis_url
    config.idemp_ttl_ms = new_config.idemp_ttl_ms
    config.idemp_timeout_ms = new_config.idemp_timeout_ms
    config.idemp_retry_max_attempts = new_config.idemp_retry_max_attempts
    config.idemp_retry_base_ms = new_config.idemp_retry_base_ms
    config.idemp_retry_max_ms = new_config.idemp_retry_max_ms
    config.idemp_cb_threshold = new_config.idemp_cb_threshold
    config.idemp_cb_cooldown_ms = new_config.idemp_cb_cooldown_ms
    config.idemp_cb_half_open_probes = new_config.idemp_cb_half_open_probes
    config.worker_id = new_config.worker_id
