"""API tests for Cockpit agent arena event button endpoints."""
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


def base_payload() -> dict:
    return {
        "agent_id": "primary-cockpit-agent-event-buttons-builder",
        "agent_number": 3,
        "rationale": "Record agent command for FSM review.",
        "payload": {"symbol": "BTCUSDT", "side_bias": "long"},
    }


def test_create_and_list_all_agent_event_buttons(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()
    endpoints = [
        ("rationale", "recorded"),
        ("sos", "pending_fsm"),
        ("testnet-order-request", "pending_fsm"),
        ("testnet-cancel-request", "pending_fsm"),
        ("testnet-close-request", "pending_fsm"),
    ]

    created = []
    for endpoint, expected_status in endpoints:
        resp = client.post(f"/chat/sessions/{session_id}/agent-events/{endpoint}", json=base_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["event_id"].startswith("event-")
        assert body["command_id"].startswith("command-")
        assert body["created_at"]
        assert body["session_id"] == session_id
        assert body["agent_id"] == "primary-cockpit-agent-event-buttons-builder"
        assert body["agent_number"] == 3
        assert body["status"] == expected_status
        assert body["environment"] == "testnet"
        assert body["exchange_submitted"] is False
        created.append(body)

    list_resp = client.get(f"/chat/sessions/{session_id}/agent-events")
    assert list_resp.status_code == 200
    listed = list_resp.json()["agent_events"]
    assert {item["event_id"] for item in listed} == {item["event_id"] for item in created}
    assert all(item["command_id"] for item in listed)
    assert all(item["created_at"] for item in listed)

    events = dashboard_app._get_session_store().list_events(session_id)
    assert sum(1 for event in events if event["event_type"].startswith("agent_arena.")) == 5


def test_agent_event_routes_fail_closed_for_missing_session(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)

    create_resp = client.post("/chat/sessions/missing-session/agent-events/rationale", json=base_payload())
    list_resp = client.get("/chat/sessions/missing-session/agent-events")

    assert create_resp.status_code == 404
    assert list_resp.status_code == 404


def test_agent_event_routes_reject_missing_agent_identity(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    missing_agent = base_payload()
    missing_agent.pop("agent_id")
    missing_number = base_payload()
    missing_number.pop("agent_number")

    agent_resp = client.post(f"/chat/sessions/{session_id}/agent-events/sos", json=missing_agent)
    number_resp = client.post(f"/chat/sessions/{session_id}/agent-events/sos", json=missing_number)

    assert agent_resp.status_code == 400
    assert number_resp.status_code == 400


def test_agent_event_routes_reject_mainnet_and_raw_exchange_payload(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    mainnet = base_payload()
    mainnet["mainnet"] = True
    raw_exchange = base_payload()
    raw_exchange["payload"] = {"raw_exchange_payload": {"endpoint": "/fapi/v1/order"}}

    mainnet_resp = client.post(
        f"/chat/sessions/{session_id}/agent-events/testnet-order-request",
        json=mainnet,
    )
    raw_resp = client.post(
        f"/chat/sessions/{session_id}/agent-events/testnet-order-request",
        json=raw_exchange,
    )

    assert mainnet_resp.status_code == 400
    assert raw_resp.status_code == 400


def test_agent_event_routes_fail_closed_if_registry_unavailable(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    def unavailable() -> None:
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(dashboard_app, "ensure_agent_arena_registry_available", unavailable)

    resp = client.post(f"/chat/sessions/{session_id}/agent-events/rationale", json=base_payload())

    assert resp.status_code == 503
    assert "registry unavailable" in resp.json()["error"]
