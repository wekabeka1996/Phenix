from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_peak_giveback_logic_arming_and_trigger(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")
    now_ms = get_clock().now_ms()

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.edge_arm_usd = 25.0
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0
    cfg.profitability_guard.enabled = False

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    # 1. Warmup (all updates count >= 1)
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "100.0", "unrealizedProfit": "0.0"}]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    # 2. Price moves up, but not enough to arm (20 < 25)
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "120.0", "unrealizedProfit": "20.0"}]))
    state = sidecar._state("BTCUSDT")
    assert state.peak_edge_usd == 20.0
    assert state.is_armed is False
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)
    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    snapshot = evaluated["peak_giveback_snapshot"]
    assert snapshot["policy_enabled"] is True
    assert snapshot["mark_price"] == 120.0
    assert snapshot["entry_price"] == 100.0
    assert snapshot["position_qty"] == 1.0
    assert snapshot["side"] == "BUY"
    assert snapshot["unrealized_pnl_usdt"] == 20.0
    assert snapshot["unrealized_pnl_pct"] == 20.0
    assert snapshot["peak_edge_usd"] == 20.0
    assert snapshot["current_edge_usd"] == 20.0
    assert snapshot["giveback_pct"] == 0.0
    assert snapshot["is_armed"] is False
    assert snapshot["arm_threshold_usd"] == 25.0
    assert snapshot["giveback_trigger_pct"] == 50.0
    assert snapshot["threshold_crossed"] is False
    assert snapshot["peak_giveback_state"] == "peak_giveback_not_armed_below_edge"
    assert snapshot["reason_codes"] == ["peak_giveback_not_armed_below_edge"]
    assert snapshot["null_reasons"] == {}

    shadow = snapshot["peak_giveback_shadow_arms"]["percent_notional"]
    assert shadow["enabled"] is True
    assert shadow["candidate_unit"] == "percent"
    assert shadow["giveback_trigger_pct"] == 50.0
    assert [row["candidate_pct"] for row in shadow["candidates"]] == [
        0.02,
        0.05,
        0.07,
    ]
    for row in shadow["candidates"]:
        assert row["is_armed"] is True
        assert row["arm_threshold_usd"] is not None
        assert row["peak_edge_usd"] == 20.0
        assert row["giveback_pct"] == 0.0
        assert row["threshold_met_under_current_giveback_trigger_pct"] is False
        assert row["would_trigger"] is False
        assert row["state"] == "shadow_percent_notional_below_trigger"
        assert isinstance(row["first_arm_ts_ms"], int)
        assert row["null_reasons"] == {}
    assert "peak_giveback_not_armed_below_edge" in evaluated["reason_codes"]

    # 3. Price moves up to arm (30 > 25)
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "130.0", "unrealizedProfit": "30.0"}]))
    assert state.peak_edge_usd == 30.0
    assert state.is_armed is True
    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    assert evaluated["peak_giveback_snapshot"]["peak_giveback_state"] == "peak_giveback_below_trigger"
    assert evaluated["peak_giveback_snapshot"]["threshold_crossed"] is False
    assert evaluated["peak_giveback_snapshot"]["reason_codes"] == [
        "peak_giveback_armed", "peak_giveback_below_trigger"]
    assert "peak_giveback_armed" in evaluated["reason_codes"]
    assert "peak_giveback_below_trigger" in evaluated["reason_codes"]

    # 4. Price gives back some, but not enough (20 USD PnL => 10 giveback => 10/30 = 33% < 50%)
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "120.0", "unrealizedProfit": "20.0"}]))
    assert state.peak_edge_usd == 30.0
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)
    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    assert evaluated["peak_giveback_snapshot"]["peak_giveback_state"] == "peak_giveback_below_trigger"
    assert evaluated["peak_giveback_snapshot"]["giveback_pct"] > 30.0
    assert evaluated["peak_giveback_snapshot"]["giveback_pct"] < 40.0

    # 5. Price gives back enough (10 USD PnL => 20 giveback => 20/30 = 66% > 50%)
    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "110.0", "unrealizedProfit": "10.0"}]))
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" in _topics(bus)

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")[-1]
    request = _payloads(bus, "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST")[-1]
    assert recommended["policy_source"] == "position_policy_sidecar:peak_giveback"
    assert recommended["peak_giveback_snapshot"]["peak_giveback_state"] == "peak_giveback_threshold_met"
    assert recommended["peak_giveback_snapshot"]["threshold_crossed"] is True
    assert recommended["peak_giveback_snapshot"]["reason_codes"] == [
        "peak_giveback_armed", "peak_giveback_threshold_met"]
    assert request["policy_source"] == "position_policy_sidecar:peak_giveback"
    assert "peak_giveback_threshold_met" in request["reason_codes"]
    assert request["score_snapshot"]["peak_edge_usd"] == 30.0
    assert request["score_snapshot"]["giveback_pct"] > 50.0
    assert request["score_snapshot"]["current_edge_usd"] == 10.0
    assert request["score_snapshot"]["giveback_trigger_pct"] == 50.0
    assert request["peak_giveback_snapshot"]["peak_giveback_state"] == "peak_giveback_threshold_met"

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
    sidecar.on_portfolio_state_updated(_event(
        positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "unrealizedProfit": "10.0"}]))

    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)


def test_peak_giveback_snapshot_emits_null_reasons_when_economics_missing(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.profitability_guard.enabled = False

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(_event(positions=[
                                       {"symbol": "BTCUSDT", "positionAmt": "1.0", "entryPrice": "100.0", "markPrice": "100.0", "unrealizedProfit": "0.0"}]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    sidecar.on_portfolio_state_updated(
        _event(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0"}]))

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    snapshot = evaluated["peak_giveback_snapshot"]
    assert snapshot["mark_price"] is None
    assert snapshot["unrealized_pnl_usdt"] is None
    assert snapshot["current_edge_usd"] is None
    assert snapshot["giveback_pct"] is None
    assert snapshot["threshold_crossed"] is None
    assert snapshot["peak_giveback_state"] == "peak_giveback_unavailable_economics_missing"
    assert snapshot["null_reasons"] == {
        "mark_price": "missing_mark_price",
        "unrealized_pnl_usdt": "missing_unrealized_pnl_usdt",
        "unrealized_pnl_pct": "missing_unrealized_pnl_pct",
        "current_edge_usd": "missing_unrealized_pnl_usdt",
        "giveback_pct": "missing_current_edge_usd",
        "threshold_crossed": "threshold_not_evaluable",
    }
    shadow = snapshot["peak_giveback_shadow_arms"]["percent_notional"]
    assert shadow["null_reason"] == "missing_unrealized_pnl_usdt"
    for row in shadow["candidates"]:
        assert row["arm_threshold_usd"] is None
        assert row["giveback_pct"] is None
        assert row["threshold_met_under_current_giveback_trigger_pct"] is None
        assert row["would_trigger"] is None
        assert row["state"] == "shadow_percent_notional_unavailable_economics_missing"
    assert "peak_giveback_unavailable_economics_missing" in evaluated["reason_codes"]


def test_shadow_percent_notional_threshold_math_and_isolation(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="2.0", entry_price="2000.0")

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.edge_arm_usd = 25.0
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0
    cfg.profitability_guard.enabled = False
    cfg.shadow_percent_notional_arm.enabled = True
    cfg.shadow_percent_notional_arm.candidate_pcts = [0.02, 0.05]

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(_event(positions=[
        {"symbol": "BTCUSDT", "positionAmt": "2.0", "entryPrice": "2000.0",
            "markPrice": "2000.0", "unrealizedProfit": "0.0"}
    ]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    sidecar.on_portfolio_state_updated(_event(positions=[
        {"symbol": "BTCUSDT", "positionAmt": "2.0", "entryPrice": "2000.0",
            "markPrice": "2001.5", "unrealizedProfit": "3.0"}
    ]))

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    shadow_candidates = evaluated["peak_giveback_snapshot"]["peak_giveback_shadow_arms"]["percent_notional"]["candidates"]
    by_pct = {row["candidate_pct"]: row for row in shadow_candidates}

    assert by_pct[0.05]["arm_threshold_usd"] == 2.0
    assert by_pct[0.05]["is_armed"] is True
    assert by_pct[0.05]["giveback_pct"] == 0.0
    assert by_pct[0.05]["threshold_met_under_current_giveback_trigger_pct"] is False
    assert by_pct[0.05]["would_trigger"] is False

    live_state = sidecar._state("BTCUSDT")
    assert live_state.is_armed is False
    assert live_state.peak_edge_usd == 3.0
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)

    sidecar.on_portfolio_state_updated(_event(positions=[
        {"symbol": "BTCUSDT", "positionAmt": "2.0", "entryPrice": "2000.0",
            "markPrice": "2000.5", "unrealizedProfit": "1.0"}
    ]))

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    shadow_candidates = evaluated["peak_giveback_snapshot"]["peak_giveback_shadow_arms"]["percent_notional"]["candidates"]
    by_pct = {row["candidate_pct"]: row for row in shadow_candidates}

    assert by_pct[0.05]["threshold_met_under_current_giveback_trigger_pct"] is True
    assert by_pct[0.05]["would_trigger"] is True
    assert by_pct[0.05]["state"] == "shadow_percent_notional_threshold_met"

    assert live_state.is_armed is False
    assert live_state.peak_edge_usd == 3.0
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)


def test_shadow_percent_notional_missing_notional_emits_null_reason(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="", entry_price="")

    cfg = _sidecar_config(tmp_path, mode="shadow")
    cfg.peak_giveback_close.enabled = True
    cfg.profitability_guard.enabled = False
    cfg.shadow_percent_notional_arm.enabled = True
    cfg.shadow_percent_notional_arm.candidate_pcts = [0.05]

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(_event(positions=[
        {"symbol": "BTCUSDT", "positionAmt": None, "entryPrice": None,
            "markPrice": "100.5", "unrealizedProfit": "1.0"}
    ]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    shadow = suppressed["peak_giveback_snapshot"]["peak_giveback_shadow_arms"]["percent_notional"]
    assert shadow["null_reason"] == "missing_position_notional_usdt"
    candidate = shadow["candidates"][0]
    assert candidate["candidate_pct"] == 0.05
    assert candidate["arm_threshold_usd"] is None
    assert candidate["threshold_met_under_current_giveback_trigger_pct"] is None
    assert candidate["would_trigger"] is None
    assert candidate["state"] == "shadow_percent_notional_unavailable_notional_missing"
