"""Tests for /chat dashboard routes."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from deepseek_terminal_agent.dashboard.app import app
from deepseek_terminal_agent.deepseek_client import DeepSeekAPIError, DeepSeekTimeoutError


def make_mock_settings(api_key: str = "sk-test-key"):
    settings = MagicMock()
    settings.deepseek.api_key = api_key
    settings.terminal.workspace_root = "/workspace/project"
    settings.dashboard.chat_enabled = True
    settings.dashboard.context_inspector_enabled = True
    settings.dashboard.memory_panel_enabled = True
    settings.dashboard.subagents_panel_enabled = True
    settings.subagents.default_tool_policy = "read_only"
    settings.subagents.default_timeout_sec = 300
    settings.project_capsule.path = "config/project_capsule.yaml"
    return settings


def make_profile(profile_id: str = "pro-thinking-max", model_id: str = "deepseek-v4-pro"):
    profile = MagicMock()
    profile.profile_id = profile_id
    profile.model_id = model_id
    profile.name = profile_id
    profile.model_dump.return_value = {
        "profile_id": profile_id, "model_id": model_id, "name": profile_id}
    return profile


def make_session(session_id: str = "session-1"):
    session = MagicMock()
    session.session_id = session_id
    session.model_dump.return_value = {
        "session_id": session_id,
        "title": "Session 1",
        "active_profile": {"profile_id": "pro-thinking-max", "model_id": "deepseek-v4-pro", "name": "pro-thinking-max"},
        "pinned_memory_atom_ids": [],
        "status": "idle",
        "metadata": {},
    }
    session.active_profile = make_profile()
    return session


def make_capsule():
    capsule = MagicMock()
    capsule.to_public_dict.return_value = {
        "project": {
            "name": "Aurora/Phenix",
            "domain": "algorithmic_trading_system",
            "mode": "live_runtime_sensitive",
            "current_phase": "project_agent_os_transition",
        },
        "ssot_rules": {
            "config": ["YAML + Pydantic only"],
            "development": ["Contract-first"],
            "runtime": ["Logs are evidence"],
        },
        "memory": {
            "deep_checkpoint": True,
            "accepted_reports_only": True,
            "default_agent_search_mode": "current_ssot_and_accepted_facts",
        },
        "permissions": {
            "production_changes": "approval_required",
            "config_changes": "approval_required",
            "registry_changes": "approval_required",
            "memory_updates": "patch_approval_required",
        },
        "current_phase": {
            "name": "Project Agent OS transition",
            "status": "in_progress",
            "completed": ["baseline"],
            "in_progress": ["capsule rollout"],
            "blockers": ["workspace proof pending"],
            "risks": ["raw logs without evidence bundle"],
            "next_best_step": ["expose capsule in workbench"],
        },
        "counts": {
            "config_rules": 1,
            "development_rules": 1,
            "runtime_rules": 1,
            "completed_items": 1,
            "in_progress_items": 1,
            "blockers": 1,
            "risks": 1,
            "next_steps": 1,
        },
    }
    return capsule


def test_chat_page_renders_without_exposing_api_key():
    client = TestClient(app)
    session_store = MagicMock()
    session_store.list_sessions.return_value = []
    model_registry = MagicMock()
    model_registry.list_models.return_value.model_dump.return_value = {
        "source": "static_fallback", "models": []}
    model_registry.get_default_profiles.return_value = [make_profile()]
    capsule_store = MagicMock()
    capsule_store.load.return_value = make_capsule()

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings(api_key="sk-secret-value")),
        patch("deepseek_terminal_agent.dashboard.app._get_session_store",
              return_value=session_store),
        patch("deepseek_terminal_agent.dashboard.app._get_model_registry",
              return_value=model_registry),
        patch("deepseek_terminal_agent.dashboard.app._get_project_capsule_store",
              return_value=capsule_store),
    ):
        resp = client.get("/chat")

    assert resp.status_code == 200
    # Title updated to Agent OS cockpit
    assert "DeepSeek" in resp.text
    assert "projectCapsule" in resp.text or "chat-bootstrap" in resp.text
    assert "projectCapsule" in resp.text
    assert 'id="layout-mode-cockpit"' in resp.text
    assert 'id="layout-mode-board"' in resp.text
    assert 'id="board-canvas"' in resp.text
    assert "sk-secret-value" not in resp.text


def test_chat_project_capsule_route_returns_capsule_payload():
    client = TestClient(app)
    capsule_store = MagicMock()
    capsule_store.load.return_value = make_capsule()

    with patch(
        "deepseek_terminal_agent.dashboard.app._get_project_capsule_store",
        return_value=capsule_store,
    ):
        resp = client.get("/chat/project-capsule")

    assert resp.status_code == 200
    assert resp.json()["project"]["name"] == "Aurora/Phenix"
    assert resp.json()["counts"]["risks"] == 1


def test_create_chat_session_returns_detail():
    client = TestClient(app)
    session_store = MagicMock()
    session_store.create_session.return_value = make_session("session-1")

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_session_store",
              return_value=session_store),
        patch("deepseek_terminal_agent.dashboard.app._default_profiles",
              return_value=[make_profile()]),
        patch("deepseek_terminal_agent.dashboard.app._session_detail", return_value={"session": {
              "session_id": "session-1"}, "turns": [], "events": [], "memory_atoms": [], "artifacts": [], "subagents": []}),
    ):
        resp = client.post("/chat/sessions", json={"title": "Session 1"})

    assert resp.status_code == 201
    assert resp.json()["session"]["session_id"] == "session-1"


def test_chat_send_message_returns_runtime_result():
    client = TestClient(app)
    runtime = MagicMock()
    runtime.send_message.return_value = {
        "assistant_turn": {"visible_content": "hello"},
        "context_report": {"warnings": []},
        "context_report_path": "/tmp/report.json",
    }

    with patch("deepseek_terminal_agent.dashboard.app._get_chat_runtime", return_value=runtime):
        resp = client.post("/chat/sessions/session-1/message",
                           json={"message": "hello"})

    assert resp.status_code == 200
    assert resp.json()["assistant_turn"]["visible_content"] == "hello"


def test_chat_send_message_returns_gateway_timeout_for_upstream_timeout():
    client = TestClient(app)
    runtime = MagicMock()
    runtime.send_message.side_effect = DeepSeekTimeoutError(
        "DeepSeek API request timed out after 300s while calling model 'deepseek-v4-pro'."
    )

    with patch("deepseek_terminal_agent.dashboard.app._get_chat_runtime", return_value=runtime):
        resp = client.post("/chat/sessions/session-1/message",
                           json={"message": "hello"})

    assert resp.status_code == 504
    assert "timed out" in resp.json()["error"].lower()


def test_chat_send_message_returns_bad_gateway_for_upstream_api_error():
    client = TestClient(app)
    runtime = MagicMock()
    runtime.send_message.side_effect = DeepSeekAPIError(
        "DeepSeek API request failed upstream.")

    with patch("deepseek_terminal_agent.dashboard.app._get_chat_runtime", return_value=runtime):
        resp = client.post("/chat/sessions/session-1/message",
                           json={"message": "hello"})

    assert resp.status_code == 502
    assert "failed upstream" in resp.json()["error"].lower()


def test_chat_models_returns_catalog_and_profiles():
    client = TestClient(app)
    model_registry = MagicMock()
    model_registry.list_models.return_value.model_dump.return_value = {
        "source": "cached", "models": [{"model_id": "deepseek-v4-pro"}]}

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_model_registry",
              return_value=model_registry),
        patch("deepseek_terminal_agent.dashboard.app._default_profiles",
              return_value=[make_profile()]),
    ):
        resp = client.get("/chat/models")

    assert resp.status_code == 200
    assert resp.json()["catalog"]["source"] == "cached"
    assert resp.json()[
        "default_profiles"][0]["profile_id"] == "pro-thinking-max"


def test_chat_context_and_subagent_routes_use_services():
    client = TestClient(app)
    session_store = MagicMock()
    session_store.get_session.return_value = make_session("session-1")
    inspector = MagicMock()
    inspector.inspect.return_value = {
        "context_report": {"warnings": []}, "context_pack": "pack"}
    manager = MagicMock()
    manager.spawn_subagent.return_value = {
        "child_run_id": "run-1", "status": "queued"}
    builder = MagicMock()
    builder.build.return_value = {"context_pack": "built context"}

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_session_store",
              return_value=session_store),
        patch("deepseek_terminal_agent.dashboard.app._get_context_inspector",
              return_value=inspector),
        patch("deepseek_terminal_agent.dashboard.app._get_subagent_manager",
              return_value=manager),
        patch("deepseek_terminal_agent.dashboard.app._get_context_builder",
              return_value=builder),
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._resolve_profile",
              return_value=make_profile("flash-scout", "deepseek-v4-flash")),
    ):
        context_resp = client.post(
            "/chat/sessions/session-1/context", json={"message": "inspect"})
        subagent_resp = client.post(
            "/chat/sessions/session-1/subagents", json={"task": "Inspect repo"})

    assert context_resp.status_code == 200
    assert context_resp.json()["context_pack"] == "pack"
    assert subagent_resp.status_code == 202
    assert subagent_resp.json()["child_run_id"] == "run-1"


def test_memory_search_route_returns_matches():
    client = TestClient(app)
    session_store = MagicMock()
    session_store.get_session.return_value = make_session("session-1")

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_session_store",
              return_value=session_store),
        patch(
            "deepseek_terminal_agent.dashboard.app._search_session_memory",
            return_value=[{"atom_id": "atom-1", "kind": "invariant",
                           "text": "ChatSession is the source of truth."}],
        ),
    ):
        resp = client.get(
            "/chat/sessions/session-1/memory/search?q=model+switch+context")

    assert resp.status_code == 200
    assert resp.json()["query"] == "model switch context"
    assert resp.json()["memory_atoms"][0]["atom_id"] == "atom-1"
