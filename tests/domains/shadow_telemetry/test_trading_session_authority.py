from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.reference.config.domains.shadow_telemetry import AgentAuthorityPolicyConfig
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries
from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentTradeIntentV2,
    AgentTradeIntentV2Processor,
    PositionQueriesSizingAdapterV2,
)
from apps.reference.domains.shadow_telemetry.main_bridge import LLMIntentIngressBridge
from apps.reference.domains.shadow_telemetry.trading_session_authority import (
    AuthorityStoreError,
    CanonicalV2AuthorityProvider,
    Participant,
    SymbolLease,
    TradingSession,
    TradingSessionAuthorityStore,
)


NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


class ControlledClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def policy(**updates):
    values = {
        "config_version": "p46-1e-test-v1",
        "supported_session_statuses": ["CREATED", "ACTIVE", "PAUSED", "CLOSED", "EXPIRED"],
        "allowed_participant_types": ["MAIN_AGENT", "SUBAGENT", "OPERATOR"],
        "execution_capable_participant_types": ["MAIN_AGENT"],
        "lease_ttl_sec": 300,
        "renewal_requires_owner": True,
        "expiry_behavior": "reject",
        "conflict_behavior": "reject",
        "session_instrument_universe": ["ETHUSDT", "SOLUSDT"],
        "max_position_horizon_sec": 10800,
        "intent_ttl_sec": 300,
        "account_snapshot_max_age_sec": 15,
        "market_snapshot_max_age_sec": 15,
        "execution_order_type": "LIMIT",
        "execution_time_in_force": "GTC",
        "execution_valid_for_ms": 900000,
        "context_ack_policy": "defer_unavailable",
    }
    values.update(updates)
    return AgentAuthorityPolicyConfig.model_validate(values)


def session(status="CREATED", session_id="session-1", symbols=None):
    return TradingSession(
        session_id=session_id,
        status=status,
        created_at=NOW,
        started_at=NOW if status == "ACTIVE" else None,
        expires_at=NOW + timedelta(hours=4),
        instrument_universe=symbols or ["ETHUSDT", "SOLUSDT"],
        participants=[],
        config_version="p46-1e-test-v1",
        instruction_version="instructions-v3",
    )


def participant(kind="MAIN_AGENT", enabled=True, participant_id="participant-1", session_id="session-1"):
    return Participant(
        participant_id=participant_id,
        agent_id="api_agent_01",
        participant_type=kind,
        enabled=enabled,
        session_id=session_id,
    )


def lease(clock, owner="participant-1", lease_id="lease-1", symbol="ETHUSDT", version=1):
    return SymbolLease(
        lease_id=lease_id,
        session_id="session-1",
        symbol=symbol,
        owner_participant_id=owner,
        acquired_at=clock(),
        expires_at=clock() + timedelta(seconds=300),
        version=version,
    )


def intent(**updates):
    values = {
        "contract_version": "2.0",
        "session_id": "session-1",
        "participant_id": "participant-1",
        "agent_id": "api_agent_01",
        "symbol": "ETHUSDT",
        "intent_type": "OPEN",
        "side": "BUY",
        "strategy_or_reason": "Thirty minute breakout confirmation",
        "confidence": "0.75",
        "max_position_horizon_sec": 7200,
        "context_version": 3,
        "context_ack_version": 3,
        "evidence_refs": ["evidence-1"],
        "subagent_acknowledgements": [],
        "lease_reference": "lease-1",
        "client_intent_id": "intent-v2-0001",
        "created_at": NOW - timedelta(seconds=30),
    }
    values.update(updates)
    return AgentTradeIntentV2.model_validate(values)


def active_store():
    clock = ControlledClock()
    store = TradingSessionAuthorityStore(policy(), clock)
    store.create_session(session())
    store.activate_session("session-1")
    store.register_participant(participant())
    store.acquire_lease(lease(clock))
    return store, clock


def assert_reason(store, value, reason):
    with pytest.raises(AuthorityStoreError, match=reason):
        store.validate_execution_authority(value)


def test_policy_is_strict_and_requires_complete_ssot() -> None:
    with pytest.raises(ValidationError):
        policy(unknown=True)
    with pytest.raises(ValidationError):
        policy(execution_capable_participant_types=["MAIN_AGENT", "OPERATOR"])
    with pytest.raises(ValidationError):
        policy(session_instrument_universe=[])


def test_session_lifecycle_and_universe_fail_closed() -> None:
    store, _ = active_store()
    assert store.read_session("session-1").status == "ACTIVE"
    store.pause_session("session-1")
    assert_reason(store, intent(), "SESSION_NOT_ACTIVE")
    store.activate_session("session-1")
    store.close_session("session-1")
    assert_reason(store, intent(), "SESSION_NOT_ACTIVE")
    assert_reason(store, intent(session_id="missing"), "SESSION_NOT_FOUND")
    with pytest.raises(AuthorityStoreError, match="SYMBOL_NOT_IN_SESSION_UNIVERSE"):
        store.create_session(session(session_id="bad", symbols=["BNBUSDT"]))


def test_session_expiry_is_rejected() -> None:
    store, clock = active_store()
    clock.advance(4 * 60 * 60)
    assert_reason(store, intent(), "SESSION_NOT_ACTIVE")


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (participant(enabled=False), "PARTICIPANT_DISABLED"),
        (participant(kind="SUBAGENT"), "SUBAGENT_EXECUTION_FORBIDDEN"),
        (participant(kind="OPERATOR"), "PARTICIPANT_ROLE_FORBIDDEN"),
    ],
)
def test_participant_execution_eligibility(candidate, reason) -> None:
    clock = ControlledClock()
    store = TradingSessionAuthorityStore(policy(), clock)
    store.create_session(session(status="ACTIVE"))
    store.register_participant(candidate)
    if candidate.enabled and candidate.participant_type == "MAIN_AGENT":
        store.acquire_lease(lease(clock))
    assert_reason(store, intent(), reason)


def test_unknown_and_wrong_session_participant_rejected() -> None:
    store, _ = active_store()
    assert_reason(store, intent(participant_id="missing"), "PARTICIPANT_NOT_FOUND")
    foreign = participant(participant_id="foreign", session_id="session-2")
    store.create_session(session(session_id="session-2"))
    store.register_participant(foreign)
    assert_reason(store, intent(participant_id="foreign"), "PARTICIPANT_SESSION_MISMATCH")


def test_lease_conflict_idempotency_renew_release_and_takeover() -> None:
    store, clock = active_store()
    original = lease(clock)
    assert store.acquire_lease(original) == original
    other = participant(participant_id="participant-2")
    store.register_participant(other)
    with pytest.raises(AuthorityStoreError, match="LEASE_CONFLICT"):
        store.acquire_lease(lease(clock, owner="participant-2", lease_id="lease-2"))
    renewed = store.renew_lease("lease-1", "participant-1", 1)
    assert renewed.version == 2
    with pytest.raises(AuthorityStoreError, match="LEASE_VERSION_CONFLICT"):
        store.renew_lease("lease-1", "participant-1", 1)
    store.release_lease("lease-1", "participant-1", 2)
    takeover = store.acquire_lease(lease(clock, owner="participant-2", lease_id="lease-2"))
    assert takeover.owner_participant_id == "participant-2"


def test_expired_lease_rejects_and_allows_takeover() -> None:
    store, clock = active_store()
    clock.advance(300)
    assert_reason(store, intent(), "LEASE_EXPIRED")
    store.register_participant(participant(participant_id="participant-2"))
    takeover = store.acquire_lease(lease(clock, owner="participant-2", lease_id="lease-2"))
    assert takeover.lease_id == "lease-2"


def test_lease_owner_symbol_and_version_fail_closed() -> None:
    store, clock = active_store()
    assert_reason(store, intent(participant_id="participant-1", lease_reference="other"), "LEASE_OWNER_MISMATCH")
    assert_reason(store, intent(symbol="SOLUSDT", lease_reference="lease-sol"), "LEASE_NOT_FOUND")
    with pytest.raises(AuthorityStoreError, match="LEASE_OWNER_MISMATCH"):
        store.release_lease("lease-1", "other", 1)
    with pytest.raises(AuthorityStoreError, match="SYMBOL_NOT_IN_SESSION_UNIVERSE"):
        store.acquire_lease(lease(clock, symbol="BNBUSDT", lease_id="bad"))


class FSM:
    def __init__(self):
        self.emitted = []

    def emit(self, name, payload=None, why="", **kwargs):
        self.emitted.append((name, payload or kwargs.get("payload") or {}, why))


def bridge_config():
    return SimpleNamespace(
        domains=SimpleNamespace(
            shadow_telemetry=SimpleNamespace(
                enabled=True,
                api=SimpleNamespace(enabled=True, write=SimpleNamespace(enabled=True)),
                egress_to_main=SimpleNamespace(ipc_commands_endpoint="tcp://127.0.0.1:7102"),
                lifecycle=SimpleNamespace(stop_timeout_ms=100),
            )
        ),
        trading=SimpleNamespace(llm_orchestration=SimpleNamespace(mode="baseline", symbols_llm=[], allowlist_symbols=[])),
    )


def processor(store, portfolio=None, price="2500"):
    dm = SimpleNamespace(
        latest_portfolio=portfolio or {
            "equity": "1000", "positions": [], "ts_ms": int(NOW.timestamp() * 1000)
        },
        latest_portfolio_ref="account-1",
        symbol_states={"ETHUSDT": {
            "current_price": price,
            "snapshot_ref": "market-1",
            "timestamp_ms": int(NOW.timestamp() * 1000),
        }},
    )
    instrument = SimpleNamespace(
        sizing=SimpleNamespace(
            margin_pct=0.10, fee_buffer_fraction="0.001"),
        execution=SimpleNamespace(target_leverage=2),
        step_size=Decimal("0.01"),
        min_qty=Decimal("0.01"),
        min_notional=Decimal("5"),
    )
    queries = PositionQueries(
        config=SimpleNamespace(instruments={"ETHUSDT": instrument}),
        get_portfolio=lambda: dm.latest_portfolio,
        min_pos_size_usd=Decimal("5"),
        liq_cap_usd=Decimal("500"),
        logger=logging.getLogger("test.p46_1e"),
    )
    return AgentTradeIntentV2Processor(
        authority_provider=CanonicalV2AuthorityProvider(store, dm),
        sizing_adapter=PositionQueriesSizingAdapterV2(queries),
    )


def submit(bridge, value):
    bridge._on_command({"request_kind": "agent_trade_intent_v2", "request_id": "request-1", **value.model_dump(mode="json")})


def commands(fsm):
    return [entry for entry in fsm.emitted if entry[0].startswith("CMD:")]


def test_valid_v2_authority_and_sizing_emit_exactly_one_command() -> None:
    store, _ = active_store()
    fsm = FSM()
    bridge = LLMIntentIngressBridge(fsm, bridge_config(), v2_processor=processor(store))
    submit(bridge, intent())
    assert [row[0] for row in commands(fsm)] == ["CMD:EXTERNAL_OPEN_REQUEST_V1"]
    assert commands(fsm)[0][1]["qty"] == "0.07"
    decision = store.decisions()[-1]
    assert decision.authority_decision == "ACCEPTED"
    assert decision.lease_version == 1


@pytest.mark.parametrize("mutation", ["missing_session", "inactive", "subagent", "missing_lease", "expired", "owner"])
def test_authority_failures_emit_zero_commands(mutation) -> None:
    store, clock = active_store()
    value = intent()
    if mutation == "missing_session":
        value = intent(session_id="missing")
    elif mutation == "inactive":
        store.pause_session("session-1")
    elif mutation == "subagent":
        store._participants["participant-1"] = participant(kind="SUBAGENT")
    elif mutation == "missing_lease":
        store.release_lease("lease-1", "participant-1", 1)
    elif mutation == "expired":
        clock.advance(300)
    elif mutation == "owner":
        value = intent(lease_reference="other")
    fsm = FSM()
    bridge = LLMIntentIngressBridge(fsm, bridge_config(), v2_processor=processor(store))
    submit(bridge, value)
    assert commands(fsm) == []


def test_sizing_failure_and_duplicate_intent_emit_zero_additional_commands() -> None:
    store, _ = active_store()
    fsm = FSM()
    bridge = LLMIntentIngressBridge(fsm, bridge_config(), v2_processor=processor(store))
    value = intent()
    submit(bridge, value)
    submit(bridge, value)
    assert len(commands(fsm)) == 1

    store2, _ = active_store()
    fsm2 = FSM()
    bridge2 = LLMIntentIngressBridge(fsm2, bridge_config(), v2_processor=processor(store2, portfolio={"equity": "0", "positions": []}))
    submit(bridge2, value)
    assert commands(fsm2) == []


def test_caller_quantity_remains_rejected() -> None:
    payload = intent().model_dump(mode="json")
    payload["qty"] = "1"
    with pytest.raises(ValidationError):
        AgentTradeIntentV2.model_validate(payload)
