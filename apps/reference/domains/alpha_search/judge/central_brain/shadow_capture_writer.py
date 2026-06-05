from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


EVIDENCE_EVENT = "EVT:JUDGE_EVIDENCE_ENVELOPE_BUILT_V2"
VERDICT_EVENT = "EVT:JUDGE_POLICY_VERDICT_EMITTED_V2"
BRIDGE_EVENT = "EVT:JUDGE_BRIDGE_DECISION_EVALUATED_V1"
ROW_EVENT = "EVT:JUDGE_SHADOW_CALIBRATION_ROW_BUILT_V1"


class ShadowCapturePaths(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_dir: str = Field(min_length=1)
    evidence_envelope_file: str = Field(min_length=1)
    policy_verdict_file: str = Field(min_length=1)
    bridge_decision_file: str = Field(min_length=1)
    calibration_row_file: str = Field(min_length=1)

    def path_for(self, name: str) -> Path:
        file_name = getattr(self, name)
        return Path(self.output_dir) / str(file_name)


class ShadowCaptureWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    written: dict[str, int] = Field(default_factory=dict)
    paths: dict[str, str] = Field(default_factory=dict)


class JudgeShadowCaptureWriter:
    def __init__(self, *, enabled: bool, paths: ShadowCapturePaths) -> None:
        self._enabled = bool(enabled)
        self._paths = paths

    @staticmethod
    def _dump_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        if isinstance(payload, dict):
            return dict(payload)
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        raise TypeError("shadow capture payload must be a model or dict")

    @staticmethod
    def _event_row(event_name: str, payload: Any) -> dict[str, Any]:
        data = JudgeShadowCaptureWriter._dump_payload(payload)
        return {
            "event_name": event_name,
            "payload": data,
        }

    @staticmethod
    def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    def write_capture(
        self,
        *,
        envelope: Any,
        verdict: Any,
        bridge_decision: Any,
        calibration_row: Any,
    ) -> ShadowCaptureWriteResult:
        if not self._enabled:
            return ShadowCaptureWriteResult(enabled=False, written={}, paths={})

        entries = {
            "evidence_envelope_file": (EVIDENCE_EVENT, envelope),
            "policy_verdict_file": (VERDICT_EVENT, verdict),
            "bridge_decision_file": (BRIDGE_EVENT, bridge_decision),
            "calibration_row_file": (ROW_EVENT, calibration_row),
        }
        written: dict[str, int] = {}
        paths: dict[str, str] = {}
        for key, (event_name, payload) in entries.items():
            path = self._paths.path_for(key)
            self._append_jsonl(path, self._event_row(event_name, payload))
            written[key] = 1
            paths[key] = str(path)
        return ShadowCaptureWriteResult(enabled=True, written=written, paths=paths)
