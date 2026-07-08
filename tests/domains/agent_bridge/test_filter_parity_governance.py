from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from apps.reference.domains.agent_bridge.exchange_info import PublicExchangeInfoSymbolV0
from apps.reference.domains.agent_bridge.parity_governance import (
    ACK_FILENAME,
    HISTORY_FILENAME,
    FilterParityHistoryRowV1,
    FilterParityHistoryStore,
)
from apps.reference.domains.agent_bridge.publication import AgentBridgeRuntimePublisher
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer


NOW = 1_800_000_000_000


def _instrument(*, tick="0.1", step="0.001", qty="0.001", notional="100"):
    return SimpleNamespace(
        tick_size=Decimal(tick),
        step_size=Decimal(step),
        min_qty=Decimal(qty),
        min_notional=Decimal(notional),
    )


def _runtime(instrument=None):
    instruments = {} if instrument is None else {"BTCUSDT": instrument}
    return SimpleNamespace(config=SimpleNamespace(instruments=instruments))


def _exchange(*, freshness="fresh", tick="0.1", step="0.0001", qty="0.0001", notional="50"):
    return PublicExchangeInfoSymbolV0(
        symbol="BTCUSDT",
        source_ts_ms=NOW - 100,
        fetched_ts_ms=NOW,
        freshness=freshness,
        tick_size=tick,
        step_size=step,
        min_qty=qty,
        min_notional=notional,
    )


def _ack_document(
    *, state_ref: str, parity_status="conservative_mismatch",
    compatibility="compatible_conservative", ack_status="acknowledged_conservative",
    symbol="BTCUSDT", environment="testnet", created=NOW + 1,
    expires=NOW + 10_000, review_by=NOW + 9_000,
):
    return {
        "schema_version": "filter-parity-operator-acknowledgements/v0",
        "acknowledgements": [{
            "schema_version": "operator-parity-acknowledgement/v0",
            "ack_id": "ack_btc_0001", "operator_id": "ops.reviewer.1",
            "operator_display_name": "Test Reviewer",
            "created_ts_ms": created, "expires_ts_ms": expires,
            "symbol": symbol, "venue": "binance_usdm", "environment": environment,
            "state_ref": state_ref, "parity_status": parity_status,
            "compatibility_assessment": compatibility, "ack_status": ack_status,
            "ack_reason": "Reviewed exact public-filter parity state.",
            "review_required_by_ts_ms": review_by,
            "provenance": {"source": "operator_authored_offline_file", "format_version": "v0"},
        }],
    }


def test_match_is_not_required_and_conservative_stays_unacknowledged(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    match = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument(step="0.0001", qty="0.0001", notional="50")),
        exchange=_exchange(), environment="testnet", observed_ts_ms=NOW,
    )
    assert (match.parity_status, match.operator_ack_status) == ("match", "not_required")

    conservative = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 1,
    )
    assert conservative.parity_status == "conservative_mismatch"
    assert conservative.compatibility_assessment == "compatible_conservative"
    assert conservative.operator_ack_status == "unacknowledged"
    assert conservative.requires_execution_block_before_authority is False


def test_risky_stale_and_missing_never_auto_acknowledge(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    risky = store.observe(
        symbol="BTCUSDT",
        runtime=_runtime(_instrument(step="0.00001", qty="0.00001", notional="10")),
        exchange=_exchange(), environment="testnet", observed_ts_ms=NOW,
    )
    assert risky.parity_status == "risky_mismatch"
    assert risky.operator_ack_status == "unacknowledged"
    assert risky.requires_yaml_review is True
    assert risky.requires_execution_block_before_authority is True

    stale = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()),
        exchange=_exchange(freshness="stale"), environment="testnet", observed_ts_ms=NOW + 1,
    )
    assert (stale.parity_status, stale.operator_ack_status) == ("stale", "unacknowledged")
    assert stale.requires_execution_block_before_authority is True

    missing = store.observe(
        symbol="BTCUSDT", runtime=_runtime(None), exchange=None,
        environment="testnet", observed_ts_ms=NOW + 2,
    )
    assert (missing.parity_status, missing.operator_ack_status) == ("missing", "unacknowledged")


def test_ack_requires_explicit_matching_operator_state_ref(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    initial = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW,
    )
    wrong = _ack_document(state_ref=initial.state_ref + "-wrong")
    (tmp_path / ACK_FILENAME).write_text(json.dumps(wrong), encoding="utf-8")
    assert store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 2,
    ).operator_ack_status == "expired"

    wrong["acknowledgements"][0]["state_ref"] = initial.state_ref
    (tmp_path / ACK_FILENAME).write_text(json.dumps(wrong), encoding="utf-8")
    accepted = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 3,
    )
    assert accepted.operator_ack_status == "acknowledged_conservative"
    assert accepted.operator_id == "ops.reviewer.1"
    assert accepted.operator_ack_validation_status == "valid"
    assert accepted.operator_ack_file_hash is not None


def test_ack_status_must_be_compatible_with_parity_state(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    risky_kwargs = dict(
        symbol="BTCUSDT",
        runtime=_runtime(_instrument(step="0.00001", qty="0.00001", notional="10")),
        exchange=_exchange(), environment="testnet", observed_ts_ms=NOW,
    )
    risky = store.observe(**risky_kwargs)
    document = _ack_document(
        state_ref=risky.state_ref, parity_status="risky_mismatch",
        compatibility="incompatible_or_looser", ack_status="acknowledged_conservative",
    )
    (tmp_path / ACK_FILENAME).write_text(json.dumps(document), encoding="utf-8")
    assert store.observe(
        **{**risky_kwargs, "observed_ts_ms": NOW + 2}
    ).operator_ack_status == "unacknowledged"

    document["acknowledgements"][0]["ack_status"] = "acknowledged_requires_review"
    (tmp_path / ACK_FILENAME).write_text(json.dumps(document), encoding="utf-8")
    assert store.observe(
        **{**risky_kwargs, "observed_ts_ms": NOW + 3}
    ).operator_ack_status == "acknowledged_requires_review"


def test_history_is_idempotent_and_tracks_lifecycle(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    kwargs = dict(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW,
    )
    first = store.observe(**kwargs)
    store.observe(**kwargs)
    store.observe(**{**kwargs, "observed_ts_ms": NOW + 1})
    resolved = store.observe(
        symbol="BTCUSDT",
        runtime=_runtime(_instrument(step="0.0001", qty="0.0001", notional="50")),
        exchange=_exchange(), environment="testnet", observed_ts_ms=NOW + 2,
    )
    lines = (tmp_path / HISTORY_FILENAME).read_text(encoding="utf-8").splitlines()
    rows = [FilterParityHistoryRowV1.model_validate_json(line) for line in lines]
    assert len(rows) == 3
    assert [row.transition for row in rows] == ["new", "unchanged", "resolved"]
    assert first.first_seen_ts_ms == NOW
    assert resolved.operator_ack_status == "not_required"


class _Cache:
    environment = "testnet"

    def __init__(self, rows):
        self.rows = rows

    def get_symbol(self, symbol, *_):
        return self.rows.get(symbol)

    def start(self):
        return None

    def stop(self):
        return None


def test_packet_projects_compact_parity_ack_state_under_budget(tmp_path: Path) -> None:
    instruments = {
        "BTCUSDT": _instrument(),
        "ETHUSDT": _instrument(tick="0.01", step="0.001", qty="0.001", notional="20"),
    }
    runtime = SimpleNamespace(
        config=SimpleNamespace(instruments=instruments), no_order_observation_mode=True,
        shadow_mode=True, is_live_execution=False, adapter=None,
        no_order_blocked_action_count=0, exchange_filter_cache=None,
        correlation_store=object(),
    )
    rows = {
        "BTCUSDT": _exchange(),
        "ETHUSDT": PublicExchangeInfoSymbolV0(
            symbol="ETHUSDT", source_ts_ms=NOW - 100, fetched_ts_ms=NOW,
            freshness="fresh", tick_size="0.01", step_size="0.001",
            min_qty="0.001", min_notional="20",
        ),
    }
    publisher = AgentBridgeRuntimePublisher(
        event_bus=None, execution_position=runtime,
        output_dir=tmp_path / "ops" / "agent_bridge" / "runtime",
        parity_history_dir=tmp_path / "ops" / "agent_bridge" / "parity_history",
        symbols=instruments, publisher_version="p7.v0", public_exchange_info=_Cache(rows),
    )
    publisher.publish_initial(NOW)
    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW).build_packet(
        symbols=["BTCUSDT", "ETHUSDT"]
    )
    items = {item.symbol: item for item in packet.execution_body.filter_parity_acknowledgements}
    assert items["BTCUSDT"].parity_status == "conservative_mismatch"
    assert items["BTCUSDT"].ack_status == "unacknowledged"
    assert items["BTCUSDT"].validation_status == "missing"
    assert items["BTCUSDT"].state_ref.startswith(
        "aurora-publication://exchange-info/filter-parity/v0/sha256:"
    )
    assert items["BTCUSDT"].reason == "operator_acknowledgement_file_missing"
    assert items["ETHUSDT"].ack_status == "not_required"
    assert items["ETHUSDT"].validation_status == "not_required"
    assert packet.budget.estimated_tokens <= 4_400
    assert packet.budget.truncated is False


def test_packet_projects_valid_operator_identity_and_expiry(tmp_path: Path) -> None:
    runtime = SimpleNamespace(
        config=SimpleNamespace(instruments={"BTCUSDT": _instrument()}),
        no_order_observation_mode=True, shadow_mode=True, is_live_execution=False,
        adapter=None, no_order_blocked_action_count=0, exchange_filter_cache=None,
        correlation_store=object(),
    )
    parity_dir = tmp_path / "ops" / "agent_bridge" / "parity_history"
    store = FilterParityHistoryStore(parity_dir)
    state = store.observe(
        symbol="BTCUSDT", runtime=runtime, exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW,
    )
    (parity_dir / ACK_FILENAME).write_text(
        json.dumps(_ack_document(state_ref=state.state_ref)), encoding="utf-8"
    )
    publisher = AgentBridgeRuntimePublisher(
        event_bus=None, execution_position=runtime,
        output_dir=tmp_path / "ops" / "agent_bridge" / "runtime",
        parity_history_dir=parity_dir, symbols=["BTCUSDT"],
        publisher_version="p8.v0", public_exchange_info=_Cache({"BTCUSDT": _exchange()}),
    )
    publisher.publish_initial(NOW + 2)
    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW + 2).build_packet(
        symbols=["BTCUSDT"]
    )
    item = packet.execution_body.filter_parity_acknowledgements[0]
    assert item.ack_status == "acknowledged_conservative"
    assert item.operator_id == "ops.reviewer.1"
    assert item.created_ts_ms == NOW + 1
    assert item.expires_ts_ms == NOW + 10_000
    assert item.validation_status == "valid"
    assert item.provenance_ref is not None
    assert packet.budget.estimated_tokens <= 4_400
