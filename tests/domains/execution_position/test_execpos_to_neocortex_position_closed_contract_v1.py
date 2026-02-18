from __future__ import annotations

import asyncio
import math

import pytest

from vfoundation.core.protocol import Message

from apps.reference.domains.neocortex.logic.ingest.multi_tailer import (
    Episode,
    MultiSourceConfig,
    MultiTailer,
)


def _portfolio_event(
    positions: list[dict],
    *,
    realized_pnl: str,
    ts_ms: int,
    rid: str = "rid-portfolio",
) -> Message:
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="execution_position",
        rid=rid,
        pld={
            "positions": positions,
            "realized_pnl": realized_pnl,
            "ts": ts_ms,
            "equity_free_usdt": "1000",
            "equity_cross_usdt": "1000",
        },
    )


def _extract_position_closed_payloads(bus) -> list[dict]:
    return [evt[1][0] for evt in bus.events if evt[0] == "EVT:POSITION_CLOSED"]


def _build_tailer(tmp_path, episode_handler):
    async def _feature_handler(_payload):
        return None

    return MultiTailer(
        config=MultiSourceConfig(
            enabled=True,
            features_dir=tmp_path / "features",
            orders_file=tmp_path / "order_log_v1.jsonl",
            core_log=tmp_path / "aurora_core.log",
            symbols=["BTCUSDT"],
        ),
        feature_handler=_feature_handler,
        episode_handler=episode_handler,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_execpos_position_closed_event_to_neocortex_structured_reward(fsm_harness, tmp_path) -> None:
    fsm, bus, _cfg = fsm_harness

    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.5"}],
            realized_pnl="100.0",
            ts_ms=1_700_000_000_000,
        )
    )
    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.0"}],
            realized_pnl="103.5",
            ts_ms=1_700_000_001_000,
            rid="rid-close",
        )
    )
    await asyncio.sleep(0.01)

    close_payloads = _extract_position_closed_payloads(bus)
    assert len(close_payloads) == 1
    payload = close_payloads[0]

    captured = []

    async def _episode_handler(ep):
        captured.append(ep)

    tailer = _build_tailer(tmp_path, _episode_handler)
    tailer._pending_episodes["BTCUSDT"] = Episode(
        symbol="BTCUSDT",
        timestamp=1_700_000_000.0,
        features={"rsi": 50.0},
        side="BUY",
    )

    await tailer.handle_position_closed_event(payload)

    assert len(captured) == 1
    assert captured[0].position_closed is True
    assert captured[0].pnl == pytest.approx(3.5)
    assert captured[0].reward == pytest.approx(math.tanh(3.5 / tailer.REWARD_SCALE))
    assert "BTCUSDT" not in tailer._pending_episodes


@pytest.mark.asyncio
@pytest.mark.integration
async def test_execpos_position_closed_event_to_neocortex_no_fallback_policy(fsm_harness, tmp_path) -> None:
    fsm, bus, _cfg = fsm_harness

    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.2"}],
            realized_pnl="200.0",
            ts_ms=1_700_000_100_000,
        )
    )
    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.0"}],
            realized_pnl="201.0",
            ts_ms=1_700_000_101_000,
            rid="rid-close-no-reward",
        )
    )
    await asyncio.sleep(0.01)

    close_payloads = _extract_position_closed_payloads(bus)
    assert len(close_payloads) == 1
    payload = dict(close_payloads[0])
    payload.pop("realized_pnl_net", None)

    captured = []

    async def _episode_handler(ep):
        captured.append(ep)

    tailer = _build_tailer(tmp_path, _episode_handler)
    tailer._pending_episodes["BTCUSDT"] = Episode(
        symbol="BTCUSDT",
        timestamp=1_700_000_100.0,
        features={"rsi": 55.0},
        side="BUY",
    )

    await tailer.handle_position_closed_event(payload)

    assert len(captured) == 1
    assert captured[0].position_closed is True
    assert captured[0].pnl is None
    assert captured[0].reward is None
    assert "BTCUSDT" not in tailer._pending_episodes
