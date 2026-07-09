"""Repeatable integrated Cockpit smoke test for session creation, attachments, and context integration."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

DUMMY_API_KEY = "dummy-p34b-integrated-smoke-not-secret"


def find_free_port() -> int:
    """Find a random free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_integrated_cockpit_smoke():
    """Verify session creation, attachment APIs, and bounded context integration in the merged branch."""
    test_dir = Path(__file__).resolve().parent
    agent_root = test_dir.parent
    src_dir = agent_root / "src"
    config_src = agent_root / "config"

    # Setup isolated temp directory CWD
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        shutil.copytree(config_src, temp_path / "config")

        # Write dummy .env config
        (temp_path / ".env").write_text(
            "DEEPSEEK_API_KEY=dummy-p34b-integrated-smoke-not-secret\n"
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

        print(f"\nStarting integrated Cockpit dashboard on port {port}...")
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

        # Poll health endpoint until healthy
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
            assert started, "FastAPI server did not become healthy within 15 seconds."
            print("Dashboard server started successfully.")

            # 1. Validate GET /chat
            print("Verifying GET /chat...")
            chat_resp = httpx.get(chat_url, timeout=3.0)
            assert chat_resp.status_code == 200
            assert "DeepSeek" in chat_resp.text or "Agent OS cockpit" in chat_resp.text

            # 2. Validate POST /chat/sessions (Session Creation)
            print("Verifying POST /chat/sessions...")
            session_title = "P34B Integrated Smoke Session"
            post_sess_resp = httpx.post(
                sessions_url,
                json={"title": session_title},
                timeout=3.0,
            )
            assert post_sess_resp.status_code == 201
            session_data = post_sess_resp.json()
            session_id = session_data["session"]["session_id"]
            assert session_id

            # 3. Validate GET /chat/sessions
            print("Verifying GET /chat/sessions...")
            list_sess_resp = httpx.get(sessions_url, timeout=3.0)
            assert list_sess_resp.status_code == 200
            sessions_list = list_sess_resp.json()
            session_ids = [s["session_id"] for s in sessions_list]
            assert session_id in session_ids

            # 4. Validate POST /chat/sessions/{session_id}/attachments (Attachment creation)
            print(f"Verifying POST /chat/sessions/{session_id}/attachments...")
            attach_payload = {
                "kind": "market_screenshot",
                "raw_ref": "file://screenshots/btc-vwap.png",
                "summary": "BTC compression range near 95k VWAP",
                "source_refs": ["operator-upload://btc-vwap"],
                "include_in_prompt": True,
            }
            post_attach_resp = httpx.post(
                f"{sessions_url}/{session_id}/attachments",
                json=attach_payload,
                timeout=3.0,
            )
            assert post_attach_resp.status_code == 201
            attach_data = post_attach_resp.json()
            attachment_id = attach_data["attachment_id"]
            assert attachment_id

            # 5. Validate POST /chat/sessions/{session_id}/attachments fails on raw binary keys (Rejection)
            print("Verifying rejection of raw binary fields...")
            forbidden_payload = {
                "kind": "market_screenshot",
                "summary": "Forbidden raw bytes",
                "raw_bytes": "base64_data_here...",
            }
            post_forbid_resp = httpx.post(
                f"{sessions_url}/{session_id}/attachments",
                json=forbidden_payload,
                timeout=3.0,
            )
            assert post_forbid_resp.status_code == 400
            assert "Raw attachment bytes are not accepted" in post_forbid_resp.json().get("error", "")

            # 6. Validate GET /chat/sessions/{session_id}/attachments (Attachment listing)
            print("Verifying listing attachments...")
            list_attach_resp = httpx.get(
                f"{sessions_url}/{session_id}/attachments",
                timeout=3.0,
            )
            assert list_attach_resp.status_code == 200
            attachments_list = list_attach_resp.json()["attachments"]
            attachment_ids = [a["attachment_id"] for a in attachments_list]
            assert attachment_id in attachment_ids

            # 7. Validate GET /chat/attachments/{attachment_id} (Attachment details)
            print(f"Verifying GET /chat/attachments/{attachment_id}...")
            detail_resp = httpx.get(
                f"{base_url}/chat/attachments/{attachment_id}",
                timeout=3.0,
            )
            assert detail_resp.status_code == 200
            assert detail_resp.json()["summary"] == "BTC compression range near 95k VWAP"

            # 8. Validate bounded context integration (GET /chat/sessions/{session_id}/context)
            print("Verifying context inspection contains bounded summary...")
            context_resp = httpx.post(
                f"{sessions_url}/{session_id}/context",
                json={"current_user_message": "integrated test message"},
                timeout=3.0,
            )
            assert context_resp.status_code == 200
            context_data = context_resp.json()
            assert "attachments" in context_data["context_report"]["included_sections"]
            # Ensure the raw screenshot reference does not leak base64, only summary/refs
            context_pack = context_data["context_pack"]
            assert "BTC compression range near 95k VWAP" in context_pack
            assert "operator-upload://btc-vwap" in context_pack

            # 9. Verify missing P33 endpoint behavior (fail-closed check)
            print("Verifying missing P33 endpoint status...")
            p33_url = f"{sessions_url}/{session_id}/session-context"
            p33_resp = httpx.get(p33_url, timeout=3.0)
            print(f"P33 GET status: {p33_resp.status_code}")
            # Should be 404 since P33 endpoint is not present in app.py
            assert p33_resp.status_code == 404

            # 10. Verify Proposal Ledger API (POST/GET/List)
            print("Verifying Proposal Ledger API...")
            prop_payload = {
                "agent_id": "integrated-agent-1",
                "agent_number": 2,
                "kind": "analysis_note",
                "rationale": "Strong order book imbalance support.",
                "source_refs": ["ob-imbalance"],
                "payload": {"ratio": 1.45},
            }
            post_prop_resp = httpx.post(
                f"{sessions_url}/{session_id}/agent-proposals",
                json=prop_payload,
                timeout=3.0,
            )
            assert post_prop_resp.status_code == 201
            proposal_id = post_prop_resp.json()["proposal_id"]
            assert proposal_id

            list_prop_resp = httpx.get(
                f"{sessions_url}/{session_id}/agent-proposals",
                timeout=3.0,
            )
            assert list_prop_resp.status_code == 200
            proposals = list_prop_resp.json()["agent_proposals"]
            proposal_ids = [p["proposal_id"] for p in proposals]
            assert proposal_id in proposal_ids

            detail_prop_resp = httpx.get(
                f"{base_url}/chat/agent-proposals/{proposal_id}",
                timeout=3.0,
            )
            assert detail_prop_resp.status_code == 200
            assert detail_prop_resp.json()["rationale"] == "Strong order book imbalance support."

            # 11. Verify Forbidden Proposal Fields are Rejected
            print("Verifying Forbidden Proposal Fields Rejection...")
            forbidden_prop_payload = {
                "agent_id": "integrated-agent-1",
                "agent_number": 2,
                "kind": "analysis_note",
                "rationale": "Attempting forbidden sizing",
                "payload": {"sizing": 1000},
            }
            post_forbid_prop_resp = httpx.post(
                f"{sessions_url}/{session_id}/agent-proposals",
                json=forbidden_prop_payload,
                timeout=3.0,
            )
            assert post_forbid_prop_resp.status_code == 400
            assert "Forbidden proposal field" in post_forbid_prop_resp.json()["error"]

        finally:
            print("Cleaning up server subprocess...")
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            
            print("\n--- Subprocess Server Stdout ---")
            print(stdout)
            print("--- Subprocess Server Stderr ---")
            print(stderr)

    print("Integrated Cockpit smoke validation complete.")
