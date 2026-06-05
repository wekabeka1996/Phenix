import ast
from pathlib import Path


def test_main_has_no_to_dict_calls() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    main_py = repo_root / "apps" / "reference" / "main.py"
    src = main_py.read_text(encoding="utf-8")

    tree = ast.parse(src)
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "to_dict":
                hits.append(node.lineno)

    assert hits == [], f"Forbidden .to_dict() calls in apps/reference/main.py at lines: {hits}"

