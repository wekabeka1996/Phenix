"""Tests for dashboard/app.py FastAPI routes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from deepseek_terminal_agent.dashboard.app import app

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_mock_settings(api_key: str = "sk-test-key-for-tests"):
    s = MagicMock()
    s.deepseek.api_key = api_key
    s.deepseek.model = "deepseek-v4-pro"
    s.deepseek.base_url = "https://api.deepseek.com"
    s.deepseek.reasoning_enabled = True
    s.terminal.workspace_root = "/workspace/project"
    s.agent.log_dir = "/tmp/test_agent_runs"
    s.dashboard.max_prompt_chars = 12000
    s.dashboard.max_output_chars = 30000
    s.dashboard.recent_runs_limit = 20
    return s


def make_mock_runner():
    runner = MagicMock()
    runner.list_runs.return_value = [
        {
            "run_id": "testrun001",
            "prompt": "hello",
            "status": "succeeded",
            "duration_ms": 123,
            "created_at": "2026-04-30T12:00:00+00:00",
            "exit_code": 0,
            "current_phase": "succeeded",
            "latest_event": "Run completed successfully",
            "run_dir": "/tmp/test_agent_runs/2026-04-30T12-00-00",
        }
    ]
    runner.create_run.return_value = {
        "run_id": "testrun001",
        "prompt": "hello",
        "status": "running",
        "created_at": "2026-04-30T12:00:00+00:00",
        "started_at": "2026-04-30T12:00:01+00:00",
        "finished_at": None,
        "duration_ms": 10,
        "exit_code": None,
        "current_phase": "running",
        "latest_event": "Starting agent process",
        "error": None,
        "run_dir": None,
    }
    runner.get_status.return_value = {
        "run_id": "testrun001",
        "prompt": "hello",
        "status": "running",
        "created_at": "2026-04-30T12:00:00+00:00",
        "started_at": "2026-04-30T12:00:01+00:00",
        "finished_at": None,
        "duration_ms": 10,
        "exit_code": None,
        "current_phase": "waiting_model",
        "latest_event": "Agent iteration 1/20",
        "error": None,
        "run_dir": "/tmp/test_agent_runs/2026-04-30T12-00-00",
    }
    runner.get_output.return_value = {
        "run_id": "testrun001",
        "status": "running",
        "output": "visible output\n",
        "stdout": "visible output\n",
        "stderr": "",
        "truncated": False,
        "run_dir": "/tmp/test_agent_runs/2026-04-30T12-00-00",
    }
    runner.get_events.return_value = [
        {
            "ts": "2026-04-30T12:00:01+00:00",
            "run_id": "testrun001",
            "type": "tool_call",
            "phase": "tool_call",
            "message": "Tool call: terminal_exec",
            "metadata": {"cmd": "pwd"},
        }
    ]
    runner.cancel.return_value = True
    return runner


# ── /health ───────────────────────────────────────────────────────────────────


def test_health_ok():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["service"] == "deepseek-terminal-agent-dashboard"


# ── /config-status ────────────────────────────────────────────────────────────


def test_config_status_has_api_key_present_not_value():
    client = TestClient(app)
    with patch(
        "deepseek_terminal_agent.dashboard.app._get_settings",
        return_value=make_mock_settings(api_key="sk-secret-never-shown"),
    ):
        resp = client.get("/config-status")

    assert resp.status_code == 200
    data = resp.json()
    assert "api_key_present" in data
    assert data["api_key_present"] is True
    assert "api_key" not in data
    # The actual key must NOT appear anywhere in the response body
    assert "sk-secret-never-shown" not in resp.text


def test_config_status_api_key_absent():
    client = TestClient(app)
    with patch(
        "deepseek_terminal_agent.dashboard.app._get_settings",
        return_value=make_mock_settings(api_key=""),
    ):
        resp = client.get("/config-status")

    assert resp.status_code == 200
    assert resp.json()["api_key_present"] is False


def test_config_status_has_model_and_workspace():
    client = TestClient(app)
    with patch(
        "deepseek_terminal_agent.dashboard.app._get_settings",
        return_value=make_mock_settings(),
    ):
        resp = client.get("/config-status")

    data = resp.json()
    assert "model" in data
    assert "base_url" in data
    assert "workspace_root" in data
    assert "reasoning_enabled" in data


# ── GET / ─────────────────────────────────────────────────────────────────────


def test_root_returns_200():
    client = TestClient(app)
    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=make_mock_runner()),
    ):
        resp = client.get("/")

    assert resp.status_code == 200
    assert "DeepSeek Terminal Agent Dashboard" in resp.text
    assert "Live Status" in resp.text
    assert "Activity Feed" in resp.text


def test_root_does_not_expose_api_key():
    client = TestClient(app)
    with (
        patch(
            "deepseek_terminal_agent.dashboard.app._get_settings",
            return_value=make_mock_settings(api_key="sk-super-secret-key"),
        ),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=make_mock_runner()),
    ):
        resp = client.get("/")

    assert "sk-super-secret-key" not in resp.text


def test_post_run_prompt_too_long_returns_error():
    client = TestClient(app)
    runner = make_mock_runner()
    runner.create_run.side_effect = ValueError("Prompt too long")

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.post("/runs", json={"prompt": "x" * 101})

    assert resp.status_code == 400
    assert "too long" in resp.text.lower()


def test_post_run_returns_run_id_quickly_with_mocked_runner():
    client = TestClient(app)
    runner = make_mock_runner()

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.post("/runs", json={"prompt": "hello"})

    assert resp.status_code == 202
    assert resp.json()["run_id"] == "testrun001"
    runner.create_run.assert_called_once()


def test_get_run_status_returns_running():
    client = TestClient(app)
    runner = make_mock_runner()

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.get("/runs/testrun001/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    assert resp.json()["current_phase"] == "waiting_model"


def test_get_run_status_returns_succeeded_after_mocked_completion():
    client = TestClient(app)
    runner = make_mock_runner()
    runner.get_status.return_value = {
        **runner.get_status.return_value,
        "status": "succeeded",
        "current_phase": "succeeded",
        "latest_event": "Run completed successfully",
        "finished_at": "2026-04-30T12:00:03+00:00",
        "exit_code": 0,
    }

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.get("/runs/testrun001/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"
    assert resp.json()["exit_code"] == 0


def test_get_runs_returns_json_list():
    client = TestClient(app)
    runner = make_mock_runner()
    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.get("/runs")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["run_id"] == "testrun001"


def test_get_run_events_returns_events_without_reasoning_content():
    client = TestClient(app)
    runner = make_mock_runner()

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.get("/runs/testrun001/events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["events"][0]["type"] == "tool_call"
    assert "reasoning_content" not in resp.text


def test_get_run_output_returns_redacted_output():
    client = TestClient(app)
    runner = make_mock_runner()
    runner.get_output.return_value = {
        **runner.get_output.return_value,
        "output": "api_key=[REDACTED]\n",
        "stdout": "api_key=[REDACTED]\n",
        "stderr": "",
    }

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.get("/runs/testrun001/output")

    assert resp.status_code == 200
    assert "[REDACTED" in resp.text
    assert "sk-" not in resp.text


def test_cancel_endpoint_calls_runner_cancel():
    client = TestClient(app)
    runner = make_mock_runner()

    with (
        patch("deepseek_terminal_agent.dashboard.app._get_settings",
              return_value=make_mock_settings()),
        patch("deepseek_terminal_agent.dashboard.app._get_runner",
              return_value=runner),
    ):
        resp = client.post("/runs/testrun001/cancel")

    assert resp.status_code == 200
    runner.cancel.assert_called_once_with("testrun001")


def test_no_raw_shell_endpoint_exists():
    client = TestClient(app)
    assert client.get("/exec").status_code == 404
    assert client.post("/shell").status_code == 404


def test_dashboard_js_contains_terminal_state_reset_logic():
    project_root = Path(__file__).resolve().parents[1]
    js = (project_root / "src" / "deepseek_terminal_agent" /
          "dashboard" / "static" / "dashboard.js").read_text(encoding="utf-8")

    assert 'TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"]' in js
    assert "setRunControls(false)" in js
