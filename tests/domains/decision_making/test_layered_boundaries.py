"""Guard Variant B decision_making layer visibility."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DM_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "decision_making"
SHARED_DIR = PROJECT_ROOT / "apps" / \
    "reference" / "shared" / "decision_primitives"
DM_PREFIX = "apps.reference.domains.decision_making"
SHARED_PREFIX = "apps.reference.shared.decision_primitives"
STRATEGY_RUNTIMES_PREFIX = "apps.reference.domains.strategies.runtimes"
CONFIG_MODELS_PREFIX = "apps.reference.config_models"
MOVED_PRIMITIVE_PREFIXES = (
    f"{DM_PREFIX}.primitives.scoring_kernel",
    f"{DM_PREFIX}.primitives.aurora_math",
    f"{DM_PREFIX}.primitives.aurora_policy",
    f"{DM_PREFIX}.primitives.entry_plan",
    f"{DM_PREFIX}.primitives.exit_manager",
    f"{DM_PREFIX}.primitives.tpsl_owner",
    f"{DM_PREFIX}.primitives.sizing_margin_first",
    f"{DM_PREFIX}.primitives.instrument_quantizer",
    f"{DM_PREFIX}.primitives.shields",
)

# Rule: core is the composition root and may import any layer below it,
# except concrete strategy runtimes (those are registry/plugin-mediated).
# See DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_04.md section 2.
LAYER_RULES = {
    "core": {"forbid": ["strategies"]},
    "gateway": {"forbid": ["strategies"]},
    "gates": {"forbid": ["strategies", "intent.builder", "intent.emitter"]},
    "intent": {"forbid": ["strategies"]},
    "primitives": {"forbid": ["core", "gateway", "gates", "intent", "strategies", "observability"]},
    "contracts": {"forbid": ["core", "gateway", "gates", "intent", "strategies", "primitives"]},
    "observability": {"forbid": ["strategies"]},
}


def _import_sources(path: Path, package_root: Path, package_prefix: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sources: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                parts = path.relative_to(package_root).parts[:-1]
                base = [package_prefix, *
                        parts[: max(0, len(parts) - node.level + 1)]]
                sources.append(".".join([*base, node.module]))
            else:
                sources.append(node.module)
        elif isinstance(node, ast.Import):
            sources.extend(alias.name for alias in node.names)
    return sources


def _dm_layer(module: str) -> str | None:
    prefix = f"{DM_PREFIX}."
    if not module.startswith(prefix):
        return None
    remainder = module[len(prefix):]
    return remainder.split(".", 1)[0]


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


def _dm_production_paths() -> list[Path]:
    paths: list[Path] = []
    for layer in LAYER_RULES:
        layer_root = DM_DIR / layer
        if layer_root.exists():
            paths.extend(_iter_python_files(layer_root))
    return paths


def _is_allowed_shared_app_import(source: str) -> bool:
    return (
        source.startswith(f"{SHARED_PREFIX}.")
        or source.startswith("apps.reference.core.")
        or source == CONFIG_MODELS_PREFIX
        or source.startswith(f"{CONFIG_MODELS_PREFIX}.")
    )


def test_positive_allowed_dm_local_and_shared_imports():
    imports = _import_sources(
        DM_DIR / "primitives" / "position_queries.py", DM_DIR, DM_PREFIX)
    assert f"{DM_PREFIX}.contracts.normalized_reject_reasons" in imports
    assert f"{SHARED_PREFIX}.sizing_margin_first" in imports


def test_negative_layer_forbidden_imports_are_absent():
    violations: list[str] = []
    for layer, rule in LAYER_RULES.items():
        for path in _iter_python_files(DM_DIR / layer):
            for source in _import_sources(path, DM_DIR, DM_PREFIX):
                if not source.startswith(f"{DM_PREFIX}."):
                    continue
                for forbidden in rule["forbid"]:
                    forbidden_prefix = f"{DM_PREFIX}.{forbidden}"
                    if source == forbidden_prefix or source.startswith(f"{forbidden_prefix}."):
                        violations.append(
                            f"{path.relative_to(PROJECT_ROOT).as_posix()} imports {source}")
    assert not violations


def test_dm_runtime_tree_does_not_import_strategy_runtimes():
    violations: list[str] = []
    for path in _dm_production_paths():
        for source in _import_sources(path, DM_DIR, DM_PREFIX):
            if source.startswith(STRATEGY_RUNTIMES_PREFIX):
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()} imports {source}")
    assert not violations


def test_dm_runtime_tree_uses_shared_decision_primitives_for_moved_modules():
    violations: list[str] = []
    for path in _dm_production_paths():
        for source in _import_sources(path, DM_DIR, DM_PREFIX):
            for old_prefix in MOVED_PRIMITIVE_PREFIXES:
                if source == old_prefix or source.startswith(f"{old_prefix}."):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT).as_posix()} imports {source}")
    assert not violations


def test_shared_decision_primitives_import_only_allowed_app_prefixes():
    violations: list[str] = []
    for path in _iter_python_files(SHARED_DIR):
        for source in _import_sources(path, SHARED_DIR, SHARED_PREFIX):
            if not source.startswith("apps."):
                continue
            if not _is_allowed_shared_app_import(source):
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()} imports {source}")
    assert not violations
