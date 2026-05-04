"""Persistence helpers for atomic state writes and resilient JSONL reads."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from ..logging_utils import redact_obj
from .models import utc_now_iso


def write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    text = json.dumps(redact_obj(payload), ensure_ascii=False, indent=2)
    try:
        with temp_path.open("w", encoding="utf-8") as file_handle:
            file_handle.write(text)
            file_handle.flush()
            _best_effort_fsync(file_handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def write_text_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file_handle:
            file_handle.write(text)
            file_handle.flush()
            _best_effort_fsync(file_handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def append_jsonl_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(redact_obj(payload), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as file_handle:
        file_handle.write(line + "\n")
        file_handle.flush()
        _best_effort_fsync(file_handle.fileno())


def read_jsonl_records(path: Path, *, quarantine_root: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            quarantine_jsonl_issue(
                source_path=path,
                quarantine_root=quarantine_root,
                line_number=line_number,
                raw_line=raw_line,
                error=f"json_decode_error: {exc}",
            )
            continue
        if not isinstance(payload, dict):
            quarantine_jsonl_issue(
                source_path=path,
                quarantine_root=quarantine_root,
                line_number=line_number,
                raw_line=raw_line,
                error="jsonl_line_must_be_object",
            )
            continue
        rows.append((line_number, payload))
    return rows


def quarantine_jsonl_issue(
    *,
    source_path: Path,
    quarantine_root: Path,
    line_number: int,
    raw_line: str,
    error: str,
) -> Path:
    stamp = utc_now_iso().replace(":", "-")
    target_dir = quarantine_root / stamp
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{source_path.name}.quarantine.jsonl"
    payload = {
        "quarantined_at": utc_now_iso(),
        "source_path": str(source_path),
        "line_number": line_number,
        "error": error,
        "raw_line": raw_line,
    }
    append_jsonl_record(target_path, payload)
    return target_path


def _best_effort_fsync(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError:
        return
