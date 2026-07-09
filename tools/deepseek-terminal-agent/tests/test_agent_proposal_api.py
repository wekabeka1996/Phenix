"""API tests for session-bound agent proposal routes."""
from __future__ import annotations

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
        "_compressor",
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


def valid_payload() -> dict:
    return {
        "agent_id": "primary-cli-proposal-ledger-builder",
        "agent_number": 3,
        "kind": "trade_intent_draft",
        "confidence": 0.55,
        "rationale": "Non-executable draft for operator review.",
        "source_refs": ["report:p35c"],
        "payload": {
            "symbol": "BTCUSDT",
            "side_bias": "long",
            "rationale": "Market structure shifted.",
            "refs": ["market-note:1"],
        },
    }


def test_create_list_get_agent_proposal_and_logs_event(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    create_resp = client.post(
        f"/chat/sessions/{session_id}/agent-proposals",
        json=valid_payload(),
    )

    assert create_resp.status_code == 201
    proposal = create_resp.json()
    assert proposal["session_id"] == session_id
    assert proposal["kind"] == "trade_intent_draft"
    assert proposal["execution_authority"] is False

    list_resp = client.get(f"/chat/sessions/{session_id}/agent-proposals")
    assert list_resp.status_code == 200
    assert list_resp.json()["agent_proposals"][0]["proposal_id"] == proposal["proposal_id"]

    detail_resp = client.get(f"/chat/agent-proposals/{proposal['proposal_id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["agent_id"] == "primary-cli-proposal-ledger-builder"

    events = dashboard_app._get_session_store().list_events(session_id)
    assert events[-1]["event_type"] == "agent_proposal_submitted"
    assert events[-1]["metadata"]["proposal_id"] == proposal["proposal_id"]
    assert events[-1]["metadata"]["agent_number"] == 3


def test_agent_proposal_routes_fail_closed_for_missing_session(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)

    create_resp = client.post("/chat/sessions/missing-session/agent-proposals", json=valid_payload())
    list_resp = client.get("/chat/sessions/missing-session/agent-proposals")

    assert create_resp.status_code == 404
    assert list_resp.status_code == 404


def test_agent_proposal_api_rejects_forbidden_fields(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    nested = valid_payload()
    nested["payload"] = {"quantity": "0.1"}
    top_level = valid_payload()
    top_level["notional"] = 1000

    nested_resp = client.post(f"/chat/sessions/{session_id}/agent-proposals", json=nested)
    top_level_resp = client.post(f"/chat/sessions/{session_id}/agent-proposals", json=top_level)

    assert nested_resp.status_code == 400
    assert top_level_resp.status_code == 400


def test_agent_proposal_api_rejects_missing_required_agent_number(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()
    payload = valid_payload()
    payload.pop("agent_number")

    resp = client.post(f"/chat/sessions/{session_id}/agent-proposals", json=payload)

    assert resp.status_code == 400
    assert "agent_number is required" in resp.json()["error"]
