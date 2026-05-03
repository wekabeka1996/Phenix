"""Disk-backed session state for the session-first dashboard workbench."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from ..config import Settings
from .model_registry import ModelRegistry
from .models import ChatSession, ChatTurn, ModelProfile, SessionEvent, utc_now_iso
from .persistence import (
    append_jsonl_record,
    quarantine_jsonl_issue,
    read_jsonl_records,
    write_json_atomic,
    write_text_atomic,
)


class SessionStore:
    """Persist sessions, turns, events, and snapshots under .agent_memory/."""

    SESSION_STATE_NAME = "session.dsstate.json"
    TURNS_NAME = "turns.dsctx.jsonl"
    EVENTS_NAME = "events.dsctx.jsonl"
    CONTEXT_PACK_NAME = "context_pack.latest.md"

    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.memory_root = self.root_dir / ".agent_memory"
        self.sessions_root = self.root_dir / settings.sessions.root_dir
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root = self.memory_root / "quarantine"
        self._registry = ModelRegistry(settings, root_dir=root_dir)

    def create_session(
        self,
        title: Optional[str] = None,
        default_profile: Optional[ModelProfile] = None,
    ) -> ChatSession:
        session_id = uuid.uuid4().hex
        profile = default_profile or self._registry.get_default_profiles()[0]
        session = ChatSession(
            session_id=session_id,
            title=title or "New Session",
            active_profile=profile,
            status="idle",
        )
        session_dir = self._session_dir(session_id)
        self._ensure_layout(session_dir)
        self._write_session_state(session)
        return session

    def list_sessions(self) -> list[ChatSession]:
        sessions: list[ChatSession] = []
        for child in self.sessions_root.iterdir():
            if not child.is_dir():
                continue
            state_path = child / self.SESSION_STATE_NAME
            if not state_path.exists():
                continue
            sessions.append(ChatSession(**self._load_json(state_path)))
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions[: self.settings.sessions.max_recent_sessions]

    def get_session(self, session_id: str) -> ChatSession:
        session_path = self._session_dir(session_id) / self.SESSION_STATE_NAME
        return ChatSession(**self._load_json(session_path))

    def update_session_profile(self, session_id: str, profile: ModelProfile) -> ChatSession:
        session = self.get_session(session_id)
        session.active_profile = profile
        session.updated_at = utc_now_iso()
        return self.save_session(session)

    def save_session(self, session: ChatSession) -> ChatSession:
        session.updated_at = utc_now_iso()
        self._write_session_state(session)
        return session

    def append_turn(self, session_id: str, turn: ChatTurn) -> ChatTurn:
        session = self.get_session(session_id)
        session.updated_at = utc_now_iso()
        self._append_jsonl(self._session_dir(session_id) /
                           self.TURNS_NAME, turn.model_dump())
        self._write_session_state(session)
        return turn

    def list_turns(self, session_id: str, *, include_internal: bool = False) -> list[dict[str, Any]]:
        turns = self._load_turn_models(session_id)
        if include_internal:
            return [turn.model_dump() for turn in turns]
        return [turn.to_public_dict() for turn in turns]

    def update_turn(self, session_id: str, turn_id: str, **updates: Any) -> ChatTurn:
        turns = {
            turn.turn_id: turn for turn in self._load_turn_models(session_id)}
        turn = turns[turn_id]
        payload = turn.model_dump()
        payload.update(updates)
        updated = ChatTurn(**payload)
        self._append_jsonl(self._session_dir(session_id) /
                           self.TURNS_NAME, updated.model_dump())
        session = self.get_session(session_id)
        self.save_session(session)
        return updated

    def append_event(self, session_id: str, event: SessionEvent) -> SessionEvent:
        session = self.get_session(session_id)
        session.updated_at = utc_now_iso()
        self._append_jsonl(self._session_dir(session_id) /
                           self.EVENTS_NAME, event.model_dump())
        self._write_session_state(session)
        return event

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        path = self._session_dir(session_id) / self.EVENTS_NAME
        for line_number, record in self._read_jsonl_records(path):
            try:
                rows.append(SessionEvent(**record).model_dump())
            except Exception as exc:
                quarantine_jsonl_issue(
                    source_path=path,
                    quarantine_root=self.quarantine_root,
                    line_number=line_number,
                    raw_line=json.dumps(record, ensure_ascii=False),
                    error=f"invalid_session_event: {exc}",
                )
        return rows

    def save_snapshot(self, session_id: str) -> Path:
        session_dir = self._session_dir(session_id)
        snapshots_dir = session_dir / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshots_dir / f"{self._snapshot_stamp()}.dsctx.json"
        snapshot = {
            "session": self.get_session(session_id).model_dump(),
            "turns": self.list_turns(session_id, include_internal=True),
            "events": self.list_events(session_id),
        }
        return write_json_atomic(snapshot_path, snapshot)

    def write_context_report(self, session_id: str, payload: dict[str, Any]) -> Path:
        report_path = self._session_dir(
            session_id) / "context_reports" / f"{self._snapshot_stamp()}.json"
        return write_json_atomic(report_path, payload)

    def write_context_pack(self, session_id: str, content: str) -> Path:
        context_pack_path = self._session_dir(
            session_id) / self.CONTEXT_PACK_NAME
        return write_text_atomic(context_pack_path, str(content or ""))

    def load_session_after_restart(self, session_id: str) -> ChatSession:
        return self.get_session(session_id)

    def export_session(self, session_id: str) -> Path:
        export_path = self._session_dir(session_id) / "session_export.json"
        export_payload = {
            "session": self.get_session(session_id).model_dump(),
            "turns": self.list_turns(session_id, include_internal=True),
            "events": self.list_events(session_id),
        }
        return write_json_atomic(export_path, export_payload)

    def import_session(self, path: str | Path) -> ChatSession:
        payload = self._load_json(Path(path))
        session = ChatSession(**payload["session"])
        session_id = session.session_id
        if self._session_dir(session_id).exists():
            session_id = uuid.uuid4().hex
            session.session_id = session_id
        session.updated_at = utc_now_iso()
        session_dir = self._session_dir(session_id)
        self._ensure_layout(session_dir)
        self._write_session_state(session)

        for record in payload.get("turns", []):
            turn = ChatTurn(**record)
            turn.session_id = session_id
            self.append_turn(session_id, turn)
        for record in payload.get("events", []):
            event = SessionEvent(**record)
            event.session_id = session_id
            self.append_event(session_id, event)
        return session

    def _session_dir(self, session_id: str) -> Path:
        normalized = str(session_id or "").strip()
        if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
            raise ValueError("session_id must be a safe single path segment")
        return self.sessions_root / normalized

    def _ensure_layout(self, session_dir: Path) -> None:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context_reports").mkdir(parents=True, exist_ok=True)
        (session_dir / "snapshots").mkdir(parents=True, exist_ok=True)

    def _load_turn_models(self, session_id: str) -> list[ChatTurn]:
        ordered_ids: list[str] = []
        latest: dict[str, ChatTurn] = {}
        path = self._session_dir(session_id) / self.TURNS_NAME
        for line_number, record in self._read_jsonl_records(path):
            try:
                turn = ChatTurn(**record)
            except Exception as exc:
                quarantine_jsonl_issue(
                    source_path=path,
                    quarantine_root=self.quarantine_root,
                    line_number=line_number,
                    raw_line=json.dumps(record, ensure_ascii=False),
                    error=f"invalid_chat_turn: {exc}",
                )
                continue
            if turn.turn_id not in latest:
                ordered_ids.append(turn.turn_id)
            latest[turn.turn_id] = turn
        return [latest[turn_id] for turn_id in ordered_ids]

    def _write_session_state(self, session: ChatSession) -> None:
        session_path = self._session_dir(
            session.session_id) / self.SESSION_STATE_NAME
        write_json_atomic(session_path, session.model_dump())

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        append_jsonl_record(path, payload)

    def _read_jsonl_records(self, path: Path) -> list[tuple[int, dict[str, Any]]]:
        return read_jsonl_records(path, quarantine_root=self.quarantine_root)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _snapshot_stamp() -> str:
        return utc_now_iso().replace(":", "-")
