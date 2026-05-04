"""LossReport generation for context compression events."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso


class LossReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    loss_report_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    source_turn_ids: list[str] = Field(default_factory=list)
    compression_ratio: float = 0.0
    preserved: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    risky_drops: list[str] = Field(default_factory=list)
    requires_review: bool = False
    created_at: str = Field(default_factory=utc_now_iso)


def generate_loss_report(
    *,
    session_id: str,
    source_turn_ids: list[str],
    spine_summary: str,
    omitted_items: list[str],
    preserved_facts: list[str],
    source_chars: int = 0,
    compressed_chars: int = 0,
) -> LossReport:
    """Create a LossReport describing what was preserved/dropped during compression."""
    risky: list[str] = []
    for item in omitted_items:
        text_lower = item.lower()
        if any(kw in text_lower for kw in ("decision", "risk", "error", "block", "fail", "reject")):
            risky.append(item)

    ratio = (compressed_chars / source_chars) if source_chars > 0 else 0.0

    return LossReport(
        loss_report_id=uuid.uuid4().hex,
        session_id=session_id,
        source_turn_ids=source_turn_ids,
        compression_ratio=ratio,
        preserved=preserved_facts[:100],
        dropped=omitted_items[:100],
        risky_drops=risky[:20],
        requires_review=len(risky) > 0,
        created_at=utc_now_iso(),
    )
