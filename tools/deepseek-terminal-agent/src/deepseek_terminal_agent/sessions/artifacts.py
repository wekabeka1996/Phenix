"""Local artifact persistence for subagent evidence packs and context packs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..logging_utils import redact_obj
from .models import ArtifactRecord
from .persistence import write_json_atomic


class ArtifactStore:
    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.artifacts_root = self.root_dir / ".agent_memory" / "artifacts"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def write_artifact(self, artifact: ArtifactRecord) -> Path:
        target = self.artifacts_root / \
            f"{artifact.artifact_id}.dsartifact.json"
        return write_json_atomic(target, redact_obj(artifact.model_dump()))

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        target = self.artifacts_root / f"{artifact_id}.dsartifact.json"
        return ArtifactRecord(**json.loads(target.read_text(encoding="utf-8")))

    def list_artifacts(
        self,
        *,
        parent_session_id: Optional[str] = None,
        child_session_id: Optional[str] = None,
    ) -> list[ArtifactRecord]:
        artifacts: list[ArtifactRecord] = []
        for path in self.artifacts_root.glob("*.dsartifact.json"):
            artifact = ArtifactRecord(
                **json.loads(path.read_text(encoding="utf-8")))
            if parent_session_id and artifact.parent_session_id != parent_session_id:
                continue
            if child_session_id and artifact.child_session_id != child_session_id:
                continue
            artifacts.append(artifact)
        artifacts.sort(key=lambda item: item.created_at, reverse=True)
        return artifacts
