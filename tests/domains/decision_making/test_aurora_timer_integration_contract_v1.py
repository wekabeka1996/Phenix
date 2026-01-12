import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.conftest import make_app_cfg_stub

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult


class DeterministicClock:
    def __init__(self, start_ts: float = 1000.0):
        self._ts = float(start_ts)

    def now(self) -> float:
        return float(self._ts)

    def advance(self, seconds: float) -> None:
        self._ts += float(seconds)


@dataclass
class HoldingPeriodCfg:
    enabled: bool = True
    min_duration_sec: float = 10.0
    emergency_exit_threshold: float = 0.9
    apply_to_flips: bool = True


@dataclass
class GatesCfg:
    enabled: bool = False


@dataclass
class RegimeInertiaCfg:
    confirm_window_sec: float = 90.0
    confirm_window_same_severity_sec: float = 5.0
    immediate_risk_off: bool = True
    severity_map: dict = field(default_factory=dict)


@dataclass
class AntiChurnCfg:
    enabled: bool = True
    time_multipliers: dict = field(default_factory=dict)
    regime_inertia: RegimeInertiaCfg = field(default_factory=RegimeInertiaCfg)


@dataclass
class AuroraDecisionCfg:
    reentry_cooldown_sec: float = 60.0
    holding_period: HoldingPeriodCfg = field(default_factory=HoldingPeriodCfg)
    anti_churn: Optional[AntiChurnCfg] = None

    # required defaults used by handler
    signal_threshold: float = 0.1
    neutral_threshold: float = 0.05
    side_bias_window_sec: float = 600.0
    side_bias_target_ratio: float = 0.5
    side_bias_penalty_factor: float = 0.5
    side_bias_min_intents: int = 10
    regime_threshold_multipliers: dict = field(default_factory=dict)

    signal_weights: dict = field(default_factory=dict)
    feature_neutrals: dict = field(default_factory=dict)
    essential_features: list = field(default_factory=list)

    signals: Any = None
    direction_strength_scoring: Any = None
    anchor_shock_veto: Any = None
    gates: GatesCfg = field(default_factory=GatesCfg)


@dataclass
class AuroraAssetCfg:
    enabled: bool = True
    signal_threshold: float = 0.1
    neutral_threshold: float = 0.05
    reentry_cooldown_sec: Optional[float] = None
    holding_period: Optional[HoldingPeriodCfg] = None


@dataclass
class AuroraCfg:
    timeframe_sec: int = 60
    enabled_symbols: Any = None
    allowed_regimes: Any = None
    decision: AuroraDecisionCfg = field(default_factory=AuroraDecisionCfg)
    assets: dict = field(default_factory=dict)


@dataclass
class StrategiesCfg:
    aurora: AuroraCfg


class QueueKernel:
    queue: list[ScoringResult] = []

    @staticmethod
    def compute(**kwargs) -> ScoringResult:
        return QueueKernel.queue.pop(0)


def _build_config(*, symbol: str, decision: AuroraDecisionCfg) -> Any:
    cfg = make_app_cfg_stub()
    aurora = AuroraCfg(timeframe_sec=60, decision=decision, assets={symbol: AuroraAssetCfg()})
    cfg.strategies = StrategiesCfg(aurora=aurora)
    return cfg


def _types(events: list[tuple[str, dict]]) -> list[str]:
    return [t for (t, _payload) in events]


def _payloads(events: list[tuple[str, dict]], event_type: str) -> list[dict]:
    return [p for (t, p) in events if t == event_type]


def test_timer_integration_reentry_cooldown_after_close() -> None:
    clock = DeterministicClock(start_ts=5000.0)
    symbol = "BTCUSDT"

    decision = AuroraDecisionCfg(
        reentry_cooldown_sec=60.0,
        holding_period=HoldingPeriodCfg(enabled=False),
        anti_churn=None,
    )
    cfg = _build_config(symbol=symbol, decision=decision)

    events: list[tuple[str, dict]] = []
    handler = AuroraHandler(
        config=cfg,
        emit_fn=lambda t, p: events.append((t, p)),
        monotonic_fn=clock.now,
        wall_time_fn=clock.now,
    )

    handler.scoring_kernel_cls = QueueKernel
    QueueKernel.queue = [
        ScoringResult(score=Decimal("0.8"), side="BUY", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
        ScoringResult(score=Decimal("0.0"), side="", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
        ScoringResult(score=Decimal("0.5"), side="BUY", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
        ScoringResult(score=Decimal("0.5"), side="BUY", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
    ]

    event = {"symbol": symbol, "features": {"price": 100}, "tf_sec": 60, "warmup": {"full_ready": True}}

    # open
    handler.on_features_calculated(event)
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in _types(events)

    # close
    handler.on_features_calculated(event)
    state = handler._symbol_states[symbol]
    assert state.position_side == ""
    assert state.last_exit_timestamp == 5000.0

    # reentry too soon
    events.clear()
    clock.advance(30.0)
    handler.on_features_calculated(event)
    assert "EVT:STRATEGY_DECISION_BLOCKED" in _types(events)
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in _types(events)

    blocked = _payloads(events, "EVT:STRATEGY_DECISION_BLOCKED")
    assert blocked[0]["reason_code"] == "REENTRY_COOLDOWN"

    # reentry allowed
    events.clear()
    clock.advance(31.0)
    handler.on_features_calculated(event)
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in _types(events)


def test_timer_integration_flip_min_duration_holding_period() -> None:
    clock = DeterministicClock(start_ts=2000.0)
    symbol = "ETHUSDT"

    decision = AuroraDecisionCfg(
        reentry_cooldown_sec=0.0,
        holding_period=HoldingPeriodCfg(enabled=True, min_duration_sec=10.0, emergency_exit_threshold=0.9, apply_to_flips=True),
        anti_churn=None,
    )
    cfg = _build_config(symbol=symbol, decision=decision)

    events: list[tuple[str, dict]] = []
    handler = AuroraHandler(
        config=cfg,
        emit_fn=lambda t, p: events.append((t, p)),
        monotonic_fn=clock.now,
        wall_time_fn=clock.now,
    )

    handler.scoring_kernel_cls = QueueKernel
    QueueKernel.queue = [
        ScoringResult(score=Decimal("0.5"), side="BUY", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
        ScoringResult(score=Decimal("0.5"), side="SELL", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
        ScoringResult(score=Decimal("0.5"), side="SELL", thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1")),
    ]

    event = {"symbol": symbol, "features": {"price": 100}, "tf_sec": 60, "warmup": {"full_ready": True}}

    # open buy
    handler.on_features_calculated(event)
    state = handler._symbol_states[symbol]
    assert state.position_side == "buy"
    assert state.entry_timestamp == 2000.0

    # flip too soon -> blocked + hold emitted
    events.clear()
    clock.advance(5.0)
    handler.on_features_calculated(event)

    blocked = _payloads(events, "EVT:STRATEGY_DECISION_BLOCKED")
    assert blocked[0]["reason_code"] == "HOLDING_PERIOD_ACTIVE"

    produced = _payloads(events, "EVT:STRATEGY_SIGNAL_PRODUCED")
    assert produced[0]["side"] == "BUY"

    # flip allowed
    events.clear()
    clock.advance(6.0)
    handler.on_features_calculated(event)
    produced = _payloads(events, "EVT:STRATEGY_SIGNAL_PRODUCED")
    assert produced[0]["side"] == "SELL"


def test_timer_integration_time_multipliers_and_regime_inertia_do_not_break_timers() -> None:
    clock = DeterministicClock(start_ts=1000.0)
    symbol = "BTCUSDT"

    inertia = RegimeInertiaCfg(
        confirm_window_sec=90.0,
        confirm_window_same_severity_sec=5.0,
        immediate_risk_off=True,
        severity_map={"FLAT_LOW": 1, "HIGH_VOLATILITY": 3},
    )
    anti_churn = AntiChurnCfg(
        enabled=True,
        time_multipliers={"FLAT_LOW": 5.0, "HIGH_VOLATILITY": 1.0},
        regime_inertia=inertia,
    )
    decision = AuroraDecisionCfg(
        reentry_cooldown_sec=10.0,
        holding_period=HoldingPeriodCfg(enabled=True, min_duration_sec=10.0),
        anti_churn=anti_churn,
    )
    cfg = _build_config(symbol=symbol, decision=decision)

    handler = AuroraHandler(
        config=cfg,
        emit_fn=lambda *_args: None,
        monotonic_fn=clock.now,
        wall_time_fn=clock.now,
    )

    # Risk-off (higher severity) should switch immediately
    handler._update_effective_regime(symbol, "HIGH_VOLATILITY")
    state = handler._symbol_states[symbol]
    assert state.regime_effective == "HIGH_VOLATILITY"
    assert handler._get_reentry_cooldown_sec(symbol) == pytest.approx(10.0)

    # Risk-on (lower severity) should not switch until confirm window elapsed
    handler._update_effective_regime(symbol, "FLAT_LOW")
    assert state.regime_effective == "HIGH_VOLATILITY"
    assert handler._get_min_duration_sec(symbol) == pytest.approx(10.0)

    clock.advance(91.0)
    handler._update_effective_regime(symbol, "FLAT_LOW")
    assert state.regime_effective == "FLAT_LOW"

    assert handler._get_reentry_cooldown_sec(symbol) == pytest.approx(50.0)
    assert handler._get_min_duration_sec(symbol) == pytest.approx(50.0)
