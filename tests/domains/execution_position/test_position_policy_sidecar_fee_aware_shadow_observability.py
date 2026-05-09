import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import jsonschema

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import PositionPolicySidecar
from tests.domains.execution_position.test_position_policy_sidecar import (
    RecordingBus,
    DummyManageFlow,
    _sidecar_config,
    _event,
    _topics,
    _payloads
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    PROJECT_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "execution_position"
    / "schemas"
    / "position_policy_sidecar_fee_aware_shadow_arm_state_v1.json"
)


def test_fee_aware_shadow_arm_state_emission_and_schema(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0

    cfg.shadow_fee_aware_arm.enabled = True
    cfg.shadow_fee_aware_arm.candidate_fee_multiples = [2.0]
    cfg.shadow_fee_aware_arm.fee_source_priority = ["realized_lifecycle_fee"]
    cfg.shadow_fee_aware_arm.optional_pct_notional_floor.enabled = False

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
        lifecycle_fee_getter=lambda symbol: 2.0,  # $2 fee
    )

    # 1. Warmup
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "100.0", "unrealizedProfit": "0.0"}]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    bus.clear()

    # 2. PnL moves to $3. Not enough to arm ($2 fee * 2.0 = $4 edge required)
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "103.0", "unrealizedProfit": "3.0"}]))
    assert "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE" not in _topics(
        bus)

    # 3. PnL moves to $5. Arm threshold is crossed (5 > 4).
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "105.0", "unrealizedProfit": "5.0"}]))
    assert "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE" in _topics(
        bus)

    arm_payloads = _payloads(
        bus, "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE")
    assert len(arm_payloads) == 1
    arm_payload = arm_payloads[0]

    assert arm_payload["shadow_only"] is True
    assert arm_payload["authority_applied"] is False
    assert arm_payload["no_effect"] is True
    assert arm_payload["symbol"] == "BTCUSDT"
    assert arm_payload["candidate_state"]["is_armed"] is True
    assert arm_payload["candidate_state"]["fee_multiple"] == 2.0
    assert arm_payload["candidate_state"]["estimated_fee_usd"] == 2.0
    assert arm_payload["candidate_state"]["required_edge_usd"] == 4.0
    assert "ARMED" in arm_payload["transitions"]
    assert "shadow_fee_aware_armed" in arm_payload["reason_codes"]

    # Validate schema
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=arm_payload, schema=schema)

    bus.clear()

    # 4. PnL drops to $2. Giveback is (5 - 2) / 5 = 60%. Threshold (50%) is crossed.
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "102.0", "unrealizedProfit": "2.0"}]))
    assert "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE" in _topics(
        bus)

    trigger_payloads = _payloads(
        bus, "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE")
    assert len(trigger_payloads) == 1
    trigger_payload = trigger_payloads[0]

    assert "TRIGGERED" in trigger_payload["transitions"]
    assert "shadow_fee_aware_triggered" in trigger_payload["reason_codes"]
    assert trigger_payload["candidate_state"]["would_trigger"] is True
    assert trigger_payload["candidate_state"]["giveback_pct"] == 60.0

    # Check isolation: no actual close request emitted for shadow fee-aware
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)


def test_fee_aware_shadow_event_isolation_and_backward_compat(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.edge_arm_usd = 10.0  # Live policy arms at 10
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0
    cfg.profitability_guard.enabled = False

    cfg.shadow_fee_aware_arm.enabled = True
    cfg.shadow_fee_aware_arm.candidate_fee_multiples = [2.0]
    cfg.shadow_fee_aware_arm.fee_source_priority = ["realized_lifecycle_fee"]
    cfg.shadow_fee_aware_arm.optional_pct_notional_floor.enabled = False

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
        lifecycle_fee_getter=lambda symbol: 2.0,  # $2 fee => requires 4.0 edge to arm
    )

    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "100.0", "unrealizedProfit": "0.0"}]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    # Cross fee-aware threshold but NOT live policy threshold
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "105.0", "unrealizedProfit": "5.0"}]))
    assert sidecar._state("BTCUSDT").is_armed is False  # Live is NOT armed
    assert sidecar._state(
        # Shadow IS armed
        "BTCUSDT").shadow_fee_aware_arm_states["2.00000000:none"].is_armed is True

    # Check that backward compat fields in EVALUATED are intact
    evaluated_payload = _payloads(
        bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    assert evaluated_payload["peak_giveback_snapshot"]["peak_giveback_state"] == "peak_giveback_not_armed_below_edge"

    # Shadow fee aware should have missing economics tested too (optional)
    assert evaluated_payload["peak_giveback_snapshot"]["peak_giveback_shadow_arms"]["fee_aware"]["candidates"][0]["is_armed"] is True
