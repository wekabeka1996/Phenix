"""Public-surface contract for ``apps.reference.config_models``.

CONFIG_MODELS Phase 0 (2026-04-18). Gate test for every subsequent
package in the decomposition initiative — see
[CONFIG_MODELS_ROADMAP.md](../../CONFIG_MODELS_ROADMAP.md), section 14.

Contract enforced (additive-only):

1. Every name present in the frozen snapshot must still be importable
   from ``apps.reference.config_models``.
2. For each Pydantic model in the snapshot, every previously-frozen
   field must still be present (no field removal). Adding new fields is
   allowed; removing is not.
3. For each enum in the snapshot, every previously-frozen member must
   still be present.
4. For each frozen set/sequence constant, every previously-frozen
   member must still be present.

Violations indicate a contract regression in the public façade and
must be addressed before the responsible PR can land. New names may be
added by re-running ``tools/dev/snapshot_config_models_public_surface.py``
*after* the change is explicitly authorized by the roadmap; the diff
must be reviewed.
"""
from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import Any, Dict

import pytest
from pydantic import BaseModel

from apps.reference import config_models as cm
import apps.reference.config.domains.decision_making as domain_dm

ARTIFACT = (
    Path(__file__).resolve().parent
    / "_artifacts"
    / "config_models_public_surface.json"
)


@pytest.fixture(scope="module")
def frozen_manifest() -> Dict[str, Any]:
    assert ARTIFACT.exists(), (
        f"Frozen public-surface manifest not found at {ARTIFACT}. "
        "Regenerate with tools/dev/snapshot_config_models_public_surface.py "
        "(only when the roadmap authorizes a manifest update)."
    )
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_manifest_module_identity(frozen_manifest: Dict[str, Any]) -> None:
    assert frozen_manifest["module"] == cm.__name__
    assert frozen_manifest["public_surface_version"] == 1


def test_no_public_name_was_removed(frozen_manifest: Dict[str, Any]) -> None:
    missing = [
        name for name in frozen_manifest["names"] if not hasattr(cm, name)
    ]
    assert not missing, (
        "The following names were dropped from the public surface of "
        "apps.reference.config_models: "
        f"{sorted(missing)}. Adding names is permitted via a roadmap-"
        "authorized manifest update; removal is not."
    )


def test_no_pydantic_field_was_removed(frozen_manifest: Dict[str, Any]) -> None:
    failures = []
    for name, entry in frozen_manifest["names"].items():
        if entry.get("kind") != "pydantic_model":
            continue
        current = getattr(cm, name, None)
        if not (isinstance(current, type) and issubclass(current, BaseModel)):
            failures.append(f"{name}: no longer a Pydantic model")
            continue
        frozen_fields = set(entry.get("fields", []))
        current_fields = set(current.model_fields.keys())
        removed = frozen_fields - current_fields
        if removed:
            failures.append(f"{name}: removed fields {sorted(removed)}")
    assert not failures, (
        "Pydantic model field-removal regressions:\n  " + "\n  ".join(failures)
    )


def test_no_enum_member_was_removed(frozen_manifest: Dict[str, Any]) -> None:
    failures = []
    for name, entry in frozen_manifest["names"].items():
        if entry.get("kind") != "enum":
            continue
        current = getattr(cm, name, None)
        if not (isinstance(current, type) and issubclass(current, enum.Enum)):
            failures.append(f"{name}: no longer an enum")
            continue
        frozen_members = set(entry.get("members", []))
        current_members = {m.name for m in current}
        removed = frozen_members - current_members
        if removed:
            failures.append(f"{name}: removed members {sorted(removed)}")
    assert not failures, (
        "Enum member removals:\n  " + "\n  ".join(failures)
    )


def test_no_set_constant_member_was_removed(frozen_manifest: Dict[str, Any]) -> None:
    failures = []
    for name, entry in frozen_manifest["names"].items():
        if entry.get("kind") != "set_constant":
            continue
        current = getattr(cm, name, None)
        if not isinstance(current, (set, frozenset)):
            failures.append(f"{name}: no longer a set constant")
            continue
        frozen_members = set(entry.get("members", []))
        current_members = {str(x) for x in current}
        removed = frozen_members - current_members
        if removed:
            failures.append(f"{name}: removed members {sorted(removed)}")
    assert not failures, (
        "Set-constant member removals:\n  " + "\n  ".join(failures)
    )


def test_phase0_no_class_shadowing() -> None:
    """The Phase-9 shield classes must have one canonical source definition.

    Phase 2 / Pkg 7 moves the canonical definitions into the extracted
    decision_making leaf module while the public facade re-exports them.
    """
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    domain_source = Path(domain_dm.__file__).read_text(encoding="utf-8")
    for name in (
        "DangerZoneShieldConfig",
        "ContextShieldConfig",
        "MemoryShieldConfig",
        "ScoringEngineConfig",
    ):
        marker = f"\nclass {name}("
        facade_count = facade_source.count(marker)
        domain_count = domain_source.count(marker)
        assert facade_count == 0, (
            f"{name} should no longer be defined in config_models.py after "
            "Pkg 7 extraction."
        )
        assert domain_count == 1, (
            f"{name} has {domain_count} top-level class definitions in "
            "apps.reference.config.domains.decision_making; expected exactly 1."
        )
