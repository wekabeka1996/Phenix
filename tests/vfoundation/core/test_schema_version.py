"""Tests for Schema Version Registry — Phase 16.1."""
import pytest

from vfoundation.core.schema_version import (
    SchemaRegistry,
    SchemaStatus,
    SchemaVersion,
)


class TestSchemaVersionRegistry:
    """Phase 16.1: Schema version lifecycle management tests."""

    def test_register_and_get_roundtrip(self):
        """Register a schema and retrieve it by name."""
        reg = SchemaRegistry()
        sv = SchemaVersion(name="cmd_open_v1", version=1)
        reg.register(sv)
        result = reg.get("cmd_open_v1")
        assert result is not None
        assert result.name == "cmd_open_v1"
        assert result.version == 1
        assert result.status == SchemaStatus.ACTIVE

    def test_register_duplicate_raises(self):
        """Registering the same name twice raises ValueError."""
        reg = SchemaRegistry()
        sv = SchemaVersion(name="cmd_open_v1", version=1)
        reg.register(sv)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(sv)

    def test_deprecate_sets_status_and_successor(self):
        """Deprecating a schema sets DEPRECATED status with successor info."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="cmd_open_v1", version=1))
        reg.deprecate(
            "cmd_open_v1",
            successor="cmd_open_v2",
            removal_target="2026-06-01",
            deprecated_since="2026-03-01",
        )
        sv = reg.get("cmd_open_v1")
        assert sv is not None
        assert sv.status == SchemaStatus.DEPRECATED
        assert sv.successor == "cmd_open_v2"
        assert sv.removal_target == "2026-06-01"
        assert sv.deprecated_since == "2026-03-01"

    def test_deprecate_nonexistent_raises(self):
        """Deprecating a schema that doesn't exist raises KeyError."""
        reg = SchemaRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.deprecate("nonexistent", successor="x", removal_target="2026-06-01")

    def test_remove_sets_status(self):
        """Removing a schema sets REMOVED status."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="evt_fill_v1", version=1))
        reg.deprecate("evt_fill_v1", successor="evt_fill_v2", removal_target="2026-06-01")
        reg.remove("evt_fill_v1")
        sv = reg.get("evt_fill_v1")
        assert sv is not None
        assert sv.status == SchemaStatus.REMOVED

    def test_active_schemas_filter(self):
        """active_schemas() returns only ACTIVE schemas."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="a_v1", version=1))
        reg.register(SchemaVersion(name="b_v1", version=1))
        reg.register(SchemaVersion(name="c_v1", version=1))
        reg.deprecate("b_v1", successor="b_v2", removal_target="2026-06-01")
        active = reg.active_schemas()
        assert len(active) == 2
        active_names = {sv.name for sv in active}
        assert active_names == {"a_v1", "c_v1"}

    def test_deprecated_schemas_filter(self):
        """deprecated_schemas() returns only DEPRECATED schemas."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="a_v1", version=1))
        reg.register(SchemaVersion(name="b_v1", version=1))
        reg.deprecate("b_v1", successor="b_v2", removal_target="2026-06-01")
        deprecated = reg.deprecated_schemas()
        assert len(deprecated) == 1
        assert deprecated[0].name == "b_v1"

    def test_is_active_check(self):
        """is_active() returns correct boolean for active and non-active schemas."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="x_v1", version=1))
        assert reg.is_active("x_v1") is True
        reg.deprecate("x_v1", successor="x_v2", removal_target="2026-06-01")
        assert reg.is_active("x_v1") is False
        assert reg.is_active("nonexistent") is False

    def test_validate_removed_in_use(self):
        """validate_no_removed_in_use() warns when removed schemas are still referenced."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="old_v1", version=1))
        reg.deprecate("old_v1", successor="old_v2", removal_target="2026-06-01")
        reg.remove("old_v1")
        warnings = reg.validate_no_removed_in_use({"old_v1", "other_v1"})
        assert len(warnings) == 1
        assert "old_v1" in warnings[0]
        assert "REMOVED" in warnings[0]

    def test_validate_all_active_ok(self):
        """validate_no_removed_in_use() returns empty list when only active schemas used."""
        reg = SchemaRegistry()
        reg.register(SchemaVersion(name="good_v1", version=1))
        warnings = reg.validate_no_removed_in_use({"good_v1"})
        assert warnings == []

    def test_get_nonexistent_returns_none(self):
        """get() returns None for unregistered schema."""
        reg = SchemaRegistry()
        assert reg.get("nope") is None

    def test_schema_version_frozen(self):
        """SchemaVersion is frozen (immutable)."""
        sv = SchemaVersion(name="frozen_test", version=1)
        with pytest.raises(AttributeError):
            sv.name = "changed"  # type: ignore[misc]
