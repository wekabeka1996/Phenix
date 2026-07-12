from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from tests.domains.shadow_telemetry.p46_1f_runtime_harness import P46RuntimeHarness
from vfoundation.core.fsm_core import InvalidMessagePayloadError
from vfoundation.core.schema_registry import VerbSchemaRegistry, get_global_registry


@pytest.fixture
def runtime_harness(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    harness = P46RuntimeHarness(tmp_path / "runtime", monkeypatch).start()
    try:
        yield harness
    finally:
        harness.stop()


def test_valid_http_tcp_path_reaches_exactly_one_real_fsm(runtime_harness) -> None:
    harness = runtime_harness
    response = harness.post(harness.payload())
    assert response.status_code == 202
    harness.wait_for(lambda: len(harness.fsm_results) == 1)

    assert harness.bridge.command_envelope_count == 1
    assert harness.bridge.v2_handler_count == 1
    assert len(harness.command_emissions) == 1
    assert len(harness.bus.listeners["CMD:EXTERNAL_OPEN_REQUEST_V1"]) == 1
    assert len(harness.fsm_ingress) == 1
    assert harness.fsm_ingress[0].verb == "OPEN"
    assert harness.fsm_ingress[0].pld["qty"] == "0.2"
    assert harness.fsm_ingress[0].pld["metadata"]["source_intent_id"] == "intent-runtime-0001"
    assert harness.authority_store.decisions()[-1].authority_decision == "ACCEPTED"
    assert harness.adapter.network_enabled is False
    assert harness.adapter_call_count == 0
    assert not hasattr(harness.app.state, "fsm_ref")

    assert len(harness.fsm_results) == 1
    assert harness.fsm_results[0] is not None
    assert (harness.fsm_results[0].op, harness.fsm_results[0].verb) == ("DEC", "OPEN")
    assert harness.fsm_results[0].why == "OPEN_OK"


def test_http_and_tcp_duplicates_do_not_repeat_fsm_or_adapter(runtime_harness) -> None:
    harness = runtime_harness
    payload = harness.payload()
    first = harness.post(payload)
    harness.wait_for(lambda: len(harness.fsm_ingress) == 1)
    duplicate_http = harness.post(payload)
    assert first.status_code == duplicate_http.status_code == 202
    assert first.json() == duplicate_http.json()
    assert harness.bridge.command_envelope_count == 1

    harness.send_tcp({"request_kind": "agent_trade_intent_v2", "request_id": "ipc-duplicate", **payload})
    harness.wait_for(lambda: harness.bridge.command_envelope_count == 2)
    assert len(harness.fsm_ingress) == 1
    assert len(harness.command_emissions) == 1
    assert harness.adapter_call_count == 0

    conflict = deepcopy(payload)
    conflict["side"] = "SELL"
    assert harness.post(conflict).status_code == 409
    assert harness.bridge.command_envelope_count == 2


def test_authority_schema_and_sizing_failures_never_reach_fsm(runtime_harness) -> None:
    harness = runtime_harness
    from datetime import timedelta
    from apps.reference.domains.shadow_telemetry.trading_session_authority import (
        Participant, TradingSession,
    )
    policy = harness.authority_store.policy
    harness.authority_store.create_session(TradingSession(
        session_id="session-no-lease",
        status="ACTIVE",
        created_at=harness.now(),
        started_at=harness.now(),
        expires_at=harness.now() + timedelta(hours=1),
        instrument_universe=["ETHUSDT"],
        participants=[],
        config_version=policy.config_version,
        instruction_version="instructions-runtime-v1",
    ))
    harness.authority_store.register_participant(Participant(
        participant_id="participant-no-lease",
        agent_id="api_agent_02",
        participant_type="MAIN_AGENT",
        enabled=True,
        session_id="session-no-lease",
    ))
    harness.authority_store.register_participant(Participant(
        participant_id="participant-wrong-owner",
        agent_id="api_agent_03",
        participant_type="MAIN_AGENT",
        enabled=True,
        session_id="session-runtime-1",
    ))
    harness.authority_store.register_participant(Participant(
        participant_id="participant-disabled",
        agent_id="api_agent_04",
        participant_type="MAIN_AGENT",
        enabled=False,
        session_id="session-runtime-1",
    ))
    cases = [
        harness.payload(session_id="unknown", client_intent_id="intent-negative-0001"),
        harness.payload(participant_id="unknown", client_intent_id="intent-negative-0002"),
        harness.payload(
            session_id="session-no-lease", participant_id="participant-no-lease",
            agent_id="api_agent_02", lease_reference="missing",
            client_intent_id="intent-negative-0003",
        ),
        harness.payload(symbol="SOLUSDT", client_intent_id="intent-negative-0004"),
        harness.payload(
            participant_id="participant-wrong-owner", agent_id="api_agent_03",
            client_intent_id="intent-negative-0005",
        ),
        harness.payload(
            participant_id="participant-disabled", agent_id="api_agent_04",
            client_intent_id="intent-negative-0006",
        ),
    ]
    for payload in cases:
        assert harness.post(payload).status_code == 202
    harness.wait_for(lambda: harness.bridge.v2_handler_count >= len(cases))
    assert harness.fsm_ingress == []
    assert harness.adapter_call_count == 0

    with_qty = harness.payload(client_intent_id="intent-negative-qty", qty="1")
    assert harness.post(with_qty).status_code == 422
    assert harness.fsm_ingress == []

    harness.decision_fixture.latest_portfolio = None
    assert harness.post(harness.payload(client_intent_id="intent-negative-sizing")).status_code == 202
    harness.wait_for(lambda: harness.bridge.v2_handler_count >= len(cases) + 1)
    assert harness.fsm_ingress == []
    assert harness.adapter_call_count == 0

    harness.decision_fixture.latest_portfolio = {"equity": "1000", "positions": []}
    harness.decision_fixture.symbol_states["ETHUSDT"]["current_price"] = None
    assert harness.post(harness.payload(client_intent_id="intent-negative-market")).status_code == 202
    harness.wait_for(lambda: harness.bridge.v2_handler_count >= len(cases) + 2)
    assert harness.fsm_ingress == []
    assert harness.adapter_call_count == 0


def test_subagent_inactive_expired_and_owner_mismatch_never_reach_fsm(runtime_harness) -> None:
    harness = runtime_harness
    store = harness.authority_store
    store.pause_session("session-runtime-1")
    assert harness.post(harness.payload(client_intent_id="intent-inactive-1")).status_code == 202
    harness.wait_for(lambda: harness.bridge.v2_handler_count == 1)
    assert harness.fsm_ingress == []

    store.activate_session("session-runtime-1")
    from apps.reference.domains.shadow_telemetry.trading_session_authority import Participant
    store.register_participant(Participant(
        participant_id="participant-subagent-1",
        agent_id="subagent_01",
        participant_type="SUBAGENT",
        enabled=True,
        session_id="session-runtime-1",
    ))
    assert harness.post(harness.payload(
        participant_id="participant-subagent-1",
        agent_id="subagent_01",
        client_intent_id="intent-subagent-1",
    )).status_code == 202
    harness.wait_for(lambda: harness.bridge.v2_handler_count == 2)
    assert harness.fsm_ingress == []

    harness.clock.advance_sec(store.policy.lease_ttl_sec)
    assert harness.post(harness.payload(client_intent_id="intent-expired-1")).status_code == 202
    harness.wait_for(lambda: harness.bridge.v2_handler_count == 3)
    assert harness.fsm_ingress == []
    assert harness.adapter_call_count == 0


def test_malformed_envelope_and_unregistered_command_fail_closed(runtime_harness) -> None:
    harness = runtime_harness
    harness.send_tcp({"request_kind": "agent_trade_intent_v2", "request_id": "malformed-1"})
    harness.wait_for(lambda: harness.bridge.command_envelope_count == 1)
    assert harness.fsm_ingress == []
    assert harness.adapter_call_count == 0

    assert harness.client.post("/intents/llm/v1", json={}).status_code == 404
    assert harness.client.post("/execution/eze/intents/v1", json={}).status_code == 404
    harness.send_tcp({"request_kind": "eze_open", "request_id": "legacy-bypass-1"})
    harness.wait_for(lambda: harness.bridge.command_envelope_count == 2)
    assert harness.fsm_ingress == []
    assert harness.adapter_call_count == 0

    registry = get_global_registry()
    assert registry is not None
    assert registry.is_registered("CMD", "EXTERNAL_OPEN_REQUEST_V1")
    with pytest.raises(InvalidMessagePayloadError, match="Unregistered command"):
        harness.bus.emit("CMD:P46_UNKNOWN_COMMAND", {}, "negative_registry_proof")


def test_duplicate_registry_entry_is_rejected(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "apps/reference/dictionaries/verb_registry_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    source["registry"].append(deepcopy(source["registry"][0]))
    registry_path = tmp_path / "duplicate_registry.yaml"
    registry_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    registry = VerbSchemaRegistry(Path(__file__).resolve().parents[3])
    with pytest.raises(ValueError, match="duplicate verb registry entry"):
        registry.load_registry(str(registry_path))
