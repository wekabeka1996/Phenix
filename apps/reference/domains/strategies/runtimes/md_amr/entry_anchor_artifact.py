from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.core.time import get_clock

LOG = logging.getLogger(__name__)

MD_AMR_ENTRY_ANCHOR_ARTIFACT_SCHEMA_VERSION = "1.0.0"
MD_AMR_ENTRY_ANCHOR_ARTIFACT_TYPE = "md_amr_entry_anchor_state_v1"
MD_AMR_ENTRY_ANCHOR_ARTIFACT_WRITER_COMPONENT = "md_amr_handler"


class MDAMREntryAnchorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    entry_target_price: float = Field(gt=0.0)
    entry_price_hint: Optional[float] = Field(default=None, gt=0.0)
    updated_at_ms: int = Field(ge=0)
    entry_signal_rid: Optional[str] = Field(default=None, min_length=1)


class MDAMREntryAnchorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    artifact_type: Literal["md_amr_entry_anchor_state_v1"]
    generated_at_ms: int = Field(ge=0)
    writer_component: Literal["md_amr_handler"]
    anchors: list[MDAMREntryAnchorRecord] = Field(default_factory=list)


class MDAMREntryAnchorArtifactStore:
    """Atomic reader/writer for md_amr strategy-local entry anchors."""

    def __init__(
        self,
        storage_path: str,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._path = Path(storage_path)
        self._logger = logger or LOG
        self._last_payload_json: Optional[str] = None

    @property
    def storage_path(self) -> str:
        return str(self._path)

    def load_records(self) -> dict[str, MDAMREntryAnchorRecord]:
        if not self._path.exists():
            return {}

        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}

        envelope = MDAMREntryAnchorEnvelope.model_validate(json.loads(raw))
        self._last_payload_json = json.dumps(
            envelope.model_dump(mode="json", exclude_none=True),
            ensure_ascii=True,
            sort_keys=True,
        )
        return {
            str(record.symbol).strip().upper(): record
            for record in envelope.anchors
        }

    def persist_records(self, records: Dict[str, MDAMREntryAnchorRecord]) -> bool:
        envelope = self._build_envelope(records)
        payload = envelope.model_dump(mode="json", exclude_none=True)
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        if serialized == self._last_payload_json:
            return False

        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Optional[Path] = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f"{path.name}.",
                suffix=".tmp",
                dir=str(path.parent),
            )
            temp_path = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(str(temp_path), str(path))
            temp_path = None
            self._fsync_parent_dir(path.parent)
            self._last_payload_json = serialized
            return True
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    self._logger.debug(
                        "failed to remove temp md_amr entry anchor artifact %s",
                        temp_path,
                    )

    @staticmethod
    def _build_envelope(
        records: Dict[str, MDAMREntryAnchorRecord],
    ) -> MDAMREntryAnchorEnvelope:
        ordered = [records[key] for key in sorted(records)]
        return MDAMREntryAnchorEnvelope(
            schema_version=MD_AMR_ENTRY_ANCHOR_ARTIFACT_SCHEMA_VERSION,
            artifact_type=MD_AMR_ENTRY_ANCHOR_ARTIFACT_TYPE,
            generated_at_ms=get_clock().now_ms(),
            writer_component=MD_AMR_ENTRY_ANCHOR_ARTIFACT_WRITER_COMPONENT,
            anchors=ordered,
        )

    @staticmethod
    def _fsync_parent_dir(path: Path) -> None:
        try:
            dir_fd = os.open(str(path), os.O_RDONLY)
        except Exception:
            return
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            try:
                os.close(dir_fd)
            except Exception:
                pass
