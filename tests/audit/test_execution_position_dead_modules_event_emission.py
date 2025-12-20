import ast
from pathlib import Path

import pytest


MODULE_PATHS = [
    Path("apps/reference/domains/execution_position/drift_monitor.py"),
    Path("apps/reference/domains/execution_position/idempotent_cancel.py"),
    Path("apps/reference/domains/execution_position/order_index.py"),
]

# What we consider "event emission" in this codebase.
FORBIDDEN_CALL_NAMES = {
    "emit",  # fsm.emit(...)
    "emit_compat",  # vfoundation.core.fsm_emit_compat.emit_compat(...)
}

# Imports that would indicate bus/emit coupling.
FORBIDDEN_IMPORT_MODULES = {
    "vfoundation.core.fsm_emit_compat",
}
FORBIDDEN_IMPORT_SYMBOLS = {
    "emit_compat",
    "Message",
}


def _iter_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _call_name(node: ast.Call) -> str | None:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ("import", alias.name, None)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
            for alias in node.names:
                yield ("from", mod, alias.name)


@pytest.mark.unit
@pytest.mark.parametrize("path", MODULE_PATHS)
def test_dead_modules_do_not_emit_events(path: Path):
    """These modules are expected to be pure helpers/off-path logic (no EVT emission)."""
    assert path.exists(), f"Missing file: {path}"

    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    # 1) No calls to emit/emit_compat
    bad_calls: list[str] = []
    for call in _iter_calls(tree):
        name = _call_name(call)
        if name in FORBIDDEN_CALL_NAMES:
            bad_calls.append(name)

    assert not bad_calls, (
        f"{path} has event-emission calls {sorted(set(bad_calls))}. "
        "If this is intentional, wire it explicitly and add integration tests."
    )

    # 2) No imports of compatibility emitter API
    bad_imports: list[str] = []
    for kind, mod, sym in _iter_imports(tree):
        if kind == "import" and mod in FORBIDDEN_IMPORT_MODULES:
            bad_imports.append(mod)
        if kind == "from" and mod in FORBIDDEN_IMPORT_MODULES and sym in FORBIDDEN_IMPORT_SYMBOLS:
            bad_imports.append(f"{mod}:{sym}")

    assert not bad_imports, (
        f"{path} imports emitter API {sorted(set(bad_imports))}. "
        "That would couple it to runtime event bus unexpectedly."
    )
