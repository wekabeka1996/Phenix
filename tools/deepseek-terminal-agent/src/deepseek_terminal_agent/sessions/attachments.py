"""Session-bound attachment metadata persistence.

Attachments store operator-provided refs and bounded summaries separately from
compressed memory. Raw bytes and uncontrolled blobs are intentionally out of
scope for this store.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import Settings
from ..logging_utils import redact_obj
from .models import utc_now_iso
from .persistence import write_json_atomic
from .token_budget import estimate_tokens, truncate_chars

AttachmentKind = Literal[
    "operator_note",
    "pasted_text",
    "news_summary",
    "image_ref",
    "chart_snapshot",
    "market_screenshot",
    "file_ref",
]


class AttachmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    attachment_id: str = Field(default_factory=lambda: f"attachment-{uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    kind: AttachmentKind
    raw_ref: str = ""
    summary: str = Field(..., min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    created_by: str = "operator"
    include_in_prompt: bool = True
    token_estimate: int = 0

    @field_validator("attachment_id", "session_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or any(part in cleaned for part in ("..", "/", "\\")):
            raise ValueError("identifier must be a local safe id")
        return cleaned

    @field_validator("raw_ref")
    @classmethod
    def bounded_raw_ref(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower().startswith("data:"):
            raise ValueError("raw_ref must be a reference/path, not inline data")
        return truncate_chars(cleaned, 1024)

    @field_validator("summary")
    @classmethod
    def bounded_summary(cls, value: str) -> str:
        return truncate_chars(value.strip(), 2000)

    @field_validator("source_refs")
    @classmethod
    def bounded_source_refs(cls, value: list[str]) -> list[str]:
        return [truncate_chars(str(item).strip(), 512) for item in value[:20] if str(item).strip()]

    @field_validator("created_by")
    @classmethod
    def bounded_created_by(cls, value: str) -> str:
        return truncate_chars(value.strip() or "operator", 80)

    @field_validator("token_estimate")
    @classmethod
    def non_negative_token_estimate(cls, value: int) -> int:
        if value < 0:
            raise ValueError("token_estimate must be >= 0")
        return value

    def prompt_ref(self) -> str:
        lines = [
            f"Attachment {self.attachment_id} ({self.kind})",
            f"Summary: {self.summary}",
        ]
        if self.raw_ref:
            lines.append(f"Ref: {truncate_chars(self.raw_ref, 240)}")
        for ref in self.source_refs[:5]:
            lines.append(f"Source: {ref}")
        return "\n".join(lines)


class AttachmentStore:
    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.attachments_root = self.root_dir / ".agent_memory" / "attachments"
        self.attachments_root.mkdir(parents=True, exist_ok=True)

    def create_attachment(
        self,
        *,
        session_id: str,
        kind: AttachmentKind,
        raw_ref: str = "",
        summary: str,
        source_refs: Optional[list[str]] = None,
        created_by: str = "operator",
        include_in_prompt: bool = True,
        token_estimate: int = 0,
    ) -> AttachmentRecord:
        record = AttachmentRecord(
            session_id=session_id,
            kind=kind,
            raw_ref=raw_ref,
            summary=summary,
            source_refs=source_refs or [],
            created_by=created_by,
            include_in_prompt=include_in_prompt,
            token_estimate=token_estimate,
        )
        if record.token_estimate == 0:
            record.token_estimate = estimate_tokens(
                "\n".join([record.summary, record.raw_ref, *record.source_refs]),
                self.settings.context.approximate_token_ratio,
            )
        self.write_attachment(record)
        return record

    def write_attachment(self, attachment: AttachmentRecord) -> Path:
        target = self.attachments_root / f"{attachment.attachment_id}.dsattachment.json"
        return write_json_atomic(target, redact_obj(attachment.model_dump()))

    def get_attachment(self, attachment_id: str) -> AttachmentRecord:
        AttachmentRecord.model_validate(
            {
                "attachment_id": attachment_id,
                "session_id": "validation-only",
                "kind": "operator_note",
                "summary": "validation-only",
            }
        )
        target = self.attachments_root / f"{attachment_id}.dsattachment.json"
        if not target.exists():
            raise FileNotFoundError(attachment_id)
        return AttachmentRecord(**json.loads(target.read_text(encoding="utf-8")))

    def list_attachments(
        self,
        *,
        session_id: Optional[str] = None,
        include_in_prompt: Optional[bool] = None,
    ) -> list[AttachmentRecord]:
        attachments: list[AttachmentRecord] = []
        for path in self.attachments_root.glob("*.dsattachment.json"):
            attachment = AttachmentRecord(**json.loads(path.read_text(encoding="utf-8")))
            if session_id and attachment.session_id != session_id:
                continue
            if include_in_prompt is not None and attachment.include_in_prompt != include_in_prompt:
                continue
            attachments.append(attachment)
        attachments.sort(key=lambda item: item.created_at, reverse=True)
        return attachments
