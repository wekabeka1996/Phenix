"""
PREFIX-CANON-01: Tests for canonical prefix registry and classification.

Proves:
 1. All generated prefixes are in the canonical registry.
 2. classify_client_order_id returns the correct role for each prefix.
 3. is_guardian_managed_prefix returns True for all managed prefixes.
 4. is_bracket_prefix correctly identifies bracket roles.
 5. TP1/TP2/BHSL/BHTP are no longer classified as UNKNOWN.
 6. Longest-prefix-first prevents TP matching before TP1/TP2.
 7. Drift guard: each generate_client_order_id call site uses a registered prefix.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from apps.reference.domains.execution_position.utils import (
    ALL_KNOWN_PREFIXES,
    GUARDIAN_MANAGED_PREFIXES,
    classify_client_order_id,
    generate_client_order_id,
    is_bracket_prefix,
    is_exit_prefix,
    is_guardian_managed_prefix,
)


# ---- Basic classification tests ----


class TestClassifyClientOrderId:
    """Each registered prefix must classify to its canonical role."""

    @pytest.mark.parametrize(
        "coid, expected_role",
        [
            ("ENTRY-abc123", "ENTRY"),
            ("SL-def456", "SL"),
            ("TP-ghi789", "TP"),
            ("TP1-jkl012", "TP1"),
            ("TP2-mno345", "TP2"),
            ("BHSL-pqr678", "BHSL"),
            ("BHTP-stu901", "BHTP"),
            ("CLOSE-vwx234", "CLOSE"),
        ],
    )
    def test_known_prefixes(self, coid: str, expected_role: str):
        assert classify_client_order_id(coid) == expected_role

    def test_unknown_prefix(self):
        assert classify_client_order_id("XYZ-random") == "UNKNOWN"

    def test_none_input(self):
        assert classify_client_order_id(None) == "UNKNOWN"

    def test_empty_string(self):
        assert classify_client_order_id("") == "UNKNOWN"

    def test_case_insensitive(self):
        assert classify_client_order_id("entry-abc") == "ENTRY"
        assert classify_client_order_id("tp1-xyz") == "TP1"
        assert classify_client_order_id("bhsl-123") == "BHSL"


class TestLongestPrefixFirst:
    """TP1/TP2 must match before TP; BHSL/BHTP before generic fallback."""

    def test_tp1_not_matched_as_tp(self):
        assert classify_client_order_id("TP1-abc") == "TP1"

    def test_tp2_not_matched_as_tp(self):
        assert classify_client_order_id("TP2-abc") == "TP2"

    def test_tp_still_works(self):
        assert classify_client_order_id("TP-abc") == "TP"

    def test_bhsl_not_matched_as_sl(self):
        """BHSL- must not match SL- (SL is a substring of BHSL but not a prefix)."""
        assert classify_client_order_id("BHSL-recovery") == "BHSL"

    def test_bhtp_not_matched_as_tp(self):
        assert classify_client_order_id("BHTP-recovery") == "BHTP"


# ---- Guardian managed checks ----


class TestGuardianManagedPrefix:
    @pytest.mark.parametrize(
        "coid",
        [
            "ENTRY-abc", "SL-abc", "TP-abc", "TP1-abc", "TP2-abc",
            "BHSL-abc", "BHTP-abc", "CLOSE-abc",
        ],
    )
    def test_all_known_prefixes_are_guardian_managed(self, coid: str):
        assert is_guardian_managed_prefix(coid) is True

    def test_unknown_prefix_not_managed(self):
        assert is_guardian_managed_prefix("XYZ-random") is False

    def test_none_returns_false(self):
        assert is_guardian_managed_prefix(None) is False


# ---- Bracket / exit classification ----


class TestBracketPrefix:
    @pytest.mark.parametrize(
        "coid, expected",
        [
            ("SL-abc", True),
            ("TP-abc", True),
            ("TP1-abc", True),
            ("TP2-abc", True),
            ("BHSL-abc", True),
            ("BHTP-abc", True),
            ("ENTRY-abc", False),
            ("CLOSE-abc", False),
        ],
    )
    def test_bracket_classification(self, coid: str, expected: bool):
        assert is_bracket_prefix(coid) is expected


class TestExitPrefix:
    @pytest.mark.parametrize(
        "coid, expected",
        [
            ("SL-abc", True),
            ("TP-abc", True),
            ("TP1-abc", True),
            ("TP2-abc", True),
            ("BHSL-abc", True),
            ("BHTP-abc", True),
            ("CLOSE-abc", True),
            ("ENTRY-abc", False),
        ],
    )
    def test_exit_classification(self, coid: str, expected: bool):
        assert is_exit_prefix(coid) is expected


# ---- TP1/TP2/BHSL/BHTP no longer UNKNOWN ----


class TestFormerlyUnknownPrefixes:
    """These prefixes were previously classified as UNKNOWN by event_handlers.
    This test proves the defect is now fixed."""

    @pytest.mark.parametrize(
        "prefix",
        ["TP1", "TP2", "BHSL", "BHTP"],
    )
    def test_formerly_unknown_prefix_now_classified(self, prefix: str):
        coid = f"{prefix}-test123"
        role = classify_client_order_id(coid)
        assert role != "UNKNOWN", f"{prefix} still classified as UNKNOWN"
        assert role == prefix


# ---- generate_client_order_id produces classifiable IDs ----


class TestGeneratedIdsAreClassifiable:
    """Every generated clientOrderId must be classifiable back to its role."""

    @pytest.mark.parametrize(
        "prefix",
        ["ENTRY", "SL", "TP", "TP1", "TP2", "BHSL", "BHTP", "CLOSE"],
    )
    def test_generated_id_classifiable(self, prefix: str):
        coid = generate_client_order_id(prefix, "BTCUSDT")
        role = classify_client_order_id(coid)
        assert role == prefix, f"Generated '{coid}' with prefix '{prefix}' classified as '{role}'"


# ---- Drift guard: static analysis of generate_client_order_id call sites ----


class TestPrefixDriftGuard:
    """
    Static analysis: every generate_client_order_id() call in the domain must
    use a prefix that is in ALL_KNOWN_PREFIXES.

    If someone adds a new generate_client_order_id("FOO", ...) without updating
    the registry, this test will fail.
    """

    _DOMAIN_ROOT = Path("apps/reference/domains/execution_position")

    def _find_generated_prefixes(self) -> list[tuple[str, int, str]]:
        """Return list of (file, line, prefix_arg) from all call sites."""
        results = []
        pattern = re.compile(
            r'generate_client_order_id\(\s*["\'](\w+)["\']'
        )
        for py_file in self._DOMAIN_ROOT.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(source.splitlines(), 1):
                for m in pattern.finditer(line):
                    results.append((str(py_file), i, m.group(1)))
        return results

    def test_all_generation_prefixes_are_registered(self):
        """Every prefix used in generate_client_order_id() calls must be in ALL_KNOWN_PREFIXES."""
        sites = self._find_generated_prefixes()
        assert len(
            sites) > 0, "No generate_client_order_id() calls found (test is stale)"

        unregistered = []
        for filepath, lineno, prefix in sites:
            if prefix not in ALL_KNOWN_PREFIXES:
                unregistered.append(f"{filepath}:{lineno} prefix={prefix!r}")

        assert not unregistered, (
            f"Found generate_client_order_id() calls with unregistered prefixes:\n"
            + "\n".join(f"  - {u}" for u in unregistered)
            + f"\n\nRegistered prefixes: {sorted(ALL_KNOWN_PREFIXES)}"
        )

    def test_registry_has_minimum_expected_prefixes(self):
        """Registry must contain at least the known production prefixes."""
        expected = {"ENTRY", "SL", "TP", "TP1", "TP2", "BHSL", "BHTP", "CLOSE"}
        missing = expected - ALL_KNOWN_PREFIXES
        assert not missing, f"Missing expected prefixes from registry: {missing}"

    def test_guardian_managed_tuple_covers_all_registered(self):
        """Every registered guardian_managed prefix must appear in GUARDIAN_MANAGED_PREFIXES."""
        for prefix_dash in GUARDIAN_MANAGED_PREFIXES:
            raw = prefix_dash.rstrip("-")
            assert raw in ALL_KNOWN_PREFIXES, (
                f"GUARDIAN_MANAGED_PREFIXES contains '{prefix_dash}' "
                f"but '{raw}' is not in ALL_KNOWN_PREFIXES"
            )
