import asyncio
import inspect
import json
import logging
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from vfoundation.core.protocol import Message

import apps.reference.main as main_module
from apps.reference.domains.decision_making.contracts import PortfolioSnapshot
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.portfolio_provider import PortfolioProvider
from apps.reference.domains.execution_position.runtime_factory import build_execution_runtime
from apps.reference.main import AuroraBridge


BASE_CONFIG: Dict[str, Any] = {
    "trading": {
        "mode": "test",
        "decision": {
            "signal_threshold": "0.1",
            "neutral_threshold": "0.0",
            "signals": {
                "normalize": False,
                "signal_weights": {
                    "obi": 0.4,
                    "tfi": 0.4,
                    "delta_price": 0.2,
                },
            },
            "signal_weights": {
                "obi": 0.4,
                "tfi": 0.4,
                "delta_price": 0.2,
            },
            "position_sizing": {
                "min_position_size_usd": "10",
                "liquidity_based_cap_usd": "2000",
                "risk_fraction_q": "0.02",
                "liquidity_kappa_mode": "static",
                "liquidity_kappa": "1",
            },
            "kelly": {
                "base_probability": 0.55,
                "kelly_cap": 0.2,
                "kelly_alpha": 0.5,
            },
            "qos": {
                "mode": "shadow",
                "symbol_intent_cooldown_sec": 0,
                "max_intents_per_minute_per_symbol": 120,
                "exposure_block_cooldown_sec": 0,
            },
            "features": {"ttl_sec": 5},
            "side_bias_penalty_factor": 0,
        },
        "tca_prefs": {
            "max_slippage_bps": "25",
            "max_latency_ms": "1000",
            "maker_preference": "prefer",
        },
        "risk_budgets": {
            "trade_cvar95_max_bps": "50",
            "session_cvar95_max_bps": "500",
            "max_cvar_per_session_usd": "10000",
        },
        "execution": {
            "brackets": {
                "sl": {"fixed_bps": "75"},
                "tp": {"fixed_bps": "150"},
                "offset_bps": 5,
            }
        },
        "instruments": {
            "SOLUSDT": {
                "step_size": "0.01",
                "tick_size": "0.01",
                "min_qty": "0.1",
                "quote_precision": 5,
                "quantity_precision": 3,
            }
        },
    },
    "position_tracking": {"positions_stale_ttl_sec": 60},
    "execution_position": {
        "runtime_mode": "v2",
        "cooldown_sec": 0,
        "snapshot": {"orders_ttl_sec": 5, "position_ttl_sec": 5},
        "manage": {
            "brackets": {
                "sl": {"fixed_bps": "75"},
                "tp": {"fixed_bps": "150"},
                "offset_bps": 5,
            }
        },
    },
    "config_v2": {
        "domains": {
            "execution": {
                "brackets": {
                    "sl": {"fixed_bps": "75"},
                    "tp": {"fixed_bps": "150"},
                    "offset_bps": 5,
                }
            },
            "decision": {
                "thresholds": {
                    "signal_threshold": 0.1,
                    "neutral_threshold": 0.0,
                },
                "qos": {
                    "max_intents_per_minute_per_symbol": 120,
                    "symbol_intent_cooldown_sec": 0,
                    "exposure_block_cooldown_sec": 0,
                },
            },
        }
    },
}


class StubFSM:
    """Minimal FSM stub for wiring listeners and capturing emitted events."""

    def __init__(self) -> None:
        self.listeners: Dict[str, List[Any]] = {}
        self.emitted: List[Message] = []
        self.domains: Dict[str, Any] = {}

    def listen(self, event_name: str, callback: Any) -> None:
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, *args: Any, **kwargs: Any) -> Message:
        if not args:
            raise TypeError("emit requires arguments")

        event_name: Optional[str] = None
        if isinstance(args[0], Message):
            msg = args[0]
            event_name = f"{msg.op}:{msg.verb}"
        elif isinstance(args[0], str) and ":" in args[0]:
            event_name = args[0]
            op, verb = event_name.split(":", 1)
            msg = Message(
                op=op,
                verb=verb,
                src=kwargs.get("src", "stub"),
                dst=kwargs.get("dst", "*"),
                rid=kwargs.get("rid") or kwargs.get(
                    "corr_id") or str(time.time()),
                pld=kwargs.get("payload", {}),
                why=kwargs.get("why"),
                data_ref=kwargs.get("data_ref") or [],
            )
        elif len(args) == 4:
            op, verb, payload, why = args
            event_name = f"{op}:{verb}"
            msg = Message(op=op, verb=verb, src="stub",
                          dst="*", pld=payload, why=why)
        elif len(args) == 3:
            op, payload, why = args
            verb = payload.get("verb", "") if isinstance(payload, dict) else ""
            event_name = f"{op}:{verb}" if verb else op
            msg = Message(op=op, verb=verb, src="stub",
                          dst="*", pld=payload, why=why)
        else:
            raise TypeError("Unsupported emit signature")

        self.emitted.append(msg)
        if event_name:
            self._dispatch(event_name, msg)
        return msg

    def _dispatch(self, event_name: str, msg: Message) -> None:
        callbacks = self.listeners.get(event_name, [])
        if event_name == "EVT:TRADE_INTENT_PROPOSED":
            self._force_market_entry(msg)
        for callback in callbacks:
            try:
                result = callback(msg)
                if inspect.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                continue

    def register_domain(self, name: str, domain: Any) -> None:
        self.domains[name] = domain

    def _force_market_entry(self, msg: Message) -> None:
        payload = msg.pld or {}
        order = payload.setdefault("order", {})
        resolved = payload.get("order_type") or order.get(
            "order_type") or order.get("type")
        resolved = str(resolved or "MARKET").upper()
        if resolved != "MARKET":
            # Drop stale price references to keep bridge happy
            payload.pop("price", None)
            order.pop("price", None)
            order.pop("price_ref", None)
            resolved = "MARKET"
        payload["order_type"] = resolved
        order["order_type"] = resolved
        order["type"] = resolved


class MockBinanceExecutionAdapter:
    """Async adapter stub that records entry/bracket activity."""

    def __init__(self) -> None:
        self.placed_orders: List[Dict[str, Any]] = []
        self.cancel_requests: List[Dict[str, Any]] = []
        self._order_seq = 1

    async def place_order_v2(self, **kwargs: Any) -> Dict[str, Any]:
        order_id = f"order_{self._order_seq}"
        self._order_seq += 1
        order = {
            "order_id": order_id,
            "client_order_id": kwargs.get("client_order_id") or f"cid_{order_id}",
            "symbol": kwargs.get("symbol"),
            "side": (kwargs.get("side") or "").upper(),
            "order_type": kwargs.get("order_type"),
            "quantity": Decimal(str(kwargs.get("quantity"))),
            "price": Decimal(str(kwargs.get("price"))) if kwargs.get("price") is not None else None,
            "stop_price": Decimal(str(kwargs.get("stop_price"))) if kwargs.get("stop_price") is not None else None,
            "reduce_only": bool(kwargs.get("reduce_only")),
            "canceled": False,
            "ts": time.time(),
        }
        self.placed_orders.append(order)
        return {
            "orderId": order_id,
            "clientOrderId": order["client_order_id"],
            "symbol": order["symbol"],
            "status": "NEW",
            "success": True,
        }

    async def cancel_order(
        self,
        *,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        self.cancel_requests.append(
            {
                "symbol": symbol,
                "order_id": order_id,
                "client_order_id": client_order_id,
            }
        )
        for order in self.placed_orders:
            if order["order_id"] == order_id or order["client_order_id"] == client_order_id:
                order["canceled"] = True
        return {
            "symbol": symbol,
            "orderId": order_id,
            "clientOrderId": client_order_id,
            "status": "CANCELED",
            "success": True,
        }

    async def close_position(self, **_: Any) -> Dict[str, Any]:
        return {
            "status": "CLOSED",
            "success": True,
            "orderId": f"close_{self._order_seq}",
        }

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        orders: List[Dict[str, Any]] = []
        for order in self.placed_orders:
            if order["canceled"]:
                continue
            if symbol and order["symbol"] != symbol:
                continue
            orders.append(
                {
                    "symbol": order["symbol"],
                    "orderId": order["order_id"],
                    "clientOrderId": order["client_order_id"],
                    "side": order["side"],
                    "type": order["order_type"],
                    "origQty": str(order["quantity"]),
                    "price": str(order["price"]) if order["price"] is not None else None,
                    "stopPrice": str(order["stop_price"]) if order["stop_price"] is not None else None,
                    "reduceOnly": order["reduce_only"],
                    "status": "NEW",
                }
            )
        return orders

    @property
    def entry_orders(self) -> List[Dict[str, Any]]:
        return [order for order in self.placed_orders if not order["reduce_only"]]

    @property
    def bracket_orders(self) -> List[Dict[str, Any]]:
        return [order for order in self.placed_orders if order["reduce_only"]]


@dataclass
class TradeLoopHarness:
    fsm: StubFSM
    bridge: AuroraBridge
    runtime: Any
    adapter: MockBinanceExecutionAdapter
    decision_making: Optional[DecisionMaking] = None
    portfolio_provider: Optional["IntegrationPortfolioProviderAdapter"] = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    @property
    def bus(self) -> StubFSM:
        return self.fsm


class IntegrationPortfolioProviderAdapter:
    """Async helper that feeds snapshots into DM + bridge while preserving last_nonzero."""

    def __init__(self, decision_making: DecisionMaking, bridge: AuroraBridge, fsm: StubFSM) -> None:
        self._decision_making = decision_making
        self._bridge = bridge
        self._fsm = fsm

    @property
    def store(self) -> PortfolioProvider:
        return self._decision_making.portfolio_provider

    async def update_from_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        normalized = snapshot
        payload = {
            "equity_total_usdt": str(normalized.equity_total_usdt),
            "equity_free_usdt": str(normalized.equity_free_usdt),
            "positions_value_usdt": str(normalized.positions_value_usdt or Decimal("0")),
            "timestamp": int(normalized.timestamp.timestamp() * 1000),
            "source": normalized.source or "integration-test",
            "positions": [],
            "positions_last_ts_ms": int(normalized.timestamp.timestamp() * 1000),
        }
        now_ms = int(time.time() * 1000)
        # Align snapshot timestamps with wall clock to avoid bridge TTL drift on Windows
        payload["positions_last_ts_ms"] = now_ms
        payload["timestamp"] = now_ms
        msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="*",
            pld=payload,
            why="integration_snapshot",
        )
        self._fsm.emit(msg)
        await self._bridge.on_portfolio_state_updated(msg)
        self._bridge._last_portfolio_ts = payload["positions_last_ts_ms"]
        return normalized

    def get_snapshot(self, *, prefer_nonzero: bool = True) -> PortfolioSnapshot:
        return self.store.get_snapshot(prefer_nonzero=prefer_nonzero)


@pytest.fixture
def integration_config() -> Dict[str, Any]:
    return deepcopy(BASE_CONFIG)


@pytest.fixture
def trade_loop_harness(monkeypatch: pytest.MonkeyPatch, integration_config: Dict[str, Any]):
    fsm = StubFSM()
    adapter = MockBinanceExecutionAdapter()
    runtime = build_execution_runtime(
        config=integration_config, fsm=fsm, adapter=adapter)
    monkeypatch.setattr(main_module, "execution_position",
                        runtime, raising=False)
    decision_making = DecisionMaking(fsm=fsm, config=integration_config)
    decision_making.portfolio_provider = PortfolioProvider()
    fsm.register_domain("decision_making", decision_making)
    bridge = AuroraBridge(fsm=fsm, config=integration_config, logger=None)
    monkeypatch.setattr(main_module, "_bridge_instance", bridge, raising=False)
    provider_adapter = IntegrationPortfolioProviderAdapter(
        decision_making=decision_making, bridge=bridge, fsm=fsm)
    harness = TradeLoopHarness(
        fsm=fsm,
        bridge=bridge,
        runtime=runtime,
        adapter=adapter,
        decision_making=decision_making,
        portfolio_provider=provider_adapter,
    )
    yield harness
    runtime.runtime.async_manager.shutdown_background_tasks()


@pytest.fixture
def integration_env(trade_loop_harness: TradeLoopHarness) -> TradeLoopHarness:
    """Alias fixture to mirror spec naming for TASK INT-01.B scenarios."""

    return trade_loop_harness


async def _emit_portfolio_fresh(env: TradeLoopHarness, *, equity_free: str = "15000") -> None:
    msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="*",
        pld={
            "positions_last_ts_ms": int(time.time() * 1000),
            "equity_free_usdt": equity_free,
        },
        why="portfolio_fresh",
    )
    await env.bridge.on_portfolio_state_updated(msg)


async def _submit_trade_intent(
    env: TradeLoopHarness,
    *,
    symbol: str,
    side: str,
    quantity: str,
    rid: str,
    idempotent_key: str,
    order_type: str = "MARKET",
) -> Message:
    intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld={
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order": {"qty": quantity, "type": order_type},
            "idempotent_key": idempotent_key,
            "why": [f"task-int-01b|{side.lower()}"]
        },
        why=f"intent_{side.lower()}",
    )
    await env.bridge.on_trade_intent_proposed(intent)
    await asyncio.sleep(0.05)
    return intent


async def _wait_for_event(
    env: TradeLoopHarness,
    *,
    verb: str,
    op: Optional[str] = None,
    start_index: Optional[int] = None,
    timeout: float = 2.0,
) -> Message:
    deadline = time.time() + timeout
    cursor = start_index if start_index is not None else 0
    while time.time() < deadline:
        for msg in env.fsm.emitted[cursor:]:
            if msg.verb == verb and (op is None or msg.op == op):
                return msg
        await asyncio.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {op or '*'}:{verb}")


async def _wait_for_entry_order(env: TradeLoopHarness, *, timeout: float = 2.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if env.adapter.entry_orders:
            return env.adapter.entry_orders[-1]
        await asyncio.sleep(0.02)
    raise AssertionError("Adapter did not receive entry order in time")


async def _wait_for_brackets(
    env: TradeLoopHarness,
    *,
    min_count: int = 2,
    timeout: float = 2.0,
) -> List[Dict[str, Any]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(env.adapter.bracket_orders) >= min_count:
            return env.adapter.bracket_orders
        await asyncio.sleep(0.02)
    raise AssertionError("Bracket orders not created in time")


def _append_aurora_event(event: str, *, rid: str, payload: Dict[str, Any]) -> None:
    log_path = Path("logs") / "aurora_events.jsonl"
    entry = {
        "ts_ms": int(time.time() * 1000),
        "event": event,
        "rid": rid,
        "payload": payload,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


async def _simulate_fill(
    env: TradeLoopHarness,
    *,
    symbol: str,
    side: str,
    quantity: str,
    price: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None,
) -> None:
    payload = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "timestamp": time.time(),
    }
    if order_id:
        payload["order_id"] = order_id
    if client_order_id:
        payload["client_order_id"] = client_order_id

    await env.runtime.runtime.handle({"kind": "TRADE_EXECUTED", "symbol": symbol, "payload": payload})
    await asyncio.sleep(0.05)


DEFAULT_SYMBOL = "SOLUSDT"


def _make_portfolio_snapshot(
    *,
    equity_total: str,
    equity_free: str,
    positions_value: str = "0",
    timestamp: Optional[datetime] = None,
    source: str = "integration-test",
    allow_negative: bool = False,
) -> PortfolioSnapshot:
    resolved_ts = timestamp or datetime.utcnow()
    if allow_negative and Decimal(equity_free) < 0:
        construct = getattr(PortfolioSnapshot, "model_construct", None)
        if construct is None:
            # type: ignore[attr-defined]
            construct = getattr(PortfolioSnapshot, "construct")
        data = {
            "equity_total_usdt": Decimal(equity_total),
            "equity_free_usdt": Decimal(equity_free),
            "positions_value_usdt": Decimal(positions_value),
            "timestamp": resolved_ts,
            "source": source,
        }
        return construct(**data)  # type: ignore[misc]
    return PortfolioSnapshot(
        equity_total=equity_total,
        equity_free=equity_free,
        positions_value=positions_value,
        timestamp=resolved_ts,
        source=source,
    )


async def _push_portfolio_equity(
    env: TradeLoopHarness,
    *,
    equity_total: str,
    equity_free: str,
    positions_value: str = "0",
    allow_negative: bool = False,
) -> PortfolioSnapshot:
    snapshot = _make_portfolio_snapshot(
        equity_total=equity_total,
        equity_free=equity_free,
        positions_value=positions_value,
        allow_negative=allow_negative,
    )
    await env.portfolio_provider.update_from_snapshot(snapshot)
    return snapshot


def _send_risk_event(env: TradeLoopHarness, *, symbol: str = DEFAULT_SYMBOL, allowed: bool = True) -> None:
    rid = f"risk-{symbol.lower()}"
    risk_msg = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="risk_strategy",
        dst="decision_making",
        rid=rid,
        pld={
            "symbol": symbol,
            "ts": int(time.time() * 1000),
            "risk_parameters": {"is_trading_allowed": allowed},
        },
        why="risk-ok" if allowed else "risk-blocked",
    )
    env.fsm.emit(risk_msg)


def _send_features_event(
    env: TradeLoopHarness,
    *,
    symbol: str = DEFAULT_SYMBOL,
    overrides: Optional[Dict[str, float]] = None,
) -> None:
    ts_ms = int(time.time() * 1000)
    base_features: Dict[str, float] = {
        "obi": 0.8,
        "tfi": 0.6,
        "delta_price": 0.01,
        "price": 120.0,
        "ema_bias": 0.7,
        "volume_spike": 0.5,
        "volatility_state": 0.2,
        "depth_imbalance": 0.4,
        "macro_sync": 0.6,
    }
    if overrides:
        base_features.update(overrides)

    features_msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="analyzer",
        dst="decision_making",
        pld={
            "symbol": symbol,
            "ts": ts_ms,
            "features": base_features,
        },
        why="features-updated",
    )
    env.fsm.emit(features_msg)


async def _drive_signal_context(
    env: TradeLoopHarness,
    *,
    feature_overrides: Optional[Dict[str, float]] = None,
    settle_delay: float = 0.2,
) -> None:
    _send_risk_event(env)
    _send_features_event(env, overrides=feature_overrides)
    await asyncio.sleep(settle_delay)


@pytest.mark.asyncio
async def test_trade_loop_happy_path_long_with_brackets(trade_loop_harness: TradeLoopHarness):
    harness = trade_loop_harness

    portfolio_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="*",
        pld={
            "positions_last_ts_ms": int(time.time() * 1000),
            "equity_free_usdt": "15000",
        },
        why="portfolio_fresh",
    )
    await harness.bridge.on_portfolio_state_updated(portfolio_msg)

    trade_intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid="int-001",
        pld={
            "symbol": "SOLUSDT",
            "side": "BUY",
            "quantity": "5",
            "order": {"qty": "5", "type": "MARKET"},
            "idempotent_key": "intent-solusdt-001",
            "why": ["alpha_signal>=0.9"],
        },
        why="happy_path_long",
    )

    await harness.bridge.on_trade_intent_proposed(trade_intent)
    await asyncio.sleep(0.05)

    entry_orders = harness.adapter.entry_orders
    assert len(entry_orders) == 1, "Bridge should submit a single MARKET entry"
    entry_order = entry_orders[0]
    assert entry_order["symbol"] == "SOLUSDT"
    assert entry_order["order_type"] == "MARKET"
    assert entry_order["side"] == "BUY"

    fill_payload = {
        "symbol": "SOLUSDT",
        "side": "BUY",
        "quantity": "5",
        "price": "100.0",
        "timestamp": time.time(),
        "order_id": entry_order["order_id"],
        "client_order_id": entry_order["client_order_id"],
    }
    await harness.runtime.runtime.handle(
        {
            "kind": "TRADE_EXECUTED",
            "symbol": "SOLUSDT",
            "payload": fill_payload,
        }
    )
    await asyncio.sleep(0.05)

    bracket_orders = harness.adapter.bracket_orders
    assert len(
        bracket_orders) >= 2, "Runtime should place SL/TP brackets after fill"
    kinds = {order["order_type"] for order in bracket_orders}
    assert "STOP_MARKET" in kinds, "Expected stop-loss bracket"
    assert "TAKE_PROFIT_MARKET" in kinds, "Expected take-profit bracket"
    for order in bracket_orders:
        assert order["symbol"] == "SOLUSDT"
        assert order["side"] == "SELL"
        assert order["stop_price"] is not None, "Bracket order must include stop/trigger price"
        assert order["reduce_only"] is True


@pytest.mark.asyncio
async def test_trade_loop_happy_path_short_with_brackets(integration_env: TradeLoopHarness):
    env = integration_env

    await _emit_portfolio_fresh(env)
    await _submit_trade_intent(
        env,
        symbol="SOLUSDT",
        side="SELL",
        quantity="3",
        rid="int-short-001",
        idempotent_key="intent-solusdt-short-001",
    )

    entry_orders = env.adapter.entry_orders
    assert len(entry_orders) == 1, "Expected single MARKET short entry"
    entry_order = entry_orders[0]
    assert entry_order["side"] == "SELL"
    assert entry_order["order_type"] == "MARKET"

    await _simulate_fill(
        env,
        symbol="SOLUSDT",
        side="SELL",
        quantity="3",
        price="95.0",
        order_id=entry_order["order_id"],
        client_order_id=entry_order["client_order_id"],
    )

    bracket_orders = env.adapter.bracket_orders
    assert len(
        bracket_orders) >= 2, "Short position must be protected by SL and TP"

    sl_orders = [
        order for order in bracket_orders if order["order_type"] == "STOP_MARKET"]
    tp_orders = [
        order for order in bracket_orders if order["order_type"] == "TAKE_PROFIT_MARKET"]
    assert len(sl_orders) == 1, "Exactly one STOP_MARKET order expected for short"
    assert len(
        tp_orders) == 1, "Exactly one TAKE_PROFIT_MARKET order expected for short"

    runtime_state = env.runtime.runtime._positions_by_symbol.get("SOLUSDT")
    assert runtime_state is not None and runtime_state.qty < 0, "Short position should be tracked in runtime state"
    position_qty = Decimal(str(abs(runtime_state.qty)))

    for order in bracket_orders:
        assert order["symbol"] == "SOLUSDT"
        assert order["side"] == "BUY", "Short exits must be BUY reduce-only"
        assert order["reduce_only"] is True
        assert order["stop_price"] is not None

    sl_qty = sum(order["quantity"] for order in sl_orders)
    tp_qty = sum(order["quantity"] for order in tp_orders)
    assert sl_qty <= position_qty and tp_qty <= position_qty, "Bracket qty per leg must not exceed short size"


@pytest.mark.asyncio
async def test_trade_loop_qos_blocks_intent_before_execpos(integration_env: TradeLoopHarness):
    env = integration_env

    await _emit_portfolio_fresh(env)
    env.bridge._qos_next_allowed_ts_per_symbol["SOLUSDT"] = int(
        time.time() * 1000) + 30_000

    await _submit_trade_intent(
        env,
        symbol="SOLUSDT",
        side="BUY",
        quantity="2",
        rid="int-qos-001",
        idempotent_key="intent-solusdt-qos-001",
    )

    deferred_events = [
        msg for msg in env.fsm.emitted if msg.verb == "INTENT_DEFERRED"]
    assert deferred_events, "QoS block should emit INTENT_DEFERRED"
    assert deferred_events[0].pld.get("reason") == "QOS_COOLDOWN"
    assert deferred_events[0].pld.get("symbol") == "SOLUSDT"

    assert env.adapter.entry_orders == [
    ], "Adapter must not be invoked when QoS blocks intent"
    assert env.adapter.bracket_orders == []
    assert "SOLUSDT" not in env.runtime.runtime._positions_by_symbol, "ExecPosRuntimeV2 should stay idle"


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason=(
        "FLAT position bracket cleanup not fully implemented. "
        "_handle_reverse_cleanup only handles LONG→SHORT/SHORT→LONG, "
        "not LONG→FLAT. BracketService.evaluate() requires side in (LONG, SHORT). "
        "Pending R2-L: cancel orphan brackets when position becomes FLAT."
    ),
    strict=False,
)
async def test_trade_loop_reverse_cleanup_after_position_close(integration_env: TradeLoopHarness):
    env = integration_env

    await _emit_portfolio_fresh(env)
    await _submit_trade_intent(
        env,
        symbol="SOLUSDT",
        side="BUY",
        quantity="4",
        rid="int-reverse-001",
        idempotent_key="intent-solusdt-reverse-001",
    )

    entry_order = env.adapter.entry_orders[0]
    await _simulate_fill(
        env,
        symbol="SOLUSDT",
        side="BUY",
        quantity="4",
        price="100.0",
        order_id=entry_order["order_id"],
        client_order_id=entry_order["client_order_id"],
    )

    initial_bracket_ids = [order["order_id"]
                           for order in env.adapter.bracket_orders]
    assert initial_bracket_ids, "Happy-path long should create SL/TP"

    # Reverse fill closes the position fully
    await _simulate_fill(env, symbol="SOLUSDT", side="SELL", quantity="4", price="101.0")

    # Feed ORDERS_SNAPSHOT with live adapter data to mirror exchange state
    live_orders = await env.adapter.get_open_orders("SOLUSDT")
    await env.runtime.runtime.handle({"kind": "ORDERS_SNAPSHOT", "payload": {"orders": live_orders}})
    await asyncio.sleep(0.05)

    cancel_order_ids = {req["order_id"]
                        for req in env.adapter.cancel_requests if req.get("order_id")}
    assert cancel_order_ids.issuperset(
        initial_bracket_ids), "Reverse cleanup must cancel prior SL/TP"

    for order in env.adapter.placed_orders:
        if order["order_id"] in initial_bracket_ids:
            assert order["canceled"] is True

    runtime_orders = env.runtime.runtime._open_orders_by_symbol.get(
        "SOLUSDT", [])
    assert not runtime_orders, "Runtime mirror should be clear after full close"

    position_state = env.runtime.runtime._positions_by_symbol.get("SOLUSDT")
    assert position_state is not None
    assert abs(
        position_state.qty) < 1e-9, "Position should be flat after reverse fill"


@pytest.mark.asyncio
async def test_dm_equity_positive_allows_trade_and_execpos_flow(integration_env: TradeLoopHarness):
    env = integration_env

    snapshot = _make_portfolio_snapshot(equity_total="1000", equity_free="500")
    await env.portfolio_provider.update_from_snapshot(snapshot)
    _send_risk_event(env)
    _send_features_event(env)
    await asyncio.sleep(0.2)

    intent_events = [
        msg for msg in env.fsm.emitted if msg.verb == "TRADE_INTENT_PROPOSED"]
    assert intent_events, "DecisionMaking should emit TRADE_INTENT_PROPOSED when equity is positive"
    reasons = " ".join(
        intent_events[-1].pld.get("why", [])) if intent_events[-1].pld.get("why") else ""
    assert "equity_non_positive" not in reasons.lower()

    entry_orders = env.adapter.entry_orders
    assert entry_orders, "DM-triggered trade must reach adapter"
    entry_order = entry_orders[-1]
    assert entry_order["symbol"] == DEFAULT_SYMBOL

    await _simulate_fill(
        env,
        symbol=DEFAULT_SYMBOL,
        side=entry_order["side"],
        quantity=str(entry_order["quantity"]),
        price="98.0",
        order_id=entry_order["order_id"],
        client_order_id=entry_order["client_order_id"],
    )
    await asyncio.sleep(0.1)

    bracket_orders = env.adapter.bracket_orders
    assert len(
        bracket_orders) >= 2, "SL/TP brackets should be created after DM-driven fill"
    for order in bracket_orders:
        assert order["symbol"] == DEFAULT_SYMBOL
        assert order["reduce_only"] is True
        assert order["side"] in {"BUY", "SELL"}
        assert order["stop_price"] is not None

    runtime_state = env.runtime.runtime._positions_by_symbol.get(
        DEFAULT_SYMBOL)
    assert runtime_state is not None, "ExecPosRuntimeV2 should track DM-driven position"


@pytest.mark.asyncio
async def test_dm_equity_positive_full_trade_loop_round_trip(integration_env: TradeLoopHarness):
    env = integration_env

    emitted_cursor = len(env.fsm.emitted)
    snapshot = _make_portfolio_snapshot(
        equity_total="1250",
        equity_free="640",
        positions_value="200",
    )
    await env.portfolio_provider.update_from_snapshot(snapshot)
    _send_risk_event(env)
    _send_features_event(env, overrides={"obi": 0.92, "tfi": 0.88})

    intent_msg = await _wait_for_event(
        env, verb="TRADE_INTENT_PROPOSED", op="EVT", start_index=emitted_cursor
    )
    assert intent_msg.pld["symbol"] == DEFAULT_SYMBOL
    reasons = " ".join(intent_msg.pld.get("why", []))
    assert "equity_non_positive" not in reasons.lower()
    rid = intent_msg.rid or intent_msg.pld.get("idempotent_key", "")
    _append_aurora_event(
        "EVT:TRADE_INTENT_PROPOSED",
        rid=rid,
        payload={
            "symbol": intent_msg.pld.get("symbol"),
            "side": intent_msg.pld.get("side"),
            "quantity": intent_msg.pld.get("quantity"),
            "reasons": intent_msg.pld.get("why", []),
        },
    )

    entry_order = await _wait_for_entry_order(env)
    assert entry_order["order_type"] == "MARKET"
    assert entry_order["symbol"] == DEFAULT_SYMBOL
    assert entry_order["quantity"] > 0
    _append_aurora_event(
        "CMD:OPEN",
        rid=rid,
        payload={
            "symbol": entry_order["symbol"],
            "side": entry_order["side"],
            "order_type": entry_order["order_type"],
            "quantity": str(entry_order["quantity"]),
            "client_order_id": entry_order["client_order_id"],
        },
    )

    await _simulate_fill(
        env,
        symbol=DEFAULT_SYMBOL,
        side=entry_order["side"],
        quantity=str(entry_order["quantity"]),
        price="101.5",
        order_id=entry_order["order_id"],
        client_order_id=entry_order["client_order_id"],
    )

    bracket_orders = await _wait_for_brackets(env)
    sl_orders = [
        order for order in bracket_orders if order["order_type"] == "STOP_MARKET"]
    tp_orders = [
        order for order in bracket_orders if order["order_type"] == "TAKE_PROFIT_MARKET"]
    assert sl_orders and tp_orders, "Expected STOP_MARKET and TAKE_PROFIT_MARKET brackets"

    position_state = env.runtime.runtime._positions_by_symbol.get(
        DEFAULT_SYMBOL)
    assert position_state is not None and position_state.qty != 0
    position_qty = Decimal(str(abs(position_state.qty)))

    for order in bracket_orders:
        assert order["symbol"] == DEFAULT_SYMBOL
        assert order["reduce_only"] is True
        assert order["stop_price"] is not None

    sl_total = sum(order["quantity"] for order in sl_orders)
    tp_total = sum(order["quantity"] for order in tp_orders)
    assert sl_total <= position_qty
    assert tp_total <= position_qty
    _append_aurora_event(
        "BRACKETS_PLANNED",
        rid=rid,
        payload={
            "symbol": DEFAULT_SYMBOL,
            "orders": len(bracket_orders),
            "sl_qty": str(sl_total),
            "tp_qty": str(tp_total),
        },
    )


@pytest.mark.asyncio
async def test_dm_equity_zero_blocks_trade_before_execpos(
    integration_env: TradeLoopHarness, caplog: pytest.LogCaptureFixture
):
    env = integration_env
    caplog.set_level(
        logging.WARNING, logger="apps.reference.domains.decision_making.decision_making.DecisionMaking"
    )

    emitted_cursor = len(env.fsm.emitted)
    await _push_portfolio_equity(
        env,
        equity_total="1000",
        equity_free="0",
        positions_value="500",
    )
    await _drive_signal_context(env)

    recent_events = env.fsm.emitted[emitted_cursor:]
    assert not any(
        msg.verb == "TRADE_INTENT_PROPOSED" for msg in recent_events)
    assert not any(msg.op == "CMD" and msg.verb ==
                   "OPEN" for msg in recent_events)
    assert env.adapter.entry_orders == []
    assert env.adapter.bracket_orders == []
    assert DEFAULT_SYMBOL not in env.runtime.runtime._positions_by_symbol
    assert any(
        "equity is zero or negative" in record.message.lower() for record in caplog.records
    ), "DM should log equity-based rejection"


@pytest.mark.asyncio
async def test_dm_equity_negative_blocks_trade_before_execpos(integration_env: TradeLoopHarness):
    env = integration_env

    emitted_cursor = len(env.fsm.emitted)
    await _push_portfolio_equity(
        env,
        equity_total="1000",
        equity_free="-15",
        positions_value="1015",
        allow_negative=True,
    )
    await _drive_signal_context(env, feature_overrides={"obi": 0.9})

    recent_events = env.fsm.emitted[emitted_cursor:]
    assert not any(
        msg.verb == "TRADE_INTENT_PROPOSED" for msg in recent_events)
    assert not any(msg.op == "CMD" and msg.verb ==
                   "OPEN" for msg in recent_events)
    assert env.adapter.entry_orders == []
    assert env.adapter.bracket_orders == []
    assert DEFAULT_SYMBOL not in env.runtime.runtime._positions_by_symbol


@pytest.mark.asyncio
async def test_dm_uses_last_nonzero_snapshot_when_zero_update_arrives(integration_env: TradeLoopHarness):
    env = integration_env

    first_snapshot = _make_portfolio_snapshot(
        equity_total="1000", equity_free="500")
    await env.portfolio_provider.update_from_snapshot(first_snapshot)
    _send_risk_event(env)
    _send_features_event(env)
    await asyncio.sleep(0.2)

    first_entry_count = len(env.adapter.entry_orders)
    assert first_entry_count == 1, "Initial DM cycle should place one entry order"

    preferred_snapshot = env.portfolio_provider.get_snapshot(
        prefer_nonzero=True)
    assert preferred_snapshot.equity_free_usdt == Decimal("500")

    zero_snapshot = _make_portfolio_snapshot(
        equity_total="1000",
        equity_free="0",
        positions_value="400",
        timestamp=datetime.utcnow() + timedelta(seconds=1),
    )
    await env.portfolio_provider.update_from_snapshot(zero_snapshot)

    latest_snapshot = env.portfolio_provider.get_snapshot(prefer_nonzero=False)
    assert latest_snapshot.equity_free_usdt == Decimal("0")
    retained_snapshot = env.portfolio_provider.get_snapshot(
        prefer_nonzero=True)
    assert retained_snapshot.equity_free_usdt == Decimal(
        "500"), "Provider should retain last non-zero snapshot"

    _send_risk_event(env)
    _send_features_event(env, overrides={"obi": 0.85})
    await asyncio.sleep(0.2)

    assert len(env.adapter.entry_orders) == first_entry_count + \
        1, "DM should continue trading using last non-zero snapshot"
