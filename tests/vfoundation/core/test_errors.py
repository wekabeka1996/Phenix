"""Tests for Error Taxonomy — Phase 17.1."""
import pytest

from vfoundation.core.errors import (
    ErrorCategory,
    ErrorCode,
    ErrorRegistry,
    STANDARD_ERRORS,
)


class TestErrorCategory:
    """Phase 17.1: ErrorCategory enum tests."""

    def test_category_values(self):
        """All categories have distinct non-overlapping ranges."""
        values = [c.value for c in ErrorCategory]
        assert len(values) == len(set(values))
        assert ErrorCategory.VALIDATION == 1000
        assert ErrorCategory.INTERNAL == 9000


class TestErrorCode:
    """Phase 17.1: ErrorCode dataclass tests."""

    def test_code_property(self):
        """code = category + sub_code."""
        ec = ErrorCode(ErrorCategory.TIMEOUT, 1, "ACK_TIMEOUT")
        assert ec.code == 2001

    def test_full_label_property(self):
        """full_label = ERR.<category_name>.<label>."""
        ec = ErrorCode(ErrorCategory.SECURITY, 1, "AUTH_FAILED")
        assert ec.full_label == "ERR.SECURITY.AUTH_FAILED"

    def test_frozen(self):
        """ErrorCode is immutable."""
        ec = ErrorCode(ErrorCategory.VALIDATION, 1, "INVALID")
        with pytest.raises(AttributeError):
            ec.label = "CHANGED"  # type: ignore[misc]


class TestErrorRegistry:
    """Phase 17.1: ErrorRegistry tests."""

    def test_register_and_get(self):
        """Register an error code and retrieve by numeric code."""
        reg = ErrorRegistry()
        ec = ErrorCode(ErrorCategory.VALIDATION, 1, "INVALID_PAYLOAD")
        reg.register(ec)
        result = reg.get(1001)
        assert result is ec

    def test_get_by_label(self):
        """Retrieve error code by full label."""
        reg = ErrorRegistry()
        ec = ErrorCode(ErrorCategory.TIMEOUT, 2, "FILL_TIMEOUT")
        reg.register(ec)
        result = reg.get_by_label("ERR.TIMEOUT.FILL_TIMEOUT")
        assert result is ec

    def test_duplicate_code_raises(self):
        """Registering duplicate code raises ValueError."""
        reg = ErrorRegistry()
        ec1 = ErrorCode(ErrorCategory.VALIDATION, 1, "A")
        ec2 = ErrorCode(ErrorCategory.VALIDATION, 1, "B")
        reg.register(ec1)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(ec2)

    def test_codes_in_category(self):
        """Filter codes by category."""
        reg = ErrorRegistry()
        reg.register(ErrorCode(ErrorCategory.TIMEOUT, 1, "A"))
        reg.register(ErrorCode(ErrorCategory.TIMEOUT, 2, "B"))
        reg.register(ErrorCode(ErrorCategory.SECURITY, 1, "C"))
        timeout_codes = reg.codes_in_category(ErrorCategory.TIMEOUT)
        assert len(timeout_codes) == 2

    def test_all_codes(self):
        """all_codes returns complete list."""
        reg = ErrorRegistry()
        reg.register(ErrorCode(ErrorCategory.DR, 1, "X"))
        reg.register(ErrorCode(ErrorCategory.PROTOCOL, 1, "Y"))
        assert len(reg.all_codes()) == 2

    def test_get_nonexistent_returns_none(self):
        """get() returns None for unknown code."""
        reg = ErrorRegistry()
        assert reg.get(9999) is None


class TestStandardErrors:
    """Phase 17.1: Pre-populated STANDARD_ERRORS singleton tests."""

    def test_standard_errors_has_entries(self):
        """STANDARD_ERRORS should have 9 pre-registered codes."""
        assert len(STANDARD_ERRORS.all_codes()) == 9

    def test_standard_errors_contains_validation(self):
        """STANDARD_ERRORS should contain VALIDATION.INVALID_PAYLOAD."""
        ec = STANDARD_ERRORS.get(1001)
        assert ec is not None
        assert ec.label == "INVALID_PAYLOAD"

    def test_standard_errors_contains_timeout(self):
        """STANDARD_ERRORS should contain TIMEOUT.ORDER_ACK_TIMEOUT."""
        ec = STANDARD_ERRORS.get_by_label("ERR.TIMEOUT.ORDER_ACK_TIMEOUT")
        assert ec is not None
        assert ec.code == 2001
