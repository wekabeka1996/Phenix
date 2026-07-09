"""Tests for session-bound agent proposal ledger routes."""
from __future__ import annotations

import json
from fastapi.testclient import TestClient

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.dashboard import app as dashboard_app
from deepseek_terminal_agent.sessions.models import ModelProfile


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def make_profile() -> ModelProfile:
    return ModelProfile(
        profile_id="profile-a",
        name="Profile A",
        model_id="deepseek-v4-pro",
        thinking_type="enabled",
        reasoning_effort="high",
        temperature=0.2,
        top_p=1.0,
        max_tokens=4096,
        response_format="text",
        stream=False,
        tool_mode="auto",
        max_iterations=6,
        command_timeout_sec=30,
        max_command_output_chars=1200,
        context_budget_chars=40000,
        memory_atom_budget=4,
        recent_turns_budget=3,
        tool_output_budget_chars=1500,
    )


def reset_dashboard(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    for name in (
        "_runner",
        "_session_store",
        "_model_registry",
        "_memory_store",
        "_artifact_store",
        "_attachment_store",
        "_agent_proposal_store",
        "_context_builder",
        "_context_inspector",
        "_chat_runtime",
        "_subagent_manager",
        "_project_capsule_store",
        "_playbook_registry",
        "_tool_registry",
        "_approval_queue",
        "_report_center",
        "_decision_ledger",
        "_memory_patch_store",
        "_evidence_bundle_store",
    ):
        setattr(dashboard_app, name, None)
    dashboard_app._settings = make_settings()
    return TestClient(dashboard_app.app)


def create_session() -> str:
    session = dashboard_app._get_session_store().create_session(default_profile=make_profile())
    return session.session_id


def test_create_list_get_proposals(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    # 1. Create a valid proposal
    resp = client.post(
        f"/chat/sessions/{session_id}/agent-proposals",
        json={
            "agent_id": "test-agent",
            "agent_number": 1,
            "kind": "analysis_note",
            "rationale": "High orderbook imbalance detected.",
            "source_refs": ["ob-imbalance"],
            "payload": {"ratio": 1.45},
        },
    )
    assert resp.status_code == 201
    proposal = resp.json()
    assert proposal["session_id"] == session_id
    assert proposal["kind"] == "analysis_note"
    assert proposal["payload"] == {"ratio": 1.45}

    # 2. List proposals
    list_resp = client.get(f"/chat/sessions/{session_id}/agent-proposals")
    assert list_resp.status_code == 200
    proposals_list = list_resp.json()["agent_proposals"]
    assert len(proposals_list) == 1
    assert proposals_list[0]["proposal_id"] == proposal["proposal_id"]

    # 3. Get proposal detail
    detail_resp = client.get(f"/chat/agent-proposals/{proposal['proposal_id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["rationale"] == "High orderbook imbalance detected."


def test_proposal_rejections_for_forbidden_fields(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    # Rejection: flat forbidden key
    resp_flat = client.post(
        f"/chat/sessions/{session_id}/agent-proposals",
        json={
            "agent_id": "test-agent",
            "agent_number": 1,
            "kind": "analysis_note",
            "rationale": "Attempting flat sizing key",
            "payload": {"sizing": 1000},
        },
    )
    assert resp_flat.status_code == 400
    assert "Forbidden proposal field" in resp_flat.json()["error"]

    # Rejection: nested forbidden key inside payload
    resp_nested = client.post(
        f"/chat/sessions/{session_id}/agent-proposals",
        json={
            "agent_id": "test-agent",
            "agent_number": 1,
            "kind": "analysis_note",
            "rationale": "Attempting nested order key",
            "payload": {"nested_data": {"order": {"price": 100}}},
        },
    )
    assert resp_nested.status_code == 400
    assert "Forbidden proposal field" in resp_nested.json()["error"]
