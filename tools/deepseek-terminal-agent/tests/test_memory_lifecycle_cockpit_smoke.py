from __future__ import annotations

from fastapi.testclient import TestClient

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.dashboard import app as dashboard_app


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
        "_agent_memory_lifecycle",
    ):
        setattr(dashboard_app, name, None)
    dashboard_app._settings = Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))
    return TestClient(dashboard_app.app)


def identity_payload() -> dict:
    return {
        "agent_id": "primary-memory-lifecycle-cockpit-smoke-builder",
        "agent_number": 4,
        "instruction_manifest_version": "manifest-p39d",
    }


def test_cockpit_memory_lifecycle_smoke_passes_without_exchange_access(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)

    session_resp = client.post("/chat/sessions", json={"title": "P39D smoke"})
    assert session_resp.status_code == 201
    session_id = session_resp.json()["session"]["session_id"]

    identity_resp = client.post(
        f"/chat/sessions/{session_id}/agent-memory/identity",
        json=identity_payload(),
    )
    assert identity_resp.status_code == 201

    ack_resp = client.post(
        f"/chat/sessions/{session_id}/agent-memory/instruction-ack",
        json={**identity_payload(), "event_id": "instruction-event-1"},
    )
    assert ack_resp.status_code == 200
    assert "instruction-event-1" in ack_resp.json()["memory"]["event_refs"]

    rationale_resp = client.post(
        f"/chat/sessions/{session_id}/agent-events/rationale",
        json={
            **identity_payload(),
            "rationale": "Strategic 30m rationale only; no order request.",
            "payload": {"symbol": "ETHUSDT", "decision_window": "30m"},
        },
    )
    assert rationale_resp.status_code == 201
    assert rationale_resp.json()["exchange_submitted"] is False

    fsm_resp = client.post(
        f"/chat/sessions/{session_id}/agent-memory/fsm-decision",
        json={
            **identity_payload(),
            "event_id": "fsm-event-1",
            "command_id": "command-1",
            "accepted": False,
            "reason": "Rejected until notional is supplied by SSOT.",
        },
    )
    assert fsm_resp.status_code == 200

    memory_resp = client.get(
        f"/chat/sessions/{session_id}/agent-memory",
        params={
            "agent_id": identity_payload()["agent_id"],
            "agent_number": identity_payload()["agent_number"],
        },
    )
    assert memory_resp.status_code == 200
    memory = memory_resp.json()["memory"]
    assert memory["session_id"] == session_id
    assert len(memory["reflections"]) == 2
    assert {item["kind"] for item in memory["reflections"]} == {
        "opening_assumptions",
        "decision_review",
    }

    end_resp = client.post(
        f"/chat/sessions/{session_id}/agent-memory/end",
        json=identity_payload(),
    )
    assert end_resp.status_code == 200
    assert end_resp.json()["summary"]["total_reflections"] == 2
    assert "Agent Session Carryover" in end_resp.json()["carryover_md"]

    subagents_resp = client.get(f"/chat/sessions/{session_id}/subagents")
    assert subagents_resp.status_code == 200
    assert subagents_resp.json()["subagents"] == []


def test_cockpit_memory_routes_reject_missing_identity(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = client.post("/chat/sessions", json={"title": "P39D identity"}).json()["session"]["session_id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/agent-memory/identity",
        json={"agent_number": 4},
    )

    assert resp.status_code == 400
    assert "agent_id is required" in resp.json()["error"]
