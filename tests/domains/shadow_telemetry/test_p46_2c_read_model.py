from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.shadow_telemetry.main import create_shadow_telemetry_app
from apps.reference.domains.shadow_telemetry.read_model_contract import (
    ContextItemProjection,
    ContextSourceSnapshot,
    LifecycleItemProjection,
    LifecycleSourceSnapshot,
)
from apps.reference.domains.shadow_telemetry.read_model_service import PhenixReadModelService
from apps.reference.domains.shadow_telemetry.trading_session_authority import (
    Participant,
    SymbolLease,
    TradingSession,
    TradingSessionAuthorityStore,
)


ROOT = Path(__file__).resolve().parents[3]
BASE_TIME = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self) -> None:
        self.value = BASE_TIME

    def __call__(self) -> datetime:
        return self.value


class NoopServer:
    def __init__(self, *args, **kwargs) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False


class NoopClient(NoopServer):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.enqueued: list[dict] = []

    def probe_endpoint(self):
        return None

    def queue_depth(self) -> int:
        return 0

    def enqueue(self, payload) -> bool:
        self.enqueued.append(payload)
        return True


def fixture() -> tuple[object, MutableClock, TradingSessionAuthorityStore, PhenixReadModelService]:
    config = ConfigLoader(config_dir=ROOT / "config" / "aurora").load_config()
    clock = MutableClock()
    authority = TradingSessionAuthorityStore(config.domains.shadow_telemetry.agent_authority, clock)
    policy = config.domains.shadow_telemetry.agent_authority
    authority.create_session(TradingSession(
        session_id="session-p46-2c",
        status="ACTIVE",
        created_at=clock(),
        started_at=clock(),
        expires_at=clock() + timedelta(hours=4),
        instrument_universe=["ETHUSDT", "SOLUSDT"],
        participants=[],
        config_version=policy.config_version,
        instruction_version="instructions-v7",
    ))
    for participant_id, agent_id, role in (
        ("participant-main", "api_agent_01", "MAIN_AGENT"),
        ("participant-sub", "subagent_01", "SUBAGENT"),
    ):
        authority.register_participant(Participant(
            participant_id=participant_id,
            agent_id=agent_id,
            participant_type=role,
            enabled=True,
            session_id="session-p46-2c",
        ))
    authority.acquire_lease(SymbolLease(
        lease_id="lease-expiring",
        session_id="session-p46-2c",
        symbol="ETHUSDT",
        owner_participant_id="participant-main",
        acquired_at=clock(),
        expires_at=clock() + timedelta(seconds=policy.lease_ttl_sec),
        version=1,
    ))
    clock.value += timedelta(seconds=100)
    authority.acquire_lease(SymbolLease(
        lease_id="lease-active",
        session_id="session-p46-2c",
        symbol="SOLUSDT",
        owner_participant_id="participant-main",
        acquired_at=clock(),
        expires_at=clock() + timedelta(seconds=policy.lease_ttl_sec),
        version=1,
    ))
    clock.value += timedelta(seconds=201)
    source_now = clock()

    def context_reader(session_id: str) -> ContextSourceSnapshot:
        assert session_id == "session-p46-2c"
        return ContextSourceSnapshot(
            manifest_version="manifest-v9",
            previous_manifest_version="manifest-v8",
            content_hash="sha256:context-v9",
            instruction_version="instructions-v7",
            created_at=source_now - timedelta(seconds=5),
            stale_after=source_now + timedelta(seconds=295),
            critical_items=(ContextItemProjection(
                item_id="risk-1", kind="risk_warning", summary="Exposure warning remains unresolved",
                created_at=source_now - timedelta(seconds=5), source_references=("memory://event/risk-1",),
            ),),
            unresolved_items=(),
            checkpoint_identity="checkpoint-9",
            carryover_identity="carryover-9",
            source_references=("memory://checkpoint/9", "memory://event/risk-1"),
        )

    def lifecycle_reader(session_id: str) -> LifecycleSourceSnapshot:
        assert session_id == "session-p46-2c"
        return LifecycleSourceSnapshot(
            positions=(LifecycleItemProjection(
                item_id="position-1", symbol="SOLUSDT", state="OPEN", side="BUY", quantity="1",
                updated_at=source_now - timedelta(seconds=2), source_reference="fsm://position/1",
            ),),
            open_orders=(LifecycleItemProjection(
                item_id="order-1", symbol="SOLUSDT", state="NEW", side="SELL", quantity="1",
                updated_at=source_now - timedelta(seconds=1), source_reference="fsm://order/1",
            ),),
            pending_commands=(), pending_intents=(),
            latest_fsm_decisions=(LifecycleItemProjection(
                item_id="decision-1", symbol="SOLUSDT", state="ACCEPTED",
                updated_at=source_now - timedelta(seconds=1), source_reference="fsm://decision/1",
            ),),
            reconciliation_state="DIVERGED",
            reconciliation_divergence=True,
            last_reconciled_at=source_now - timedelta(seconds=3),
            source_kind="EXEC_POS_FSM_RECONCILIATION",
            source_references=("fsm://reconciliation/latest",),
        )

    service = PhenixReadModelService(
        authority=authority,
        context_reader=context_reader,
        lifecycle_reader=lifecycle_reader,
        policy=config.domains.shadow_telemetry.api.read_model,
        clock=clock,
    )
    return config, clock, authority, service


def test_service_projects_authority_deterministically_without_mutation() -> None:
    _, _, authority, service = fixture()
    decisions_before = authority.decisions()
    first = service.snapshot("session-p46-2c")
    second = service.snapshot("session-p46-2c")
    assert first == second
    assert first.data_version == second.data_version
    assert [item.participant_id for item in first.participants] == ["participant-main", "participant-sub"]
    assert [(item.symbol, item.lease_state) for item in first.leases] == [("ETHUSDT", "EXPIRED"), ("SOLUSDT", "ACTIVE")]
    assert first.context.manifest_version == "manifest-v9"
    assert first.context.source_references == ("memory://checkpoint/9", "memory://event/risk-1")
    assert first.lifecycle.reconciliation_divergence is True
    assert first.lifecycle.positions[0].item_id == "position-1"
    assert authority.decisions() == decisions_before


def test_stale_context_and_missing_session_are_explicit() -> None:
    _, clock, _, service = fixture()
    clock.value += timedelta(minutes=10)
    snapshot = service.snapshot("session-p46-2c")
    assert snapshot.context.freshness_state == "STALE"
    assert snapshot.freshness_state == "STALE"
    with pytest.raises(RuntimeError, match="SESSION_NOT_FOUND"):
        service.snapshot("missing")


def test_authenticated_get_only_http_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    config, _, authority, service = fixture()
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "p46-2c-test-token")
    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpServer", NoopServer)
    clients: list[NoopClient] = []

    def client_factory(*args, **kwargs):
        client = NoopClient()
        clients.append(client)
        return client

    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient", client_factory)
    app = create_shadow_telemetry_app(config, read_model_service=service)
    app.state.auth_mode = "bearer"
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer p46-2c-test-token"}
        health = client.get("/read-model/v1/health", headers=headers)
        assert health.status_code == 200
        assert health.json()["authority_available"] is True
        aggregate = client.get("/read-model/v1/sessions/session-p46-2c", headers=headers)
        assert aggregate.status_code == 200
        assert aggregate.json()["schema_version"] == "p46.read-model.v1"
        assert aggregate.json()["session_id"] == "session-p46-2c"
        for suffix in ("participants", "leases", "context", "lifecycle"):
            focused = client.get(f"/read-model/v1/sessions/session-p46-2c/{suffix}", headers=headers)
            assert focused.status_code == 200
            assert suffix in focused.json()
        assert client.get("/read-model/v1/sessions/session-p46-2c").status_code == 401
        assert client.get("/read-model/v1/sessions/session-p46-2c", headers={"Authorization": "Bearer wrong"}).status_code == 403
        assert client.get("/read-model/v1/sessions/missing", headers=headers).status_code == 404
        assert client.post("/read-model/v1/sessions/session-p46-2c", headers=headers, json={}).status_code == 405
    assert authority.decisions() == []
    assert all(item.enqueued == [] for item in clients)
