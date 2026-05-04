import importlib.util
import logging
from pathlib import Path


def _count_tagged_handlers(tag: str) -> int:
    root = logging.getLogger()
    return sum(1 for h in root.handlers if getattr(h, tag, False))


def test_importing_main_does_not_duplicate_logging_handlers() -> None:
    tag = "_aurora_main_logging_configured"
    before = _count_tagged_handlers(tag)

    repo_root = Path(__file__).resolve().parents[2]
    main_path = repo_root / "apps" / "reference" / "main.py"

    spec1 = importlib.util.spec_from_file_location("apps.reference.main_once", str(main_path))
    mod1 = importlib.util.module_from_spec(spec1)
    assert spec1 and spec1.loader
    spec1.loader.exec_module(mod1)  # type: ignore[attr-defined]
    after_first = _count_tagged_handlers(tag)
    assert after_first >= before

    spec2 = importlib.util.spec_from_file_location("apps.reference.main_twice", str(main_path))
    mod2 = importlib.util.module_from_spec(spec2)
    assert spec2 and spec2.loader
    spec2.loader.exec_module(mod2)  # type: ignore[attr-defined]
    after_second = _count_tagged_handlers(tag)

    assert after_second == after_first, "Importing main.py multiple times must not add duplicate handlers"

