from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment dependent
    yaml = None


CONFIG_SNAPSHOT_MANIFEST_NAME = "config_snapshot_manifest.json"
SNAPSHOT_MODE = "FROZEN_RUNTIME_BUNDLE_CONFIG_SNAPSHOT"
AUTHORITY_CAVEAT = "CAPTURE_TIME_COPY_ONLY_NO_RUNTIME_YAML_MUTATION"

CONFIG_TARGETS = (
    {
        "relative_path": "config/aurora/domains.yaml",
        "required": True,
        "notes": "Decision-making domain config including LOW_VOL gate thresholds.",
    },
    {
        "relative_path": "config/aurora/trading.yaml",
        "required": True,
        "notes": "Trading mode and execution envelope config.",
    },
    {
        "relative_path": "config/aurora/strategies.yaml",
        "required": True,
        "notes": "Strategy routing and enablement config.",
    },
    {
        "relative_path": "config/aurora/strategies/aurora.yaml",
        "required": True,
        "notes": "Aurora strategy config surface.",
    },
    {
        "relative_path": "config/aurora/strategies/md_amr.yaml",
        "required": True,
        "notes": "MD AMR strategy config surface.",
    },
    {
        "relative_path": "config/aurora/strategies/mean_reversion.yaml",
        "required": True,
        "notes": "Mean reversion strategy config surface.",
    },
    {
        "relative_path": "config/aurora/regime.yaml",
        "required": True,
        "notes": "Regime detector config.",
    },
    {
        "relative_path": "config/aurora/observability.yaml",
        "required": True,
        "notes": "Observability config relevant for future frozen bundles.",
    },
    {
        "relative_path": "config/alpha_search.yaml",
        "required": False,
        "notes": "Optional alpha search runtime config.",
    },
    {
        "relative_path": "config/judge_review.yaml",
        "required": False,
        "notes": "Optional judge review config.",
    },
    {
        "relative_path": "config/judge_simulator.yaml",
        "required": False,
        "notes": "Optional judge simulator config.",
    },
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                    indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_from_timestamp(timestamp: float | int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()


def relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def capture_git_state(repo_root: Path) -> dict[str, Any]:
    try:
        branch = run_git(repo_root, ["branch", "--show-current"])
        commit_sha = run_git(repo_root, ["rev-parse", "HEAD"])
        status_output = run_git(repo_root, ["status", "--short"])
        status_lines = [
            line for line in status_output.splitlines() if line.strip()]
        dirty_config_paths = [
            line.strip() for line in status_lines if "config/" in line.replace("\\", "/")
        ]
        return {
            "branch": branch,
            "commit_sha": commit_sha,
            "status_short": status_lines,
            "dirty_worktree": bool(status_lines),
            "dirty_config_paths": dirty_config_paths,
            "capture_status": "OK",
            "capture_error": None,
        }
    except Exception as exc:  # pragma: no cover - depends on environment
        return {
            "branch": "UNKNOWN",
            "commit_sha": "UNKNOWN",
            "status_short": [],
            "dirty_worktree": False,
            "dirty_config_paths": [],
            "capture_status": "UNAVAILABLE",
            "capture_error": str(exc),
        }


def parse_yaml_file(path: Path) -> tuple[Any, str, list[str], str | None]:
    if not path.exists():
        return None, "MISSING", [], None
    if yaml is None:
        return None, "YAML_LIBRARY_UNAVAILABLE", [], "yaml module unavailable"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - depends on environment/files
        return None, "PARSE_ERROR", [], str(exc)
    if isinstance(payload, dict):
        return payload, "PARSED_MAPPING", sorted(str(key) for key in payload.keys()), None
    return payload, "PARSED_NON_MAPPING", [], None


def freeze_config_snapshot(
    repo_root: str | Path,
    bundle_root: str | Path,
    *,
    git_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    bundle_root = Path(bundle_root).resolve()
    snapshot_root = bundle_root / "config_snapshot"

    if git_state is None:
        git_state = capture_git_state(repo_root)

    file_entries: list[dict[str, Any]] = []
    for config_target in CONFIG_TARGETS:
        relative_path = str(config_target["relative_path"])
        source_path = repo_root / relative_path
        _, parse_status, top_level_keys, parse_error = parse_yaml_file(
            source_path)

        copied_to = None
        size_bytes = None
        modified_time = None
        sha256 = None
        if source_path.exists():
            target_path = snapshot_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            copied_to = relative_to_repo(repo_root, target_path)
            source_stat = source_path.stat()
            size_bytes = source_stat.st_size
            modified_time = iso_from_timestamp(source_stat.st_mtime)
            sha256 = sha256_file(target_path)

        file_entries.append(
            {
                "config": relative_path,
                "required": bool(config_target["required"]),
                "exists": source_path.exists(),
                "size_bytes": size_bytes,
                "sha256": sha256,
                "copied_to": copied_to,
                "modified_time_utc": modified_time,
                "parse_status": parse_status,
                "top_level_keys": top_level_keys,
                "notes": str(config_target["notes"]),
                "parse_error": parse_error,
            }
        )

    summary = {
        "required_files": sum(1 for entry in file_entries if entry["required"]),
        "required_present": sum(
            1 for entry in file_entries if entry["required"] and entry["exists"]
        ),
        "optional_present": sum(
            1 for entry in file_entries if (not entry["required"]) and entry["exists"]
        ),
        "missing_configs": [entry["config"] for entry in file_entries if not entry["exists"]],
        "parse_status_counts": dict(
            Counter(str(entry["parse_status"]) for entry in file_entries)
        ),
        "all_required_present": all(
            entry["exists"] for entry in file_entries if entry["required"]
        ),
    }

    manifest = {
        "generated_at_utc": utc_now_iso(),
        "authority_caveat": AUTHORITY_CAVEAT,
        "snapshot_mode": SNAPSHOT_MODE,
        "future_bundle_target_root": f"{relative_to_repo(repo_root, snapshot_root)}/",
        "git": git_state,
        "files": file_entries,
        "summary": summary,
    }

    manifest_path = bundle_root / CONFIG_SNAPSHOT_MANIFEST_NAME
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest,
        "manifest_path": relative_to_repo(repo_root, manifest_path),
        "snapshot_root": relative_to_repo(repo_root, snapshot_root),
    }
