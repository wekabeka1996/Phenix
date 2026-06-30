from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.domains.agent_bridge.capabilities import build_execution_capability_descriptors
from apps.reference.domains.agent_bridge.publication import AgentBridgeRuntimePublisher
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer
from apps.reference.domains.agent_bridge.exchange_info import (
    ALLOWED_ENDPOINTS,
    PublicExchangeInfoCache,
    PublicExchangeInfoSymbolV0,
    compare_filter_parity,
)


NOW = 1_800_000_000_000


def _payload(*, btc_step="0.0001", omit_notional=False):
    filters = [
        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
        {"filterType": "LOT_SIZE", "stepSize": btc_step, "minQty": "0.0001", "maxQty": "1000"},
        {"filterType": "MAX_NUM_ORDERS", "limit": 200},
    ]
    if not omit_notional:
        filters.append({"filterType": "MIN_NOTIONAL", "notional": "50"})
    return {"serverTime": NOW - 100, "symbols": [{"symbol": "BTCUSDT", "filters": filters}]}


def _cfg(*, step="0.001", min_qty="0.001", min_notional="100"):
    return SimpleNamespace(
        tick_size=Decimal("0.1"),
        step_size=Decimal(step),
        min_qty=Decimal(min_qty),
        min_notional=Decimal(min_notional),
    )


def test_endpoint_is_exact_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        PublicExchangeInfoCache(
            directory=tmp_path,
            symbols=["BTCUSDT"],
            environment="testnet",
            endpoint="https://example.com/fapi/v1/exchangeInfo",
        )


def test_refresh_projects_symbols_and_persists_atomic_cache(tmp_path: Path) -> None:
    cache = PublicExchangeInfoCache(
        directory=tmp_path,
        symbols=["BTCUSDT"],
        environment="testnet",
        endpoint=ALLOWED_ENDPOINTS["testnet"],
        fetch_fn=lambda *_: _payload(),
        now_ms_fn=lambda: NOW,
    )
    assert cache.refresh() is True
    row = cache.get_symbol("BTCUSDT", NOW)
    assert row is not None
    assert row.step_size == "0.0001"
    assert row.max_qty == "1000"
    assert row.min_notional == "50"
    assert row.unsupported_filters == ["MAX_NUM_ORDERS"]
    assert (tmp_path / "public_exchange_info_cache_v0.json").stat().st_size < 64 * 1024
    assert not list(tmp_path.glob("*.tmp"))


def test_failure_retains_last_good_values_but_marks_them_stale(tmp_path: Path) -> None:
    calls = iter([_payload(), RuntimeError("network unavailable")])

    def fetch(*_):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    cache = PublicExchangeInfoCache(
        directory=tmp_path,
        symbols=["BTCUSDT"],
        environment="testnet",
        endpoint=ALLOWED_ENDPOINTS["testnet"],
        fetch_fn=fetch,
        now_ms_fn=lambda: NOW,
    )
    assert cache.refresh() is True
    assert cache.refresh() is False
    row = cache.get_symbol("BTCUSDT", NOW)
    assert row is not None and Decimal(row.tick_size) == Decimal("0.1")
    assert row.freshness == "stale"
    assert row.fetch_status == "error"
    assert row.error_code == "RuntimeError"


def test_missing_required_filter_is_visible(tmp_path: Path) -> None:
    cache = PublicExchangeInfoCache(
        directory=tmp_path,
        symbols=["BTCUSDT"],
        environment="testnet",
        endpoint=ALLOWED_ENDPOINTS["testnet"],
        fetch_fn=lambda *_: _payload(omit_notional=True),
        now_ms_fn=lambda: NOW,
    )
    assert cache.refresh()
    row = cache.get_symbol("BTCUSDT", NOW)
    assert row is not None
    assert row.min_notional is None
    assert row.missing_filters == ["MIN_NOTIONAL|NOTIONAL"]


@pytest.mark.parametrize(
    ("configured", "exchange", "expected"),
    [
        (_cfg(step="0.0001", min_qty="0.0001", min_notional="50"), ("0.0001", "0.0001", "50"), "match"),
        (_cfg(), ("0.0001", "0.0001", "50"), "minor_mismatch"),
        (_cfg(step="0.00001", min_qty="0.00001", min_notional="10"), ("0.0001", "0.0001", "50"), "material_mismatch"),
    ],
)
def test_parity_classification(configured, exchange, expected) -> None:
    step, min_qty, min_notional = exchange
    row = PublicExchangeInfoSymbolV0(
        symbol="BTCUSDT",
        source_ts_ms=NOW,
        fetched_ts_ms=NOW,
        freshness="fresh",
        tick_size="0.1",
        step_size=step,
        min_qty=min_qty,
        min_notional=min_notional,
    )
    assert compare_filter_parity("BTCUSDT", configured, row).severity == expected


def test_stale_and_missing_parity_precedence() -> None:
    stale = PublicExchangeInfoSymbolV0(
        symbol="BTCUSDT", fetched_ts_ms=NOW, freshness="stale",
        tick_size="0.1", step_size="0.001", min_qty="0.001", min_notional="100",
    )
    assert compare_filter_parity("BTCUSDT", _cfg(), stale).severity == "stale_exchange_info"
    missing = stale.model_copy(update={"freshness": "fresh", "min_notional": None})
    assert compare_filter_parity("BTCUSDT", _cfg(), missing).severity == "exchange_missing"
    assert compare_filter_parity("BTCUSDT", None, missing).severity == "configured_missing"


class _PublicCache:
    environment = "testnet"

    def __init__(self, row):
        self.row = row

    def get_symbol(self, *_):
        return self.row

    def start(self):
        return None

    def stop(self):
        return None


def test_descriptor_uses_public_evidence_without_adapter_calls() -> None:
    row = PublicExchangeInfoSymbolV0(
        symbol="BTCUSDT", source_ts_ms=NOW - 100, fetched_ts_ms=NOW,
        freshness="fresh", tick_size="0.1", step_size="0.0001",
        min_qty="0.0001", min_notional="50",
    )
    runtime = SimpleNamespace(
        config=SimpleNamespace(instruments={"BTCUSDT": _cfg()}),
        exchange_filter_cache=None,
        _close_exec=None,
        _bracket_mgr=None,
    )
    descriptors, summaries, _ = build_execution_capability_descriptors(
        runtime=runtime,
        symbols=["BTCUSDT"],
        produced_ts_ms=NOW,
        public_exchange_info=_PublicCache(row),
    )
    descriptor = next(item for item in descriptors if item.name == "exchange_filter_constraints")
    assert descriptor.status == "ready"
    assert descriptor.evidence_level == "exchange_confirmed"
    assert descriptor.diagnostic_state == "exchange_confirmed"
    assert summaries[0].parity == "minor_mismatch"
    assert summaries[0].exchange_values["step_size"] == "0.0001"


def test_material_mismatch_and_stale_never_become_ready() -> None:
    base = PublicExchangeInfoSymbolV0(
        symbol="BTCUSDT", fetched_ts_ms=NOW, freshness="fresh",
        tick_size="0.1", step_size="0.01", min_qty="0.01", min_notional="200",
    )
    runtime = SimpleNamespace(config=SimpleNamespace(instruments={"BTCUSDT": _cfg()}), exchange_filter_cache=None)
    descriptors, _, _ = build_execution_capability_descriptors(
        runtime=runtime, symbols=["BTCUSDT"], produced_ts_ms=NOW,
        public_exchange_info=_PublicCache(base),
    )
    item = next(value for value in descriptors if value.name == "exchange_filter_constraints")
    assert (item.status, item.diagnostic_state) == ("degraded", "parity_mismatch")

    descriptors, _, _ = build_execution_capability_descriptors(
        runtime=runtime, symbols=["BTCUSDT"], produced_ts_ms=NOW,
        public_exchange_info=_PublicCache(base.model_copy(update={"freshness": "stale"})),
    )
    item = next(value for value in descriptors if value.name == "exchange_filter_constraints")
    assert (item.status, item.diagnostic_state) == ("degraded", "stale_exchange_info")


def test_p6_packet_keeps_requested_parity_under_budget(tmp_path: Path) -> None:
    instruments = {
        "BTCUSDT": _cfg(),
        "ETHUSDT": SimpleNamespace(
            tick_size=Decimal("0.01"), step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"), min_notional=Decimal("20"),
        ),
    }
    runtime = SimpleNamespace(
        config=SimpleNamespace(instruments=instruments),
        no_order_observation_mode=True,
        shadow_mode=True,
        is_live_execution=False,
        adapter=None,
        no_order_blocked_action_count=0,
        exchange_filter_cache=None,
        correlation_store=object(),
    )

    class Cache(_PublicCache):
        def get_symbol(self, symbol, *_):
            values = (
                ("0.1", "0.0001", "0.0001", "50")
                if symbol == "BTCUSDT"
                else ("0.01", "0.001", "0.001", "20")
            )
            return PublicExchangeInfoSymbolV0(
                symbol=symbol, fetched_ts_ms=NOW, source_ts_ms=NOW - 100,
                freshness="fresh", tick_size=values[0], step_size=values[1],
                min_qty=values[2], min_notional=values[3],
            )

    publisher = AgentBridgeRuntimePublisher(
        event_bus=None,
        execution_position=runtime,
        output_dir=tmp_path / "ops" / "agent_bridge" / "runtime",
        symbols=instruments,
        publisher_version="p6.v0",
        public_exchange_info=Cache(None),
    )
    for symbol, price in (("BTCUSDT", 60_000), ("ETHUSDT", 2_000)):
        publisher.ingest_mirror_record({
            "symbol": symbol, "ts_ms": NOW, "bar_close_ts": NOW,
            "tf_sec": 300, "price": price, "regime": "UNCERTAIN",
            "features": {"delta_price": 1, "obi": 0.1},
        })
    publisher.publish_initial(NOW)
    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW).build_packet(
        symbols=["BTCUSDT", "ETHUSDT"]
    )
    assert packet.budget.estimated_tokens <= 4_400
    assert packet.budget.truncated is False
    assert {item.symbol for item in packet.execution_body.constraint_summary} == {"BTCUSDT", "ETHUSDT"}
    assert {item.parity for item in packet.execution_body.constraint_summary} == {"match", "minor_mismatch"}
