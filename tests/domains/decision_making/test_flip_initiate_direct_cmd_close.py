"""
Tests for DecisionMaking._initiate_flip_close() method.
Validates direct CMD:CLOSE emission (alternative flip path).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.decision_making.decision_making import DecisionMaking


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
    flip = SimpleNamespace(enabled=True, hysteresis_mult=1.0)
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


def test_initiate_flip_close_emits_cmd_close_directly():
    """
    _initiate_flip_close() should emit CMD:CLOSE directly (not reduce-only intent).
    This is an alternative flip path.
    """
    bus = _Bus()
    symbol = "BTCUSDT"
    cfg = _mk_cfg(symbol=symbol, stale_ttl_sec=15)

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)

    original_pld = {
        "rid": "test-rid-1",
        "why_chain": ["test_signal"],
        "qty_hint": 100.0,
        "price_ctx": {"entry_price": 42000},
        "strategy_id": "aurora",
    }

    result = dm._initiate_flip_close(
        symbol=symbol,
        intent_side="BUY",
        original_pld=original_pld,
        source="aurora"
    )

    assert result == "FLIP_CLOSE_PENDING"

    # Check CMD:CLOSE was emitted
    cmd_close_events = [e for e in bus.emits if e[0] == "CMD:CLOSE"]
    assert len(cmd_close_events) == 1, "Expected CMD:CLOSE to be emitted"

    cmd_close_pld = cmd_close_events[0][1]
    assert cmd_close_pld is not None
    assert cmd_close_pld["symbol"] == symbol
    assert cmd_close_pld["reason"] == "FLIP_CLOSE"
    assert "retry_key" in cmd_close_pld
    assert cmd_close_pld["retry_key"].startswith(f"flip:{symbol}:BUY:")

    # Check EVT:INTENT_DEFERRED was emitted
    deferred_events = [e for e in bus.emits if e[0] == "EVT:INTENT_DEFERRED"]
    assert len(deferred_events) == 1, "Expected INTENT_DEFERRED to be emitted"

    deferred_pld = deferred_events[0][1]
    assert deferred_pld is not None
    assert deferred_pld["symbol"] == symbol
    assert deferred_pld["reason"] == "FLIP_CLOSE_PENDING"
    assert deferred_pld["retry_key"] == cmd_close_pld["retry_key"]
    assert deferred_pld["attempt"] == 1
    assert deferred_pld["max_attempts"] == 5


def test_initiate_flip_close_computes_next_allowed_ts_from_stale_ttl():
    """
    _initiate_flip_close() should use positions_stale_ttl_sec for next_allowed_ts calculation.
    """
    bus = _Bus()
    symbol = "ETHUSDT"
    stale_ttl_sec = 20
    cfg = _mk_cfg(symbol=symbol, stale_ttl_sec=stale_ttl_sec)

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)

    original_pld = {
        "rid": "test-rid-2",
        "why_chain": ["signal"],
    }

    now_before = int(time.time() * 1000)
    dm._initiate_flip_close(
        symbol=symbol,
        intent_side="SELL",
        original_pld=original_pld,
        source="aurora"
    )
    now_after = int(time.time() * 1000)

    deferred_events = [e for e in bus.emits if e[0] == "EVT:INTENT_DEFERRED"]
    assert len(deferred_events) == 1

    deferred_pld = deferred_events[0][1]
    next_allowed = deferred_pld["next_allowed_ts"]

    # next_allowed_ts should be now_ms + stale_ttl_sec * 1000
    expected_min = now_before + (stale_ttl_sec * 1000)
    expected_max = now_after + (stale_ttl_sec * 1000)

    assert expected_min <= next_allowed <= expected_max, \
        f"next_allowed_ts should be ~{stale_ttl_sec}s in future"


def test_initiate_flip_close_preserves_original_payload_in_deferred():
    """
    _initiate_flip_close() should preserve original payload fields in INTENT_DEFERRED.
    """
    bus = _Bus()
    symbol = "SOLUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)

    original_pld = {
        "rid": "custom-rid-123",
        "why_chain": ["custom_signal", "feature_x"],
        "qty_hint": 50.0,
        "position_size_usd": 75.0,
        "price_ctx": {"entry_price": 150.0, "stop": 145.0},
        "strategy_id": "custom_strategy",
    }

    dm._initiate_flip_close(
        symbol=symbol,
        intent_side="BUY",
        original_pld=original_pld,
        source="custom_strategy"
    )

    deferred_events = [e for e in bus.emits if e[0] == "EVT:INTENT_DEFERRED"]
    assert len(deferred_events) == 1

    deferred_pld = deferred_events[0][1]
    original_event = deferred_pld["original_event"]
    payload_min = original_event["payload_min"]

    # Core fields
    assert payload_min["symbol"] == symbol
    assert payload_min["side"] == "BUY"
    assert payload_min["strategy_id"] == "custom_strategy"
    assert payload_min["rid"] == "custom-rid-123"
    
    # Original payload fields preserved
    assert payload_min.get("qty_hint") == 50.0
    assert payload_min.get("price_ctx") == {"entry_price": 150.0, "stop": 145.0}
    
    # v7 readiness contract
    assert payload_min.get("readiness") == {"warmup_ok": True}

    # Check why_chain preservation
    assert "opposite_position_exists" in deferred_pld["why_chain"]
    assert "flip_close_emitted" in deferred_pld["why_chain"]


def test_initiate_flip_close_fails_closed_on_missing_stale_ttl():
    """
    _initiate_flip_close() should fail-closed if positions_stale_ttl_sec is missing.
    """
    bus = _Bus()
    symbol = "BTCUSDT"
    cfg = _mk_cfg(symbol=symbol)
    # Break config: remove positions_stale_ttl_sec
    cfg.domains.position_tracking.positions_stale_ttl_sec = None

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)

    original_pld = {"rid": "test-rid", "why_chain": []}

    with pytest.raises(ValueError, match="positions_stale_ttl_sec is required"):
        dm._initiate_flip_close(
            symbol=symbol,
            intent_side="BUY",
            original_pld=original_pld,
            source="aurora"
        )


def test_initiate_flip_close_uses_position_size_usd_when_qty_hint_missing():
    """
    _initiate_flip_close() should preserve position_size_usd in payload_min.
    """
    bus = _Bus()
    symbol = "DOGEUSDT"
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)

    original_pld = {
        "rid": "test-rid-fallback",
        "position_size_usd": 200.0,  # No qty_hint
        "why_chain": [],
    }

    dm._initiate_flip_close(
        symbol=symbol,
        intent_side="SELL",
        original_pld=original_pld,
        source="aurora"
    )

    deferred_events = [e for e in bus.emits if e[0] == "EVT:INTENT_DEFERRED"]
    deferred_pld = deferred_events[0][1]
    payload_min = deferred_pld["original_event"]["payload_min"]

    # position_size_usd should be preserved from original payload
    assert payload_min.get("position_size_usd") == 200.0, "Should preserve position_size_usd"
    # v7 readiness contract
    assert payload_min.get("readiness") == {"warmup_ok": True}
