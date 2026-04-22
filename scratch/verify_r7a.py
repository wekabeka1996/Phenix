import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path.cwd()))

from apps.reference.domains.execution_position.position_policy_sidecar import PositionPolicySidecar
from tests.domains.execution_position.test_position_policy_sidecar import RecordingBus, DummyManageFlow, _sidecar_config, _event

def run_verify():
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")
    
    cfg = _sidecar_config(Path("/tmp"), mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.edge_arm_usd = 25.0
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0
    
    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )
    
    # Warmup
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "0.0"}]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(_event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))
    
    # Arm
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "30.0"}]))
    state = sidecar._state("BTCUSDT")
    print(f"Armed: {state.is_armed}, Peak: {state.peak_edge_usd}")
    assert state.is_armed
    
    # Trigger
    sidecar.on_portfolio_state_updated(_event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "10.0"}]))
    
    topics = [t for t, _, _ in bus.events]
    print(f"Topics: {topics}")
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" in topics
    print("Verification SUCCESS")

if __name__ == "__main__":
    try:
        run_verify()
    except Exception as e:
        print(f"Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
