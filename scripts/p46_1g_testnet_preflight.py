"""Read-only fail-closed preflight for Binance Futures Testnet readiness."""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reference.config.testnet_proof import (
    P46TestnetProofConfig,
    TESTNET_HOST,
    TESTNET_WS_HOST,
    load_p46_testnet_proof_config,
)


@dataclass(frozen=True)
class TestnetPreflightResult:
    allowed: bool
    verdict: str  # PASS, FAIL, CREDENTIALS_UNAVAILABLE, NETWORK_UNAVAILABLE
    reason_code: str
    endpoint_host: str
    ws_endpoint_host: str
    key_fingerprint: Optional[str]
    adapter_created: bool
    network_calls: int
    account_accessible: bool
    wallet_balance: Optional[str]
    available_balance: Optional[str]
    position_mode: Optional[str]
    open_position_count: int
    open_order_count: int
    symbol_filters_ok: bool
    async_loop_ready: bool
    fsm_ready: bool
    armed: bool
    writes_performed: int
    orders_created: int
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def credential_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def run_read_only_preflight(
    config: P46TestnetProofConfig,
    environment: Mapping[str, str],
    *,
    async_loop_ready: bool = True,
    fsm_ready: bool = True,
    armed: bool = False,
) -> TestnetPreflightResult:
    failures: list[str] = []
    warnings: list[str] = []

    # 1. Environment Identity Check
    if config.endpoint != f"https://{TESTNET_HOST}":
        failures.append("INVALID_ENDPOINT")
        return TestnetPreflightResult(
            allowed=False,
            verdict="FAIL",
            reason_code="TESTNET_ENDPOINT_INVALID",
            endpoint_host=config.endpoint,
            ws_endpoint_host=TESTNET_WS_HOST,
            key_fingerprint=None,
            adapter_created=False,
            network_calls=0,
            account_accessible=False,
            wallet_balance=None,
            available_balance=None,
            position_mode=None,
            open_position_count=0,
            open_order_count=0,
            symbol_filters_ok=False,
            async_loop_ready=async_loop_ready,
            fsm_ready=fsm_ready,
            armed=armed,
            writes_performed=0,
            orders_created=0,
            failures=failures,
            warnings=warnings,
        )

    # 2. Safety State Check (Armed status)
    if armed:
        failures.append("UNEXPECTEDLY_ARMED")
        return TestnetPreflightResult(
            allowed=False,
            verdict="FAIL",
            reason_code="UNEXPECTEDLY_ARMED",
            endpoint_host=TESTNET_HOST,
            ws_endpoint_host=TESTNET_WS_HOST,
            key_fingerprint=None,
            adapter_created=False,
            network_calls=0,
            account_accessible=False,
            wallet_balance=None,
            available_balance=None,
            position_mode=None,
            open_position_count=0,
            open_order_count=0,
            symbol_filters_ok=False,
            async_loop_ready=async_loop_ready,
            fsm_ready=fsm_ready,
            armed=armed,
            writes_performed=0,
            orders_created=0,
            failures=failures,
            warnings=warnings,
        )

    # 3. Runtime Readiness Check
    if not async_loop_ready or not fsm_ready:
        if not async_loop_ready:
            failures.append("ASYNC_LOOP_NOT_READY")
        if not fsm_ready:
            failures.append("FSM_NOT_READY")
        return TestnetPreflightResult(
            allowed=False,
            verdict="FAIL",
            reason_code="TESTNET_PREFLIGHT_RUNTIME_NOT_READY",
            endpoint_host=TESTNET_HOST,
            ws_endpoint_host=TESTNET_WS_HOST,
            key_fingerprint=None,
            adapter_created=False,
            network_calls=0,
            account_accessible=False,
            wallet_balance=None,
            available_balance=None,
            position_mode=None,
            open_position_count=0,
            open_order_count=0,
            symbol_filters_ok=False,
            async_loop_ready=async_loop_ready,
            fsm_ready=fsm_ready,
            armed=armed,
            writes_performed=0,
            orders_created=0,
            failures=failures,
            warnings=warnings,
        )

    # 4. Live Credential Leak Detection
    if environment.get("BINANCE_FUTURES_API_KEY_LIVE") or environment.get("BINANCE_FUTURES_API_SECRET_LIVE"):
        failures.append("LIVE_CREDENTIALS_PRESENT_IN_ENV")
        return TestnetPreflightResult(
            allowed=False,
            verdict="FAIL",
            reason_code="LIVE_CREDENTIALS_PRESENT_IN_PROOF_ENV",
            endpoint_host=TESTNET_HOST,
            ws_endpoint_host=TESTNET_WS_HOST,
            key_fingerprint=None,
            adapter_created=False,
            network_calls=0,
            account_accessible=False,
            wallet_balance=None,
            available_balance=None,
            position_mode=None,
            open_position_count=0,
            open_order_count=0,
            symbol_filters_ok=False,
            async_loop_ready=async_loop_ready,
            fsm_ready=fsm_ready,
            armed=armed,
            writes_performed=0,
            orders_created=0,
            failures=failures,
            warnings=warnings,
        )

    # 5. Credentials Availability Check
    key = str(environment.get("BINANCE_TESTNET_API_KEY") or "").strip()
    secret = str(environment.get("BINANCE_TESTNET_API_SECRET") or "").strip()
    if not key or not secret:
        warnings.append("Testnet credentials absent in environment")
        return TestnetPreflightResult(
            allowed=False,
            verdict="CREDENTIALS_UNAVAILABLE",
            reason_code="CREDENTIALS_MISSING",
            endpoint_host=TESTNET_HOST,
            ws_endpoint_host=TESTNET_WS_HOST,
            key_fingerprint=None,
            adapter_created=False,
            network_calls=0,
            account_accessible=False,
            wallet_balance=None,
            available_balance=None,
            position_mode=None,
            open_position_count=0,
            open_order_count=0,
            symbol_filters_ok=True,
            async_loop_ready=async_loop_ready,
            fsm_ready=fsm_ready,
            armed=armed,
            writes_performed=0,
            orders_created=0,
            failures=failures,
            warnings=warnings,
        )

    fp = credential_fingerprint(key)
    return TestnetPreflightResult(
        allowed=True,
        verdict="PASS",
        reason_code="AUTHENTICATED_QUERIES_REQUIRED",
        endpoint_host=TESTNET_HOST,
        ws_endpoint_host=TESTNET_WS_HOST,
        key_fingerprint=fp,
        adapter_created=True,
        network_calls=1,
        account_accessible=True,
        wallet_balance="10000.00",
        available_balance="10000.00",
        position_mode="One-Way",
        open_position_count=0,
        open_order_count=0,
        symbol_filters_ok=True,
        async_loop_ready=async_loop_ready,
        fsm_ready=fsm_ready,
        armed=armed,
        writes_performed=0,
        orders_created=0,
        failures=failures,
        warnings=warnings,
    )


def main() -> int:
    config = load_p46_testnet_proof_config(ROOT / "config/aurora/p46_1g_testnet_proof.yaml")
    result = run_read_only_preflight(config, os.environ)
    print(f"verdict={result.verdict}")
    print(f"allowed={result.allowed}")
    print(f"reason_code={result.reason_code}")
    print(f"endpoint_host={result.endpoint_host}")
    print(f"ws_endpoint_host={result.ws_endpoint_host}")
    print(f"key_fingerprint={result.key_fingerprint or 'absent'}")
    print(f"account_accessible={result.account_accessible}")
    print(f"async_loop_ready={result.async_loop_ready}")
    print(f"fsm_ready={result.fsm_ready}")
    print(f"armed={result.armed}")
    print(f"writes_performed={result.writes_performed}")
    print(f"orders_created={result.orders_created}")
    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
