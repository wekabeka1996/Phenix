"""Dashboard FastAPI application.

Routes:
    GET  /                   — home page shell for the dashboard UI
    POST /runs               — create a background run and return its run_id
    GET  /runs               — list recent runs (active + persisted)
    GET  /runs/{run_id}/status
    GET  /runs/{run_id}/output
    GET  /runs/{run_id}/events
    POST /runs/{run_id}/cancel
    GET  /health             — liveness probe
    GET  /config-status      — sanitised config (no API key value)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Settings, load_settings
from ..deepseek_client import DeepSeekAPIError, DeepSeekTimeoutError
from ..logging_utils import redact
from ..sessions.approval_queue import ApprovalQueue
from ..sessions.artifacts import ArtifactStore
from ..sessions.chat_runtime import SessionChatRuntime
from ..sessions.compressor import ContextCompressor
from ..sessions.context_builder import ContextBuilder
from ..sessions.context_inspector import ContextInspector
from ..sessions.decision_ledger import DecisionLedger
from ..sessions.evidence_bundle import EvidenceBundleStore
from ..sessions.memory_atoms import MemoryAtom, MemoryAtomStore
from ..sessions.memory_patch import MemoryPatchStore
from ..sessions.model_registry import ModelRegistry
from ..sessions.models import ModelProfile
from ..sessions.playbooks import PlaybookRegistry
from ..sessions.project_capsule import ProjectCapsuleStore
from ..sessions.report_center import ReportCenter
from ..sessions.store import SessionStore
from ..sessions.subagents import SubAgentManager
from ..sessions.tool_registry import ToolRegistry
from .runner import TERMINAL_STATUSES, DashboardRunner, load_recent_runs

# ── Resolve paths relative to this file ────────────────────────────────────────
_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

app = FastAPI(title="DeepSeek Terminal Agent Dashboard",
              docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Settings loaded once at startup (resolved from config/agent.yaml + env)
_settings: Optional[Settings] = None
_runner: Optional[DashboardRunner] = None
_session_store: Optional[SessionStore] = None
_model_registry: Optional[ModelRegistry] = None
_memory_store: Optional[MemoryAtomStore] = None
_artifact_store: Optional[ArtifactStore] = None
_context_builder: Optional[ContextBuilder] = None
_context_inspector: Optional[ContextInspector] = None
_compressor: Optional[ContextCompressor] = None
_chat_runtime: Optional[SessionChatRuntime] = None
_subagent_manager: Optional[SubAgentManager] = None
_project_capsule_store: Optional[ProjectCapsuleStore] = None
_playbook_registry: Optional[PlaybookRegistry] = None
_tool_registry: Optional[ToolRegistry] = None
_approval_queue: Optional[ApprovalQueue] = None
_report_center: Optional[ReportCenter] = None
_decision_ledger: Optional[DecisionLedger] = None
_memory_patch_store: Optional[MemoryPatchStore] = None
_evidence_bundle_store: Optional[EvidenceBundleStore] = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def _get_runner() -> DashboardRunner:
    global _runner
    if _runner is None:
        settings = _get_settings()
        _runner = DashboardRunner(
            log_dir=settings.agent.log_dir,
            max_prompt_chars=settings.dashboard.max_prompt_chars,
            max_output_chars=settings.dashboard.max_output_chars,
            recent_runs_limit=settings.dashboard.recent_runs_limit,
        )
    return _runner


def _get_root_dir() -> Path:
    return Path.cwd()


def _get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore(
            _get_settings(), root_dir=_get_root_dir())
    return _session_store


def _get_model_registry() -> ModelRegistry:
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry(
            _get_settings(), root_dir=_get_root_dir())
    return _model_registry


def _get_memory_store() -> MemoryAtomStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryAtomStore(
            _get_settings(), root_dir=_get_root_dir())
    return _memory_store


def _get_project_capsule_store() -> ProjectCapsuleStore:
    global _project_capsule_store
    if _project_capsule_store is None:
        _project_capsule_store = ProjectCapsuleStore(
            _get_settings(), root_dir=_get_root_dir())
    return _project_capsule_store


def _get_artifact_store() -> ArtifactStore:
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore(
            _get_settings(), root_dir=_get_root_dir())
    return _artifact_store


def _get_context_builder() -> ContextBuilder:
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder(
            _get_settings(),
            session_store=_get_session_store(),
            memory_store=_get_memory_store(),
            artifact_store=_get_artifact_store(),
            root_dir=_get_root_dir(),
        )
    return _context_builder


def _get_context_inspector() -> ContextInspector:
    global _context_inspector
    if _context_inspector is None:
        _context_inspector = ContextInspector(_get_context_builder())
    return _context_inspector


def _get_compressor() -> ContextCompressor:
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor(
            _get_settings(),
            session_store=_get_session_store(),
            memory_store=_get_memory_store(),
            root_dir=_get_root_dir(),
        )
    return _compressor


def _get_chat_runtime() -> SessionChatRuntime:
    global _chat_runtime
    if _chat_runtime is None:
        _chat_runtime = SessionChatRuntime(
            _get_settings(),
            session_store=_get_session_store(),
            context_builder=_get_context_builder(),
            compressor=_get_compressor(),
            subagent_manager=_get_subagent_manager(),
        )
    return _chat_runtime


def _get_subagent_manager() -> SubAgentManager:
    global _subagent_manager
    if _subagent_manager is None:
        _subagent_manager = SubAgentManager(
            _get_settings(),
            session_store=_get_session_store(),
            artifact_store=_get_artifact_store(),
        )
    return _subagent_manager


async def _extract_prompt(request: Request) -> str:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        if isinstance(payload, dict):
            return str(payload.get("prompt") or "")
        return ""
    form = await request.form()
    return str(form.get("prompt") or "")


async def _extract_payload(request: Request) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        return payload if isinstance(payload, dict) else {}
    form = await request.form()
    return dict(form)


def _json_error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": redact(message)}, status_code=status_code)


def _lookup_persisted_run(run_id: str) -> Optional[dict[str, Any]]:
    settings = _get_settings()
    limit = max(settings.dashboard.recent_runs_limit * 10, 200)
    for record in load_recent_runs(settings.agent.log_dir, limit=limit):
        if record.get("run_id") == run_id:
            status = record.get("status")
            if status not in TERMINAL_STATUSES:
                status = "succeeded" if record.get(
                    "exit_code") == 0 else "failed"
            return {
                "run_id": run_id,
                "prompt": record.get("prompt"),
                "status": status,
                "created_at": record.get("created_at"),
                "started_at": record.get("created_at"),
                "finished_at": record.get("finished_at") or record.get("created_at"),
                "duration_ms": record.get("duration_ms", 0),
                "exit_code": record.get("exit_code"),
                "current_phase": status,
                "latest_event": record.get("status") or status,
                "error": record.get("stderr") or None,
                "run_dir": record.get("run_dir"),
                "stdout": record.get("stdout", ""),
                "stderr": record.get("stderr", ""),
                "output": _combine_output(record.get("stdout", ""), record.get("stderr", "")),
                "truncated": False,
            }
    return None


def _combine_output(stdout: str, stderr: str) -> str:
    if stdout and stderr:
        return stdout + "\n\n[stderr]\n" + stderr
    return stdout or stderr or ""


def _get_playbook_registry() -> PlaybookRegistry:
    global _playbook_registry
    if _playbook_registry is None:
        s = _get_settings()
        _playbook_registry = PlaybookRegistry(
            _get_root_dir() / s.playbooks.path)
    return _playbook_registry


def _get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        s = _get_settings()
        _tool_registry = ToolRegistry(_get_root_dir() / s.tool_registry.path)
    return _tool_registry


def _get_approval_queue() -> ApprovalQueue:
    global _approval_queue
    if _approval_queue is None:
        _approval_queue = ApprovalQueue(root_dir=_get_root_dir())
    return _approval_queue


def _get_report_center() -> ReportCenter:
    global _report_center
    if _report_center is None:
        _report_center = ReportCenter(root_dir=_get_root_dir())
    return _report_center


def _get_decision_ledger() -> DecisionLedger:
    global _decision_ledger
    if _decision_ledger is None:
        _decision_ledger = DecisionLedger(root_dir=_get_root_dir())
    return _decision_ledger


def _get_memory_patch_store() -> MemoryPatchStore:
    global _memory_patch_store
    if _memory_patch_store is None:
        _memory_patch_store = MemoryPatchStore(root_dir=_get_root_dir())
    return _memory_patch_store


def _get_evidence_bundle_store() -> EvidenceBundleStore:
    global _evidence_bundle_store
    if _evidence_bundle_store is None:
        _evidence_bundle_store = EvidenceBundleStore(root_dir=_get_root_dir())
    return _evidence_bundle_store


def _default_profiles() -> list[ModelProfile]:
    return _get_model_registry().get_default_profiles()


def _resolve_profile(payload: dict[str, Any], *, current_profile: Optional[ModelProfile] = None) -> ModelProfile:
    profiles = {profile.profile_id: profile for profile in _default_profiles()}
    profile_id = str(payload.get("profile_id") or "").strip()
    if profile_id:
        if profile_id not in profiles:
            raise ValueError(f"Unknown profile_id '{profile_id}'.")
        return profiles[profile_id]

    raw_profile = payload.get("profile")
    if isinstance(raw_profile, dict):
        profile = ModelProfile(**raw_profile)
        _get_model_registry().resolve_model_id(
            profile.model_id,
            advanced_mode=bool(payload.get("advanced_mode")),
        )
        return profile

    model_id = str(payload.get("model_id") or "").strip()
    if model_id:
        base = current_profile.model_copy(
            deep=True) if current_profile else _default_profiles()[0].model_copy(deep=True)
        base.model_id = _get_model_registry().resolve_model_id(
            model_id,
            advanced_mode=bool(payload.get("advanced_mode")),
        ).model_id
        for key in (
            "name",
            "thinking_type",
            "reasoning_effort",
            "temperature",
            "top_p",
            "max_tokens",
            "response_format",
            "stream",
            "tool_mode",
            "max_iterations",
            "command_timeout_sec",
            "max_command_output_chars",
            "context_budget_chars",
            "memory_atom_budget",
            "recent_turns_budget",
            "tool_output_budget_chars",
        ):
            if key in payload:
                setattr(base, key, payload[key])
        base.profile_id = str(payload.get("profile_id")
                              or base.profile_id or f"custom-{base.model_id}")
        base.name = str(payload.get("name") or base.name)
        return ModelProfile(**base.model_dump())

    raise ValueError("Provide profile_id, profile, or model_id.")


def _session_memory_atoms(session_id: str) -> list[dict[str, Any]]:
    session = _get_session_store().get_session(session_id)
    atoms = []
    for atom in _get_memory_store().list_atoms(include_disabled=True):
        if atom.source_session_id == session_id or atom.atom_id in session.pinned_memory_atom_ids or atom.scope == "project":
            atoms.append(atom.model_dump())
    return atoms


def _session_artifacts(session_id: str) -> list[dict[str, Any]]:
    return [artifact.to_public_dict() for artifact in _get_artifact_store().list_artifacts(parent_session_id=session_id)]


def _search_session_memory(session_id: str, query: str) -> list[dict[str, Any]]:
    session = _get_session_store().get_session(session_id)
    atoms = _get_memory_store().search(
        query,
        top_k=_get_settings().memory.retrieval_top_k,
        pinned_atom_ids=session.pinned_memory_atom_ids,
        scope="session",
    )
    filtered = [
        atom.model_dump()
        for atom in atoms
        if atom.source_session_id == session_id
        or atom.atom_id in session.pinned_memory_atom_ids
        or atom.scope == "project"
    ]
    return filtered


def _session_detail(session_id: str) -> dict[str, Any]:
    session_store = _get_session_store()
    session = session_store.get_session(session_id)
    return {
        "session": session.model_dump(),
        "routing": session.metadata.get("last_task_route"),
        "turns": session_store.list_turns(session_id, include_internal=False),
        "events": session_store.list_events(session_id),
        "memory_atoms": _session_memory_atoms(session_id),
        "artifacts": _session_artifacts(session_id),
        "subagents": _get_subagent_manager().list_subagents(session_id),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "deepseek-terminal-agent-dashboard"})


@app.get("/config-status")
async def config_status() -> JSONResponse:
    s = _get_settings()
    return JSONResponse(
        {
            "model": s.deepseek.model,
            "base_url": s.deepseek.base_url,
            "workspace_root": s.terminal.workspace_root,
            "reasoning_enabled": s.deepseek.reasoning_enabled,
            "api_key_present": bool(s.deepseek.api_key),
            # api_key itself is intentionally NOT included
        }
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    s = _get_settings()
    recent = _get_runner().list_runs(limit=s.dashboard.recent_runs_limit)
    bootstrap = {
        "maxPromptChars": s.dashboard.max_prompt_chars,
        "maxOutputChars": s.dashboard.max_output_chars,
        "recentRuns": recent,
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "model": s.deepseek.model,
            "workspace": s.terminal.workspace_root,
            "api_key_present": bool(s.deepseek.api_key),
            "reasoning_enabled": s.deepseek.reasoning_enabled,
            "bootstrap": bootstrap,
        },
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat_home(request: Request) -> HTMLResponse:
    s = _get_settings()
    project_capsule = _get_project_capsule_store().load()
    bootstrap = {
        "chatEnabled": s.dashboard.chat_enabled,
        "contextInspectorEnabled": s.dashboard.context_inspector_enabled,
        "memoryPanelEnabled": s.dashboard.memory_panel_enabled,
        "subagentsPanelEnabled": s.dashboard.subagents_panel_enabled,
        "reasoningEnabled": bool(s.deepseek.reasoning_enabled),
        "sessions": [session.model_dump() for session in _get_session_store().list_sessions()],
        "profiles": [profile.model_dump() for profile in _default_profiles()],
        "catalog": _get_model_registry().list_models().model_dump(),
        "workspace": s.terminal.workspace_root,
        "projectCapsule": project_capsule.to_public_dict(),
    }
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "bootstrap": bootstrap,
            "api_key_present": bool(s.deepseek.api_key),
            "workspace": s.terminal.workspace_root,
        },
    )


@app.post("/runs")
async def create_run(request: Request) -> JSONResponse:
    prompt = redact(await _extract_prompt(request))
    if not prompt.strip():
        return _json_error("Prompt is required.", status_code=400)

    try:
        status = _get_runner().create_run(prompt)
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)

    return JSONResponse(status, status_code=202)


@app.get("/runs")
async def list_runs() -> JSONResponse:
    s = _get_settings()
    runs = _get_runner().list_runs(limit=s.dashboard.recent_runs_limit)
    return JSONResponse(runs)


@app.get("/runs/{run_id}/status")
async def run_status(run_id: str) -> JSONResponse:
    try:
        status = _get_runner().get_status(run_id)
    except KeyError:
        persisted = _lookup_persisted_run(run_id)
        if persisted is None:
            return _json_error(f"Run '{run_id}' not found.", status_code=404)
        status = {
            key: persisted.get(key)
            for key in (
                "run_id",
                "prompt",
                "status",
                "created_at",
                "started_at",
                "finished_at",
                "duration_ms",
                "exit_code",
                "current_phase",
                "latest_event",
                "error",
                "run_dir",
            )
        }
    return JSONResponse(status)


@app.get("/runs/{run_id}/output")
async def run_output(run_id: str) -> JSONResponse:
    try:
        output = _get_runner().get_output(run_id)
    except KeyError:
        persisted = _lookup_persisted_run(run_id)
        if persisted is None:
            return _json_error(f"Run '{run_id}' not found.", status_code=404)
        output = {
            "run_id": run_id,
            "status": persisted["status"],
            "output": persisted["output"],
            "stdout": persisted["stdout"],
            "stderr": persisted["stderr"],
            "truncated": persisted["truncated"],
            "run_dir": persisted["run_dir"],
        }
    return JSONResponse(output)


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> JSONResponse:
    try:
        events = _get_runner().get_events(run_id)
    except KeyError:
        persisted = _lookup_persisted_run(run_id)
        if persisted is None:
            return _json_error(f"Run '{run_id}' not found.", status_code=404)
        events = []
    return JSONResponse({"run_id": run_id, "events": events})


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> JSONResponse:
    try:
        cancelled = _get_runner().cancel(run_id)
    except KeyError:
        return _json_error(f"Run '{run_id}' not found.", status_code=404)
    if not cancelled:
        return _json_error(f"Run '{run_id}' is not cancellable.", status_code=409)
    return JSONResponse({"run_id": run_id, "status": "cancel_requested"})


@app.get("/models")
@app.get("/chat/models")
async def chat_models() -> JSONResponse:
    return JSONResponse(
        {
            "catalog": _get_model_registry().list_models().model_dump(),
            "default_profiles": [profile.model_dump() for profile in _default_profiles()],
        }
    )


@app.get("/chat/project-capsule")
async def chat_project_capsule() -> JSONResponse:
    capsule = _get_project_capsule_store().load()
    return JSONResponse(capsule.to_public_dict())


@app.get("/chat/sessions")
async def chat_sessions() -> JSONResponse:
    return JSONResponse([session.model_dump() for session in _get_session_store().list_sessions()])


@app.post("/chat/sessions")
async def create_chat_session(request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        profile = _resolve_profile(payload) if any(key in payload for key in (
            "profile_id", "profile", "model_id")) else _default_profiles()[0]
        session = _get_session_store().create_session(
            title=str(payload.get("title") or "New Session"),
            default_profile=profile,
        )
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)
    return JSONResponse(_session_detail(session.session_id), status_code=201)


@app.get("/chat/sessions/{session_id}")
async def chat_session_detail(session_id: str) -> JSONResponse:
    try:
        detail = _session_detail(session_id)
    except (KeyError, FileNotFoundError, ValueError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(detail)


@app.post("/chat/sessions/{session_id}/message")
async def chat_send_message(session_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        result = _get_chat_runtime().send_message(
            session_id=session_id,
            user_message=str(payload.get("message") or ""),
        )
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    except DeepSeekTimeoutError as exc:
        return _json_error(str(exc), status_code=exc.status_code)
    except DeepSeekAPIError as exc:
        return _json_error(str(exc), status_code=exc.status_code)
    return JSONResponse(result)


@app.post("/chat/sessions/{session_id}/profile")
async def chat_update_profile(session_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        session = _get_session_store().get_session(session_id)
        profile = _resolve_profile(
            payload, current_profile=session.active_profile)
        updated = _get_session_store().update_session_profile(session_id, profile)
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(updated.model_dump())


@app.get("/chat/sessions/{session_id}/memory")
async def chat_list_memory(session_id: str) -> JSONResponse:
    try:
        return JSONResponse({"memory_atoms": _session_memory_atoms(session_id)})
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)


@app.get("/chat/sessions/{session_id}/memory/search")
async def chat_search_memory(session_id: str, request: Request) -> JSONResponse:
    query = str(request.query_params.get("q") or "").strip()
    if not query:
        return _json_error("q is required.", status_code=400)
    try:
        matches = _search_session_memory(session_id, query)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse({"query": query, "memory_atoms": matches})


@app.post("/chat/sessions/{session_id}/memory")
async def chat_add_memory(session_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        atom = _get_memory_store().add_atom(
            MemoryAtom(
                scope=str(payload.get("scope") or "session"),
                kind=str(payload.get("kind") or "fact"),
                text=str(payload.get("text") or "").strip(),
                evidence_refs=[str(item)
                               for item in payload.get("evidence_refs", [])],
                confidence=float(payload.get("confidence", 0.5)),
                importance=float(payload.get("importance", 0.5)),
                ttl=str(payload.get("ttl") or "session"),
                source_session_id=session_id,
                tags=[str(tag) for tag in payload.get("tags", [])],
            )
        )
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc), status_code=400)
    return JSONResponse(atom.model_dump(), status_code=201)


@app.post("/chat/sessions/{session_id}/memory/{atom_id}/pin")
async def chat_pin_memory(session_id: str, atom_id: str) -> JSONResponse:
    try:
        session = _get_session_store().get_session(session_id)
        if atom_id not in session.pinned_memory_atom_ids:
            session.pinned_memory_atom_ids.append(atom_id)
        _get_session_store().save_session(session)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(session.model_dump())


@app.post("/chat/sessions/{session_id}/memory/{atom_id}/unpin")
async def chat_unpin_memory(session_id: str, atom_id: str) -> JSONResponse:
    try:
        session = _get_session_store().get_session(session_id)
        session.pinned_memory_atom_ids = [
            item for item in session.pinned_memory_atom_ids if item != atom_id]
        _get_session_store().save_session(session)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(session.model_dump())


@app.post("/chat/sessions/{session_id}/memory/{atom_id}/disable")
async def chat_disable_memory(session_id: str, atom_id: str) -> JSONResponse:
    try:
        atom = _get_memory_store().disable_atom(atom_id)
    except KeyError:
        return _json_error(f"Memory atom '{atom_id}' not found.", status_code=404)
    return JSONResponse(atom.model_dump())


@app.post("/chat/sessions/{session_id}/context")
async def chat_context_inspect(session_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        session = _get_session_store().get_session(session_id)
        report = _get_context_inspector().inspect(
            session_id=session_id,
            current_user_message=str(payload.get("message") or ""),
            selected_profile=session.active_profile,
            relevant_artifact_ids=[str(item) for item in payload.get(
                "relevant_artifact_ids", [])],
        )
        _get_session_store().write_context_pack(
            session_id, report["context_pack"])
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(report)


@app.post("/chat/sessions/{session_id}/compress")
async def chat_compress(session_id: str) -> JSONResponse:
    try:
        result = _get_compressor().compress_session(session_id=session_id)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(result)


@app.get("/chat/sessions/{session_id}/subagents")
async def chat_subagents(session_id: str) -> JSONResponse:
    return JSONResponse({"subagents": _get_subagent_manager().list_subagents(session_id)})


@app.post("/chat/sessions/{session_id}/subagents")
async def chat_spawn_subagent(session_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        session = _get_session_store().get_session(session_id)
        profile = _resolve_profile(payload, current_profile=session.active_profile) if any(key in payload for key in (
            "profile_id", "profile", "model_id")) else _resolve_profile({"profile_id": "flash-scout"})
        context_pack = str(payload.get("context_pack") or "")
        if not context_pack:
            context_pack = _get_context_builder().build(
                session_id=session_id,
                current_user_message=str(payload.get("task") or ""),
                selected_profile=session.active_profile,
            )["context_pack"]
        state = _get_subagent_manager().spawn_subagent(
            parent_session_id=session_id,
            role=str(payload.get("role") or "ScoutAgent"),
            task=str(payload.get("task") or "Inspect repository state"),
            model_profile=profile,
            tool_policy=str(payload.get("tool_policy")
                            or _get_settings().subagents.default_tool_policy),
            context_pack=context_pack,
            timeout_sec=int(payload.get("timeout_sec")
                            or _get_settings().subagents.default_timeout_sec),
        )
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(state, status_code=202)


@app.get("/chat/subagents/{child_run_id}")
async def chat_subagent_detail(child_run_id: str) -> JSONResponse:
    try:
        state = _get_subagent_manager().get_subagent(child_run_id)
        artifact = _get_subagent_manager().get_artifact(child_run_id)
    except KeyError:
        return _json_error(f"Subagent '{child_run_id}' not found.", status_code=404)
    return JSONResponse({"subagent": state, "artifact": artifact.model_dump() if artifact else None})


@app.post("/chat/subagents/{child_run_id}/cancel")
async def chat_subagent_cancel(child_run_id: str) -> JSONResponse:
    try:
        cancelled = _get_subagent_manager().cancel_subagent(child_run_id)
    except KeyError:
        return _json_error(f"Subagent '{child_run_id}' not found.", status_code=404)
    if not cancelled:
        return _json_error(f"Subagent '{child_run_id}' is not cancellable.", status_code=409)
    return JSONResponse({"child_run_id": child_run_id, "status": "cancel_requested"})


@app.post("/chat/sessions/{session_id}/artifacts/attach")
async def chat_attach_artifact(session_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if not artifact_id:
        return _json_error("artifact_id is required.", status_code=400)
    try:
        session = _get_subagent_manager().attach_artifact_to_session(session_id, artifact_id)
    except (KeyError, FileNotFoundError):
        return _json_error(f"Session '{session_id}' not found.", status_code=404)
    return JSONResponse(session.model_dump())


@app.get("/chat/artifacts/{artifact_id}")
async def chat_artifact_detail(artifact_id: str) -> JSONResponse:
    try:
        artifact = _get_artifact_store().get_artifact(artifact_id)
    except FileNotFoundError:
        return _json_error(f"Artifact '{artifact_id}' not found.", status_code=404)
    return JSONResponse(artifact.to_public_dict())


# ── Agent OS Registry Routes ───────────────────────────────────────────────────


@app.get("/chat/playbooks")
async def list_playbooks() -> JSONResponse:
    try:
        playbooks = _get_playbook_registry().list_playbooks(enabled_only=False)
        return JSONResponse([pb.to_public_dict() for pb in playbooks])
    except Exception as exc:
        return _json_error(str(exc), status_code=500)


@app.get("/chat/playbooks/{playbook_id}")
async def get_playbook(playbook_id: str) -> JSONResponse:
    try:
        pb = _get_playbook_registry().get_playbook(playbook_id)
        return JSONResponse(pb.to_public_dict())
    except KeyError:
        return _json_error(f"Playbook '{playbook_id}' not found.", status_code=404)


@app.get("/chat/tools")
async def list_tools() -> JSONResponse:
    try:
        tools = _get_tool_registry().list_tools()
        return JSONResponse([t.to_public_dict() for t in tools])
    except Exception as exc:
        return _json_error(str(exc), status_code=500)


@app.get("/chat/tools/{tool_id}")
async def get_tool(tool_id: str) -> JSONResponse:
    try:
        tool = _get_tool_registry().get_tool(tool_id)
        return JSONResponse(tool.to_public_dict())
    except KeyError:
        return _json_error(f"Tool '{tool_id}' not found.", status_code=404)


@app.get("/chat/approvals")
async def list_approvals(request: Request) -> JSONResponse:
    session_id = request.query_params.get("session_id")
    status_filter = request.query_params.get("status")
    requests_list = _get_approval_queue().list_requests(
        session_id=session_id or None,
        status=status_filter or None,  # type: ignore[arg-type]
    )
    return JSONResponse([r.to_public_dict() for r in requests_list])


@app.post("/chat/approvals")
async def create_approval(request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        req = _get_approval_queue().create_request(
            session_id=str(payload.get("session_id") or ""),
            requested_action=str(payload.get("requested_action") or ""),
            risk_level=payload.get("risk_level", "medium"),
            reason=str(payload.get("reason") or ""),
            expected_behavior_change=bool(
                payload.get("expected_behavior_change", True)),
            files_or_scopes=[str(s)
                             for s in payload.get("files_or_scopes", [])],
            rollback_plan=str(payload.get("rollback_plan") or ""),
            requested_by=str(payload.get("requested_by") or ""),
        )
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc), status_code=400)
    return JSONResponse(req.to_public_dict(), status_code=201)


@app.post("/chat/approvals/{approval_id}/approve")
async def approve_request(approval_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        req = _get_approval_queue().resolve(
            approval_id,
            status="approved",
            resolved_by=str(payload.get("resolved_by") or "user"),
            note=str(payload.get("note") or ""),
        )
    except KeyError:
        return _json_error(f"ApprovalRequest '{approval_id}' not found.", status_code=404)
    except ValueError as exc:
        return _json_error(str(exc), status_code=409)
    return JSONResponse(req.to_public_dict())


@app.post("/chat/approvals/{approval_id}/reject")
async def reject_request(approval_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        req = _get_approval_queue().resolve(
            approval_id,
            status="rejected",
            resolved_by=str(payload.get("resolved_by") or "user"),
            note=str(payload.get("note") or ""),
        )
    except KeyError:
        return _json_error(f"ApprovalRequest '{approval_id}' not found.", status_code=404)
    except ValueError as exc:
        return _json_error(str(exc), status_code=409)
    return JSONResponse(req.to_public_dict())


@app.get("/chat/reports")
async def list_reports(request: Request) -> JSONResponse:
    report_type = request.query_params.get("type")
    status_filter = request.query_params.get("status")
    reports = _get_report_center().list_reports(
        report_type=report_type or None,  # type: ignore[arg-type]
        status=status_filter or None,  # type: ignore[arg-type]
    )
    return JSONResponse([r.to_public_dict() for r in reports])


@app.post("/chat/reports/scan")
async def scan_reports() -> JSONResponse:
    new_records = _get_report_center().scan_and_index()
    return JSONResponse({
        "scanned": len(new_records),
        "reports": [r.to_public_dict() for r in new_records],
    })


@app.get("/chat/reports/{report_id}")
async def get_report(report_id: str) -> JSONResponse:
    try:
        rec = _get_report_center().get_report(report_id)
        return JSONResponse(rec.to_public_dict())
    except KeyError:
        return _json_error(f"Report '{report_id}' not found.", status_code=404)


@app.post("/chat/reports/{report_id}/status")
async def update_report_status(report_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        rec = _get_report_center().update_status(
            report_id, payload.get("status", "accepted"))
    except KeyError:
        return _json_error(f"Report '{report_id}' not found.", status_code=404)
    except ValueError as exc:
        return _json_error(str(exc), status_code=400)
    return JSONResponse(rec.to_public_dict())


@app.get("/chat/decisions")
async def list_decisions(request: Request) -> JSONResponse:
    active_only = request.query_params.get(
        "active_only", "false").lower() in ("1", "true")
    decisions = _get_decision_ledger().list_decisions(active_only=active_only)
    return JSONResponse([d.to_public_dict() for d in decisions])


@app.post("/chat/decisions")
async def add_decision(request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        decision_text = str(payload.get("decision") or "").strip()
        if not decision_text:
            return _json_error("decision is required.", status_code=400)
        rec = _get_decision_ledger().add_decision(
            decision=decision_text,
            scope=str(payload.get("scope") or ""),
            project_id=str(payload.get("project_id") or ""),
            source_report_ids=[str(r)
                               for r in payload.get("source_report_ids", [])],
            confidence=float(payload.get("confidence", 1.0)),
        )
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc), status_code=400)
    return JSONResponse(rec.to_public_dict(), status_code=201)


@app.post("/chat/decisions/{decision_id}/deprecate")
async def deprecate_decision(decision_id: str) -> JSONResponse:
    try:
        rec = _get_decision_ledger().deprecate(decision_id)
    except KeyError:
        return _json_error(f"Decision '{decision_id}' not found.", status_code=404)
    return JSONResponse(rec.to_public_dict())


@app.get("/chat/memory-patches")
async def list_memory_patches(request: Request) -> JSONResponse:
    status_filter = request.query_params.get("status")
    patches = _get_memory_patch_store().list_patches(
        status=status_filter or None  # type: ignore[arg-type]
    )
    return JSONResponse([p.to_public_dict() for p in patches])


@app.post("/chat/memory-patches")
async def create_memory_patch(request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        patch = _get_memory_patch_store().create_patch(
            proposed_change=str(payload.get("proposed_change") or ""),
            affected_checkpoint_section=str(
                payload.get("affected_checkpoint_section") or ""),
            reason=str(payload.get("reason") or ""),
            risk=payload.get("risk", "low"),
            diff=str(payload.get("diff") or ""),
            source_report_ids=[str(r)
                               for r in payload.get("source_report_ids", [])],
        )
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc), status_code=400)
    return JSONResponse(patch.to_public_dict(), status_code=201)


@app.post("/chat/memory-patches/{patch_id}/approve")
async def approve_memory_patch(patch_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        patch = _get_memory_patch_store().approve(
            patch_id, approved_by=str(payload.get("approved_by") or "user"))
    except KeyError:
        return _json_error(f"Patch '{patch_id}' not found.", status_code=404)
    except ValueError as exc:
        return _json_error(str(exc), status_code=409)
    return JSONResponse(patch.to_public_dict())


@app.post("/chat/memory-patches/{patch_id}/reject")
async def reject_memory_patch(patch_id: str, request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    try:
        patch = _get_memory_patch_store().reject(
            patch_id, reason=str(payload.get("reason") or ""))
    except KeyError:
        return _json_error(f"Patch '{patch_id}' not found.", status_code=404)
    except ValueError as exc:
        return _json_error(str(exc), status_code=409)
    return JSONResponse(patch.to_public_dict())


@app.get("/chat/evidence-bundles")
async def list_evidence_bundles() -> JSONResponse:
    store = _get_evidence_bundle_store()
    bundles = []
    for path in store.bundles_dir.glob("*.dsbundle.json"):
        try:
            import json as _json

            from ..sessions.evidence_bundle import EvidenceBundle as _EB
            b = _EB(**_json.loads(path.read_text(encoding="utf-8")))
            bundles.append(b.to_public_dict())
        except Exception:
            continue
    bundles.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return JSONResponse(bundles)


@app.post("/chat/evidence-bundles/scan")
async def scan_evidence_bundle(request: Request) -> JSONResponse:
    payload = await _extract_payload(request)
    log_dir = str(payload.get("log_dir") or _get_settings().agent.log_dir)
    window = str(payload.get("window") or "latest")
    try:
        bundle = _get_evidence_bundle_store().create_metadata_scan(
            log_dir=_get_root_dir() / log_dir,
            window=window,
        )
    except Exception as exc:
        return _json_error(str(exc), status_code=500)
    return JSONResponse(bundle.to_public_dict(), status_code=201)


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    """Console script entry point: deepseek-agent-dashboard."""
    s = _get_settings()
    host = os.environ.get("DASHBOARD_HOST", s.dashboard.host)
    port = int(os.environ.get("DASHBOARD_PORT", s.dashboard.port))
    print(f"[DASHBOARD] Starting on http://{host}:{port}", flush=True)
    uvicorn.run(
        "deepseek_terminal_agent.dashboard.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
