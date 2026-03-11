"""
Canonical episode identity and fill-aware lifecycle tests for P2.
"""

import json
from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.neocortex.logic.ingest.multi_tailer import (
    MultiSourceConfig,
    MultiTailer,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.core_parser import (
    CoreEventType,
    CoreLogEntry,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    OrderEventType,
    parse_order_log_line,
)


def _parse_order(payload):
    entry = parse_order_log_line(json.dumps(payload))
    assert entry is not None
    return entry


def _make_tailer(tmp_path, episode_handler=None):
    return MultiTailer(
        config=MultiSourceConfig(
            enabled=True,
            features_dir=tmp_path / "features",
            orders_file=tmp_path / "order_log_v1.jsonl",
            core_log=tmp_path / "aurora_core.log",
            symbols=["BTCUSDT", "ETHUSDT"],
        ),
        feature_handler=AsyncMock(),
        episode_handler=episode_handler,
        state_path=tmp_path / "state.json",
    )


def _position_closed(
    *,
    symbol: str,
    event_ts_ms: int,
    trade_id: str | None,
    realized_pnl_net: float | None = 3.5,
):
    return CoreLogEntry(
        timestamp=event_ts_ms / 1000.0,
        event_ts_ms=event_ts_ms,
        timestamp_str="",
        event_type=CoreEventType.POSITION_CLOSED,
        symbol=symbol,
        realized_pnl_net=realized_pnl_net,
        trade_id=trade_id,
        close_ts_ms=event_ts_ms,
        fees=0.1,
        raw_line="EVT:POSITION_CLOSED",
    )


def test_parse_order_filled_extracts_identity_fields():
    entry = _parse_order(
        {
            "event_type": "ORDER_FILLED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.25,
            "timestamp": 1_700_000_000_250,
            "order_id": "12345",
            "client_order_id": "ENTRY-12345",
            "lifecycle_id": "BTCUSDT:life:1",
            "metadata": {
                "fill_trade_id": "BTCUSDT:trade:1",
                "commission": 0.1,
            },
        }
    )

    assert entry.event_type == OrderEventType.FILLED
    assert entry.lifecycle_id == "BTCUSDT:life:1"
    assert entry.trade_id == "BTCUSDT:trade:1"
    assert entry.order_id == "12345"
    assert entry.client_order_id == "ENTRY-12345"


@pytest.mark.asyncio
async def test_overlapping_same_symbol_placements_do_not_overwrite_each_other(tmp_path):
    tailer = _make_tailer(tmp_path)
    tailer._market_state["BTCUSDT"] = {"rsi": 50.0}

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.1,
                "timestamp": 1_700_000_000_100,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )
    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "quantity": 0.2,
                "timestamp": 1_700_000_000_200,
                "order_id": "order-2",
                "client_order_id": "ENTRY-2",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )

    assert tailer.stats["staged_episodes"] == 2
    assert tailer.stats["pending_episodes"] == 0
    assert len(tailer._staged_episodes) == 2


@pytest.mark.asyncio
async def test_order_placed_without_fill_does_not_become_executed_entry(tmp_path):
    captured = []

    async def episode_handler(ep):
        captured.append(ep)

    tailer = _make_tailer(tmp_path, episode_handler=episode_handler)
    tailer._market_state["BTCUSDT"] = {"rsi": 50.0}

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.1,
                "timestamp": 1_700_000_000_100,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )

    await tailer._handle_position_close(
        _position_closed(
            symbol="BTCUSDT",
            event_ts_ms=1_700_000_000_900,
            trade_id="BTCUSDT:trade:missing",
        )
    )

    assert captured == []
    assert tailer.stats["staged_episodes"] == 1
    assert tailer.stats["pending_episodes"] == 0


@pytest.mark.asyncio
async def test_order_filled_is_entry_anchor_and_close_matches_trade_id(tmp_path):
    captured = []

    async def episode_handler(ep):
        captured.append(ep)

    tailer = _make_tailer(tmp_path, episode_handler=episode_handler)
    tailer._market_state["BTCUSDT"] = {"rsi": 50.0}

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.1,
                "timestamp": 1_700_000_000_100,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )

    tailer._market_state["BTCUSDT"] = {"rsi": 55.0}

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_FILLED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.1,
                "timestamp": 1_700_000_000_200,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {
                    "fill_trade_id": "BTCUSDT:trade:1",
                    "commission": 0.1,
                },
            }
        )
    )

    assert tailer.stats["staged_episodes"] == 0
    assert tailer.stats["pending_episodes"] == 1

    await tailer._handle_position_close(
        _position_closed(
            symbol="BTCUSDT",
            event_ts_ms=1_700_000_000_900,
            trade_id="BTCUSDT:trade:1",
        )
    )

    assert len(captured) == 1
    assert captured[0].executed_entry is True
    assert captured[0].entry_anchor_event == "ORDER_FILLED"
    assert captured[0].lifecycle_state == "CLOSED"
    assert captured[0].trade_id == "BTCUSDT:trade:1"
    assert captured[0].event_ts_ms == 1_700_000_000_200
    assert captured[0].close_event_ts_ms == 1_700_000_000_900
    assert captured[0].features["rsi"] == 55.0


@pytest.mark.asyncio
async def test_symbol_only_close_mapping_fails_closed(tmp_path):
    captured = []

    async def episode_handler(ep):
        captured.append(ep)

    tailer = _make_tailer(tmp_path, episode_handler=episode_handler)
    tailer._market_state["BTCUSDT"] = {"rsi": 50.0}

    for order_id, client_order_id, trade_id in (
        ("order-1", "ENTRY-1", "BTCUSDT:trade:1"),
        ("order-2", "ENTRY-2", "BTCUSDT:trade:2"),
    ):
        await tailer._handle_order_event(
            _parse_order(
                {
                    "event_type": "ORDER_PLACED",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "quantity": 0.1,
                    "timestamp": 1_700_000_000_100,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "metadata": {"order_type": "MARKET_ENTRY"},
                }
            )
        )
        await tailer._handle_order_event(
            _parse_order(
                {
                    "event_type": "ORDER_FILLED",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "quantity": 0.1,
                    "timestamp": 1_700_000_000_200,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "metadata": {"fill_trade_id": trade_id},
                }
            )
        )

    await tailer._handle_position_close(
        _position_closed(
            symbol="BTCUSDT",
            event_ts_ms=1_700_000_000_900,
            trade_id=None,
        )
    )

    assert captured == []
    assert tailer.stats["pending_episodes"] == 2
    assert tailer.stats["unresolved_lifecycle_events"] >= 1


@pytest.mark.asyncio
async def test_cancelled_staged_order_is_not_marked_as_executed_trade(tmp_path):
    captured = []

    async def episode_handler(ep):
        captured.append(ep)

    tailer = _make_tailer(tmp_path, episode_handler=episode_handler)
    tailer._market_state["BTCUSDT"] = {"rsi": 50.0}

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.1,
                "timestamp": 1_700_000_000_100,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )
    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_CANCELLED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "timestamp": 1_700_000_000_300,
                "order_id": "order-1",
            }
        )
    )

    assert len(captured) == 1
    assert captured[0].lifecycle_state == "CANCELLED"
    assert captured[0].executed_entry is False
    assert captured[0].entry_anchor_event is None
    assert captured[0].reward == pytest.approx(-0.001)


@pytest.mark.asyncio
async def test_partial_fills_are_aggregated_explicitly(tmp_path):
    tailer = _make_tailer(tmp_path)
    tailer._market_state["BTCUSDT"] = {"rsi": 50.0}

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 1.0,
                "timestamp": 1_700_000_000_100,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_FILLED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.4,
                "timestamp": 1_700_000_000_200,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"fill_trade_id": "BTCUSDT:trade:1"},
            }
        )
    )

    pending_episode = next(iter(tailer._pending_episodes.values()))
    assert pending_episode.lifecycle_state == "PARTIALLY_FILLED"
    assert pending_episode.fill_count == 1
    assert pending_episode.filled_quantity == pytest.approx(0.4)

    await tailer._handle_order_event(
        _parse_order(
            {
                "event_type": "ORDER_FILLED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.6,
                "timestamp": 1_700_000_000_300,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"fill_trade_id": "BTCUSDT:trade:1"},
            }
        )
    )

    pending_episode = next(iter(tailer._pending_episodes.values()))
    assert pending_episode.lifecycle_state == "ENTERED"
    assert pending_episode.fill_count == 2
    assert pending_episode.filled_quantity == pytest.approx(1.0)
