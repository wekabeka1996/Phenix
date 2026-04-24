"""
CONTRACT-SSOT-GUARD-01 — Contract SSOT identity and drift guardrails.

Enforces:
- WhyCode in decision_making IS the same object as vfoundation WhyCode
- NormalizedRejectReasons re-export preserves identity
- No independent WhyCode enum definitions outside canonical source
- VERB_PAYLOAD_MAP is frozen at expected size (compatibility-only)
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestWhyCodeSSOT:
    """Guard: WhyCode has exactly one canonical source."""

    def test_decision_making_whycode_is_vfoundation_whycode(self):
        """decision_making.why_codes.WhyCode must be the exact same class as
        vfoundation.core.why_codes.WhyCode (re-export, not a fork)."""
        from vfoundation.core.why_codes import WhyCode as CanonicalWhyCode
        from apps.reference.domains.decision_making.contracts.why_codes import WhyCode as DmWhyCode

        assert DmWhyCode is CanonicalWhyCode, (
            "decision_making WhyCode is NOT the same object as vfoundation WhyCode. "
            "The compatibility shim may have been replaced with a local definition."
        )

    def test_decision_making_helpers_are_canonical(self):
        """decision_making get_why_description and format_why_with_details must
        be the same functions as vfoundation's."""
        from vfoundation.core.why_codes import (
            get_why_description as canonical_desc,
            format_why_with_details as canonical_fmt,
        )
        from apps.reference.domains.decision_making.contracts.why_codes import (
            get_why_description as dm_desc,
            format_why_with_details as dm_fmt,
        )

        assert dm_desc is canonical_desc
        assert dm_fmt is canonical_fmt

    def test_whycode_has_sizing_and_signal_codes(self):
        """Canonical WhyCode must contain SIZING and SIGNAL codes
        (promoted from decision_making fork in SSOT consolidation)."""
        from vfoundation.core.why_codes import WhyCode

        for name in (
            "SIZING_KELLY_FRACTION",
            "SIZING_CAPPED_BY_LIQUIDITY",
            "SIZING_FLOORED_BY_MIN_SIZE",
            "SIZING_ERROR_NO_INSTRUMENT_SPECS",
            "SIZING_ERROR_QTY_ZERO_AFTER_ROUNDING",
            "SIZING_SUCCESS",
            "SIGNAL_NEUTRAL",
        ):
            assert hasattr(WhyCode, name), (
                f"WhyCode.{name} missing — was it removed from canonical source?"
            )

    def test_no_independent_whycode_enum_in_decision_making(self):
        """decision_making/why_codes.py must NOT define its own WhyCode class
        (must only re-export from vfoundation)."""
        dm_path = (
            PROJECT_ROOT
            / "apps"
            / "reference"
            / "domains"
            / "decision_making"
            / "why_codes.py"
        )
        source = dm_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        local_classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        ]
        assert "WhyCode" not in local_classes, (
            "decision_making/why_codes.py defines a local WhyCode class. "
            "It must only re-export from vfoundation.core.why_codes."
        )


class TestNRRSSOT:
    """Guard: NormalizedRejectReasons has one canonical source."""

    def test_shared_types_nrr_is_canonical(self):
        """shared/types.py NRR re-export must be the exact same class."""
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
            NormalizedRejectReasons as CanonicalNRR,
        )
        from apps.reference.shared.types import NormalizedRejectReasons as SharedNRR

        assert SharedNRR is CanonicalNRR, (
            "shared/types.py NormalizedRejectReasons is NOT the canonical class"
        )

    def test_nrr_codes_follow_format(self):
        """All NRR class-level codes must match NRR-\\d{3} or NRR-CFG-\\d{3}."""
        import re
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
            NormalizedRejectReasons as NRR,
        )

        pattern = re.compile(r"^NRR-(\d{3}|CFG-\d{3}|999)$")
        for attr_name in dir(NRR):
            if attr_name.isupper() and not attr_name.startswith("_"):
                val = getattr(NRR, attr_name)
                if isinstance(val, str) and val.startswith("NRR-"):
                    assert pattern.match(val), (
                        f"NRR code {attr_name}={val} violates format contract"
                    )


class TestVerbPayloadMapFrozen:
    """Guard: VERB_PAYLOAD_MAP is compatibility-only and frozen."""

    def test_payload_map_size_frozen(self):
        """VERB_PAYLOAD_MAP must stay at 11 entries (compatibility-only).
        New payloads go in domain-local models, not here."""
        from vfoundation.core.payloads import VERB_PAYLOAD_MAP

        assert len(VERB_PAYLOAD_MAP) == 11, (
            f"VERB_PAYLOAD_MAP has {len(VERB_PAYLOAD_MAP)} entries, expected 11. "
            "New typed payloads should be domain-local Pydantic models, "
            "not additions to the legacy VERB_PAYLOAD_MAP."
        )


class TestContractRegistryOwnership:
    """Guard: verb_registry_v1.yaml is the canonical registry location."""

    def test_registry_file_exists(self):
        registry = (
            PROJECT_ROOT
            / "apps"
            / "reference"
            / "dictionaries"
            / "verb_registry_v1.yaml"
        )
        assert registry.exists(), "Canonical verb registry not found"

    def test_no_alternative_verb_registries(self):
        """No other verb_registry YAML files should exist outside the canonical location."""
        canonical = (
            PROJECT_ROOT
            / "apps"
            / "reference"
            / "dictionaries"
            / "verb_registry_v1.yaml"
        )
        all_registries = list(PROJECT_ROOT.rglob("verb_registry*.yaml"))
        non_canonical = [
            p for p in all_registries
            if p.resolve() != canonical.resolve()
        ]
        assert not non_canonical, (
            f"Alternative verb registries found: {non_canonical}. "
            "There must be exactly one canonical registry."
        )
