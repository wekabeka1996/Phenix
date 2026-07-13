from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.primitives.position_queries import (
    PositionQueries,
)
from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentIntentAuthoritySnapshotV2,
    AgentTradeIntentV2,
    AgentTradeIntentV2Processor,
    PositionQueriesSizingAdapterV2,
)
from apps.reference.domains.shadow_telemetry.main import create_shadow_telemetry_app
from apps.reference.domains.shadow_telemetry.main_bridge import LLMIntentIngressBridge


NOW = datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc)


def _intent_payload(**updates):
    payload = {
        "contract_version": "2.0",
        "session_id": "session-1",
        "participant_id": "participant-api-1",
        "agent_id": "api_agent_01",
        "symbol": "ETHUSDT",
        "intent_type": "OPEN",
        "side": "BUY",
        "strategy_or_reason": "Thirty minute breakout confirmation",
        "confidence": "0.72",
        "max_position_horizon_sec": 7200,
        "context_version": 7,
        "context_ack_version": 7,
        "evidence_refs": ["evidence-1"],
        "subagent_acknowledgements": ["subagent-review-1"],
        "lease_reference": "lease-1",
        "client_intent_id": "intent-v2-0001",
        "created_at": "2026-07-12T05:59:30+00:00",
    }
    payload.update(updates)
    return payload


def _position_queries(portfolio=None):
    instrument = SimpleNamespace(
        sizing=SimpleNamespace(
            margin_pct=0.10, fee_buffer_fraction="0.001"),
        execution=SimpleNamespace(target_leverage=2),
        step_size=Decimal("0.01"),
        min_qty=Decimal("0.01"),
        min_notional=Decimal("5"),
    )
    config = SimpleNamespace(instruments={"ETHUSDT": instrument})
    return PositionQueries(
        config=config,
        get_portfolio=lambda: portfolio,
        min_pos_size_usd=Decimal("5"),
        liq_cap_usd=Decimal("500"),
        logger=logging.getLogger("test.v2.sizing"),
    )


def _snapshot(**updates):
    values = {
        "session_known": True,
        "session_active": True,
        "participant_known": True,
        "participant_is_main_agent": True,
        "participant_agent_id": "api_agent_01",
        "session_symbols": ["ETHUSDT", "SOLUSDT"],
        "lease_reference": "lease-1",
        "lease_valid": True,
        "current_context_version": 7,
        "required_context_ack_version": 7,
        "max_horizon_sec": 10800,
        "intent_ttl_sec": 300,
        "lifecycle_allows_open": True,
        "portfolio": {"equity": "1000", "positions": []},
        "account_snapshot_ref": "account-1",
        "account_snapshot_at": NOW,
        "account_snapshot_max_age_sec": 15,
        "reference_price": Decimal("2500"),
        "market_snapshot_ref": "market-1",
        "market_snapshot_at": NOW,
        "market_snapshot_max_age_sec": 15,
        "config_version": "config-sha-1",
        "order_type": "LIMIT",
        "time_in_force": "GTC",
        "valid_for_ms": 900000,
        "observed_at": NOW,
    }
    values.update(updates)
    return AgentIntentAuthoritySnapshotV2(**values)


def _processor(snapshot=None, position_queries=None):
    resolved = snapshot or _snapshot()
    return AgentTradeIntentV2Processor(
        authority_provider=lambda intent: resolved,
        sizing_adapter=PositionQueriesSizingAdapterV2(
            position_queries or _position_queries(resolved.portfolio)
        ),
    )


class _FSM:
    def __init__(self):
        self.emitted = []

    def emit(self, name, payload=None, why="", **kwargs):
        self.emitted.append((name, payload or kwargs.get("payload") or {}, why))


def test_valid_contract_and_forbidden_money_fields() -> None:
    intent = AgentTradeIntentV2.model_validate(_intent_payload())
    assert intent.symbol == "ETHUSDT"
    assert not hasattr(intent, "qty")

    for field in (
        "qty",
        "quantity",
        "notional",
        "position_size",
        "leverage",
        "margin",
        "margin_allocation",
        "raw_exchange_params",
        "exchange_order_id",
        "precision",
        "step_size",
    ):
        with pytest.raises(ValidationError):
            AgentTradeIntentV2.model_validate(_intent_payload(**{field: "1"}))


def test_contract_rejects_unsupported_operation_and_missing_identity() -> None:
    with pytest.raises(ValidationError):
        AgentTradeIntentV2.model_validate(_intent_payload(intent_type="CLOSE"))
    with pytest.raises(ValidationError):
        AgentTradeIntentV2.model_validate(_intent_payload(agent_id=""))
    with pytest.raises(ValidationError):
        AgentTradeIntentV2.model_validate(_intent_payload(symbol="ETH/USDT"))


@pytest.mark.parametrize(
    ("snapshot_update", "reason"),
    [
        ({"session_known": False}, "SESSION_UNKNOWN"),
        ({"session_active": False}, "SESSION_INACTIVE"),
        ({"participant_known": False}, "PARTICIPANT_UNKNOWN"),
        ({"participant_is_main_agent": False}, "SUBAGENT_FORBIDDEN"),
        ({"lease_reference": None}, "LEASE_MISSING"),
        ({"lease_valid": False}, "LEASE_INVALID"),
        ({"current_context_version": 8}, "CONTEXT_STALE"),
        ({"max_horizon_sec": 3600}, "HORIZON_EXCEEDED"),
        ({"lifecycle_allows_open": False}, "LIFECYCLE_STATE_REJECTED"),
    ],
)
def test_authority_rejections_emit_no_downstream(snapshot_update, reason) -> None:
    result = _processor(_snapshot(**snapshot_update)).process(
        AgentTradeIntentV2.model_validate(_intent_payload())
    )
    assert result.sizing.approved is False
    assert result.sizing.rejection_reasons == [reason]
    assert result.downstream_command is None


@pytest.mark.parametrize(
    ("snapshot_update", "reason"),
    [
        ({"portfolio": None, "account_snapshot_ref": None}, "ACCOUNT_TRUTH_MISSING"),
        ({"reference_price": None, "market_snapshot_ref": None}, "MARKET_PRICE_MISSING"),
        ({"config_version": None}, "SIZING_CONFIG_MISSING"),
    ],
)
def test_sizing_missing_truth_fails_closed(snapshot_update, reason) -> None:
    snapshot = _snapshot(**snapshot_update)
    result = _processor(snapshot).process(
        AgentTradeIntentV2.model_validate(_intent_payload())
    )
    assert result.sizing.approved is False
    assert reason in result.sizing.rejection_reasons
    assert result.downstream_command is None


def test_sizing_is_deterministic_and_quantity_is_phenix_derived() -> None:
    intent = AgentTradeIntentV2.model_validate(_intent_payload())
    processor = _processor()
    first = processor.process(intent)
    second = processor.process(intent)
    assert first == second
    assert first.sizing.approved is True
    assert first.sizing.derived_quantity == Decimal("0.07")
    assert first.downstream_command["qty"] == "0.07"
    assert first.downstream_command["sizing_decision_id"] == "sizing:intent-v2-0001"


def test_risk_rejection_prevents_downstream_command() -> None:
    snapshot = _snapshot(portfolio={"equity": "0", "positions": []})
    result = _processor(snapshot).process(
        AgentTradeIntentV2.model_validate(_intent_payload())
    )
    assert result.sizing.approved is False
    assert result.downstream_command is None


def _bridge_config(tmp_path: Path):
    target = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), target)
    return ConfigLoader(config_dir=target).load_config()


def test_bridge_emits_exactly_one_existing_execution_command(tmp_path: Path) -> None:
    fsm = _FSM()
    bridge = LLMIntentIngressBridge(
        fsm=fsm,
        config=_bridge_config(tmp_path),
        v2_processor=_processor(),
    )
    bridge._on_command(
        {
            "request_kind": "agent_trade_intent_v2",
            "request_id": "request-1",
            **_intent_payload(),
        }
    )
    commands = [row for row in fsm.emitted if row[0].startswith("CMD:")]
    assert [row[0] for row in commands] == ["CMD:EXTERNAL_OPEN_REQUEST_V1"]
    assert commands[0][1]["qty"] == "0.07"


def test_production_bridge_without_authority_provider_fails_closed(tmp_path: Path) -> None:
    fsm = _FSM()
    bridge = LLMIntentIngressBridge(fsm=fsm, config=_bridge_config(tmp_path))
    bridge._on_command(
        {
            "request_kind": "agent_trade_intent_v2",
            "request_id": "request-1",
            **_intent_payload(),
        }
    )
    assert not [row for row in fsm.emitted if row[0].startswith("CMD:")]
    rejected = [row for row in fsm.emitted if row[0] == "EVT:AGENT_TRADE_INTENT_V2_REJECTED"]
    assert rejected[-1][1]["reason_code"] == "SIZING_AUTHORITY_UNAVAILABLE"


def test_v2_http_uses_existing_ipc_queue_without_fsm_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _bridge_config(tmp_path)

    class NoopServer:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    class CapturingClient(NoopServer):
        last = None

        def __init__(self, *args, **kwargs):
            self.enqueued = []
            CapturingClient.last = self

        def enqueue(self, payload):
            self.enqueued.append(payload)
            return True

        def queue_depth(self):
            return 0

    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main.JsonlTcpServer", NoopServer
    )
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient",
        CapturingClient,
    )
    monkeypatch.setattr(
        "apps.reference.domains.shadow_telemetry.main._probe_ipc_endpoint",
        lambda endpoint: True,
    )
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "test-v2-token")
    app = create_shadow_telemetry_app(config)
    with TestClient(app) as client:
        response = client.post(
            "/intents/llm/v2",
            json=_intent_payload(),
            headers={"Authorization": "Bearer test-v2-token"},
        )
        duplicate = client.post(
            "/intents/llm/v2",
            json=_intent_payload(),
            headers={"Authorization": "Bearer test-v2-token"},
        )
        conflict = client.post(
            "/intents/llm/v2",
            json=_intent_payload(side="SELL"),
            headers={"Authorization": "Bearer test-v2-token"},
        )
    assert response.status_code == 202
    assert duplicate.status_code == 202
    assert conflict.status_code == 409
    assert duplicate.json() == response.json()
    assert len(CapturingClient.last.enqueued) == 1
    assert CapturingClient.last.enqueued[0]["request_kind"] == "agent_trade_intent_v2"
    assert "qty" not in CapturingClient.last.enqueued[0]
    assert not hasattr(app.state, "fsm_ref")
