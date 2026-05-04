import ast
from pathlib import Path


def test_task27_config_symbols_does_not_call_get_config_at_import_time() -> None:
    py = Path("apps/reference/config_symbols.py")
    src = py.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(py))

    import_time_calls: list[int] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            return  # ignore function bodies

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            return

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "get_config":
                import_time_calls.append(node.lineno)
            if isinstance(fn, ast.Attribute) and fn.attr == "get_config":
                import_time_calls.append(node.lineno)

    Visitor().visit(tree)
    assert import_time_calls == [], f"get_config() must not be called at import time: {import_time_calls}"

