from __future__ import annotations

import time
import decimal

from vfoundation.core.fsm_core import FSMCore
from types import SimpleNamespace

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_models import create_aurora_config


def _to_dict(obj):
    if isinstance(obj, SimpleNamespace):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    return obj


def _seed_common_state(fsm: FSMCore, symbol: str) -> int:
    now_ms = int(time.time() * 1000)

    # Portfolio must exist for flip/exposure gates.
    fsm.emit(
        "EVT:PORTFOLIO_STATE_UPDATED",
        {"equity": "1000", "equity_free_usdt": "1000", "positions": []},
        why="test",
    )

    # Risk must exist for the strategy gateway.
    fsm.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {"symbol": symbol, "ts": now_ms, "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}},
        why="test",
    )

    # Features for TTL gate + sizing context.
    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        {"ts": now_ms, "symbol": symbol, "features": {"price": "100.0", "delta_price": "0.0"}},
        why="test",
    )

    return now_ms


def test_qos_is_applied_only_for_allowlisted_strategies_in_strategy_gateway() -> None:
    cfg = ConfigLoader().load_config()
    cfg.domains.decision_making.qos.apply_to_strategies = ["aurora"]

    fsm = FSMCore()
    dm = DecisionMaking(fsm=fsm, config=create_aurora_config(_to_dict(cfg)))
    dm.strategies_registry = None

    symbol = "ETHUSDT"
    now_ms = _seed_common_state(fsm, symbol)

    calls: list[str] = []

    def fake_qos_allow(sym: str, is_exposure_block: bool = False):
        calls.append(sym)
        return False, "symbol_cooldown_active_9.9s_remaining_limit=10s"

    dm._qos_allow = fake_qos_allow  # type: ignore[method-assign]

    # Aurora should invoke QoS.
    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "aurora", "symbol": symbol, "side": "BUY", "rid": "rid-aur", "ts_ms": now_ms, "why_chain": ["test"], "readiness": {"warmup_ok": True}},
        why="test",
    )
    assert calls == [symbol]

    calls.clear()

    # MeanReversion should skip QoS in the strategy gateway.
    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "mean_reversion", "symbol": symbol, "side": "BUY", "rid": "rid-mr", "ts_ms": now_ms, "why_chain": ["test"], "readiness": {"warmup_ok": True}},
        why="test",
    )
    assert calls == []


def test_mean_reversion_success_path_does_not_update_qos_state_when_disabled() -> None:
    cfg = ConfigLoader().load_config()
    cfg.domains.decision_making.qos.apply_to_strategies = ["aurora"]

    fsm = FSMCore()
    dm = DecisionMaking(fsm=fsm, config=create_aurora_config(_to_dict(cfg)))
    dm.strategies_registry = None

    symbol = "ETHUSDT"
    now_ms = _seed_common_state(fsm, symbol)

    proposed: list[dict] = []
    qos_updates: list[str] = []

    def no_qos_allow(*_a, **_k):
        raise AssertionError("QoS must not be called for mean_reversion when allowlisted only for aurora")

    def fake_calc_size(*_a, **_k):
        return decimal.Decimal("0.1"), "ok", None, {}

    dm._qos_allow = no_qos_allow  # type: ignore[method-assign]
    dm._calculate_position_size = fake_calc_size  # type: ignore[method-assign]
    dm._precheck_exposure_cache = lambda *_a, **_k: True  # type: ignore[method-assign]
    dm._warmup_gate_before_trade_intent = lambda *_a, **_k: False  # type: ignore[method-assign]
    dm._propose_trade_intent = lambda **kw: proposed.append(kw)  # type: ignore[method-assign]
    dm._update_qos_state = lambda sym: qos_updates.append(sym)  # type: ignore[method-assign]

    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {
            "strategy_id": "mean_reversion",
            "symbol": symbol,
            "side": "BUY",
            "rid": "rid-mr-success",
            "ts_ms": now_ms,
            "why_chain": ["test"],
            "price_ctx": {"entry_price": "100.0"},
            "readiness": {"warmup_ok": True},
            "volatility": {"atr_ready": True, "atr_14": "1.0"},
        },
        why="test",
    )

    assert proposed, "Expected strategy gateway to propose an intent"
    assert qos_updates == [], "QoS state must not update for mean_reversion when QoS is disabled for that strategy"


def test_empty_allowlist_applies_qos_to_all_strategies() -> None:
    cfg = ConfigLoader().load_config()
    cfg.domains.decision_making.qos.apply_to_strategies = []

    fsm = FSMCore()
    dm = DecisionMaking(fsm=fsm, config=create_aurora_config(_to_dict(cfg)))
    dm.strategies_registry = None

    symbol = "ETHUSDT"
    now_ms = _seed_common_state(fsm, symbol)

    calls: list[str] = []

    def fake_qos_allow(sym: str, is_exposure_block: bool = False):
        calls.append(sym)
        return True, None

    dm._qos_allow = fake_qos_allow  # type: ignore[method-assign]

    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "aurora", "symbol": symbol, "side": "BUY", "rid": "rid-aur", "ts_ms": now_ms, "why_chain": ["test"], "price_ctx": {"entry_price": "100.0"}, "readiness": {"warmup_ok": True}},
        why="test",
    )
    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "mean_reversion", "symbol": symbol, "side": "BUY", "rid": "rid-mr", "ts_ms": now_ms, "why_chain": ["test"], "price_ctx": {"entry_price": "100.0"}, "readiness": {"warmup_ok": True}},
        why="test",
    )

    assert calls == [symbol, symbol]


def test_allowlist_can_enable_qos_for_mean_reversion_and_block() -> None:
    cfg = ConfigLoader().load_config()
    cfg.domains.decision_making.qos.apply_to_strategies = ["mean_reversion"]

    fsm = FSMCore()
    dm = DecisionMaking(fsm=fsm, config=cfg)
    dm.strategies_registry = None

    symbol = "ETHUSDT"
    now_ms = _seed_common_state(fsm, symbol)

    qos_called: list[str] = []

    def fake_qos_allow(sym: str, is_exposure_block: bool = False):
        qos_called.append(sym)
        return False, "symbol_cooldown_active_9.9s_remaining_limit=10s"

    dm._qos_allow = fake_qos_allow  # type: ignore[method-assign]
    dm._propose_trade_intent = lambda **_kw: (_ for _ in ()).throw(AssertionError("intent must not be proposed when QoS blocks"))  # type: ignore[method-assign]

    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "mean_reversion", "symbol": symbol, "side": "BUY", "rid": "rid-mr", "ts_ms": now_ms, "why_chain": ["test"], "price_ctx": {"entry_price": "100.0"}, "readiness": {"warmup_ok": True}},
        why="test",
    )

    assert qos_called == [symbol]


def test_allowlist_unknown_skips_qos_for_all_strategies() -> None:
    cfg = ConfigLoader().load_config()
    cfg.domains.decision_making.qos.apply_to_strategies = ["some_other_strategy"]

    fsm = FSMCore()
    dm = DecisionMaking(fsm=fsm, config=cfg)
    dm.strategies_registry = None

    symbol = "ETHUSDT"
    now_ms = _seed_common_state(fsm, symbol)

    def no_qos_allow(*_a, **_k):
        raise AssertionError("QoS must not be called when allowlist excludes strategy_id")

    dm._qos_allow = no_qos_allow  # type: ignore[method-assign]

    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "aurora", "symbol": symbol, "side": "BUY", "rid": "rid-aur", "ts_ms": now_ms, "why_chain": ["test"], "price_ctx": {"entry_price": "100.0"}, "readiness": {"warmup_ok": True}},
        why="test",
    )
    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "mean_reversion", "symbol": symbol, "side": "BUY", "rid": "rid-mr", "ts_ms": now_ms, "why_chain": ["test"], "price_ctx": {"entry_price": "100.0"}, "readiness": {"warmup_ok": True}},
        why="test",
    )
