"""
Tests for Binance demo-fapi diagnostic tool (EP-ADAPTER-DEMO-CONNECTIVITY-S19).

Verifies:
1. Successful checks return exit code 0
2. Signature errors (-1022) are detected and return exit code 1
3. Network errors (ConnectTimeout) are detected and return exit code 1
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from apps.reference.tools.binance_demo_diag import (
    check_ping,
    check_time,
    check_signed_request,
    run_diagnostics,
    DiagnosticResult,
)


@pytest.mark.asyncio
async def test_ping_ok_returns_success():
    """Successful ping returns success=True."""
    # Mock httpx.AsyncClient
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)

        result = await check_ping("https://demo-fapi.binance.com", timeout=10.0)

    assert result.success is True
    assert "OK" in result.message
    assert result.latency_ms >= 0  # Mock may have latency ~0


@pytest.mark.asyncio
async def test_ping_connect_timeout_returns_failure():
    """ConnectTimeout during ping returns success=False."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("Connection timeout"))

        result = await check_ping("https://demo-fapi.binance.com", timeout=10.0)

    assert result.success is False
    assert "CONNECT_TIMEOUT" in result.message


@pytest.mark.asyncio
async def test_time_ok_returns_success_with_server_time():
    """Successful time check returns success=True with serverTime."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"serverTime": 1700000000000}

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)

        result = await check_time("https://demo-fapi.binance.com", timeout=10.0)

    assert result.success is True
    assert "OK" in result.message
    assert "serverTime=1700000000000" in result.message


@pytest.mark.asyncio
async def test_signed_request_ok_returns_success():
    """Successful signed request returns success=True."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)

        result = await check_signed_request(
            "https://demo-fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
            timeout=10.0
        )

    assert result.success is True
    assert "OK" in result.message


@pytest.mark.asyncio
async def test_signed_request_signature_invalid_returns_failure():
    """Signature error (-1022) returns success=False with SIGNATURE_INVALID."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "code": -1022,
        "msg": "Signature for this request is not valid."
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)

        result = await check_signed_request(
            "https://demo-fapi.binance.com",
            api_key="test_key",
            api_secret="wrong_secret",
            timeout=10.0
        )

    assert result.success is False
    assert "SIGNATURE_INVALID" in result.message
    assert "-1022" not in result.message or "SIGNATURE_INVALID" in result.message


@pytest.mark.asyncio
async def test_signed_request_connect_timeout_returns_network_error():
    """ConnectTimeout during signed request returns NETWORK_ERROR."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("Connection timeout"))

        result = await check_signed_request(
            "https://demo-fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
            timeout=10.0
        )

    assert result.success is False
    assert "NETWORK_ERROR" in result.message
    assert "CONNECT_TIMEOUT" in result.message


@pytest.mark.asyncio
async def test_run_diagnostics_all_pass_returns_zero():
    """All checks pass → exit code 0."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"serverTime": 1700000000000}

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)

        with patch("apps.reference.tools.binance_demo_diag.load_config") as mock_config:
            mock_config.return_value = (
                "https://demo-fapi.binance.com",
                "test_key",
                "test_secret",
                20.0
            )

            exit_code = await run_diagnostics()

    assert exit_code == 0


@pytest.mark.asyncio
async def test_run_diagnostics_signature_fail_returns_nonzero():
    """Signature error (-1022) → exit code 1."""
    # Mock: ping OK, time OK, signed FAIL
    def mock_get_side_effect(url, **kwargs):
        if "/ping" in url:
            resp = MagicMock()
            resp.status_code = 200
            return resp
        elif "/time" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"serverTime": 1700000000000}
            return resp
        elif "/balance" in url:
            resp = MagicMock()
            resp.status_code = 400
            resp.json.return_value = {
                "code": -1022, "msg": "Signature invalid"}
            return resp
        else:
            resp = MagicMock()
            resp.status_code = 404
            return resp

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(side_effect=mock_get_side_effect)

        with patch("apps.reference.tools.binance_demo_diag.load_config") as mock_config:
            mock_config.return_value = (
                "https://demo-fapi.binance.com",
                "test_key",
                "wrong_secret",
                20.0
            )

            exit_code = await run_diagnostics()

    assert exit_code == 1


@pytest.mark.asyncio
async def test_run_diagnostics_network_error_returns_nonzero():
    """Network error (ConnectTimeout) → exit code 1."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("Connection timeout"))

        with patch("apps.reference.tools.binance_demo_diag.load_config") as mock_config:
            mock_config.return_value = (
                "https://demo-fapi.binance.com",
                "test_key",
                "test_secret",
                20.0
            )

            exit_code = await run_diagnostics()

    assert exit_code == 1


@pytest.mark.asyncio
async def test_run_diagnostics_no_credentials_skips_signed():
    """No API credentials → skip signed check, return 0 if ping/time pass."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"serverTime": 1700000000000}

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)

        with patch("apps.reference.tools.binance_demo_diag.load_config") as mock_config:
            mock_config.return_value = (
                "https://demo-fapi.binance.com",
                None,  # No API key
                None,  # No API secret
                20.0
            )

            exit_code = await run_diagnostics()

    # Should pass because ping+time OK, signed skipped
    assert exit_code == 0
