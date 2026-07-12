from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.shadow_telemetry.main import (
    _authorize_or_reject,
    create_shadow_telemetry_app,
)


CONFIG_DIR = Path("config/aurora")


class _NoopServer:
    def __init__(self, *args, **kwargs) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False


class _NoopClient:
    def __init__(self, *args, **kwargs) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def probe(self, timeout_sec: float = 0.25) -> bool:
        return True

    def queue_depth(self) -> int:
        return 0

    def enqueue(self, payload) -> None:
        return None


class _CapturingClient(_NoopClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.enqueued_payloads: list[dict] = []

    def enqueue(self, payload) -> bool:
        self.enqueued_payloads.append(payload)
        return True


def _copy_config(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _set_shadow_auth_mode(cfg_dir: Path, auth_mode: str) -> None:
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["api"]["auth_mode"] = auth_mode
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _enable_legacy_execution_routes(cfg_dir: Path) -> None:
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["api"]["write"]["legacy_execution_routes_enabled"] = True
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def test_shadow_api_starts_without_bearer_token_in_loopback_optional_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_dir = _copy_config(tmp_path)
    _set_shadow_auth_mode(cfg_dir, "loopback_optional_bearer")
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    monkeypatch.delenv("SHADOW_TELEMETRY_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("SHADOW_TELEMETRY_BEARER_TOKENS", raising=False)
    monkeypatch.delenv("AURORA_SHADOW_TELEMETRY_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main.JsonlTcpServer",
        _NoopServer,
    )
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient",
        _NoopClient,
    )

    app = create_shadow_telemetry_app(config)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200


def test_loopback_optional_auth_allows_missing_bearer_for_loopback_request() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            auth_mode="loopback_optional_bearer",
            auth_tokens=set(),
            snapshot_store=SimpleNamespace(ingest_event=lambda frame: None),
        )
    )
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    subject = _authorize_or_reject(app, "req-1", request, None)

    assert subject == "loopback:noauth"


def test_loopback_optional_auth_still_rejects_missing_bearer_for_non_loopback_request() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            auth_mode="loopback_optional_bearer",
            auth_tokens={"known-token"},
            snapshot_store=SimpleNamespace(ingest_event=lambda frame: None),
        )
    )
    request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"))

    with pytest.raises(HTTPException) as exc_info:
        _authorize_or_reject(app, "req-2", request, None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["reason_code"] == "AUTH_MISSING"


def test_eze_direct_open_route_accepts_symbol_outside_guarded_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_dir = _copy_config(tmp_path)
    _set_shadow_auth_mode(cfg_dir, "loopback_optional_bearer")
    _enable_legacy_execution_routes(cfg_dir)
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    holder: dict[str, _CapturingClient] = {}

    def _client_factory(*args, **kwargs) -> _CapturingClient:
        client = _CapturingClient(*args, **kwargs)
        holder["client"] = client
        return client

    monkeypatch.setenv("AURORA_SHADOW_TELEMETRY_BEARER_TOKEN", "eze-test-token")
    monkeypatch.delenv("SHADOW_TELEMETRY_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("SHADOW_TELEMETRY_BEARER_TOKENS", raising=False)
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main.JsonlTcpServer",
        _NoopServer,
    )
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient",
        _client_factory,
    )
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main._probe_ipc_endpoint",
        lambda endpoint: True,
    )

    app = create_shadow_telemetry_app(config)
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order": {
            "type": "LIMIT",
            "limit_price": "100.0",
            "qty": "0.2",
            "time_in_force": "GTC",
        },
        "brackets": {
            "tp_price": "101.0",
            "sl_price": "99.0",
        },
        "snapshot_ref": {
            "snapshot_id": "snap-eze-1",
            "inputs_digest": "digest-eze-1234",
        },
        "why_short": "direct execution test",
        "idempotency_key": "idem-eze-open-1234",
    }

    with TestClient(app) as client:
        response = client.post(
            "/execution/eze/intents/v1",
            json=payload,
            headers={"Authorization": "Bearer eze-test-token"},
        )

    assert response.status_code == 202
    assert holder["client"].enqueued_payloads[0]["request_kind"] == "eze_open"
    assert holder["client"].enqueued_payloads[0]["symbol"] == "BTCUSDT"
