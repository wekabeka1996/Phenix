"""Read-only fail-closed preflight for the P46-1G venue proof."""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reference.config.testnet_proof import (
    P46TestnetProofConfig,
    TESTNET_HOST,
    load_p46_testnet_proof_config,
)


@dataclass(frozen=True)
class TestnetPreflightResult:
    allowed: bool
    reason_code: str
    endpoint_host: str
    key_fingerprint: Optional[str]
    adapter_created: bool
    network_calls: int


def credential_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def run_read_only_preflight(
    config: P46TestnetProofConfig,
    environment: Mapping[str, str],
) -> TestnetPreflightResult:
    if config.endpoint != f"https://{TESTNET_HOST}":
        return TestnetPreflightResult(False, "TESTNET_ENDPOINT_INVALID", TESTNET_HOST, None, False, 0)
    key = str(environment.get("BINANCE_TESTNET_API_KEY") or "").strip()
    secret = str(environment.get("BINANCE_TESTNET_API_SECRET") or "").strip()
    if not key or not secret:
        return TestnetPreflightResult(False, "CREDENTIALS_MISSING", TESTNET_HOST, None, False, 0)
    if environment.get("BINANCE_FUTURES_API_KEY_LIVE") or environment.get("BINANCE_FUTURES_API_SECRET_LIVE"):
        return TestnetPreflightResult(
            False, "LIVE_CREDENTIALS_PRESENT_IN_PROOF_ENV", TESTNET_HOST,
            credential_fingerprint(key), False, 0,
        )
    return TestnetPreflightResult(
        True, "AUTHENTICATED_QUERIES_REQUIRED", TESTNET_HOST,
        credential_fingerprint(key), False, 0,
    )


def main() -> int:
    config = load_p46_testnet_proof_config(ROOT / "config/aurora/p46_1g_testnet_proof.yaml")
    result = run_read_only_preflight(config, os.environ)
    print(f"allowed={result.allowed}")
    print(f"reason_code={result.reason_code}")
    print(f"endpoint_host={result.endpoint_host}")
    print(f"key_fingerprint={result.key_fingerprint or 'absent'}")
    print(f"adapter_created={result.adapter_created}")
    print(f"network_calls={result.network_calls}")
    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
