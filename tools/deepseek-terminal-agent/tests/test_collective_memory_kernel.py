"""Focused proof for the P41X collective-memory coordination kernel."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.collective_memory import (
    CollectiveMemoryStore,
    PrivateMemoryAccessError,
    StaleCollectiveStateError,
    SymbolAuthorityError,
)
from deepseek_terminal_agent.sessions.collective_memory_models import (
    FSMDispatchResult,
    PortfolioState,
    SourceReference,
)
from deepseek_terminal_agent.sessions.coordination_config import load_coordination_config
from deepseek_terminal_agent.sessions.models import ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


def _profile() -> ModelProfile:
    return ModelProfile(
        profile_id="p41x-test",
        name="P41X Test",
        model_id="deepseek-v4-pro",
        max_tokens=4096,
        max_iterations=4,
        command_timeout_sec=30,
        max_command_output_chars=2000,
        context_budget_chars=40000,
        memory_atom_budget=4,
        recent_turns_budget=4,
        tool_output_budget_chars=2000,
    )


@pytest.fixture
def kernel(tmp_path):
    settings = Settings(deepseek=DeepSeekConfig(api_key="test-key"))
    session_store = SessionStore(settings, root_dir=tmp_path)
    session = session_store.create_session(default_profile=_profile())
    store = CollectiveMemoryStore(
        settings,
        root_dir=tmp_path,
        config=load_coordination_config(),
        session_store=session_store,
    )
    store.initialize_session(session.session_id)
    return store, session.session_id


def _publish(store: CollectiveMemoryStore, session_id: str, agent_id: str, number: int, symbol: str, index: int):
    return store.publish_observation(
        session_id=session_id,
        agent_id=agent_id,
        agent_number=number,
        kind="peer_observation",
        summary=f"observation-{agent_id}-{index}",
        symbol=symbol,
        source_refs=[],
        idempotency_key=f"publication:{agent_id}:{index}",
    )


def test_two_agents_write_concurrently_without_corruption(kernel):
    store, session_id = kernel
    jobs = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index in range(40):
            jobs.append(pool.submit(_publish, store, session_id, "api_agent_01", 1, "ETHUSDT", index))
            jobs.append(pool.submit(_publish, store, session_id, "cli_agent_01", 2, "XRPUSDT", index))
        results = [job.result(timeout=20) for job in jobs]

    assert len(results) == 80
    events = store.list_events(session_id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert len({event.event_id for event in events}) == len(events)
    state = store.get_state(session_id)
    assert len(state.publications) == 80
    assert {item.agent_id for item in state.publications} == {"api_agent_01", "cli_agent_01"}


def test_private_memory_cannot_be_modified_or_read_by_peer(kernel):
    store, session_id = kernel
    own = store.write_private_reflection(
        session_id=session_id,
        actor_agent_id="api_agent_01",
        actor_agent_number=1,
        target_agent_id="api_agent_01",
        kind="hypothesis",
        summary="ETH volatility expansion hypothesis",
        source_refs=[],
        idempotency_key="private:api:1",
    )
    assert own.agent_id == "api_agent_01"

    with pytest.raises(PrivateMemoryAccessError):
        store.write_private_reflection(
            session_id=session_id,
            actor_agent_id="cli_agent_01",
            actor_agent_number=2,
            target_agent_id="api_agent_01",
            kind="reflection",
            summary="peer overwrite attempt",
            source_refs=[],
            idempotency_key="private:peer:blocked",
        )
    with pytest.raises(PrivateMemoryAccessError):
        store.read_private_reflections(
            session_id=session_id,
            actor_agent_id="cli_agent_01",
            actor_agent_number=2,
            target_agent_id="api_agent_01",
        )


def test_publication_cursor_and_ack_semantics(kernel):
    store, session_id = kernel
    write = _publish(store, session_id, "api_agent_01", 1, "ETHUSDT", 1)
    peer = store.get_peer_publications(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
    )
    assert [item.publication_id for item in peer] == [write.state.publications[-1].publication_id]
    store.ack_peer_publications(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
        cursor_sequence=peer[-1].sequence,
        idempotency_key="peer-ack:cli:1",
    )
    assert store.get_peer_publications(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
    ) == []


def test_wrong_symbol_and_expired_lease_fail_closed(tmp_path):
    settings = Settings(deepseek=DeepSeekConfig(api_key="test-key"))
    sessions = SessionStore(settings, root_dir=tmp_path)
    session = sessions.create_session(default_profile=_profile())
    store = CollectiveMemoryStore(settings, root_dir=tmp_path, session_store=sessions)
    past = datetime.now(timezone.utc) - timedelta(seconds=1200)
    store.initialize_session(session.session_id, now=past)

    with pytest.raises(SymbolAuthorityError, match="wrong-symbol"):
        store.request_command(
            session_id=session.session_id,
            agent_id="api_agent_01",
            agent_number=1,
            command_kind="REQUEST_ORDER",
            symbol="XRPUSDT",
            rationale="wrong owner",
            intent_ref="intent://wrong",
            sizing_ref="config://llm_microstructure/execution",
            idempotency_key="wrong-symbol",
        )
    with pytest.raises(SymbolAuthorityError, match="expired"):
        store.request_command(
            session_id=session.session_id,
            agent_id="api_agent_01",
            agent_number=1,
            command_kind="REQUEST_ORDER",
            symbol="ETHUSDT",
            rationale="expired lease",
            intent_ref="intent://expired",
            sizing_ref="config://llm_microstructure/execution",
            idempotency_key="expired-lease",
        )


def test_duplicate_command_and_stale_state_are_detected(kernel):
    store, session_id = kernel
    first = store.request_command(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        command_kind="REQUEST_ORDER",
        symbol="ETHUSDT",
        rationale="15m decision review passed",
        intent_ref="intent://eth/1",
        sizing_ref="config://llm_microstructure/execution",
        command_id="cmd-stable-1",
        idempotency_key="command:stable:1",
    )
    duplicate = store.request_command(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        command_kind="REQUEST_ORDER",
        symbol="ETHUSDT",
        rationale="retry",
        intent_ref="intent://eth/1",
        sizing_ref="config://llm_microstructure/execution",
        command_id="cmd-stable-1",
        idempotency_key="command:stable:1",
    )
    assert duplicate.deduplicated is True
    assert duplicate.event.event_id == first.event.event_id
    assert sum(event.command_id == "cmd-stable-1" for event in store.list_events(session_id)) == 1

    version = store.get_state(session_id).version
    _publish(store, session_id, "cli_agent_01", 2, "XRPUSDT", 9)
    with pytest.raises(StaleCollectiveStateError):
        store.publish_observation(
            session_id=session_id,
            agent_id="api_agent_01",
            agent_number=1,
            kind="peer_observation",
            summary="stale write",
            symbol="ETHUSDT",
            source_refs=[],
            idempotency_key="stale:write",
            expected_version=version,
        )


def test_checkpoint_preserves_critical_events_all_refs_and_feature_history(kernel):
    store, session_id = kernel
    source = SourceReference(source_id="market-1", source_type="market_snapshot")
    store.publish_risk_warning(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        summary="correlated exposure rising",
        symbol="ETHUSDT",
        source_refs=[source],
        idempotency_key="risk:1",
    )
    store.update_feature_trust(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        feature_name="order_book_imbalance",
        trust=0.7,
        reason="stable in current regime",
        source_refs=[source],
        idempotency_key="feature:1",
    )
    store.update_feature_trust(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        feature_name="order_book_imbalance",
        trust=0.5,
        reason="degraded after spread expansion",
        source_refs=[source],
        idempotency_key="feature:2",
    )
    store.ack_instructions(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        manifest_version="manifest-v41",
        idempotency_key="instruction:api:v41",
    )
    events_before = store.list_events(session_id)
    checkpoint = store.create_checkpoint(session_id)

    assert len(checkpoint.manifest.source_references) == len(events_before)
    assert {ref.source_id for ref in checkpoint.manifest.source_references} == {
        event.event_id for event in events_before
    }
    critical_in_segments = {
        event.event_id for segment in checkpoint.segments for event in segment.critical_events
    }
    assert set(checkpoint.manifest.critical_event_ids).issubset(critical_in_segments)
    feature = checkpoint.snapshot.feature_trust_states["api_agent_01:order_book_imbalance"]
    assert len(feature.history) == 2
    assert checkpoint.carryover.instruction_versions["api_agent_01"] == "manifest-v41"


def test_checkpoint_plus_replay_reconstructs_state_and_instruction_version(kernel):
    store, session_id = kernel
    store.ack_instructions(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
        manifest_version="manifest-cli-v2",
        idempotency_key="instruction:cli:v2",
    )
    checkpoint = store.create_checkpoint(session_id)
    _publish(store, session_id, "api_agent_01", 1, "SOLUSDT", 22)
    before = store.get_state(session_id)

    store._state_path(session_id).unlink()
    report = store.recover_session(session_id)
    recovered = store.get_state(session_id)

    assert report.checkpoint_id == checkpoint.checkpoint_id
    assert report.replayed_event_count >= 2
    assert report.instruction_versions_restored["cli_agent_01"] == "manifest-cli-v2"
    assert {item.publication_id for item in recovered.publications} == {
        item.publication_id for item in before.publications
    }


def test_heartbeat_expiry_and_portfolio_emergency_stop(kernel):
    store, session_id = kernel
    now = datetime.now(timezone.utc)
    store.record_heartbeat(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        idempotency_key="heartbeat:api:1",
        now=now,
    )
    assert store.heartbeat_status(session_id, now=now)["api_agent_01"]["fresh"] is True
    assert store.heartbeat_status(
        session_id,
        now=now + timedelta(seconds=store.config.symbol_leases.heartbeat_expiry_seconds + 1),
    )["api_agent_01"]["fresh"] is False

    portfolio = PortfolioState(
        total_margin_usage=store.config.portfolio_limits.max_total_margin_usage + 1,
        total_directional_exposure=0,
        correlated_exposure=0,
        active_positions=[],
        active_orders=[],
        global_drawdown_pct=0,
        risk_budget_available=0,
        emergency_stop=False,
        reconciled_at=now.isoformat(),
    )
    result = store.reconcile_portfolio(
        session_id=session_id,
        portfolio=portfolio,
        idempotency_key="portfolio:breach:1",
        source_refs=[],
    )
    assert result.state.portfolio is not None
    assert result.state.portfolio.emergency_stop is True


def test_restart_does_not_duplicate_dispatch_in_doubt(kernel):
    store, session_id = kernel
    store.request_command(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
        command_kind="REQUEST_ORDER",
        symbol="BNBUSDT",
        rationale="30m decision window",
        intent_ref="intent://bnb/1",
        sizing_ref="config://llm_microstructure/execution",
        command_id="cmd-in-doubt",
        idempotency_key="command:bnb:1",
    )
    calls = {"count": 0}

    def failing_gateway(_command):
        calls["count"] += 1
        raise RuntimeError("gateway response lost")

    with pytest.raises(RuntimeError, match="response lost"):
        store.dispatch_command_to_fsm(
            session_id=session_id,
            command_id="cmd-in-doubt",
            fsm_gateway=failing_gateway,
        )
    report = store.recover_session(session_id)
    assert report.dispatch_in_doubt_command_ids == ["cmd-in-doubt"]
    assert report.exchange_reconciliation_status == "required_hook_missing"
    second = store.dispatch_command_to_fsm(
        session_id=session_id,
        command_id="cmd-in-doubt",
        fsm_gateway=lambda _command: FSMDispatchResult(accepted=True, reason="must not run"),
    )
    assert second.deduplicated is True
    assert calls["count"] == 1


def test_synthetic_long_session_compacts_within_configured_active_limit(kernel):
    store, session_id = kernel
    for index in range(240):
        if index % 2:
            _publish(store, session_id, "api_agent_01", 1, "SOLUSDT", index + 1000)
        else:
            _publish(store, session_id, "cli_agent_01", 2, "BNBUSDT", index + 1000)
        if index % 60 == 0:
            store.publish_risk_warning(
                session_id=session_id,
                agent_id="api_agent_01",
                agent_number=1,
                summary=f"synthetic critical risk {index}",
                symbol="ETHUSDT",
                source_refs=[],
                idempotency_key=f"synthetic-risk:{index}",
            )
    checkpoint = store.create_checkpoint(session_id)
    assert checkpoint.manifest.raw_event_count >= 249
    assert checkpoint.manifest.active_context_tokens <= store.config.memory.active_context_token_limit
    assert len(checkpoint.manifest.source_references) == checkpoint.manifest.raw_event_count
