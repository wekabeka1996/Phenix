import ast
from pathlib import Path


DOMAINS_ROOT = Path("apps/reference/domains")

# `.to_dict()` is allowed only for DTO/payload serialization (NOT config fallback).
TO_DICT_ALLOWLIST = {
    # DTO/payload (not config)
    "apps/reference/domains/execution_position/drift_monitor.py",
    "apps/reference/domains/execution_position/fsm.py",
    "apps/reference/domains/account_balance/account_connector.py",
    "apps/reference/domains/alpha_search/ensemble.py",
}


def _iter_domain_py_files() -> list[Path]:
    return sorted(p for p in DOMAINS_ROOT.rglob("*.py") if p.is_file())


def _is_to_dict_allowed(rel_path: str) -> bool:
    if "/tests/" in rel_path.replace("\\", "/"):
        return True
    return rel_path in TO_DICT_ALLOWLIST


def _is_isinstance_config_dict(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not (isinstance(node.func, ast.Name) and node.func.id == "isinstance"):
        return False
    if len(node.args) != 2:
        return False

    subject, typ = node.args
    if not (isinstance(typ, ast.Name) and typ.id == "dict"):
        return False

    if isinstance(subject, ast.Name) and subject.id == "config":
        return True
    if (
        isinstance(subject, ast.Attribute)
        and subject.attr == "config"
        and isinstance(subject.value, ast.Name)
        and subject.value.id == "self"
    ):
        return True

    return False


def _raise_name(raise_node: ast.Raise) -> str | None:
    exc = raise_node.exc
    if exc is None:
        return None
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Call):
        fn = exc.func
        if isinstance(fn, ast.Name):
            return fn.id
        if isinstance(fn, ast.Attribute):
            return fn.attr
    return None


def test_task25_no_legacy_config_access_in_domains():
    violations: list[str] = []

    for py in _iter_domain_py_files():
        rel = py.as_posix()
        src = py.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=rel)

        # 1) Ban `.get(..., default)` and `getattr(..., default)` in domains runtime.
        for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
            # `.get(...)` with 2+ provided args (positional+keywords) => default present.
            if isinstance(call.func, ast.Attribute) and call.func.attr == "get":
                if (len(call.args) + len(call.keywords)) >= 2:
                    violations.append(f"{rel}:{call.lineno} forbidden .get(..., default) usage")

            # `getattr(...)` with 3+ provided args (positional+keywords) => default present.
            if isinstance(call.func, ast.Name) and call.func.id == "getattr":
                if (len(call.args) + len(call.keywords)) >= 3:
                    violations.append(f"{rel}:{call.lineno} forbidden getattr(..., default) usage")

            # `.to_dict()` banned except allowlist (DTO/payload only).
            if isinstance(call.func, ast.Attribute) and call.func.attr == "to_dict":
                if not _is_to_dict_allowed(rel):
                    violations.append(f"{rel}:{call.lineno} forbidden .to_dict() usage (not allowlisted)")

        # 2) Ban dict-thinking branches for config except raise-only TypeError/ConfigContractError.
        for if_node in [n for n in ast.walk(tree) if isinstance(n, ast.If)]:
            if not _is_isinstance_config_dict(if_node.test):
                continue

            if len(if_node.body) != 1 or not isinstance(if_node.body[0], ast.Raise):
                violations.append(f"{rel}:{if_node.lineno} dict-config branch must be raise-only")
                continue

            raise_node: ast.Raise = if_node.body[0]
            exc_name = _raise_name(raise_node)
            if exc_name not in {"TypeError", "ConfigContractError"}:
                violations.append(
                    f"{rel}:{raise_node.lineno} dict-config branch must raise TypeError/ConfigContractError"
                )

    assert not violations, "TASK25 policy violations:\n" + "\n".join(violations)

