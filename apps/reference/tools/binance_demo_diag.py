"""
Binance demo-fapi diagnostic tool (EP-ADAPTER-DEMO-CONNECTIVITY-S19).

Tests connectivity to demo-fapi.binance.com using Aurora testnet config:
1. GET /fapi/v1/ping - basic connectivity
2. GET /fapi/v1/time - server time sync
3. GET /fapi/v2/balance - signed request with API key/secret

Usage:
    python -m apps.reference.tools.binance_demo_diag

Exit codes:
    0: All checks passed
    1: One or more checks failed
"""
import sys
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Tuple, Optional
import asyncio
import logging

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class DiagnosticResult:
    """Result of a single diagnostic check."""

    def __init__(self, name: str, success: bool, latency_ms: float, message: str):
        self.name = name
        self.success = success
        self.latency_ms = latency_ms
        self.message = message


async def check_ping(base_url: str, timeout: float) -> DiagnosticResult:
    """
    Check basic connectivity to Binance demo-fapi.

    Args:
        base_url: Base URL (e.g., https://demo-fapi.binance.com)
        timeout: Request timeout in seconds

    Returns:
        DiagnosticResult with ping status
    """
    url = f"{base_url}/fapi/v1/ping"
    start = time.time()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout)
            latency_ms = (time.time() - start) * 1000

            if resp.status_code == 200:
                return DiagnosticResult(
                    "PING",
                    success=True,
                    latency_ms=latency_ms,
                    message=f"OK ({latency_ms:.0f} ms)"
                )
            else:
                return DiagnosticResult(
                    "PING",
                    success=False,
                    latency_ms=latency_ms,
                    message=f"FAIL (HTTP {resp.status_code})"
                )
    except httpx.ConnectTimeout:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "PING",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (CONNECT_TIMEOUT after {latency_ms:.0f} ms)"
        )
    except httpx.ReadTimeout:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "PING",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (READ_TIMEOUT after {latency_ms:.0f} ms)"
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "PING",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL ({type(e).__name__}: {e})"
        )


async def check_time(base_url: str, timeout: float) -> DiagnosticResult:
    """
    Check server time endpoint.

    Args:
        base_url: Base URL
        timeout: Request timeout in seconds

    Returns:
        DiagnosticResult with time check status
    """
    url = f"{base_url}/fapi/v1/time"
    start = time.time()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout)
            latency_ms = (time.time() - start) * 1000

            if resp.status_code == 200:
                data = resp.json()
                server_time = data.get("serverTime", "N/A")
                return DiagnosticResult(
                    "TIME",
                    success=True,
                    latency_ms=latency_ms,
                    message=f"OK ({latency_ms:.0f} ms, serverTime={server_time})"
                )
            else:
                return DiagnosticResult(
                    "TIME",
                    success=False,
                    latency_ms=latency_ms,
                    message=f"FAIL (HTTP {resp.status_code})"
                )
    except httpx.ConnectTimeout:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "TIME",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (CONNECT_TIMEOUT after {latency_ms:.0f} ms)"
        )
    except httpx.ReadTimeout:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "TIME",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (READ_TIMEOUT after {latency_ms:.0f} ms)"
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "TIME",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL ({type(e).__name__}: {e})"
        )


def sign_request(secret: str, params: dict) -> str:
    """
    Sign request parameters using HMAC SHA256.

    Args:
        secret: API secret key
        params: Query parameters

    Returns:
        Signature string
    """
    query_string = urlencode(params)
    signature = hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature


async def check_signed_request(
    base_url: str,
    api_key: str,
    api_secret: str,
    timeout: float
) -> DiagnosticResult:
    """
    Check signed request to Binance demo-fapi.

    Uses GET /fapi/v2/balance as test endpoint.

    Args:
        base_url: Base URL
        api_key: API key
        api_secret: API secret
        timeout: Request timeout in seconds

    Returns:
        DiagnosticResult with signed request status
    """
    url = f"{base_url}/fapi/v2/balance"
    start = time.time()

    try:
        # Prepare signed request
        timestamp = int(time.time() * 1000)
        params = {
            "timestamp": timestamp,
            "recvWindow": 5000
        }
        signature = sign_request(api_secret, params)
        params["signature"] = signature

        headers = {
            "X-MBX-APIKEY": api_key
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=timeout)
            latency_ms = (time.time() - start) * 1000

            if resp.status_code == 200:
                return DiagnosticResult(
                    "SIGNED",
                    success=True,
                    latency_ms=latency_ms,
                    message=f"OK ({latency_ms:.0f} ms)"
                )
            elif resp.status_code == 400:
                # Check for signature error (-1022)
                try:
                    data = resp.json()
                    code = data.get("code")
                    msg = data.get("msg", "")
                    if code == -1022:
                        return DiagnosticResult(
                            "SIGNED",
                            success=False,
                            latency_ms=latency_ms,
                            message=f"FAIL (SIGNATURE_INVALID: {msg})"
                        )
                    else:
                        return DiagnosticResult(
                            "SIGNED",
                            success=False,
                            latency_ms=latency_ms,
                            message=f"FAIL (HTTP 400, code={code}: {msg})"
                        )
                except Exception:
                    return DiagnosticResult(
                        "SIGNED",
                        success=False,
                        latency_ms=latency_ms,
                        message=f"FAIL (HTTP {resp.status_code})"
                    )
            else:
                return DiagnosticResult(
                    "SIGNED",
                    success=False,
                    latency_ms=latency_ms,
                    message=f"FAIL (HTTP {resp.status_code})"
                )
    except httpx.ConnectTimeout:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "SIGNED",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (NETWORK_ERROR: CONNECT_TIMEOUT after {latency_ms:.0f} ms)"
        )
    except httpx.ReadTimeout:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "SIGNED",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (NETWORK_ERROR: READ_TIMEOUT after {latency_ms:.0f} ms)"
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return DiagnosticResult(
            "SIGNED",
            success=False,
            latency_ms=latency_ms,
            message=f"FAIL (OTHER: {type(e).__name__}: {e})"
        )


def load_config() -> Tuple[str, Optional[str], Optional[str], float]:
    """
    Load Aurora config to extract Binance demo-fapi settings.

    Returns:
        Tuple of (base_url, api_key, api_secret, timeout)
    """
    import os

    # Try to load from Aurora config
    base_url = "https://demo-fapi.binance.com"
    api_key = None
    api_secret = None
    timeout = 20.0

    try:
        # Use existing Aurora config loader
        from apps.reference.config_loader import load_config

        config = load_config()

        # Try to extract trading mode
        try:
            trading_mode = config.config_v2.global_params.trading_mode
            if trading_mode == "testnet":
                base_url = "https://testnet.binancefuture.com"
            logger.info(f"Loaded trading_mode: {trading_mode}")
        except Exception:
            pass

        # Try to extract adapter config from ExecutionPositionConfig
        try:
            ep_config = config.execution_position
            if hasattr(ep_config, 'adapter_config'):
                adapter_cfg = ep_config.adapter_config
                if hasattr(adapter_cfg, 'base_url'):
                    base_url = adapter_cfg.base_url
                if hasattr(adapter_cfg, 'rest_timeout_sec'):
                    timeout = adapter_cfg.rest_timeout_sec
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"Could not load Aurora config: {e}")

    # Fallback to environment variables
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    logger.info(
        f"Config: base_url={base_url}, timeout={timeout}s, api_key={'set' if api_key else 'not set'}")

    return base_url, api_key, api_secret, timeout


async def run_diagnostics() -> int:
    """
    Run all diagnostic checks.

    Returns:
        Exit code (0 if all pass, 1 if any fail)
    """
    logger.info("=" * 60)
    logger.info("Binance demo-fapi Diagnostic Tool")
    logger.info("=" * 60)

    # Load config
    base_url, api_key, api_secret, timeout = load_config()

    # Run checks
    results = []

    # 1. Ping
    logger.info("\nChecking connectivity...")
    ping_result = await check_ping(base_url, timeout)
    results.append(ping_result)
    logger.info(f"  {ping_result.name}: {ping_result.message}")

    # 2. Time
    logger.info("\nChecking server time...")
    time_result = await check_time(base_url, timeout)
    results.append(time_result)
    logger.info(f"  {time_result.name}: {time_result.message}")

    # 3. Signed request (only if credentials available)
    if api_key and api_secret:
        logger.info("\nChecking signed request...")
        signed_result = await check_signed_request(base_url, api_key, api_secret, timeout)
        results.append(signed_result)
        logger.info(f"  {signed_result.name}: {signed_result.message}")
    else:
        logger.warning(
            "\nSkipping signed request check (no API credentials found)")
        logger.warning(
            "  Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")

    # Summary
    logger.info("\n" + "=" * 60)
    all_passed = all(r.success for r in results)
    if all_passed:
        logger.info("✅ All checks passed")
        return 0
    else:
        failed = [r for r in results if not r.success]
        logger.error(f"❌ {len(failed)} check(s) failed:")
        for r in failed:
            logger.error(f"  - {r.name}: {r.message}")
        return 1


def main():
    """CLI entrypoint."""
    exit_code = asyncio.run(run_diagnostics())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
