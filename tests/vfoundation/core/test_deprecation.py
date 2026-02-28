"""Tests for Deprecation Policy Validator — Phase 16.4."""
import warnings

import pytest

from vfoundation.core.deprecation import (
    DeprecationEntry,
    DeprecationRegistry,
    deprecated,
)


class TestDeprecationRegistry:
    """Phase 16.4: Deprecation tracking and enforcement tests."""

    def test_register_and_get(self):
        """Register an entry and retrieve it."""
        reg = DeprecationRegistry()
        entry = DeprecationEntry(
            name="Message.oco_group_id",
            deprecated_since="2026-03-01",
            removal_target="2026-06-01",
            replacement="pld['oco_group_id']",
        )
        reg.register(entry)
        result = reg.get("Message.oco_group_id")
        assert result is not None
        assert result.name == "Message.oco_group_id"
        assert result.replacement == "pld['oco_group_id']"

    def test_get_nonexistent_returns_none(self):
        """get() returns None for unregistered name."""
        reg = DeprecationRegistry()
        assert reg.get("nonexistent") is None

    def test_is_deprecated_true(self):
        """is_deprecated() returns True for registered entry."""
        reg = DeprecationRegistry()
        reg.register(DeprecationEntry(
            name="old_api", deprecated_since="v1", removal_target="v3",
        ))
        assert reg.is_deprecated("old_api") is True

    def test_is_deprecated_false(self):
        """is_deprecated() returns False for unregistered name."""
        reg = DeprecationRegistry()
        assert reg.is_deprecated("new_api") is False

    def test_warn_if_deprecated_emits_warning(self):
        """warn_if_deprecated() emits DeprecationWarning for deprecated entry."""
        reg = DeprecationRegistry()
        reg.register(DeprecationEntry(
            name="old_func",
            deprecated_since="2026-01-01",
            removal_target="2026-06-01",
            replacement="new_func",
        ))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            reg.warn_if_deprecated("old_func")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "old_func" in str(w[0].message)
            assert "new_func" in str(w[0].message)

    def test_warn_if_deprecated_noop_for_unknown(self):
        """warn_if_deprecated() does nothing for non-deprecated name."""
        reg = DeprecationRegistry()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            reg.warn_if_deprecated("not_deprecated")
            assert len(w) == 0

    def test_all_entries_list(self):
        """all_entries() returns all registered deprecation entries."""
        reg = DeprecationRegistry()
        reg.register(DeprecationEntry(name="a", deprecated_since="v1", removal_target="v3"))
        reg.register(DeprecationEntry(name="b", deprecated_since="v1", removal_target="v3"))
        entries = reg.all_entries()
        assert len(entries) == 2
        names = {e.name for e in entries}
        assert names == {"a", "b"}


class TestDeprecatedDecorator:
    """Phase 16.4: @deprecated decorator tests."""

    def test_decorator_emits_warning(self):
        """@deprecated decorator emits DeprecationWarning on call."""
        @deprecated(name="old_func", since="v1", removal="v3", replacement="new_func")
        def old_func():
            return 42

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_func()
            assert result == 42
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "old_func" in str(w[0].message)
            assert "v3" in str(w[0].message)

    def test_decorator_preserves_return_value(self):
        """@deprecated decorator preserves the original return value."""
        @deprecated(name="compute", since="v2", removal="v4")
        def compute(x, y):
            return x + y

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert compute(3, 7) == 10

    def test_decorator_preserves_function_name(self):
        """@deprecated decorator preserves __name__ via functools.wraps."""
        @deprecated(name="my_func", since="v1", removal="v2")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"
