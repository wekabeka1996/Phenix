"""Tests for session-bound attachment metadata routes."""
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


def test_create_list_get_attachment_routes(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    resp = client.post(
        f"/chat/sessions/{session_id}/attachments",
        json={
            "kind": "operator_note",
            "raw_ref": "operator://note/market-context",
            "summary": "Operator noted that BTC volatility is elevated.",
            "source_refs": ["operator-note:market-context"],
            "created_by": "operator",
            "include_in_prompt": True,
        },
    )

    assert resp.status_code == 201
    attachment = resp.json()
    assert attachment["session_id"] == session_id
    assert attachment["kind"] == "operator_note"
    assert attachment["token_estimate"] > 0
    attachment_path = (
        tmp_path
        / ".agent_memory"
        / "attachments"
        / f"{attachment['attachment_id']}.dsattachment.json"
    )
    assert attachment_path.exists()

    list_resp = client.get(f"/chat/sessions/{session_id}/attachments")
    assert list_resp.status_code == 200
    assert list_resp.json()["attachments"][0]["attachment_id"] == attachment["attachment_id"]

    detail_resp = client.get(f"/chat/attachments/{attachment['attachment_id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["summary"] == "Operator noted that BTC volatility is elevated."


def test_attachment_routes_fail_closed_for_missing_session(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)

    create_resp = client.post(
        "/chat/sessions/missing-session/attachments",
        json={"kind": "pasted_text", "summary": "unattached"},
    )
    list_resp = client.get("/chat/sessions/missing-session/attachments")

    assert create_resp.status_code == 404
    assert list_resp.status_code == 404


def test_attachment_route_rejects_invalid_kind_and_raw_blob_fields(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    invalid_kind = client.post(
        f"/chat/sessions/{session_id}/attachments",
        json={"kind": "raw_image_bytes", "summary": "bad kind"},
    )
    raw_blob = client.post(
        f"/chat/sessions/{session_id}/attachments",
        json={"kind": "image_ref", "summary": "bad bytes", "image_bytes": "abc123"},
    )
    data_uri = client.post(
        f"/chat/sessions/{session_id}/attachments",
        json={"kind": "image_ref", "summary": "bad data uri", "raw_ref": "data:image/png;base64,abc123"},
    )

    assert invalid_kind.status_code == 400
    assert raw_blob.status_code == 400
    assert data_uri.status_code == 400


def test_context_builder_includes_only_prompt_eligible_attachment_refs(tmp_path, monkeypatch):
    client = reset_dashboard(tmp_path, monkeypatch)
    session_id = create_session()

    included = client.post(
        f"/chat/sessions/{session_id}/attachments",
        json={
            "kind": "news_summary",
            "raw_ref": "news://btc/summary",
            "summary": "ETF flow summary: inflows accelerated during the US session.",
            "source_refs": ["news:btc-etf-flow"],
            "include_in_prompt": True,
        },
    )
    excluded = client.post(
        f"/chat/sessions/{session_id}/attachments",
        json={
            "kind": "pasted_text",
            "raw_ref": "operator://paste/raw-long-note",
            "summary": "EXCLUDED_RAW_MARKER should not enter context.",
            "include_in_prompt": False,
        },
    )

    assert included.status_code == 201
    assert excluded.status_code == 201

    context_resp = client.post(
        f"/chat/sessions/{session_id}/context",
        json={"message": "Inspect attachments."},
    )

    assert context_resp.status_code == 200
    payload = context_resp.json()
    assert "attachments" in payload["context_report"]["included_sections"]
    assert "ETF flow summary" in payload["context_pack"]
    assert "news:btc-etf-flow" in payload["context_pack"]
    assert "EXCLUDED_RAW_MARKER" not in payload["context_pack"]
