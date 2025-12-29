"""
Test DUPID-PARSE-4116: _safe_read_err now correctly extracts API error code.

Before fix: await resp.json() on httpx.Response would fail (TypeError),
falling back to {"code": 400, "msg": json_string} - losing API code -4116.

After fix: resp.json() (sync) works correctly, returning {"code": -4116, ...}.
"""
import pytest
from apps.reference.adapters.binance_adapter import (
    _safe_read_err,
    _make_binance_error,
    BinanceAPIError,
)


class FakeHttpxResponse:
    """Mock httpx.Response with status_code 400 but API code -4116 in body."""
    status_code = 400
    text = '{"code":-4116,"msg":"ClientOrderId is duplicated."}'

    def json(self):
        return {"code": -4116, "msg": "ClientOrderId is duplicated."}


class TestSafeReadErrFix:
    """DUPID-PARSE-4116: Fix extraction of Binance API error code."""

    def test_safe_read_err_returns_json_dict(self):
        """_safe_read_err should return parsed JSON, not fallback with HTTP status."""
        resp = FakeHttpxResponse()
        err = _safe_read_err(resp)

        assert isinstance(err, dict)
        assert err["code"] == -4116
        assert "duplicated" in err["msg"]

    def test_make_binance_error_uses_api_code_not_http_status(self):
        """_make_binance_error should use API code -4116, not HTTP 400."""
        resp = FakeHttpxResponse()
        err = _safe_read_err(resp)

        exc = _make_binance_error(resp, err)

        assert isinstance(exc, BinanceAPIError)
        assert exc.code == -4116, f"Expected -4116, got {exc.code}"
        assert "duplicated" in exc.msg.lower()

    def test_error_code_4116_triggers_recovery_condition(self):
        """With correct code, e.code == -4116 condition should match."""
        resp = FakeHttpxResponse()
        err = _safe_read_err(resp)
        exc = _make_binance_error(resp, err)

        # This is the condition that was broken before the fix:
        is_duplicate = (exc.code == -4116)

        assert is_duplicate is True, (
            f"Recovery condition 'e.code == -4116' should match! Got code={exc.code}"
        )


class TestSafeReadErrFallback:
    """Ensure fallback still works when json() fails."""

    def test_fallback_when_json_fails(self):
        """If json() throws, fallback to HTTP status code."""
        class BadJsonResponse:
            status_code = 500
            text = "Internal Server Error"

            def json(self):
                raise ValueError("not JSON")

        resp = BadJsonResponse()
        err = _safe_read_err(resp)

        assert err["code"] == 500
        assert "Internal Server Error" in err["msg"]

    def test_fallback_when_json_and_text_fail(self):
        """If both json() and text fail, fallback to 'unknown'."""
        class VeryBadResponse:
            status_code = 502

            @property
            def text(self):
                raise RuntimeError("can't read")

            def json(self):
                raise ValueError("not JSON")

        resp = VeryBadResponse()
        err = _safe_read_err(resp)

        assert err["code"] == 502
        assert err["msg"] == "unknown"
