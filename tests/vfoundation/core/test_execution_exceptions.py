"""Tests for vfoundation.core.adapters.execution_exceptions."""
from __future__ import annotations

import pytest

from vfoundation.core.adapters.execution_exceptions import (
    AdapterError,
    AdapterTimeoutError,
    CBOpenError,
    IdempotentDuplicateError,
    SDKError,
    RateLimitError,
    InvalidModeError,
    ConfigurationError,
)


class TestAdapterError:
    def test_base_error(self) -> None:
        e = AdapterError("something went wrong")
        assert e.why == "something went wrong"
        assert e.code == "ERR.adapter.unknown"
        assert "ERR.adapter.unknown" in str(e)

    def test_why_truncated_at_80(self) -> None:
        e = AdapterError("x" * 200)
        assert len(e.why) == 80

    def test_custom_code(self) -> None:
        e = AdapterError("msg", code="ERR.custom")
        assert e.code == "ERR.custom"

    def test_details_included(self) -> None:
        e = AdapterError("msg", details="extra info")
        assert "extra info" in str(e)


class TestTimeoutError:
    def test_with_actual_ms(self) -> None:
        e = AdapterTimeoutError("submit", 5000, actual_ms=6000)
        assert "6000ms" in e.why
        assert e.code == "ERR.adapter.timeout"

    def test_without_actual_ms(self) -> None:
        e = AdapterTimeoutError("cancel", 3000)
        assert "3000ms" in e.why


class TestCBOpenError:
    def test_message(self) -> None:
        e = CBOpenError("submit")
        assert "submit" in e.why
        assert e.code == "ERR.adapter.cb_open"


class TestIdempotentDuplicateError:
    def test_short_key(self) -> None:
        e = IdempotentDuplicateError("key-123")
        assert "key-123" in e.why

    def test_long_key_truncated(self) -> None:
        e = IdempotentDuplicateError("a" * 100)
        assert "..." in e.why


class TestSDKError:
    def test_with_code(self) -> None:
        e = SDKError("submit", sdk_code="-2015")
        assert "-2015" in e.why
        assert e.code == "ERR.adapter.sdk_error"

    def test_with_message_as_details(self) -> None:
        e = SDKError("submit", sdk_message="Invalid price")
        assert e.details == "Invalid price"


class TestRateLimitError:
    def test_with_retry_after(self) -> None:
        e = RateLimitError(retry_after_ms=1000)
        assert "1000ms" in e.why

    def test_without_retry_after(self) -> None:
        e = RateLimitError()
        assert "Rate limit" in e.why


class TestInvalidModeError:
    def test_message(self) -> None:
        e = InvalidModeError("submit", "SHADOW", "LIVE")
        assert "SHADOW" in e.why
        assert "LIVE" in e.why


class TestConfigurationError:
    def test_few_keys(self) -> None:
        e = ConfigurationError(["API_KEY", "SECRET"])
        assert "API_KEY" in e.why

    def test_many_keys_truncated(self) -> None:
        e = ConfigurationError(["A", "B", "C", "D", "E"])
        assert "+2 more" in e.why


class TestInheritance:
    def test_all_inherit_from_adapter_error(self) -> None:
        assert issubclass(AdapterTimeoutError, AdapterError)
        assert issubclass(CBOpenError, AdapterError)
        assert issubclass(IdempotentDuplicateError, AdapterError)
        assert issubclass(SDKError, AdapterError)
        assert issubclass(RateLimitError, AdapterError)
        assert issubclass(InvalidModeError, AdapterError)
        assert issubclass(ConfigurationError, AdapterError)

    def test_all_inherit_from_exception(self) -> None:
        for cls in (AdapterError, AdapterTimeoutError, CBOpenError):
            assert issubclass(cls, Exception)
