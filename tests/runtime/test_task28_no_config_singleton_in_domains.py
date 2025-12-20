import ast
from pathlib import Path


def _iter_domain_py_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "apps" / "reference" / "domains"
    root = root.resolve()
    return sorted([p for p in root.rglob("*.py") if "__pycache__" not in p.parts])


def _module_endswith(module: str | None, suffix: str) -> bool:
    if not module:
        return False
    return module == suffix or module.endswith("." + suffix)


def _attr_chain(expr: ast.AST) -> str | None:
    """Return dotted chain for Name/Attribute trees (best-effort)."""
    parts: list[str] = []
    cur: ast.AST | None = expr
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        return None
    return ".".join(reversed(parts))


def test_task28_no_config_singleton_in_domains() -> None:
    banned_get_config_module = "apps.reference.config_loader"
    banned_singleton_wrapper_module = "apps.reference.config_symbols"

    offenders: list[str] = []

    for path in _iter_domain_py_files():
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            # Skip non-python-compatible files (should not happen, but don't hide real issues elsewhere)
            continue

        imported_get_config_names: set[str] = set()
        imported_singleton_module_aliases: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and _module_endswith(node.module, banned_get_config_module):
                for alias in node.names:
                    if alias.name == "get_config" or alias.name == "*":
                        imported_get_config_names.add(alias.asname or alias.name)
                        offenders.append(
                            f"{path}: forbidden import from {node.module} import {alias.name}"
                        )

            if isinstance(node, ast.ImportFrom) and _module_endswith(node.module, banned_singleton_wrapper_module):
                for alias in node.names:
                    offenders.append(
                        f"{path}: forbidden import from {node.module} import {alias.name}"
                    )

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == banned_singleton_wrapper_module:
                        imported_singleton_module_aliases.add(alias.asname or alias.name.split(".")[-1])
                        offenders.append(f"{path}: forbidden import {alias.name}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in imported_get_config_names:
                    offenders.append(f"{path}: forbidden call {func.id}()")

                if isinstance(func, ast.Attribute) and func.attr == "get_config":
                    chain = _attr_chain(func)
                    if chain and chain.endswith("apps.reference.config_loader.get_config"):
                        offenders.append(f"{path}: forbidden call {chain}()")
                    if chain and chain.endswith("apps.reference.config_symbols.get_config"):
                        offenders.append(f"{path}: forbidden call {chain}()")
                    # alias.get_config() where alias imported as config_symbols
                    if isinstance(func.value, ast.Name) and func.value.id in imported_singleton_module_aliases:
                        offenders.append(f"{path}: forbidden call {func.value.id}.get_config()")

    assert not offenders, "Forbidden config singleton usage in domains:\n" + "\n".join(offenders)
