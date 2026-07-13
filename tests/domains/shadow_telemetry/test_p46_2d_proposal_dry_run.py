from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries
from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentIntentAuthoritySnapshotV2,
    PositionQueriesSizingAdapterV2,
)
from apps.reference.domains.shadow_telemetry.main import create_shadow_telemetry_app
from apps.reference.domains.shadow_telemetry.proposal_dry_run import (
    CockpitTradeProposal,
    ExposurePreviewDecision,
    ProposalDryRunAuthoritySnapshot,
    ProposalDryRunService,
    ProposalValidationError,
    proposal_to_agent_trade_intent_v2,
    validate_proposal_payload,
)
from apps.reference.domains.shadow_telemetry.trading_session_authority import (
    Participant,
    SymbolLease,
    TradingSession,
    TradingSessionAuthorityStore,
)
from tests.domains.shadow_telemetry.test_p46_2c_read_model import NoopClient, NoopServer, ROOT


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


class Clock:
    value = NOW

    def __call__(self):
        return self.value


def proposal(**updates) -> CockpitTradeProposal:
    values = {
        "schema_version": "p46.trade-proposal.v1", "proposal_id": "proposal-p46-2d-0001",
        "cockpit_session_id": "cockpit-p46-2d", "phenix_session_id": "phenix-p46-2d",
        "binding_id": "binding-p46-2d", "proposer_id": "operator-1", "proposer_role": "OPERATOR",
        "participant_id": "participant-main", "intent_kind": "OPEN", "symbol": "DOGEUSDT",
        "side": "BUY", "entry_preference": "CURRENT_MARKET", "rationale_summary": "bounded proof proposal",
        "confidence": "0.75", "horizon_sec": 1800, "context_manifest_version": "manifest-v9",
        "instruction_version": "instructions-v7", "lease_id": "lease-doge", "lease_version": 1,
        "created_at": NOW, "expires_at": NOW + timedelta(minutes=5),
    }
    values.update(updates)
    return CockpitTradeProposal.model_validate(values)


def fixture():
    config = ConfigLoader(config_dir=ROOT / "config" / "aurora").load_config()
    clock = Clock()
    authority = TradingSessionAuthorityStore(config.domains.shadow_telemetry.agent_authority, clock)
    authority.create_session(TradingSession(
        session_id="phenix-p46-2d", status="ACTIVE", created_at=NOW, started_at=NOW,
        expires_at=NOW + timedelta(hours=4), instrument_universe=["DOGEUSDT"], participants=[],
        config_version=config.domains.shadow_telemetry.agent_authority.config_version,
        instruction_version="instructions-v7",
    ))
    authority.register_participant(Participant(
        participant_id="participant-main", agent_id="api-agent-1", participant_type="MAIN_AGENT",
        enabled=True, session_id="phenix-p46-2d",
    ))
    authority.acquire_lease(SymbolLease(
        lease_id="lease-doge", session_id="phenix-p46-2d", symbol="DOGEUSDT",
        owner_participant_id="participant-main", acquired_at=NOW,
        expires_at=NOW + timedelta(seconds=config.domains.shadow_telemetry.agent_authority.lease_ttl_sec), version=1,
    ))
    portfolio = {"equity": "1000", "positions": []}
    queries = PositionQueries(config, lambda: portfolio, Decimal("5"), Decimal("20"), logging.getLogger("p46-2d"))
    snapshot = ProposalDryRunAuthoritySnapshot(
        v2=AgentIntentAuthoritySnapshotV2(
            session_known=True, session_active=True, participant_known=True, participant_is_main_agent=True,
            participant_agent_id="api-agent-1", session_symbols=["DOGEUSDT"], lease_reference="lease-doge",
            lease_valid=True, current_context_version=9, required_context_ack_version=9, max_horizon_sec=3600,
            intent_ttl_sec=300, lifecycle_allows_open=True, portfolio=portfolio,
            account_snapshot_ref="account://snapshot/1", account_snapshot_at=NOW, account_snapshot_max_age_sec=30,
            reference_price=Decimal("0.1"), market_snapshot_ref="market://snapshot/1", market_snapshot_at=NOW,
            market_snapshot_max_age_sec=30, config_version=config.domains.shadow_telemetry.agent_authority.config_version,
            order_type="LIMIT", time_in_force="GTC", valid_for_ms=5000, observed_at=NOW,
        ),
        context_manifest_version="manifest-v9", instruction_version="instructions-v7", lease_version=1,
        source_references=("memory://manifest/9", "authority://lease/lease-doge"),
    )
    exposure_calls = []

    def exposure_preview(item, qty, notional, source):
        exposure_calls.append((item.proposal_id, qty, notional))
        return ExposurePreviewDecision(exposure_decision_id=f"exposure:{item.proposal_id}", approved=True, reason_codes=())

    service = ProposalDryRunService(
        authority=authority, snapshot_reader=lambda _: snapshot,
        sizing_adapter=PositionQueriesSizingAdapterV2(queries), exposure_preview=exposure_preview, clock=clock,
    )
    return config, clock, authority, service, exposure_calls


def test_contract_rejects_money_fields_recursively_and_expiry() -> None:
    payload = proposal().model_dump(mode="json")
    for field in ("qty", "quantity", "notional", "leverage", "margin", "position_size"):
        with pytest.raises(ProposalValidationError, match="PROPOSAL_FORBIDDEN_FIELD"):
            validate_proposal_payload({**payload, field: "1"})
    with pytest.raises(ProposalValidationError, match="PROPOSAL_FORBIDDEN_FIELD"):
        validate_proposal_payload({**payload, "metadata": {"raw_exchange_params": {"x": 1}}})
    with pytest.raises(ProposalValidationError, match="PROPOSAL_EXPIRED"):
        validate_proposal_payload({**payload, "expires_at": payload["created_at"]})


def test_accepted_dry_run_is_deterministic_idempotent_and_has_zero_effects() -> None:
    _, _, authority, service, exposure_calls = fixture()
    decisions_before = authority.decisions()
    first = service.evaluate(proposal())
    second = service.evaluate(proposal())
    assert first == second
    assert first.decision == "ACCEPTED"
    assert first.derived_quantity is not None and first.derived_notional is not None
    assert first.execution_state == "DRY_RUN_ONLY"
    assert first.side_effects.model_dump() == {
        "session_mutations": 0, "lease_mutations": 0, "exposure_reservations": 0,
        "command_emissions": 0, "fsm_calls": 0, "adapter_calls": 0, "exchange_calls": 0,
    }
    assert len(exposure_calls) == 1
    assert authority.decisions() == decisions_before
    assert service.evaluate(proposal(side="SELL")).decision == "CONFLICT"


def test_explicit_v2_mapper_preserves_identity_and_cannot_carry_money_fields() -> None:
    _, _, _, service, _ = fixture()
    item = proposal()
    source = service.snapshot_reader(item)
    intent = proposal_to_agent_trade_intent_v2(item, agent_id="api-agent-1", source=source)
    payload = intent.model_dump(mode="json")
    assert payload["session_id"] == item.phenix_session_id
    assert payload["client_intent_id"] == item.proposal_id
    assert payload["lease_reference"] == item.lease_id
    assert payload["strategy_or_reason"] == item.rationale_summary
    assert not ({"qty", "quantity", "notional", "leverage", "margin"} & set(payload))


@pytest.mark.parametrize(("update", "reason"), [
    ({"lease_version": 2}, "LEASE_VERSION_MISMATCH"),
    ({"context_manifest_version": "manifest-old"}, "CONTEXT_VERSION_MISMATCH"),
    ({"instruction_version": "instructions-old"}, "INSTRUCTION_VERSION_MISMATCH"),
])
def test_version_mismatch_is_stale_and_never_sizes(update, reason) -> None:
    _, _, _, service, exposure_calls = fixture()
    result = service.evaluate(proposal(**update))
    assert result.decision == "STALE"
    assert result.reason_codes == (reason,)
    assert result.derived_quantity is None
    assert exposure_calls == []


def test_authenticated_http_route_is_idempotent_and_not_a_command_route(monkeypatch) -> None:
    config, _, authority, service, _ = fixture()
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "p46-2d-test-token")
    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpServer", NoopServer)
    clients = []

    def factory(*args, **kwargs):
        client = NoopClient()
        clients.append(client)
        return client

    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient", factory)
    app = create_shadow_telemetry_app(config, proposal_dry_run_service=service)
    app.state.auth_mode = "bearer"
    headers = {"Authorization": "Bearer p46-2d-test-token"}
    payload = proposal().model_dump(mode="json")
    with TestClient(app) as client:
        assert client.post("/proposal-dry-run/v1/sessions/phenix-p46-2d", json=payload).status_code == 401
        first = client.post("/proposal-dry-run/v1/sessions/phenix-p46-2d", headers=headers, json=payload)
        second = client.post("/proposal-dry-run/v1/sessions/phenix-p46-2d", headers=headers, json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert client.get(f"/proposal-dry-run/v1/results/{payload['proposal_id']}", headers=headers).status_code == 200
        assert client.put("/proposal-dry-run/v1/sessions/phenix-p46-2d", headers=headers, json=payload).status_code == 405
    assert authority.decisions() == []
    assert all(item.enqueued == [] for item in clients)


def test_uncomposed_authority_fails_typed_without_fixture_fallback(monkeypatch) -> None:
    config, _, _, _, _ = fixture()
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "p46-2d-test-token")
    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpServer", NoopServer)
    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient", NoopClient)
    app = create_shadow_telemetry_app(config)
    app.state.auth_mode = "bearer"
    with TestClient(app) as client:
        response = client.post(
            "/proposal-dry-run/v1/sessions/phenix-p46-2d",
            headers={"Authorization": "Bearer p46-2d-test-token"},
            json=proposal().model_dump(mode="json"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "DRY_RUN_AUTHORITY_UNAVAILABLE"
