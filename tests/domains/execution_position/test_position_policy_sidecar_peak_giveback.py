from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.position_policy_sidecar import PositionPolicySidecar
from tests.domains.execution_position.test_position_policy_sidecar import (
    RecordingBus, 
    DummyManageFlow, 
    _sidecar_config, 
    _event, 
    _topics, 
    _payloads
)

def test_peak_giveback_logic_arming_and_trigger(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")
    now_ms = get_clock().now_ms()
    
    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.edge_arm_usd = 25.0
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0
    
    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )
    
    # 1. Warmup (all updates count >= 1)
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "0.0"}]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(_event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))
    
    # 2. Price moves up, but not enough to arm (20 < 25)
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "20.0"}]))
    state = sidecar._state("BTCUSDT")
    assert state.peak_edge_usd == 20.0
    assert state.is_armed is False
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)
    
    # 3. Price moves up to arm (30 > 25)
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "30.0"}]))
    assert state.peak_edge_usd == 30.0
    assert state.is_armed is True
    
    # 4. Price gives back some, but not enough (20 USD PnL => 10 giveback => 10/30 = 33% < 50%)
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "20.0"}]))
    assert state.peak_edge_usd == 30.0
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)
    
    # 5. Price gives back enough (10 USD PnL => 20 giveback => 20/30 = 66% > 50%)
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "10.0"}]))
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" in _topics(bus)
    
    request = _payloads(bus, "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST")[-1]
    assert request["policy_source"] == "position_policy_sidecar:peak_giveback"
    assert "peak_giveback_threshold_met" in request["reason_codes"]
    assert request["score_snapshot"]["peak_edge_usd"] == 30.0
    assert request["score_snapshot"]["giveback_pct"] > 50.0
    
    # 6. Verify state reset after trigger to avoid double emission
    assert state.is_armed is False
    assert state.peak_edge_usd == 0.0

def test_peak_giveback_resets_on_new_entry(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="enable"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )
    
    state = sidecar._state("BTCUSDT")
    state.peak_edge_usd = 100.0
    state.is_armed = True
    
    # New entry fill (reduce_only=False)
    sidecar.on_order_fill(_event(symbol="BTCUSDT", reduce_only=False))
    
    assert state.peak_edge_usd == 0.0
    assert state.is_armed is False

def test_peak_giveback_disabled_prevents_action(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = False
    
    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )
    
    state = sidecar._state("BTCUSDT")
    state.peak_edge_usd = 100.0
    state.is_armed = True
    
    # Large giveback
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "10.0"}]))
    
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)
