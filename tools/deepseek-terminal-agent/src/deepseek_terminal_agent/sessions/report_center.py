"""Report center — index, classify, and manage agent reports."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso
from .persistence import write_json_atomic

ReportType = Literal[
    "AGENT_REPORT_V1",
    "AUDIT_REPORT_V1",
    "RUNTIME_FORENSIC_REPORT_V1",
    "MEMORY_PATCH_V1",
    "TEST_REPORT",
    "EVIDENCE_PACK",
    "UNKNOWN",
]
ReportStatus = Literal["draft", "accepted", "rejected", "superseded", "stale"]


class ReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    report_id: str = Field(..., min_length=1)
    report_type: ReportType = "UNKNOWN"
    verdict: str = ""
    source_path: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    status: ReportStatus = "draft"
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump()


_TYPE_PATTERNS: list[tuple[str, ReportType]] = [
    (r"AGENT_REPORT_V\d+", "AGENT_REPORT_V1"),
    (r"AUDIT_REPORT", "AUDIT_REPORT_V1"),
    (r"FORENSIC", "RUNTIME_FORENSIC_REPORT_V1"),
    (r"MEMORY_PATCH", "MEMORY_PATCH_V1"),
    (r"TEST_REPORT|TestReport", "TEST_REPORT"),
    (r"EVIDENCE_PACK|EvidencePack", "EVIDENCE_PACK"),
]


def _classify_type(content: str, filename: str) -> ReportType:
    text = filename.upper() + " " + content[:500].upper()
    for pattern, rtype in _TYPE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return rtype
    return "UNKNOWN"


def _extract_verdict(content: str) -> str:
    m = re.search(r"verdict[:\s]+([A-Z_]+)", content, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extract_summary(content: str) -> str:
    m = re.search(r"summary[:\s]+([^\n]{10,200})", content, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    lines = content.strip().splitlines()
    for line in lines[:10]:
        line = line.strip()
        if len(line) > 20:
            return line[:200]
    return ""


class ReportCenter:
    """Index and manage agent reports across the repo."""

    def __init__(self, *, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.index_dir = self.root_dir / ".agent_memory" / "report_center"
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, report_id: str) -> Path:
        return self.index_dir / f"{report_id}.dsreport.json"

    def _scan_paths(self) -> list[Path]:
        """Scan known locations for report files."""
        patterns = [
            ".agent_runs/**/*.md",
            "reports/**/*.md",
            ".agent_memory/artifacts/*.dsartifact.json",
            "AGENT_REPORT*.md",
        ]
        found: list[Path] = []
        for pattern in patterns:
            found.extend(self.root_dir.glob(pattern))
        return found

    def scan_and_index(self) -> list[ReportRecord]:
        """Scan known paths and index new reports (idempotent by source_path)."""
        existing = {r.source_path: r for r in self.list_reports()}
        new_records: list[ReportRecord] = []
        for path in self._scan_paths():
            rel = str(path.relative_to(self.root_dir))
            if rel in existing:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            record = ReportRecord(
                report_id=uuid.uuid4().hex,
                report_type=_classify_type(content, path.name),
                verdict=_extract_verdict(content),
                source_path=rel,
                summary=_extract_summary(content),
            )
            write_json_atomic(self._record_path(
                record.report_id), record.model_dump())
            new_records.append(record)
        return new_records

    def list_reports(
        self,
        *,
        report_type: Optional[ReportType] = None,
        status: Optional[ReportStatus] = None,
        verdict: Optional[str] = None,
    ) -> list[ReportRecord]:
        records: list[ReportRecord] = []
        for path in self.index_dir.glob("*.dsreport.json"):
            try:
                rec = ReportRecord(
                    **json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if report_type and rec.report_type != report_type:
                continue
            if status and rec.status != status:
                continue
            if verdict and rec.verdict.upper() != verdict.upper():
                continue
            records.append(rec)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def get_report(self, report_id: str) -> ReportRecord:
        path = self._record_path(report_id)
        if not path.exists():
            raise KeyError(f"Report '{report_id}' not found")
        return ReportRecord(**json.loads(path.read_text(encoding="utf-8")))

    def update_status(self, report_id: str, status: ReportStatus) -> ReportRecord:
        rec = self.get_report(report_id)
        rec.status = status
        write_json_atomic(self._record_path(report_id), rec.model_dump())
        return rec

    def register_report(
        self,
        *,
        source_path: str,
        report_type: ReportType = "UNKNOWN",
        verdict: str = "",
        summary: str = "",
        evidence_refs: Optional[list[str]] = None,
        status: ReportStatus = "draft",
    ) -> ReportRecord:
        """Manually register a report (e.g., from a subagent artifact)."""
        rec = ReportRecord(
            report_id=uuid.uuid4().hex,
            report_type=report_type,
            verdict=verdict,
            source_path=source_path,
            summary=summary,
            evidence_refs=evidence_refs or [],
            status=status,
        )
        write_json_atomic(self._record_path(rec.report_id), rec.model_dump())
        return rec
