from __future__ import annotations

from pathlib import Path


def test_runtime_code_has_no_star_imports() -> None:
    offenders: list[str] = []
    for path in Path("apps/reference").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if " import *" in text:
            offenders.append(str(path))

    assert offenders == []
