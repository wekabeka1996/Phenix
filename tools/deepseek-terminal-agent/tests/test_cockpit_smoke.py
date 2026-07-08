"""Repeatable safe smoke test for Cockpit chat session creation."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

DUMMY_API_KEY = "dummy-p31b-cockpit-smoke-not-secret"


@dataclass(frozen=True)
class AutomationStatus:
    playwright: str
    selenium: str
    httpx: str
    requests: str


def _module_status(module_name: str) -> str:
    try:
        __import__(module_name)
    except Exception as exc:
        return f"missing:{type(exc).__name__}"
    return "available"


def inspect_automation() -> AutomationStatus:
    return AutomationStatus(
        playwright=_module_status("playwright"),
        selenium=_module_status("selenium"),
        httpx=_module_status("httpx"),
        requests=_module_status("requests"),
    )


def find_free_port() -> int:
    """Find a random free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cockpit_session_creation_smoke():
    """Start dashboard on an isolated port and create a session without LLM calls."""
    automation = inspect_automation()
    print(f"automation={automation}")

    test_dir = Path(__file__).resolve().parent
    agent_root = test_dir.parent
    src_dir = agent_root / "src"
    config_src = agent_root / "config"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        shutil.copytree(config_src, temp_path / "config")

        (temp_path / ".env").write_text(
            "DEEPSEEK_API_KEY=dummy-p31b-cockpit-smoke-not-secret\n"
            "DEEPSEEK_MODEL=deepseek-v4-pro\n"
            "DASHBOARD_HOST=127.0.0.1\n"
            "AGENT_WORKSPACE=/workspace/project\n"
            "MODELS_REFRESH_ON_STARTUP=false\n",
            encoding="utf-8",
        )

        port = find_free_port()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(src_dir)
        env["DEEPSEEK_API_KEY"] = DUMMY_API_KEY
        env["DASHBOARD_HOST"] = "127.0.0.1"
        env["DASHBOARD_PORT"] = str(port)

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "deepseek_terminal_agent.dashboard.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ]

        process = subprocess.Popen(
            cmd,
            cwd=temp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        base_url = f"http://127.0.0.1:{port}"
        health_url = f"{base_url}/health"
        chat_url = f"{base_url}/chat"
        sessions_url = f"{base_url}/chat/sessions"

        started = False
        for _ in range(30):
            time.sleep(0.5)
            try:
                resp = httpx.get(health_url, timeout=1.0)
                if resp.status_code == 200 and resp.json().get("ok") is True:
                    started = True
                    break
            except httpx.HTTPError:
                pass

        try:
            assert started, _server_output(process)

            chat_resp = httpx.get(chat_url, timeout=3.0)
            assert chat_resp.status_code == 200
            assert 'id="new-session-btn"' in chat_resp.text
            assert "/static/chat.js" in chat_resp.text

            initial_resp = httpx.get(sessions_url, timeout=3.0)
            assert initial_resp.status_code == 200
            assert initial_resp.json() == []

            post_resp = httpx.post(
                sessions_url,
                json={"title": "P31B Smoke Test Chat Session"},
                timeout=3.0,
            )
            assert post_resp.status_code == 201
            session_data = post_resp.json()
            session_id = session_data["session"]["session_id"]
            assert session_id

            list_resp = httpx.get(sessions_url, timeout=3.0)
            assert list_resp.status_code == 200
            sessions_list = list_resp.json()
            session_ids = [s["session_id"] for s in sessions_list]
            assert session_id in session_ids

            expected_session_dir = temp_path / ".agent_memory" / "sessions" / session_id
            expected_state_file = expected_session_dir / "session.dsstate.json"
            assert expected_session_dir.exists()
            assert expected_state_file.exists()

            state_data = expected_state_file.read_text(encoding="utf-8")
            assert session_id in state_data
            assert "P31B Smoke Test Chat Session" in state_data

        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def _server_output(process: subprocess.Popen[str]) -> str:
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    return "\n".join(
        [
            "FastAPI dashboard did not become healthy within 15 seconds.",
            "--- stdout ---",
            stdout or "",
            "--- stderr ---",
            stderr or "",
        ]
    )
