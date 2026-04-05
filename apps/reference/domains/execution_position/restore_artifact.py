from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
)
from apps.reference.core.time import get_clock

LOG = logging.getLogger(__name__)

RESTORE_ARTIFACT_SCHEMA_VERSION = "1.0.0"
RESTORE_ARTIFACT_TYPE = "execution_position_restore_envelope_v1"
RESTORE_ARTIFACT_WRITER_COMPONENT = "execution_position"
RESTORE_PHASE_UNKNOWN = "UNKNOWN"
BRACKET_STATE_DEFERRED_PENDING_WAL = "DEFERRED_PENDING_WAL"
BRACKET_STATE_LINKED_ACTIVE = "LINKED_ACTIVE"
BRACKET_STATE_PARTIAL_LINKAGE = "PARTIAL_LINKAGE"
BRACKET_STATE_UNKNOWN = "UNKNOWN"


class DeferredBracketRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_order_id: str = Field(min_length=1)


class ExecutionPositionRestoreLifecycleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    manage_phase: str = Field(min_length=1)
    close_phase: str = Field(min_length=1)
    bracket_state: str = Field(min_length=1)
    live_reconcile_required: bool = Field(default=True)
    deferred_bracket_ref: Optional[DeferredBracketRef] = Field(default=None)

    @model_validator(mode="after")
    def _validate_deferred_ref(self) -> "ExecutionPositionRestoreLifecycleRecord":
        if self.bracket_state == BRACKET_STATE_DEFERRED_PENDING_WAL:
            if self.deferred_bracket_ref is None:
                raise ValueError(
                    "deferred_bracket_ref is required when bracket_state=DEFERRED_PENDING_WAL"
                )
        elif self.deferred_bracket_ref is not None:
            raise ValueError(
                "deferred_bracket_ref is only allowed when bracket_state=DEFERRED_PENDING_WAL"
            )
        return self


class ExecutionPositionRestoreEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    artifact_type: Literal["execution_position_restore_envelope_v1"]
    generated_at_ms: int = Field(ge=0)
    writer_component: Literal["execution_position"]
    requires_live_reconcile: bool = Field(default=True)
    active_lifecycles: List[ExecutionPositionRestoreLifecycleRecord] = Field(
        default_factory=list
    )


class ExecutionPositionRestoreArtifactWriter:
    """Writer-only whole-envelope persistence for execution_position restart truth."""

    def __init__(
        self,
        config: ExecutionPositionRestoreArtifactConfig,
        *,
        observability_hook: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._observability_hook = observability_hook
        self._logger = logger or LOG
        self._path = Path(config.storage_path)
        self._last_payload_json: Optional[str] = None

    @property
    def mode(self) -> ExecutionPositionRestoreArtifactMode:
        return self._config.mode

    @property
    def flush_interval_ms(self) -> int:
        return int(self._config.flush_interval_ms)

    def writes_enabled(self) -> bool:
        return self.mode != ExecutionPositionRestoreArtifactMode.OFF

    def build_envelope(self, fsm: Any) -> ExecutionPositionRestoreEnvelope:
        records = fsm._build_execution_restore_artifact_records()
        return ExecutionPositionRestoreEnvelope(
            schema_version=RESTORE_ARTIFACT_SCHEMA_VERSION,
            artifact_type=RESTORE_ARTIFACT_TYPE,
            generated_at_ms=get_clock().now_ms(),
            writer_component=RESTORE_ARTIFACT_WRITER_COMPONENT,
            requires_live_reconcile=True,
            active_lifecycles=records,
        )

    def persist(
        self,
        fsm: Any,
        *,
        trigger: str,
        allow_empty: bool,
    ) -> bool:
        if not self.writes_enabled():
            return False

        envelope = self.build_envelope(fsm)
        if not envelope.active_lifecycles and not allow_empty:
            return False

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
            self._emit_observability(
                "RESTORE:EXECUTION_POSITION_ARTIFACT_WRITE_OK",
                {
                    "artifact_path": str(path),
                    "record_count": len(envelope.active_lifecycles),
                    "symbol_count": len({record.symbol for record in envelope.active_lifecycles}),
                    "trigger": trigger,
                },
            )
            return True
        except Exception as exc:
            self._emit_observability(
                "RESTORE:EXECUTION_POSITION_ARTIFACT_WRITE_FAILED",
                {
                    "artifact_path": str(path),
                    "record_count": len(envelope.active_lifecycles),
                    "symbol_count": len({record.symbol for record in envelope.active_lifecycles}),
                    "trigger": trigger,
                    "failure_reason": type(exc).__name__,
                    "failure_detail": str(exc),
                },
            )
            self._logger.warning(
                "execution restore artifact write failed (%s): %s",
                trigger,
                exc,
            )
            return False
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _emit_observability(self, event_name: str, payload: Dict[str, Any]) -> None:
        if self._observability_hook is None:
            return
        try:
            self._observability_hook(event_name, payload)
        except Exception:
            pass

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
