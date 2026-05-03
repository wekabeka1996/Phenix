"""Evidence Bundle schema for script-first runtime forensics."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso
from .persistence import write_json_atomic

BundleValidation = Literal["passed", "failed", "partial"]


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    bundle_id: str = Field(..., min_length=1)
    source: str = "runtime_logs"
    window: str = ""
    files: list[str] = Field(default_factory=list)
    row_count: int = 0
    symbols: list[str] = Field(default_factory=list)
    event_counts: dict[str, int] = Field(default_factory=dict)
    tables: dict[str, Any] = Field(default_factory=dict)
    validation: BundleValidation = "partial"
    insufficient_fields: list[str] = Field(default_factory=list)
    sample_lines: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)

    def summary_text(self) -> str:
        lines = [
            f"EvidenceBundle {self.bundle_id}",
            f"Source: {self.source}  Window: {self.window}",
            f"Files: {len(self.files)}  Rows: {self.row_count}",
            f"Symbols: {', '.join(self.symbols[:10]) if self.symbols else 'none'}",
            f"Validation: {self.validation}",
        ]
        if self.insufficient_fields:
            lines.append(
                f"Insufficient: {', '.join(self.insufficient_fields)}")
        if self.event_counts:
            top = sorted(self.event_counts.items(), key=lambda x: -x[1])[:5]
            lines.append("Top events: " +
                         ", ".join(f"{k}={v}" for k, v in top))
        return "\n".join(lines)

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["summary"] = self.summary_text()
        return data


class EvidenceBundleStore:
    """Store and retrieve evidence bundles from disk."""

    def __init__(self, *, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.bundles_dir = self.root_dir / ".agent_memory" / "evidence_bundles"
        self.bundles_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, bundle_id: str) -> Path:
        return self.bundles_dir / f"{bundle_id}.dsbundle.json"

    def save_bundle(self, bundle: EvidenceBundle) -> Path:
        path = self._path(bundle.bundle_id)
        write_json_atomic(path, bundle.model_dump())
        return path

    def get_bundle(self, bundle_id: str) -> EvidenceBundle:
        import json
        path = self._path(bundle_id)
        if not path.exists():
            raise KeyError(f"Bundle '{bundle_id}' not found")
        return EvidenceBundle(**json.loads(path.read_text(encoding="utf-8")))

    def create_metadata_scan(
        self,
        *,
        log_dir: str | Path,
        window: str = "latest",
        max_sample_lines: int = 20,
    ) -> EvidenceBundle:
        """Scan log directory metadata without dumping full raw log content."""
        log_dir = Path(log_dir)
        files: list[str] = []
        row_count = 0
        event_counts: dict[str, int] = {}
        sample_lines: list[str] = []
        insufficient: list[str] = []

        if not log_dir.exists():
            return EvidenceBundle(
                bundle_id=uuid.uuid4().hex,
                source="runtime_logs",
                window=window,
                validation="failed",
                insufficient_fields=["log_dir_not_found"],
            )

        for log_file in sorted(log_dir.glob("**/*.log")) + sorted(log_dir.glob("**/*.jsonl")):
            rel = str(log_file.relative_to(log_dir))
            files.append(rel)
            try:
                lines = log_file.read_text(
                    encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            row_count += len(lines)
            for line in lines[:max_sample_lines]:
                if len(sample_lines) < max_sample_lines:
                    # Only store first 200 chars per line — never full raw content
                    sample_lines.append(line[:200])
                # Count event types (keyword heuristic)
                for kw in ("EVT:", "CMD:", "ERR", "INFO", "WARN", "DEBUG"):
                    if kw in line:
                        event_counts[kw] = event_counts.get(kw, 0) + 1

        if not files:
            insufficient.append("no_log_files_found")

        validation: BundleValidation = "passed" if files and not insufficient else (
            "partial" if files else "failed"
        )

        bundle = EvidenceBundle(
            bundle_id=uuid.uuid4().hex,
            source="runtime_logs",
            window=window,
            files=files[:100],
            row_count=row_count,
            event_counts=event_counts,
            sample_lines=sample_lines,
            validation=validation,
            insufficient_fields=insufficient,
        )
        self.save_bundle(bundle)
        return bundle
