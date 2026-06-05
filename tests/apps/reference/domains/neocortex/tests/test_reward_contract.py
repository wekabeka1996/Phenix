"""
Canonical reward contract tests for P3.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.reference.domains.neocortex.logic.ingest.multi_tailer import (
    Episode,
    EpisodeReward,
    MultiSourceConfig,
    MultiTailer,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.core_parser import (
    CoreEventType,
    CoreLogEntry,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    parse_order_log_line,
)
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


def _parse_order(payload):
    entry = parse_order_log_line(__import__("json").dumps(payload))
    assert entry is not None
    return entry


def _make_tailer(tmp_path, episode_handler=None):
    return MultiTailer(
        config=MultiSourceConfig(
            enabled=True,
            features_dir=tmp_path / "features",
            orders_file=tmp_path / "order_log_v1.jsonl",
            core_log=tmp_path / "aurora_core.log",
            symbols=["BTCUSDT"],
        ),
        feature_handler=AsyncMock(),
        episode_handler=episode_handler,
        state_path=tmp_path / "state.json",
    )


def _close_entry(
    *,
    symbol: str = "BTCUSDT",
    event_type: CoreEventType = CoreEventType.POSITION_CLOSED,
    trade_id: str | None = "BTCUSDT:trade:1",
    close_ts_ms: int = 1_700_000_000_900,
    close_price: float | None = 110.0,
    realized_pnl: float | None = None,
    realized_pnl_net: float | None = 4.9,
    fees: float | None = 0.1,
):
    return CoreLogEntry(
        timestamp=close_ts_ms / 1000.0,
        event_ts_ms=close_ts_ms,
        timestamp_str="",
        event_type=event_type,
        symbol=symbol,
        trade_id=trade_id,
        close_ts_ms=close_ts_ms,
        close_price=close_price,
        realized_pnl=realized_pnl,
        realized_pnl_net=realized_pnl_net,
        fees=fees,
        raw_line=f"EVT:{event_type.name}",
    )


@pytest.mark.asyncio
async def test_episode_reward_created_only_after_authoritative_close(tmp_path):
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
                "quantity": 0.5,
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
                "quantity": 0.5,
                "price": 100.0,
                "timestamp": 1_700_000_000_200,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"fill_trade_id": "BTCUSDT:trade:1"},
            }
        )
    )

    episode_key = tailer._episode_keys_by_trade_id["BTCUSDT:trade:1"]
    pending = tailer._pending_episodes[episode_key]
    assert pending.episode_reward is None
    assert pending.reward_complete is False

    await tailer._handle_position_close(
        _close_entry(
            trade_id="BTCUSDT:trade:1",
            close_ts_ms=1_700_000_000_900,
            close_price=110.0,
            realized_pnl=5.0,
            realized_pnl_net=4.9,
            fees=0.1,
        )
    )

    assert len(captured) == 1
    reward = captured[0].episode_reward
    assert reward is not None
    assert reward.episode_id == episode_key
    assert reward.trade_id == "BTCUSDT:trade:1"
    assert reward.entry_ts_ms == 1_700_000_000_200
    assert reward.close_ts_ms == 1_700_000_000_900
    assert reward.duration_ms == 700
    assert reward.entry_price == pytest.approx(100.0)
    assert reward.close_price == pytest.approx(110.0)
    assert reward.quantity == pytest.approx(0.5)
    assert reward.realized_pnl == pytest.approx(5.0)
    assert reward.fees == pytest.approx(0.1)
    assert reward.net_pnl == pytest.approx(4.9)
    assert reward.entry_event == "ORDER_FILLED"
    assert reward.close_event == "POSITION_CLOSED"
    assert reward.reward_complete is True
    assert captured[0].reward_complete is True
    assert captured[0].reward == pytest.approx(0.4542164326822591)


@pytest.mark.asyncio
async def test_partial_fills_aggregate_entry_vwap(tmp_path):
    captured = []

    async def episode_handler(ep):
        captured.append(ep)

    tailer = _make_tailer(tmp_path, episode_handler=episode_handler)
    tailer._market_state["BTCUSDT"] = {"rsi": 55.0}

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

    for qty, price in ((0.4, 100.0), (0.6, 110.0)):
        await tailer._handle_order_event(
            _parse_order(
                {
                    "event_type": "ORDER_FILLED",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "quantity": qty,
                    "price": price,
                    "timestamp": 1_700_000_000_200 + int(price),
                    "order_id": "order-1",
                    "client_order_id": "ENTRY-1",
                    "metadata": {"fill_trade_id": "BTCUSDT:trade:1"},
                }
            )
        )

    await tailer._handle_position_close(
        _close_entry(
            trade_id="BTCUSDT:trade:1",
            close_ts_ms=1_700_000_000_900,
            close_price=120.0,
            realized_pnl_net=14.0,
            fees=0.2,
        )
    )

    reward = captured[0].episode_reward
    assert reward is not None
    assert reward.entry_price == pytest.approx(106.0)
    assert reward.realized_pnl == pytest.approx(14.2)
    assert reward.net_pnl == pytest.approx(14.0)
    assert reward.quantity == pytest.approx(1.0)
    assert captured[0].fill_count == 2
    assert captured[0].filled_quantity == pytest.approx(1.0)
    assert captured[0].reward_complete is True


@pytest.mark.asyncio
async def test_close_without_trade_id_fails_closed(tmp_path):
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
                "quantity": 0.5,
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
                "quantity": 0.5,
                "price": 100.0,
                "timestamp": 1_700_000_000_200,
                "order_id": "order-1",
                "client_order_id": "ENTRY-1",
                "metadata": {"fill_trade_id": "BTCUSDT:trade:1"},
            }
        )
    )

    await tailer._handle_position_close(
        _close_entry(trade_id=None, close_price=110.0,
                     realized_pnl_net=4.9, fees=0.1)
    )

    assert captured == []
    assert tailer.stats["unresolved_lifecycle_events"] == 1
    assert tailer.stats["pending_episodes"] == 1


def test_adapter_marks_incomplete_reward_as_reward_missing():
    adapter = object.__new__(NeocortexAdapter)
    adapter.config = SimpleNamespace(
        ingest=SimpleNamespace(feature_list=["rsi"]))
    adapter._emit_alert = MagicMock()

    episode = Episode(
        symbol="BTCUSDT",
        timestamp=1_700_000_000.2,
        event_ts_ms=1_700_000_000_200,
        features={"rsi": 50.0},
        side="BUY",
        reward=0.4,
        pnl=4.9,
        trade_id="BTCUSDT:trade:1",
        executed_entry=True,
        entry_anchor_event="ORDER_FILLED",
        lifecycle_state="CLOSED",
    )
    episode.episode_id = "trade:BTCUSDT:trade:1"
    episode.reward_complete = False
    episode.episode_reward = EpisodeReward(
        episode_id="trade:BTCUSDT:trade:1",
        trade_id="BTCUSDT:trade:1",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_200,
        close_ts_ms=1_700_000_000_900,
        duration_ms=700,
        entry_price=100.0,
        close_price=None,
        quantity=0.5,
        realized_pnl=None,
        fees=0.1,
        net_pnl=4.9,
        entry_event="ORDER_FILLED",
        close_event="POSITION_CLOSED",
        reward_complete=False,
    )

    payload = NeocortexAdapter._episode_to_dict(adapter, episode)

    assert payload["reward_missing"] is True
    assert payload["reward_complete"] is False
    assert payload["episode_reward"]["reward_complete"] is False
    assert payload["reward"] == pytest.approx(0.4)


def test_adapter_preserves_missing_reward_as_none():
    adapter = object.__new__(NeocortexAdapter)
    adapter.config = SimpleNamespace(
        ingest=SimpleNamespace(feature_list=["rsi"]))
    adapter._emit_alert = MagicMock()

    episode = Episode(
        symbol="BTCUSDT",
        timestamp=1_700_000_000.2,
        event_ts_ms=1_700_000_000_200,
        features={"rsi": 50.0},
        side="BUY",
        reward=None,
        pnl=None,
        trade_id="BTCUSDT:trade:1",
        executed_entry=True,
        entry_anchor_event="ORDER_FILLED",
        lifecycle_state="OPEN",
    )

    payload = NeocortexAdapter._episode_to_dict(adapter, episode)

    assert payload["reward"] is None
    assert payload["reward_missing"] is True
    assert payload["reward_complete"] is False


def test_adapter_treats_absent_reward_key_as_missing():
    adapter = object.__new__(NeocortexAdapter)
    adapter.config = SimpleNamespace(
        ingest=SimpleNamespace(feature_list=["rsi"]))
    adapter._emit_alert = MagicMock()

    payload = NeocortexAdapter._episode_to_dict(
        adapter,
        {
            "symbol": "BTCUSDT",
            "timestamp": 1_700_000_000.2,
            "features": {"rsi": 50.0},
            "side": "BUY",
        },
    )

    assert payload["reward"] is None
    assert payload["reward_missing"] is True
    assert payload["reward_complete"] is False
