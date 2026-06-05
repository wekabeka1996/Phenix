"""Tests for Message v1↔v2 Compatibility Layer — Phase 16.2."""
import warnings

import pytest

from vfoundation.core.protocol import Message
from vfoundation.core.message_compat import (
    TRADING_ENVELOPE_FIELDS,
    is_backward_compatible,
    upgrade_v1_to_v2,
    validate_v2_contract,
)


def _make_msg(**overrides) -> Message:
    """Helper to create a minimal valid Message."""
    defaults = dict(op="CMD", verb="OPEN", src="test", dst="any", why="test-why")
    defaults.update(overrides)
    return Message(**defaults)


class TestUpgradeV1ToV2:
    """Phase 16.2: v1 → v2 upgrade tests."""

    def test_upgrade_sets_v2(self):
        """upgrade_v1_to_v2 sets v=2 on a v=1 message."""
        msg = _make_msg(v=1)
        assert msg.v == 1
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            upgraded = upgrade_v1_to_v2(msg)
        assert upgraded.v == 2

    def test_upgrade_v2_noop(self):
        """upgrade_v1_to_v2 returns v=2 message unchanged."""
        msg = _make_msg(v=2)
        result = upgrade_v1_to_v2(msg)
        assert result is msg  # same object, no copy

    def test_upgrade_emits_deprecation_warning(self):
        """upgrade_v1_to_v2 emits DeprecationWarning for v=1 messages."""
        msg = _make_msg(v=1)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            upgrade_v1_to_v2(msg)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "v=1" in str(w[0].message)
            assert "ADR-003" in str(w[0].message)

    def test_upgrade_preserves_core_fields(self):
        """Upgrade preserves rid, op, verb, src, dst, pld."""
        msg = _make_msg(v=1, pld={"signal": "BUY"})
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            upgraded = upgrade_v1_to_v2(msg)
        assert upgraded.rid == msg.rid
        assert upgraded.op == msg.op
        assert upgraded.verb == msg.verb
        assert upgraded.src == msg.src
        assert upgraded.dst == msg.dst
        assert upgraded.pld["signal"] == "BUY"

    def test_upgrade_migrates_trading_fields_to_pld(self):
        """Upgrade copies top-level trading fields into pld."""
        msg = _make_msg(v=1, oco_group_id="oco-123", link_ack_id="ack-456")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            upgraded = upgrade_v1_to_v2(msg)
        assert upgraded.pld.get("oco_group_id") == "oco-123"
        assert upgraded.pld.get("link_ack_id") == "ack-456"

    def test_upgrade_does_not_overwrite_existing_pld_fields(self):
        """If pld already has a trading field, upgrade does not overwrite it."""
        msg = _make_msg(
            v=1,
            oco_group_id="top-level-value",
            pld={"oco_group_id": "pld-value"},
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            upgraded = upgrade_v1_to_v2(msg)
        assert upgraded.pld["oco_group_id"] == "pld-value"


class TestValidateV2Contract:
    """Phase 16.2: v2 contract validation tests."""

    def test_validate_v2_clean_passes(self):
        """A clean v=2 message with why passes validation."""
        msg = _make_msg(v=2, why="valid reason")
        issues = validate_v2_contract(msg)
        assert issues == []

    def test_validate_v1_reports_version(self):
        """v=1 message fails v2 contract with version issue."""
        msg = _make_msg(v=1, why="reason")
        issues = validate_v2_contract(msg)
        assert any("v=1" in i for i in issues)

    def test_validate_missing_why(self):
        """Message without why fails v2 contract."""
        msg = _make_msg(v=2, why=None)
        issues = validate_v2_contract(msg)
        assert any("why" in i for i in issues)

    def test_validate_trading_field_at_top_level(self):
        """Trading field at top-level fails v2 contract."""
        msg = _make_msg(v=2, oco_group_id="oco-bad")
        issues = validate_v2_contract(msg)
        assert any("oco_group_id" in i for i in issues)


class TestBackwardCompatibility:
    """Phase 16.2: backward compatibility check tests."""

    def test_backward_compatible_after_upgrade(self):
        """Upgraded message is backward compatible with original."""
        msg = _make_msg(v=1, pld={"data": "value"})
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            upgraded = upgrade_v1_to_v2(msg)
        assert is_backward_compatible(msg, upgraded) is True

    def test_not_backward_compatible_different_verb(self):
        """Messages with different verbs are not backward compatible."""
        msg1 = _make_msg(v=1, verb="OPEN")
        msg2 = _make_msg(v=2, verb="CLOSE")
        # Force same rid for fair comparison
        msg2 = msg2.model_copy(update={"rid": msg1.rid})
        assert is_backward_compatible(msg1, msg2) is False
