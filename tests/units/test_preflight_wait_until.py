"""Unit tests for ExecPosFSM WS-driven preflight checks."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.execution_position.fsm import ExecPosFSM, PositionSnapshot


class DummyAdapter:
    def __init__(self, positions: list[dict[str, object]] | None = None) -> None:
        self.positions = positions or []
        self.calls = 0

    def get_open_positions(self, symbol: str | None = None):  # pragma: no cover - simple shim
        self.calls += 1
        return list(self.positions)


def _build_config(*, enabled: bool = True, max_age_ms: int = 1500, rest_enabled: bool = True):
    return {
        "trading": {
            "execution": {
                "manage": {
                    "positions": {
                        "ws_snapshot": {
                            "enabled": enabled,
                            "max_age_ms": max_age_ms,
                            "rest_fallback_enabled": rest_enabled,
                        }
                    }
                }
            }
        }
    }


def _make_fsm(config=None) -> ExecPosFSM:
    cfg = config or _build_config()
    return ExecPosFSM(config=cfg, fsm=MagicMock())


@pytest.mark.asyncio
async def test_preflight_uses_fresh_ws_snapshot():
    fsm = _make_fsm()
    fsm.adapter = DummyAdapter()
    fsm._ws_position_cache[("BTCUSDT", "LONG")] = PositionSnapshot(
        symbol="BTCUSDT",
        side="LONG",
        position_amt=0.25,
        avg_price=100.0,
        updated_ts=time.time(),
    )

    assert await fsm._preflight_position_check("BTCUSDT", "LONG") is True
    assert fsm.adapter.calls == 0


@pytest.mark.asyncio
async def test_preflight_rest_fallback_updates_cache():
    fsm = _make_fsm()
    adapter = DummyAdapter(
        [{"symbol": "ETHUSDT", "positionAmt": "0.5", "entryPrice": "2000"}]
    )
    fsm.adapter = adapter

    result = await fsm._preflight_position_check("ETHUSDT", "LONG")

    assert result is True
    assert adapter.calls == 1
    snapshot = fsm._ws_position_cache.get(("ETHUSDT", "LONG"))
    assert snapshot is not None
    assert snapshot.position_amt == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_preflight_uses_rest_when_snapshot_stale():
    fsm = _make_fsm(config=_build_config(max_age_ms=100))
    adapter = DummyAdapter(
        [{"symbol": "SOLUSDT", "positionAmt": "1.0", "entryPrice": "150"}]
    )
    fsm.adapter = adapter
    fsm._ws_position_cache[("SOLUSDT", "LONG")] = PositionSnapshot(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.0,
        avg_price=150.0,
        updated_ts=time.time() - 5,  # stale (>100ms)
    )

    assert await fsm._preflight_position_check("SOLUSDT", "LONG") is True
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_preflight_reports_no_position_when_ws_and_rest_empty():
    fsm = _make_fsm()
    adapter = DummyAdapter([{"symbol": "BTCUSDT", "positionAmt": "0"}])
    fsm.adapter = adapter

    result = await fsm._preflight_position_check("BTCUSDT", "LONG")

    assert result is False
    assert adapter.calls == 1
    assert fsm._orphan_metrics.get("tp_sl_skipped_no_position", 0) == 1
