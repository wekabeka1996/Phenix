from __future__ import annotations

import ast
from pathlib import Path

from tests.domains.neocortex.architecture.test_import_boundaries import (
    HOT_PATH_FILES,
    NEOCORTEX_ROOT,
)


FORBIDDEN_RETURN_SNIPPETS = (
    "return None",
    "return {}",
    "return []",
    'return "FLAT"',
    "return 'FLAT'",
    "return 0.0",
    "zeros(",
    "zeros_like(",
)


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}:
        return True
    return False


def _handler_segment(source: str, handler: ast.ExceptHandler) -> str:
    lines = source.splitlines()
    end_lineno = handler.end_lineno or handler.lineno
    return "\n".join(lines[handler.lineno - 1 : end_lineno])


def _scan_hot_path_file(relative_path: str) -> list[str]:
    filepath = NEOCORTEX_ROOT / relative_path
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not _is_broad_exception(handler):
                continue
            segment = _handler_segment(source, handler)
            if "record_failure_outcome" not in segment and "phase3: allow-broad-exception" not in segment:
                offenders.append(
                    f"{relative_path}:{handler.lineno} broad exception without typed failure ledger"
                )
            if any(snippet in segment for snippet in FORBIDDEN_RETURN_SNIPPETS):
                offenders.append(
                    f"{relative_path}:{handler.lineno} broad exception returns forbidden fallback value"
                )
    return offenders


def test_hot_path_broad_exception_handlers_are_typed_or_absent() -> None:
    offenders: list[str] = []
    for relative_path in HOT_PATH_FILES:
        offenders.extend(_scan_hot_path_file(relative_path))
    assert offenders == [], f"hot-path broad exception audit failed: {offenders}"
