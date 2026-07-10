from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import uvicorn
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from deepseek_terminal_agent.config import DashboardConfig, DeepSeekConfig, Settings
from deepseek_terminal_agent.dashboard import app as dashboard_app
from deepseek_terminal_agent.sessions.arena_runtime_view import (
    ArenaRuntimeViewService,
    classify_exchange_evidence,
)
from deepseek_terminal_agent.sessions.store import SessionStore


def _write_source_and_state(tmp_path: Path) -> tuple[Path, Path]:
    config_path = tmp_path / "p42_dual_agent_mvp.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "agents": {
                    "api_agent_01": {
                        "agent_id": "api_agent_01",
                        "agent_number": 1,
                        "runtime_kind": "api",
                        "symbols": ["ETHUSDT", "SOLUSDT"],
                        "heartbeat_cadence_sec": 10,
                    },
                    "cli_agent_01": {
                        "agent_id": "cli_agent_01",
                        "agent_number": 2,
                        "runtime_kind": "cli",
                        "symbols": ["XRPUSDT", "BNBUSDT"],
                        "heartbeat_cadence_sec": 10,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    now = datetime.now(timezone.utc)
    state_path = tmp_path / "active_dual_agent_session.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": "session-p42",
                "agents": {
                    "api_agent_01": {
                        "status": "active",
                        "last_heartbeat": now.isoformat(),
                        "last_exchange_response": {
                            "status": "exchange_ack",
                            "order_id": "stub-command-1",
                        },
                    },
                    "cli_agent_01": {
                        "status": "degraded",
                        "last_heartbeat": (now - timedelta(minutes=5)).isoformat(),
                        "last_exchange_response": {
                            "status": "shadow_ack",
                            "mode": "shadow",
                        },
                    },
                },
                "shared": {
                    "portfolio_state": {"status": "reported"},
                    "open_orders": [],
                    "open_positions": [],
                    "pending_commands": [],
                    "kill_switch_state": "ARMED",
                    "last_reconciliation": {"status": "complete"},
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path, state_path


def _service(tmp_path: Path) -> ArenaRuntimeViewService:
    config_path, state_path = _write_source_and_state(tmp_path)
    return ArenaRuntimeViewService(
        root_dir=tmp_path,
        config_path=config_path.name,
        state_path=state_path.name,
        environment_label="BINANCE_FUTURES_TESTNET",
        heartbeat_stale_after_sec=30,
    )


def test_default_dashboard_is_localhost_only():
    config = DashboardConfig()
    assert config.host == "127.0.0.1"
    assert config.private_lan_enabled is False
    assert "private-lan" not in config.allowed_hosts


def test_non_loopback_bind_requires_explicit_private_lan():
    with pytest.raises(ValidationError, match="private_lan_enabled"):
        DashboardConfig(host="0.0.0.0")

    config = DashboardConfig(
        host="0.0.0.0",
        private_lan_enabled=True,
        allowed_hosts=["127.0.0.1", "localhost", "testserver", "private-lan"],
        allowed_origins=["http://127.0.0.1:8787", "private-lan"],
    )
    assert config.private_lan_enabled is True


def test_public_bind_is_rejected_even_with_private_lan_flag():
    with pytest.raises(ValidationError, match="public address"):
        DashboardConfig(
            host="8.8.8.8",
            private_lan_enabled=True,
            allowed_hosts=["private-lan"],
            allowed_origins=["private-lan"],
        )


def test_runtime_view_shows_both_agents_ownership_stale_and_evidence(tmp_path):
    view = _service(tmp_path).build()
    assert [agent.agent_id for agent in view.agents] == ["api_agent_01", "cli_agent_01"]
    assert view.shared.symbol_ownership == {
        "ETHUSDT": "api_agent_01",
        "SOLUSDT": "api_agent_01",
        "XRPUSDT": "cli_agent_01",
        "BNBUSDT": "cli_agent_01",
    }
    assert view.agents[0].heartbeat_freshness == "FRESH"
    assert view.agents[0].exchange_evidence == "STUB"
    assert view.agents[1].heartbeat_freshness == "STALE"
    assert view.agents[1].timeout_degraded_state == "DEGRADED_STALE_HEARTBEAT"
    assert view.agents[1].exchange_evidence == "SHADOW"
    assert view.shared.kill_switch_state == "ARMED"
    assert view.shared.exchange_evidence == "SHADOW"


def test_real_external_requires_explicit_external_verification():
    assert classify_exchange_evidence({"status": "exchange_ack"}) == "UNKNOWN"
    assert classify_exchange_evidence({"order_id": "stub-1"}) == "STUB"
    assert classify_exchange_evidence({"mode": "shadow"}) == "SHADOW"
    assert classify_exchange_evidence({"external_verified": True, "order_id": "venue-123"}) == "REAL_EXTERNAL"


def test_arena_api_returns_read_only_runtime_view(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_dashboard_config", DashboardConfig())
    monkeypatch.setattr(dashboard_app, "_arena_runtime_view_service", _service(tmp_path))
    client = TestClient(dashboard_app.app)
    page = client.get("/arena")
    assert page.status_code == 200
    assert "Dual-Agent Runtime" in page.text
    response = client.get("/arena/runtime")
    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert len(payload["agents"]) == 2
    assert payload["agents"][0]["exchange_evidence"] == "STUB"
    assert payload["shared"]["kill_switch_state"] == "ARMED"


def test_private_lan_host_and_origin_are_explicitly_filtered(monkeypatch):
    config = DashboardConfig(
        host="0.0.0.0",
        private_lan_enabled=True,
        allowed_hosts=["127.0.0.1", "localhost", "testserver", "private-lan"],
        allowed_origins=["http://127.0.0.1:8787", "private-lan"],
    )
    monkeypatch.setattr(dashboard_app, "_dashboard_config", config)
    client = TestClient(dashboard_app.app)
    allowed = client.get(
        "/health",
        headers={"host": "192.168.1.20:8787", "origin": "http://192.168.1.10:8787"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://192.168.1.10:8787"
    blocked = client.get("/health", headers={"host": "8.8.8.8:8787"})
    assert blocked.status_code == 400


def test_registered_control_route_records_event_without_exchange(tmp_path, monkeypatch):
    settings = Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(title="P42 controls")
    monkeypatch.setattr(dashboard_app, "_dashboard_config", DashboardConfig())
    monkeypatch.setattr(dashboard_app, "_session_store", store)
    client = TestClient(dashboard_app.app)
    now = datetime.now(timezone.utc).isoformat()
    response = client.post(
        "/arena/commands/pause_agent",
        json={
            "session_id": session.session_id,
            "agent_id": "api_agent_01",
            "agent_number": 1,
            "command_id": "command-pause-1",
            "event_id": "event-pause-1",
            "symbol": "ETHUSDT",
            "created_at": now,
            "rationale": "Operator pause for runtime inspection.",
            "instruction_version": "instructions-v1",
            "collective_state_version": "collective-v2",
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "recorded"
    assert payload["exchange_submitted"] is False
    assert payload["symbol"] == "ETHUSDT"
    assert payload["instruction_version"] == "instructions-v1"
    event = store.list_events(session.session_id)[-1]
    assert event["metadata"]["arena_command"]["command_id"] == "command-pause-1"


def test_no_raw_exchange_or_buy_sell_arena_routes():
    paths = {route.path for route in dashboard_app.app.routes if route.path.startswith("/arena")}
    assert all("exchange" not in path for path in paths)
    assert all("buy" not in path and "sell" not in path for path in paths)
    assert "/arena/commands/{action}" in paths


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.parametrize(
    ("bind_host", "dashboard_config"),
    [
        ("127.0.0.1", DashboardConfig()),
        (
            "0.0.0.0",
            DashboardConfig(
                host="0.0.0.0",
                private_lan_enabled=True,
                allowed_hosts=["127.0.0.1", "localhost", "testserver", "private-lan"],
                allowed_origins=["http://127.0.0.1:8787", "private-lan"],
            ),
        ),
    ],
)
def test_actual_uvicorn_localhost_and_lan_bind_smoke(bind_host, dashboard_config, monkeypatch):
    port = _free_port()
    monkeypatch.setattr(dashboard_app, "_dashboard_config", dashboard_config)
    server = uvicorn.Server(
        uvicorn.Config(dashboard_app.app, host=bind_host, port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        response = None
        for _ in range(40):
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        assert response is not None
        assert response.status_code == 200
        assert response.json()["ok"] is True
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_main_binds_from_validated_dashboard_config(monkeypatch):
    config = DashboardConfig(port=8899)
    monkeypatch.setattr(dashboard_app, "_dashboard_config", config)
    monkeypatch.delenv("DASHBOARD_HOST", raising=False)
    monkeypatch.delenv("DASHBOARD_PORT", raising=False)
    with patch("deepseek_terminal_agent.dashboard.app.uvicorn.run") as run:
        dashboard_app.main()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8899


def test_arena_ui_contains_truth_badges_and_controls():
    root = Path(__file__).resolve().parents[1]
    css = (root / "src/deepseek_terminal_agent/dashboard/static/arena.css").read_text(encoding="utf-8")
    html = (root / "src/deepseek_terminal_agent/dashboard/templates/arena.html").read_text(encoding="utf-8")
    js = (root / "src/deepseek_terminal_agent/dashboard/static/arena.js").read_text(encoding="utf-8")
    for badge in ("REAL_EXTERNAL", "SHADOW", "STUB", "TEST", "BLOCKED", "UNKNOWN"):
        assert badge in css
    for action in (
        "pause_agent",
        "resume_agent",
        "stop_agent",
        "stop_session",
        "trigger_analysis",
        "request_instruction_refresh",
        "emergency_stop",
    ):
        assert action in html
    assert 'setBadge(connection, currentView.blocked_reasons.length ? "BLOCKED" : "TEST")' in js


def test_startup_and_compose_require_explicit_private_lan_exposure():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts/start_dashboard.ps1").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "[switch]$PrivateLan" in script
    assert '$env:DASHBOARD_BIND_ADDRESS = "0.0.0.0"' in script
    assert "-Profile Private" in script
    assert "-LocalPort $Port" in script
    assert "${DASHBOARD_BIND_ADDRESS:-127.0.0.1}" in compose
    assert "${DASHBOARD_PRIVATE_LAN_ENABLED:-false}" in compose
    assert "ngrok" not in script.lower()
    assert "cloudflared" not in script.lower()
