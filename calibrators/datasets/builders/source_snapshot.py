from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class SnapshotSourceSpec:
    role: str
    source_path: str | Path
    source_kind: str
    required: bool
    notes: str | None = None


def _to_utc_iso(timestamp_s: float | None) -> Optional[str]:
    if timestamp_s is None:
        return None
    return datetime.fromtimestamp(timestamp_s, tz=timezone.utc).isoformat()


def _normalize_source_path(value: str | Path) -> str:
    path = Path(value)
    if path.exists():
        return path.resolve().as_posix()
    if path.is_absolute():
        return path.as_posix()
    return path.as_posix()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_source_file(
    source_path: str | Path,
    dest_dir: str | Path,
    role: str,
    source_kind: str,
    required: bool,
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    source = Path(source_path)
    entry: dict[str, Any] = {
        "role": role,
        "source_path": _normalize_source_path(source),
        "source_kind": source_kind,
        "exists": source.exists(),
        "size_bytes": None,
        "sha256": None,
        "mtime_utc": None,
        "copied_to": None,
        "required": required,
        "notes": notes,
    }
    if not source.exists():
        return entry

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / source.name
    shutil.copy2(source, destination)
    source_stat = source.stat()
    entry.update(
        {
            "size_bytes": source_stat.st_size,
            "sha256": sha256_file(destination),
            "mtime_utc": _to_utc_iso(source_stat.st_mtime),
            "copied_to": destination.resolve().as_posix(),
        }
    )
    return entry


def snapshot_sources(
    sources: Iterable[SnapshotSourceSpec],
    out_dir: str | Path,
    builder_name: str,
    *,
    strict: bool = False,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    snapshot_dir = out_dir / "source_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    source_entries: list[dict[str, Any]] = []
    missing_required_sources: list[str] = []
    warnings: list[str] = []
    for source in sources:
        entry = snapshot_source_file(
            source.source_path,
            snapshot_dir,
            source.role,
            source.source_kind,
            source.required,
            notes=source.notes,
        )
        copied_to = entry.get("copied_to")
        if copied_to is not None:
            entry["copied_to"] = Path(copied_to).resolve().relative_to(
                out_dir.resolve()
            ).as_posix()
        if source.required and not entry["exists"]:
            missing_required_sources.append(source.role)
            warnings.append(
                f"MISSING_REQUIRED_SOURCE:{source.role}:{entry['source_path']}"
            )
        elif not source.required and not entry["exists"]:
            warnings.append(
                f"MISSING_OPTIONAL_SOURCE:{source.role}:{entry['source_path']}"
            )
        source_entries.append(entry)

    if strict and missing_required_sources:
        raise FileNotFoundError("; ".join(warnings))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder": builder_name,
        "repo_root": Path(repo_root).resolve().as_posix() if repo_root is not None else None,
        "sources": source_entries,
        "missing_required_sources": missing_required_sources,
        "warnings": warnings,
    }
    manifest_path = snapshot_dir / "source_snapshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_source_snapshot_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source snapshot manifest must be a JSON object")
    return payload
