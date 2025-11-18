"""Runtime-level regression test for aggregated OCO pipeline (OCO-11.15)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest
import yaml
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.domains.execution_position.fsm import PositionSnapshot
from tests.domains.execution_position.agg_oco_test_utils import (
    StubOrderGuardian,
    StubWatchdog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"


class AttrDict(dict):
    """Dict with attribute access for nested runtime config."""

    def __getattr__(self, item: str) -> Any:
        try:
            value = self[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc
        if isinstance(value, dict) and not isinstance(value, AttrDict):
            value = AttrDict(value)
            self[item] = value
        return value

    def copy(self) -> "AttrDict":  # type: ignore[override]
        return AttrDict(super().copy())


def _as_attr_dict(data: Any) -> Any:
    if isinstance(data, dict):
        return AttrDict({key: _as_attr_dict(value) for key, value in data.items()})
    if isinstance(data, list):
        return [_as_attr_dict(item) for item in data]
    return data


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def _load_runtime_config() -> AttrDict:
    execution_profile = _load_yaml(CONFIG_DIR / "domains" / "execution.yaml")
    instruments_cfg = _load_yaml(CONFIG_DIR / "instruments.yaml")
    overrides_cfg = _load_yaml(CONFIG_DIR / "overrides.yaml")
    symbols_cfg = _load_yaml(CONFIG_DIR / "symbols.yaml")
    modes_cfg = _load_yaml(CONFIG_DIR / "modes.yaml")

    config_payload: Dict[str, Any] = {
        "trading": {
            "execution": execution_profile,
            "instruments": instruments_cfg.get("instruments", {}),
        },
        # Provide legacy root alias for code paths that access config.execution
        "execution": execution_profile,
    }

    attr_config = _as_attr_dict(config_payload)
    attr_config["config_v2"] = SimpleNamespace(
        domains={"execution": execution_profile},
        instruments=instruments_cfg,
        overrides=overrides_cfg,
        symbols=symbols_cfg,
        modes=modes_cfg,
        core=_load_yaml(CONFIG_DIR / "core.yaml"),
    )
    return attr_config


@dataclass
class RecordingCall:
    kind: str
    symbol: str
    side: str
    payload: Dict[str, Any]


class RecordingRuntimeAdapter:
    """Adapter spy that records SL/TP placements without hitting the network."""

    def __init__(self) -> None:
        self.base_url = "https://testnet.binancefuture.com"
        self.calls: List[RecordingCall] = []
        self._seq = 0

    def _push_call(self, kind: str, symbol: str, side: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._seq += 1
        record = RecordingCall(kind=kind, symbol=symbol,
                               side=side, payload=payload)
        self.calls.append(record)
        return {
            "orderId": f"{kind.lower()}-{self._seq}",
            "clientOrderId": payload.get("new_client_order_id", f"auto-{self._seq}"),
        }

    async def place_stop_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: str | None = None,
        new_client_order_id: str | None = None,
    ) -> Dict[str, Any]:
        return self._push_call(
            "STOP_MARKET",
            symbol,
            side,
            {
                "stop_price": stop_price,
                "position_side": position_side,
                "new_client_order_id": new_client_order_id,
            },
        )

    async def place_limit_reduce_only(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        position_side: str | None = None,
        new_client_order_id: str | None = None,
    ) -> Dict[str, Any]:
        return self._push_call(
            "LIMIT",
            symbol,
            side,
            {
                "price": price,
                "qty": quantity,
                "position_side": position_side,
                "new_client_order_id": new_client_order_id,
            },
        )

    async def place_take_profit_market_close_position(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:  # pragma: no cover - safety
        return self._push_call("TAKE_PROFIT_MARKET", kwargs.get("symbol", "UNKNOWN"), kwargs.get("side", ""), kwargs)


@pytest.fixture(scope="module")
def runtime_config() -> AttrDict:
    return _load_runtime_config()


@pytest.fixture
def runtime_execpos(monkeypatch: pytest.MonkeyPatch, runtime_config: AttrDict) -> Tuple[execpos_mod.ExecPosFSM, RecordingRuntimeAdapter]:
    def _submit_async_stub(self, maybe_coro_or_fn: Any, loop: asyncio.AbstractEventLoop | None = None) -> None:
        target_loop = loop or asyncio.get_event_loop()
        coro = maybe_coro_or_fn() if callable(maybe_coro_or_fn) else maybe_coro_or_fn
        task = target_loop.create_task(coro)
        getattr(self, "_test_pending_tasks", []).append(task)

    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_initialize_adapter", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_bind_watchdog_hooks", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_guardian_start", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_fsm_cleanup_loop", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_submit_async", _submit_async_stub)
    monkeypatch.setattr(execpos_mod, "OrderGuardian",
                        lambda *a, **k: StubOrderGuardian(*a, **k))
    monkeypatch.setattr(execpos_mod, "OrderTimeoutWatchdog",
                        lambda *a, **k: StubWatchdog(*a, **k))

    fsm_core = FSMCore()
    execpos = execpos_mod.ExecPosFSM(
        config=runtime_config, fsm=fsm_core, shadow_mode=False)
    adapter = RecordingRuntimeAdapter()
    execpos.adapter = adapter
    execpos._test_pending_tasks = []  # type: ignore[attr-defined]
    return execpos, adapter


@pytest.mark.asyncio
async def test_agg_oco_runtime_pipeline_places_brackets(
    runtime_execpos: Tuple[execpos_mod.ExecPosFSM, RecordingRuntimeAdapter],
    caplog: pytest.LogCaptureFixture,
) -> None:
    execpos, adapter = runtime_execpos
    symbol = "SOLUSDT"

    cache_key = execpos._ws_cache_key(symbol, "LONG")
    execpos._ws_position_cache[cache_key] = PositionSnapshot(
        symbol=symbol,
        side="LONG",
        position_amt=1.2,
        avg_price=110.0,
        updated_ts=0.0,
    )

    caplog.set_level("INFO", logger="agg_oco")

    fill_msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="watchdog",
        dst="execution_position",
        rid="agg-oco-runtime",
        pld={
            "symbol": symbol,
            "qty": "1.2",
            "side": "BUY",
            "price": "110.0",
            "orderId": "rest-fill",
            "source": "rest_watchdog",
        },
    )

    decision = execpos.handle(fill_msg)
    assert decision is not None, "ManageFlow must emit DEC:PLACE_ORDER"
    assert decision.verb == "PLACE_ORDER"
    assert decision.op == "DEC"
    assert decision.pld.get("symbol") == symbol

    pending = getattr(execpos, "_test_pending_tasks", [])
    if pending:
        await asyncio.gather(*pending)
        pending.clear()

    kinds = [call.kind for call in adapter.calls]
    assert kinds == ["STOP_MARKET",
                     "LIMIT"], "ExecPosFSM must place SL and TP via adapter"

    manage_flow = execpos.manage_flow(symbol)
    assert manage_flow.sl_order_id is not None
    assert manage_flow.tp_order_id is not None

    log_messages = [record.getMessage()
                    for record in caplog.records if record.name == "agg_oco"]
    assert any("AGG_OCO_COMPUTE_BRACKETS_START" in msg for msg in log_messages)
    assert any("AGG_OCO_BEFORE_QTY_GUARD" in msg for msg in log_messages)
    assert not any(
        "AGG_OCO_WATCHDOG" in msg for msg in log_messages), "Watchdog warnings should not fire for healthy pipeline"
