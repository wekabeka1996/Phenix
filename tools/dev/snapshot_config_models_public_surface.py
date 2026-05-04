"""Generate the public-surface manifest snapshot for apps.reference.config_models.

CONFIG_MODELS Phase 0 (2026-04-18). See [CONFIG_MODELS_ROADMAP.md](../../../CONFIG_MODELS_ROADMAP.md)
section 14 (Validation doctrine).

Run manually only when the roadmap explicitly authorizes a manifest update
(i.e. when a new public name is being added by a planned package). The
roadmap mandates that the manifest is a *frozen* snapshot used by
``tests/config/test_config_models_public_surface.py`` as a no-removal /
no-field-removal contract for every subsequent decomposition package.

Usage:
    python tools/dev/snapshot_config_models_public_surface.py

This rewrites tests/config/_artifacts/config_models_public_surface.json.
The diff MUST be reviewed and approved against the roadmap before commit.
"""
from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

from apps.reference import config_models as cm

ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "config"
    / "_artifacts"
    / "config_models_public_surface.json"
)


def _classify(name: str, value: Any) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"name": name}
    if isinstance(value, type) and issubclass(value, BaseModel):
        entry["kind"] = "pydantic_model"
        entry["fields"] = sorted(value.model_fields.keys())
    elif isinstance(value, type) and issubclass(value, enum.Enum):
        entry["kind"] = "enum"
        entry["members"] = sorted(m.name for m in value)
    elif isinstance(value, type):
        entry["kind"] = "class"
    elif callable(value):
        entry["kind"] = "callable"
    elif isinstance(value, (frozenset, set)):
        entry["kind"] = "set_constant"
        entry["members"] = sorted(str(x) for x in value)
    elif isinstance(value, (list, tuple)):
        entry["kind"] = "sequence_constant"
        entry["members"] = [str(x) for x in value]
    elif isinstance(value, (str, int, float, bool)) or value is None:
        entry["kind"] = "scalar_constant"
    else:
        entry["kind"] = "other"
    return entry


def _collect() -> Dict[str, Any]:
    public: Dict[str, Dict[str, Any]] = {}
    for name in dir(cm):
        if name.startswith("__"):
            continue
        # Exclude re-imported standard / third-party symbols that are
        # not part of the config_models contract surface.
        value = getattr(cm, name)
        if getattr(value, "__module__", None) not in (cm.__name__, None):
            # Re-exported from elsewhere; skip unless it is a known
            # contract-surface re-export (back-compat aliases of local
            # classes preserve __module__ == config_models so they are
            # included automatically).
            continue
        public[name] = _classify(name, value)
    return {
        "module": cm.__name__,
        "public_surface_version": 1,
        "names": public,
    }


def main() -> None:
    manifest = _collect()
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {ARTIFACT_PATH} with {len(manifest['names'])} public names")


if __name__ == "__main__":
    main()
