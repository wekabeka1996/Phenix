"""
Tests for DecisionMaking._handle_regime_flip() method.
Validates that regime conflicts trigger reduce-only close intents.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.config_models import create_aurora_config
from apps.reference.domains.decision_making.core.facade import DecisionMaking


def _to_dict(obj):
    if isinstance(obj, SimpleNamespace):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    return obj


class _Bus:
    def __init__(self) -> None:
        self.emits: list[tuple[str, dict | None, str | None, object]] = []

    def listen(self, _event: str, _handler: object) -> None:
        return

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
    ) -> None:
        self.emits.append((event_name, payload, why, data_ref))


def _dm_cfg():
    qos = SimpleNamespace(
        exposure_block_cooldown_sec=0,
        max_intents_per_minute_per_symbol=1000,
        mode="shadow",
        symbol_cooldown_sec=0,
        enforce=False,
    )
    position_sizing = SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000)
    arming = SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1)
    features = SimpleNamespace(ttl_sec=60)
    bar_gating = SimpleNamespace(enable=False, bar_ms=60_000)
    behavior_fsm = SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5)
    risk_skew = SimpleNamespace(
        max_skew_sec=5,
        max_defer_count=3,
        defer_cooldown_sec=2,
        defer_window_sec=60,
        until_refresh_retry_sec=30,
    )
    risk_gate = SimpleNamespace(
        threshold_pct_testnet=20.0,
        threshold_pct_production=50.0,
        min_intents_for_check=10,
    )
    flip = SimpleNamespace(enabled=True)
    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        risk_skew=risk_skew,
        risk_gate=risk_gate,
        flip=flip,
    )


def _dm_domain_cfg():
    risk_gate = SimpleNamespace(
        min_intents_for_check=100,
        threshold_pct_testnet=90.0,
        threshold_pct_production=80.0,
    )
    return SimpleNamespace(risk_gate=risk_gate)


def _mk_cfg(*, symbol: str, stale_ttl_sec: int = 15):
    return SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": "neutral"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200},
            mode="testnet",
        ),
        domains=SimpleNamespace(
            decision_making=_dm_cfg(),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=stale_ttl_sec),
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    retry_ttl_ms=60_000,
                    signal_threshold=0.0,
                    retry_max_count=3,
                    retry_backoff_factor=1.5,
                ),
                assets={symbol: SimpleNamespace(position_mode="STRICT")},
            )
        ),
        instruments={
            symbol: SimpleNamespace(
                tick_size="0.1",
                step_size="0.001",
                min_qty="0.001",
                min_notional="5",
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=20,
                    leverage_policy="verify_only",
                ),
                sizing=SimpleNamespace(margin_pct=0.02),
                flip=SimpleNamespace(enabled=True, hysteresis_mult=1.3),
            )
        },
        strategies_registry=None,
    )


def _bind_registry_owner(dm: DecisionMaking, symbol: str, strategy_id: str = "aurora") -> None:
    dm._emitter._registry_lookup_fn = (  # type: ignore[attr-defined]
        lambda lookup_symbol: [strategy_id] if lookup_symbol == symbol else []
    )


def test_regime_flip_short_in_trend_up_emits_reduce_only_close():
    """
    REGIME FLIP: Short position in TREND_UP regime should trigger reduce-only close.
    """
    bus = _Bus()
    symbol = "BTCUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=create_aurora_config(_to_dict(cfg)))
    _bind_registry_owner(dm, symbol)

    # Set portfolio: SHORT position (negative qty)
    now_ms = int(time.time() * 1000)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "positionAmt": "-0.5", "avg_entry_price": "42000"}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    # Mock _propose_trade_intent to capture the call
    captured = []

    def _mock_propose(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        captured.append({
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "reduce_only": reduce_only,
            "why_chain": why_chain,
        })

    dm._propose_trade_intent = _mock_propose  # type: ignore[method-assign]

    # Trigger regime flip: TREND_UP conflicts with SHORT
    regime_data = {"regime": "TREND_UP"}
    dm._handle_regime_flip(symbol, regime_data)

    assert len(captured) == 1, "Expected one reduce-only close intent"
    intent = captured[0]
    assert intent["symbol"] == symbol
    assert intent["side"] == "BUY", "Should close SHORT with BUY"
    assert intent["reduce_only"] is True
    assert intent["qty"] == "0.5"
    assert "flip_orchestration_close" in intent["why_chain"]
    assert "regime_flip_TREND_UP" in intent["why_chain"]


def test_regime_flip_long_in_trend_down_emits_reduce_only_close():
    """
    REGIME FLIP: Long position in TREND_DOWN regime should trigger reduce-only close.
    """
    bus = _Bus()
    symbol = "ETHUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=create_aurora_config(_to_dict(cfg)))
    _bind_registry_owner(dm, symbol)

    # Set portfolio: LONG position (positive qty)
    now_ms = int(time.time() * 1000)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "positionAmt": "2.5", "avg_entry_price": "2800"}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    captured = []

    def _mock_propose(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        captured.append({
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "reduce_only": reduce_only,
            "why_chain": why_chain,
        })

    dm._propose_trade_intent = _mock_propose  # type: ignore[method-assign]

    # Trigger regime flip: TREND_DOWN conflicts with LONG
    regime_data = {"regime": "TREND_DOWN"}
    dm._handle_regime_flip(symbol, regime_data)

    assert len(captured) == 1
    intent = captured[0]
    assert intent["side"] == "SELL", "Should close LONG with SELL"
    assert intent["reduce_only"] is True
    assert intent["qty"] == "2.5"
    assert "flip_orchestration_close" in intent["why_chain"]
    assert "regime_flip_TREND_DOWN" in intent["why_chain"]


def test_regime_flip_uncertain_closes_any_position():
    """
    REGIME FLIP: UNCERTAIN regime should close any position (LONG or SHORT).
    """
    bus = _Bus()
    symbol = "SOLUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=create_aurora_config(_to_dict(cfg)))
    _bind_registry_owner(dm, symbol)

    # Set portfolio: LONG position
    now_ms = int(time.time() * 1000)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "positionAmt": "10.0", "avg_entry_price": "150"}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    captured = []

    def _mock_propose(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        captured.append({
            "symbol": symbol,
            "side": side,
            "reduce_only": reduce_only,
            "why_chain": why_chain,
        })

    dm._propose_trade_intent = _mock_propose  # type: ignore[method-assign]

    # Trigger regime flip: UNCERTAIN
    regime_data = {"regime": "UNCERTAIN"}
    dm._handle_regime_flip(symbol, regime_data)

    assert len(captured) == 1
    intent = captured[0]
    assert intent["side"] == "SELL"
    assert intent["reduce_only"] is True
    assert "flip_orchestration_close" in intent["why_chain"]
    assert "regime_flip_UNCERTAIN" in intent["why_chain"]


def test_regime_flip_no_position_does_nothing():
    """
    REGIME FLIP: No position → no close intent emitted.
    """
    bus = _Bus()
    symbol = "BTCUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=create_aurora_config(_to_dict(cfg)))

    # Set portfolio: FLAT (no position)
    now_ms = int(time.time() * 1000)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "positionAmt": "0", "avg_entry_price": "0"}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    captured = []

    def _mock_propose(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        captured.append({"symbol": symbol})

    dm._propose_trade_intent = _mock_propose  # type: ignore[method-assign]

    regime_data = {"regime": "BULL_TREND"}
    dm._handle_regime_flip(symbol, regime_data)

    assert len(captured) == 0, "No close intent should be emitted for FLAT position"


def test_regime_flip_no_portfolio_does_nothing():
    """
    REGIME FLIP: No portfolio → fail-safe, no close.
    """
    bus = _Bus()
    symbol = "BTCUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=create_aurora_config(_to_dict(cfg)))

    # No portfolio
    dm.latest_portfolio = None

    captured = []

    def _mock_propose(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        captured.append({"symbol": symbol})

    dm._propose_trade_intent = _mock_propose  # type: ignore[method-assign]

    regime_data = {"regime": "BULL_TREND"}
    dm._handle_regime_flip(symbol, regime_data)

    assert len(captured) == 0


def test_regime_flip_long_in_bull_trend_does_nothing():
    """
    REGIME FLIP: Long position in BULL_TREND is OK → no close.
    """
    bus = _Bus()
    symbol = "BTCUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=create_aurora_config(_to_dict(cfg)))

    now_ms = int(time.time() * 1000)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "positionAmt": "1.0", "avg_entry_price": "42000"}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    captured = []

    def _mock_propose(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        captured.append({"symbol": symbol})

    dm._propose_trade_intent = _mock_propose  # type: ignore[method-assign]

    regime_data = {"regime": "BULL_TREND"}
    dm._handle_regime_flip(symbol, regime_data)

    assert len(captured) == 0, "Long in BULL_TREND should NOT trigger close"
