"""
DataRef Model — Phase 16.3.

Structured data reference per Constitution §5.2 / §11.1.
Replaces the informal List[str] data_ref with a Pydantic model
that preserves backward compatibility with plain string URIs.

Constitution §5.2 specifies:
    "data_ref": [{"uri":"s3://...", "sha256":"...", "bytes": N, "ctype":"...", "ttl_ms": N}]
"""
from __future__ import annotations

import re
from typing import Any, Union

from pydantic import BaseModel, Field, field_validator

_SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class DataRef(BaseModel):
    """Structured data reference per Constitution §5.2."""
    uri: str
    sha256: str = Field(..., description="hex digest, 64 chars")
    bytes: int = Field(default=0, ge=0, description="payload size in bytes")
    ctype: str = Field(default="application/octet-stream", description="content type")
    ttl_ms: int = Field(
        default=600_000,
        ge=1,
        le=86_400_000,
        description="TTL in ms (1ms .. 24h)",
    )

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, v: str) -> str:
        if not _SHA256_PATTERN.match(v):
            raise ValueError(
                f"sha256 must be exactly 64 hex characters, got {len(v)} chars"
            )
        return v.lower()


# Union type for backward compat: accept both str and DataRef
DataRefItem = Union[str, DataRef]


def coerce_data_ref(value: Any) -> DataRefItem:
    """
    Coerce a value to DataRefItem.

    - str → returned as-is (backward compat)
    - dict → parsed as DataRef
    - DataRef → returned as-is

    Raises:
        TypeError: If value is not str, dict, or DataRef.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, DataRef):
        return value
    if isinstance(value, dict):
        return DataRef(**value)
    raise TypeError(f"Cannot coerce {type(value).__name__} to DataRefItem")
