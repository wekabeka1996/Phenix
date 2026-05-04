"""
Phase-2 coverage: ExecutionGate — all gate stages, all branches.

Current coverage: 25% (60 miss lines).
Target: cover _check_direction, _check_structural, and Shield stage fully.

Invariants under test:
- Each stage is individually testable (gates_enabled controls which stages run).
- _check_direction has 5 distinct branches.
- _check_structural has 5 distinct branches.
- Shield stage has 3 branches: invariant violation, veto 0.0, pass.
"""
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock
import pytest

from apps.reference.domains.decision_making.gates.execution_gate import ExecutionGate
from apps.reference.config_models import (
    ExecutionGateConfig,
    ExecutionGateName,
    StructuralGateConfig,
)
from apps.reference.shared.decision_primitives.entry_plan import EntryPlanResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_entry_plan(entry=50000.0, stop=49000.0, tp=52000.0) -> EntryPlanResult:
    """Build a minimal EntryPlanResult. RR = (52000-50000)/(50000-49000) = 2.0"""
    ep = MagicMock(spec=EntryPlanResult)
    ep.entry_price = Decimal(str(entry))
    ep.stop_loss_price = Decimal(str(stop))
    ep.take_profit_price = Decimal(str(tp))
    return ep


def _make_gate(
    gates: list[ExecutionGateName] | None = None,
    min_rr: float = 1.0,
    max_rr: float | None = 5.0,
) -> ExecutionGate:
    if gates is None:
        gates = [
            ExecutionGateName.HARD_VETO,
            ExecutionGateName.DIRECTION,
            ExecutionGateName.THRESHOLD,
            ExecutionGateName.SHIELD,
            ExecutionGateName.STRUCTURAL,
        ]
    struct_cfg = MagicMock(spec=StructuralGateConfig)
    struct_cfg.min_risk_reward = min_rr
    struct_cfg.max_risk_reward = max_rr

    cfg = MagicMock(spec=ExecutionGateConfig)
    cfg.gates_enabled = gates
    cfg.structural_gate = struct_cfg
    return ExecutionGate(config=cfg)


_GOOD_FEATURES = {
    "pillar_operator_trend": "1",
    "pillar_strategist_trend": "1",
}


# ---------------------------------------------------------------------------
# Stage 0: Hard Veto
# ---------------------------------------------------------------------------

class TestHardVeto:
    def test_danger_zone_blocks(self):
        gate = _make_gate(gates=[ExecutionGateName.HARD_VETO])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1, danger_zone_active=True,
        )
        assert not ok
        assert "DangerZone" in reason

    def test_oracle_high_blocks(self):
        gate = _make_gate(gates=[ExecutionGateName.HARD_VETO])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1, oracle_level="HIGH",
        )
        assert not ok
        assert "OracleHIGH" in reason

    def test_oracle_critical_blocks(self):
        gate = _make_gate(gates=[ExecutionGateName.HARD_VETO])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1, oracle_level="CRITICAL",
        )
        assert not ok
        assert "CRITICAL" in reason

    def test_missing_entry_plan_blocks(self):
        gate = _make_gate(gates=[ExecutionGateName.HARD_VETO])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=None,
            signal_threshold=0.1,
        )
        assert not ok
        assert "EntryPlanMissing" in reason

    def test_normal_conditions_pass(self):
        gate = _make_gate(gates=[ExecutionGateName.HARD_VETO])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok
        assert reason is None


# ---------------------------------------------------------------------------
# Stage 1: Direction Gate
# ---------------------------------------------------------------------------

class TestDirectionGate:
    def test_missing_op_trend_defers(self):
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features={},  # no pillar_operator_trend
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "MissingOpTrend" in reason

    def test_invalid_trend_value_defers(self):
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "NOT_A_NUMBER"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "InvalidTrendValue" in reason

    def test_counter_trend_buy_vs_sell_trend_blocks(self):
        """intent=BUY, op_trend=-1 (SELL) → CounterTrend"""
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "-1"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "CounterTrend" in reason

    def test_flat_trend_no_strat_blocks(self):
        """op_trend=0, strat_trend=0 → FlatTrend"""
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "0", "pillar_strategist_trend": "0"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "FlatTrend" in reason

    def test_flat_op_but_strat_confirms_passes(self):
        """op_trend=0, strat_trend=1, intent=BUY → pass via strategist"""
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "0", "pillar_strategist_trend": "1"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok

    def test_strategist_conflict_blocks(self):
        """op_trend=1 (BUY), strat_trend=-1 → StrategistConflict"""
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "1", "pillar_strategist_trend": "-1"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "StrategistConflict" in reason

    def test_aligned_buy_no_strat_passes(self):
        """op_trend=1, no strat_trend → passes (strat defaults to 0)"""
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "1"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok

    def test_aligned_sell_passes(self):
        """op_trend=-1, intent=sell → aligned → pass"""
        gate = _make_gate(gates=[ExecutionGateName.DIRECTION])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="sell",
            features={"pillar_operator_trend": "-1"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok


# ---------------------------------------------------------------------------
# Stage 2: Threshold Gate
# ---------------------------------------------------------------------------

class TestThresholdGate:
    def test_weak_score_blocks(self):
        gate = _make_gate(gates=[ExecutionGateName.THRESHOLD])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.01, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.2,
        )
        assert not ok
        assert "SCORE_TOO_WEAK" in reason

    def test_exactly_at_threshold_passes(self):
        gate = _make_gate(gates=[ExecutionGateName.THRESHOLD])
        ok, _ = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.2, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.2,
        )
        assert ok


# ---------------------------------------------------------------------------
# Stage 3: Shield Gate
# ---------------------------------------------------------------------------

class TestShieldGate:
    def test_shield_invariant_violated_above_one(self):
        gate = _make_gate(gates=[ExecutionGateName.SHIELD])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=1.5, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "NRR-056" in reason  # SHIELD_INVARIANT_VIOLATED

    def test_shield_invariant_violated_negative(self):
        gate = _make_gate(gates=[ExecutionGateName.SHIELD])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=-0.1, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "NRR-056" in reason  # SHIELD_INVARIANT_VIOLATED

    def test_shield_zero_veto(self):
        gate = _make_gate(gates=[ExecutionGateName.SHIELD])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.0, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert not ok
        assert "NRR-057" in reason  # SHIELD_VETO_BLOCKED

    def test_shield_valid_multiplier_passes(self):
        gate = _make_gate(gates=[ExecutionGateName.SHIELD])
        ok, _ = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.7, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok


# ---------------------------------------------------------------------------
# Stage STRUCTURAL Gate
# ---------------------------------------------------------------------------

class TestStructuralGate:
    def test_missing_entry_plan_blocks(self):
        """STRUCTURAL without HARD_VETO must also guard entry_plan=None"""
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=None,
            signal_threshold=0.1,
        )
        assert not ok
        assert "EntryPlanMissing" in reason

    def test_zero_risk_dist_blocks(self):
        """entry == stop → ZeroRiskDist"""
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL])
        ep = _make_entry_plan(entry=50000.0, stop=50000.0, tp=52000.0)
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=ep,
            signal_threshold=0.1,
        )
        assert not ok
        assert "ZeroRiskDist" in reason

    def test_low_rr_blocks(self):
        """RR=0.5 < min_rr=1.0 → LowRR"""
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL], min_rr=1.0)
        ep = _make_entry_plan(entry=50000.0, stop=49000.0, tp=50500.0)  # RR=0.5
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=ep,
            signal_threshold=0.1,
        )
        assert not ok
        assert "LowRR" in reason

    def test_high_rr_blocks(self):
        """RR=10 > max_rr=5.0 → HighRR"""
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL], min_rr=0.5, max_rr=5.0)
        ep = _make_entry_plan(entry=50000.0, stop=49900.0, tp=51000.0)  # RR=10
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=ep,
            signal_threshold=0.1,
        )
        assert not ok
        assert "HighRR" in reason

    def test_no_max_rr_allows_high_rr(self):
        """When max_rr=None, any high RR passes."""
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL], min_rr=0.5, max_rr=None)
        ep = _make_entry_plan(entry=50000.0, stop=49900.0, tp=51000.0)  # RR=10
        ok, _ = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=ep,
            signal_threshold=0.1,
        )
        assert ok

    def test_invalid_prices_blocks(self):
        """Non-numeric price values → InvalidPrices"""
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL])
        ep = MagicMock(spec=EntryPlanResult)
        ep.entry_price = "NOT_A_NUMBER"
        ep.stop_loss_price = "BAD"
        ep.take_profit_price = "BAD"
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=ep,
            signal_threshold=0.1,
        )
        assert not ok
        assert "InvalidPrices" in reason

    def test_valid_entry_plan_passes(self):
        gate = _make_gate(gates=[ExecutionGateName.STRUCTURAL], min_rr=0.5)
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features=_GOOD_FEATURES,
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok
        assert reason is None


# ---------------------------------------------------------------------------
# Full gate chain — happy path
# ---------------------------------------------------------------------------

class TestFullGateChain:
    def test_all_stages_pass_with_valid_inputs(self):
        gate = _make_gate()  # all stages enabled
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={"pillar_operator_trend": "1", "pillar_strategist_trend": "1"},
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1,
        )
        assert ok
        assert reason is None

    def test_gate_short_circuits_on_first_fail(self):
        """danger_zone_active should block before direction is ever checked."""
        gate = _make_gate()
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy",
            features={},  # empty — direction would also fail, but HARD_VETO runs first
            final_score=0.5, shield_multiplier=0.8, entry_plan=_make_entry_plan(),
            signal_threshold=0.1, danger_zone_active=True,
        )
        assert not ok
        assert "DangerZone" in reason

    def test_empty_gate_list_allows_everything(self):
        gate = _make_gate(gates=[])
        ok, reason = gate.check_entry(
            symbol="BTCUSDT", side="buy", features={},
            final_score=0.0, shield_multiplier=0.0, entry_plan=None,
            signal_threshold=99.0,
        )
        assert ok
        assert reason is None
