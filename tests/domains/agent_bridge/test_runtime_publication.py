from __future__ import annotations

import json
from pathlib import Path

from apps.reference.domains.agent_bridge.contracts import (
    AgentMarketRuntimeSnapshotV0,
)
from apps.reference.domains.agent_bridge.publication import (
    AgentBridgeRuntimePublisher,
    AtomicPublicationStore,
    MARKET_FILENAME,
    RuntimePublicationReader,
)
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer


NOW_MS = 1_800_000_000_000


def _record(ts_ms: int = NOW_MS - 1_000) -> dict:
    return {
        "ts_ms": ts_ms,
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": ts_ms,
        "price": 100_000.0,
        "features": {
            "delta_price": "10",
            "ema_bias": "0.7",
            "tfi": "0.2",
            "rsi_14": 62.0,
            "obi": "0.1",
            "liquidity_kappa": "0.8",
            "volatility_state": "0.3",
            "atr_ratio": 1.1,
            "macro_sync": "0.9",
        },
        "regime": "TREND_UP",
        "regime_confidence": 0.8,
    }


def test_atomic_publication_write_read_and_no_temp_residue(tmp_path: Path) -> None:
    publisher = AgentBridgeRuntimePublisher(
        event_bus=None,
        execution_position=None,
        output_dir=tmp_path,
        symbols=["BTCUSDT"],
        source_owner="aurora_main_feature_mirror_relay",
    )
    publisher.ingest_mirror_record(_record())
    publisher.publish_initial(now_ms=NOW_MS)

    market, diagnostics = RuntimePublicationReader(tmp_path).market()

    assert market is not None
    assert market.schema_version == "agent-market-runtime/v0"
    assert market.symbols[0].last_price == 100_000.0
    assert market.symbols[0].features.direction_impulse.delta_price == 10.0
    assert "runtime_publication:market_snapshot_v0.json" in diagnostics
    assert not list(tmp_path.glob("*.tmp"))


def test_reader_rejects_oversized_or_invalid_publication(tmp_path: Path) -> None:
    path = tmp_path / MARKET_FILENAME
    path.write_text("not-json", encoding="utf-8")
    value, diagnostics = AtomicPublicationStore(tmp_path).read(MARKET_FILENAME, AgentMarketRuntimeSnapshotV0)
    assert value is None
    assert any(item.startswith("publication_invalid") for item in diagnostics)


def test_reducer_prefers_runtime_publication_over_disk_fallback(tmp_path: Path) -> None:
    disk = tmp_path / "data" / "shadow_telemetry" / "snapshots" / "BTCUSDT" / "2026-01-01" / "00.jsonl"
    disk.parent.mkdir(parents=True)
    disk.write_text(json.dumps({"ts_ms": NOW_MS - 60_000, "symbol": "BTCUSDT", "tf_sec": 300, "bar": {"close": 1}}) + "\n", encoding="utf-8")
    publisher = AgentBridgeRuntimePublisher(
        event_bus=None,
        execution_position=None,
        output_dir=tmp_path / "ops" / "agent_bridge" / "runtime",
        symbols=["BTCUSDT"],
        source_owner="aurora_main_feature_mirror_relay",
    )
    publisher.ingest_mirror_record(_record())
    publisher.publish_initial(now_ms=NOW_MS)

    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW_MS).build_packet(symbols=["BTCUSDT"])

    assert packet.symbol_markets[0].close_price == 100_000.0
    assert packet.symbol_markets[0].meta.source_ownership == "publication_relay"
    assert packet.feature_signals[0].meta.source_ownership == "publication_relay"
    assert packet.execution_body.meta.source_ownership == "publication_relay"
    assert packet.budget.estimated_tokens <= 4_400


def test_missing_publication_falls_back_explicitly(tmp_path: Path) -> None:
    disk = tmp_path / "data" / "shadow_telemetry" / "snapshots" / "BTCUSDT" / "2026-01-01" / "00.jsonl"
    disk.parent.mkdir(parents=True)
    disk.write_text(json.dumps({"ts_ms": NOW_MS - 1_000, "symbol": "BTCUSDT", "tf_sec": 300, "bar": {"close": 99_000}}) + "\n", encoding="utf-8")

    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW_MS).build_packet(symbols=["BTCUSDT"])

    assert packet.symbol_markets[0].close_price == 99_000.0
    assert packet.symbol_markets[0].meta.source_ownership == "bounded_disk_fallback"


def test_main_event_bus_listener_publishes_without_execution(tmp_path: Path) -> None:
    class Bus:
        def __init__(self):
            self.listeners = {}

        def listen(self, event_name, handler):
            self.listeners[event_name] = handler

    bus = Bus()
    publication_dir = tmp_path / "ops" / "agent_bridge" / "runtime"
    publisher = AgentBridgeRuntimePublisher(
        event_bus=bus,
        execution_position=None,
        output_dir=publication_dir,
        symbols=["BTCUSDT"],
        publisher_version="p4.v0",
    )
    assert set(bus.listeners) == {"EVT:FEATURES_CALCULATED", "EVT:REGIME_DETECTED"}

    bus.listeners["EVT:REGIME_DETECTED"]({"symbol": "BTCUSDT", "regime": "TREND_UP", "confidence": "0.8", "ts_ms": NOW_MS - 1_000})
    bus.listeners["EVT:FEATURES_CALCULATED"](_record())
    publisher.publish_initial(now_ms=NOW_MS)

    market, _ = RuntimePublicationReader(publication_dir).market()
    assert market is not None
    assert market.symbols[0].source_owner == "aurora_main_event_bus"
    assert market.publisher_version == "p4.v0"
    assert market.symbols[0].regime_label == "TREND_UP"

    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW_MS).build_packet(
        symbols=["BTCUSDT"]
    )
    assert packet.symbol_markets[0].meta.source_ownership == "direct_main_publication"
    assert packet.execution_body.meta.source_ownership == "publication_relay"


def test_market_publication_retains_canonical_300s_rows_before_extra_timeframes(
    tmp_path: Path,
) -> None:
    symbols = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "DOGEUSDT", "XRPUSDT"]
    publisher = AgentBridgeRuntimePublisher(
        event_bus=None,
        execution_position=None,
        output_dir=tmp_path,
        symbols=symbols,
        publisher_version="p4.v0",
    )
    for symbol in symbols:
        for tf_sec in (180, 300, 900):
            record = _record()
            record.update({"symbol": symbol, "tf_sec": tf_sec})
            publisher.ingest_mirror_record(record)
    publisher.publish_initial(now_ms=NOW_MS)

    market, _ = RuntimePublicationReader(tmp_path).market()
    assert market is not None
    canonical = {(item.symbol, item.tf_sec) for item in market.symbols}
    assert {(symbol, 300) for symbol in symbols}.issubset(canonical)
