from pathlib import Path


def test_no_shadow_adapter_imports_in_prod_code():
    """
    Ensure non-test, non-shadow code does not pull shadow adapters in V2 runtime paths.
    """
    root = Path("apps/reference")
    offenders = []
    for py in root.rglob("*.py"):
        if "tests" in py.parts or "shadow_execpos" in py.parts or "legacy" in py.parts or "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        # flag suspicious adapter references to shadow_execpos execution adapters
        if "shadow_execpos" in text and "execution_adapter" in text:
            offenders.append(py)
    assert not offenders, f"Unexpected shadow adapter references in prod code: {offenders}"


def test_main_and_runtime_factory_no_shadow_adapter_hint():
    """
    Ensure main/runtime_factory V2 branch does not mention shadow adapter wiring.
    """
    targets = [
        Path("apps/reference/main.py"),
        Path("apps/reference/domains/execution_position/runtime_factory.py"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "shadow_execpos adapter" not in text.lower()
