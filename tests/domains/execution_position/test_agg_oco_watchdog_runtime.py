"""Runtime tests for ExecPosFSM aggregated OCO watchdog (OCO-11.4)."""

from __future__ import annotations

import asyncio
import time
import types
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.domains.execution_position.agg_oco_watchdog import AggOcoViolationKind
from apps.reference.services.order_guardian import BracketSetMeta


@dataclass
class StubOrder:
    symbol: str
    side: str
    position_side: str
    order_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "positionSide": self.position_side,
            "orderId": self.order_id,
            "type": "STOP_MARKET",
            "reduceOnly": True,
            "closePosition": True,
            "stopPrice": "123.4",
        }


class StubAdapter:
    def __init__(self) -> None:
        self._open_orders: List[Dict[str, Any]] = []
        self._positions: List[Dict[str, Any]] = []

    @property
    def open_orders(self) -> List[Dict[str, Any]]:
        return self._open_orders

    @open_orders.setter
    def open_orders(self, orders: List[Dict[str, Any]]) -> None:
        self._open_orders = orders

    @property
    def positions(self) -> List[Dict[str, Any]]:
        return self._positions

    @positions.setter
    def positions(self, positions: List[Dict[str, Any]]) -> None:
        self._positions = positions

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:  # noqa: ARG002
        return list(self._open_orders)

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        return list(self._positions)


class StubGuardian:
    def __init__(self) -> None:
        self.bracket_sets: List[BracketSetMeta] = []
        self.cleanup_calls: List[str] = []
        self.cleared_sets: List[tuple[str, str]] = []
        self.rehydrate_calls: List[tuple[str, str]] = []
        self.known_symbols: set[str] = set()

    def list_bracket_sets(self) -> List[BracketSetMeta]:
        return list(self.bracket_sets)

    def update_known_symbols(self, symbols: List[str]) -> None:
        self.known_symbols.update(sym.upper() for sym in symbols)

    async def cleanup_orphans(self, symbol: Optional[str] = None, **_: Any) -> int:
        key_symbol = (symbol or "").upper()
        self.cleanup_calls.append(key_symbol)
        before = len(self.bracket_sets)
        self.bracket_sets = [
            meta for meta in self.bracket_sets if meta.symbol.upper() != key_symbol
        ]
        return before

    def clear_bracket_set_for_position(self, *, symbol: str, side: str) -> None:
        self.cleared_sets.append((symbol.upper(), side.upper()))
        self.bracket_sets = [
            meta
            for meta in self.bracket_sets
            if not (meta.symbol.upper() == symbol.upper() and meta.side.upper() == side.upper())
        ]

    def rehydrate_bracket_set_for_position(
        self,
        *,
        symbol: str,
        side: str,
        position_amt: float,
        open_orders: List[Dict[str, Any]],
        now_ts: float,
    ) -> Optional[BracketSetMeta]:
        self.rehydrate_calls.append((symbol.upper(), side.upper()))
        if position_amt <= 0:
            return None
        matching_order = next(iter(open_orders or []), None)
        if not matching_order:
            return None
        meta = BracketSetMeta(
            bracket_set_id=f"rehydrated-{symbol}-{side}-{int(now_ts)}",
            symbol=symbol.upper(),
            side=side.upper(),
            sl_order_id=str(matching_order.get("orderId")),
            tp_order_id=None,
            created_ts=now_ts,
            version=0,
        )
        self.bracket_sets.append(meta)
        return meta

    async def start(self) -> None:  # pragma: no cover - not used in tests
        return None

    async def stop(self) -> None:  # pragma: no cover - not used in tests
        return None


class StubWatchdog:
    def __init__(self, *_, **__):
        self.started = False

    def ensure_started(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:  # noqa: ARG002
        self.started = True

    def stop(self) -> None:  # pragma: no cover - not used in tests
        self.started = False


@pytest.fixture
def watchdog_execpos(monkeypatch: pytest.MonkeyPatch) -> execpos_mod.ExecPosFSM:
    adapter = StubAdapter()
    guardian = StubGuardian()

    monkeypatch.setattr(execpos_mod, "OrderGuardian", lambda *a, **k: guardian)
    monkeypatch.setattr(execpos_mod, "OrderTimeoutWatchdog",
                        lambda *a, **k: StubWatchdog())
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_guardian_start", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_fsm_cleanup_loop", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_agg_oco_watchdog", lambda self: None)

    fsm = execpos_mod.ExecPosFSM(
        config=_build_watchdog_config(), fsm=None, shadow_mode=True)
    fsm.adapter = adapter
    fsm.order_guardian = guardian
    return fsm


def _build_watchdog_config() -> Dict[str, Any]:
    return {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "aggregated_oco": {
                            "enabled": True,
                            "aggregated_only_mode": True,
                            "recalc_on_scale_in": True,
                            "recalc_on_partial_close": True,
                            "ttl_protect_new_bracket_ms": 0,
                            "allow_unprotected_position": False,
                            "watchdog": {
                                "enabled": True,
                                "interval_sec": 1,
                                "auto_heal_orphans": True,
                            },
                        },
                    },
                },
            }
        }
    }


@pytest.mark.asyncio
async def test_watchdog_cleans_orphan_sl_when_position_zero(watchdog_execpos: execpos_mod.ExecPosFSM) -> None:
    adapter: StubAdapter = watchdog_execpos.adapter  # type: ignore[assignment]
    # type: ignore[assignment]
    guardian: StubGuardian = watchdog_execpos.order_guardian

    adapter.positions = []
    adapter.open_orders = [
        StubOrder(symbol="BTCUSDT", side="SELL",
                  position_side="LONG", order_id="orphan-sl").to_dict()
    ]
    guardian.bracket_sets = [
        BracketSetMeta(
            bracket_set_id="agg-1",
            symbol="BTCUSDT",
            side="LONG",
            sl_order_id="orphan-sl",
            tp_order_id=None,
            created_ts=time.time(),
            version=0,
        )
    ]

    await watchdog_execpos._run_agg_oco_watchdog_once()

    assert guardian.cleanup_calls == ["BTCUSDT"]
    assert guardian.cleared_sets == [("BTCUSDT", "LONG")]
    assert guardian.bracket_sets == []


@pytest.mark.asyncio
async def test_watchdog_does_not_autoheal_missing_sl(watchdog_execpos: execpos_mod.ExecPosFSM) -> None:
    adapter: StubAdapter = watchdog_execpos.adapter  # type: ignore[assignment]
    # type: ignore[assignment]
    guardian: StubGuardian = watchdog_execpos.order_guardian

    adapter.positions = [
        {
            "symbol": "ETHUSDT",
            "positionSide": "LONG",
            "positionAmt": "0.5",
        }
    ]
    adapter.open_orders = []
    guardian.bracket_sets = [
        BracketSetMeta(
            bracket_set_id="agg-eth",
            symbol="ETHUSDT",
            side="LONG",
            sl_order_id=None,
            tp_order_id=None,
            created_ts=time.time(),
            version=0,
        )
    ]

    await watchdog_execpos._run_agg_oco_watchdog_once()

    assert guardian.cleanup_calls == []
    assert guardian.cleared_sets == []


@pytest.mark.asyncio
async def test_watchdog_rehydrates_bracket_state_before_validation(watchdog_execpos: execpos_mod.ExecPosFSM) -> None:
    adapter: StubAdapter = watchdog_execpos.adapter  # type: ignore[assignment]
    # type: ignore[assignment]
    guardian: StubGuardian = watchdog_execpos.order_guardian

    adapter.positions = [
        {
            "symbol": "SOLUSDT",
            "positionSide": "LONG",
            "positionAmt": "1.25",
        }
    ]
    adapter.open_orders = [
        StubOrder(symbol="SOLUSDT", side="SELL", position_side="LONG",
                  order_id="rehydrate-sl").to_dict()
    ]
    guardian.bracket_sets = []

    await watchdog_execpos._run_agg_oco_watchdog_once()

    assert guardian.rehydrate_calls == [("SOLUSDT", "LONG")]
    assert guardian.cleanup_calls == []
    assert guardian.bracket_sets  # rehydrated meta should now exist


@pytest.mark.asyncio
async def test_watchdog_nominal_flow_never_flags_no_sl(watchdog_execpos: execpos_mod.ExecPosFSM) -> None:
    adapter: StubAdapter = watchdog_execpos.adapter  # type: ignore[assignment]
    # type: ignore[assignment]
    guardian: StubGuardian = watchdog_execpos.order_guardian

    violations: List[AggOcoViolationKind] = []

    original_logger = watchdog_execpos._log_watchdog_violation

    def _capture_violation(self, violation):
        violations.append(violation.kind)
        return original_logger(violation)

    watchdog_execpos._log_watchdog_violation = types.MethodType(  # type: ignore[assignment]
        _capture_violation,
        watchdog_execpos,
    )

    def _stage(position_amt: float, sl_order_id: Optional[str], version: int) -> None:
        if position_amt > 0 and sl_order_id:
            adapter.positions = [
                {
                    "symbol": "BTCUSDT",
                    "positionSide": "LONG",
                    "positionAmt": str(position_amt),
                }
            ]
            adapter.open_orders = [
                StubOrder(
                    symbol="BTCUSDT",
                    side="SELL",
                    position_side="LONG",
                    order_id=sl_order_id,
                ).to_dict()
            ]
            guardian.bracket_sets = [
                BracketSetMeta(
                    bracket_set_id=f"agg-{version}",
                    symbol="BTCUSDT",
                    side="LONG",
                    sl_order_id=sl_order_id,
                    tp_order_id=None,
                    created_ts=time.time(),
                    version=version,
                )
            ]
        else:
            adapter.positions = []
            adapter.open_orders = []
            guardian.bracket_sets = []

    for idx, payload in enumerate(
        [
            (0.003, "sl-open", 1),
            (0.005, "sl-scale", 2),
            (0.002, "sl-partial", 3),
            (0.0, None, 4),
        ]
    ):
        _stage(*payload)
        await watchdog_execpos._run_agg_oco_watchdog_once()
        assert AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION not in violations, f"unexpected NO_SL at stage {idx}"
        violations.clear()
