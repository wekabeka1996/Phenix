from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OpsConfig(BaseModel):
    """Operations configuration (killswitch, quiet hours, monitoring)."""
    model_config = ConfigDict(extra='forbid')

    # Emergency controls (A-01 fix)
    panic_killswitch: bool = Field(
        ..., description='Emergency kill switch - blocks all new CMD:OPEN when True')

    # Used in tooling only
    metrics_url: Optional[str] = Field(
        ..., description='Metrics endpoint (tooling only)'
    )
    reports_dir: Optional[str] = Field(
        ..., description='Reports output directory (tooling only)'
    )
