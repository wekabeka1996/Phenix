"""Cockpit API smoke for both P41X agents and collective state."""
from __future__ import annotations

from fastapi.testclient import TestClient

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.dashboard import app as dashboard_app
from deepseek_terminal_agent.sessions.models import ModelProfile


def _reset_dashboard(tmp_path, monkeypatch) -> TestClient:
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
        "_collective_memory_store",
        "_agent_tool_runtime",
    ):
        setattr(dashboard_app, name, None)
    dashboard_app._settings = Settings(deepseek=DeepSeekConfig(api_key="test-key"))
    return TestClient(dashboard_app.app)


def test_cockpit_smoke_shows_both_agents_collective_state_and_tool_registry(tmp_path, monkeypatch):
    client = _reset_dashboard(tmp_path, monkeypatch)
    session = dashboard_app._get_session_store().create_session(
        default_profile=ModelProfile(profile_id="p41x", name="P41X", model_id="deepseek-v4-pro")
    )

    initial = client.get(f"/chat/sessions/{session.session_id}/coordination")
    assert initial.status_code == 200
    body = initial.json()
    assert set(body["active_agents"]) == {"api_agent_01", "cli_agent_01"}
    assert {item["symbol"] for item in body["symbol_ownership"]} == {
        "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"
    }

    for agent_id, agent_number, symbol, suffix in (
        ("api_agent_01", 1, "ETHUSDT", "api"),
        ("cli_agent_01", 2, "XRPUSDT", "cli"),
    ):
        response = client.post(
            f"/chat/sessions/{session.session_id}/agent-tools/PUBLISH_OBSERVATION",
            json={
                "agent_id": agent_id,
                "agent_number": agent_number,
                "kind": "peer_observation",
                "summary": f"{symbol} coordination smoke",
                "symbol": symbol,
                "source_refs": [],
                "idempotency_key": f"api-smoke:{suffix}",
            },
        )
        assert response.status_code == 201

    refreshed = client.get(f"/chat/sessions/{session.session_id}/coordination")
    assert refreshed.status_code == 200
    assert refreshed.json()["collective_memory"]["publication_count"] == 2
    assert {item["agent_id"] for item in refreshed.json()["peer_publications"]} == {
        "api_agent_01", "cli_agent_01"
    }

    contracts = client.get("/chat/agent-tools")
    assert contracts.status_code == 200
    assert len(contracts.json()["agent_tools"]) == 15
