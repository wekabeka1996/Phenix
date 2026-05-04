"""Tests for safety gate adapter — Slice 4.2.

Verifies the thin wrapper maps SafetyGateResult outcomes correctly.
"""
import pytest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from apps.reference.domains.decision_making.gateway.protocol import GateContext, GateOutcome
from apps.reference.domains.decision_making.gates import safety_gate
from apps.reference.domains.decision_making.gates.safety_gates import SafetyGateResult


def _ctx(**kw) -> GateContext:
    defaults = dict(
        symbol="BTCUSDT",
        strategy_id="aurora",
        side="BUY",
        rid="test-rid",
        pld={"ts_ms": 1_000_000},
        config=SimpleNamespace(),
        clock=MagicMock(),
        dm=MagicMock(),
        symbol_states={"BTCUSDT": {}},
        ts_ms=1_000_000,
    )
    defaults.update(kw)
    return GateContext(**defaults)


class TestSafetyGateAdapter:

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_pass_on_allow(self, mock_asg):
        mock_asg.return_value = SafetyGateResult(outcome="ALLOW")
        ctx = _ctx()
        r = safety_gate.check(ctx)
        assert r.outcome == GateOutcome.PASS
        assert r.gate_name == "safety"
        assert "safety_gate_result" in ctx.accumulated

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_reject_on_deny(self, mock_asg):
        mock_asg.return_value = SafetyGateResult(
            outcome="DENY",
            deny_reason="NRR-029",
            why_short="flash_motion",
        )
        r = safety_gate.check(_ctx())
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "NRR-029"
        assert "flash_motion" in r.context

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_reject_on_config_error(self, mock_asg):
        mock_asg.return_value = SafetyGateResult(
            outcome="CONFIG_ERROR",
            deny_reason="CONFIG_SAFETY_GATES_MISSING",
            config_error_context="safety_gates:config_error",
        )
        r = safety_gate.check(_ctx())
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "CONFIG_SAFETY_GATES_MISSING"
        assert r.reason == "CONFIG_ERROR"

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_carries_full_result_in_accumulated(self, mock_asg):
        sg_result = SafetyGateResult(outcome="ALLOW", signal_score=0.75)
        mock_asg.return_value = sg_result
        ctx = _ctx()
        safety_gate.check(ctx)
        assert ctx.accumulated["safety_gate_result"] is sg_result
        assert ctx.accumulated["safety_gate_result"].signal_score == 0.75

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_passes_correct_args(self, mock_asg):
        mock_asg.return_value = SafetyGateResult(outcome="ALLOW")
        dm = MagicMock()
        dm._per_symbol_regimes = {"BTCUSDT": {"regime": "TRENDING_UP"}}
        dm._system_stress_states = {"BTCUSDT": "NORMAL"}
        ctx = _ctx(dm=dm, symbol="BTCUSDT", strategy_id="aurora", side="BUY")
        safety_gate.check(ctx)
        mock_asg.assert_called_once()
        call_kw = mock_asg.call_args.kwargs
        assert call_kw["symbol"] == "BTCUSDT"
        assert call_kw["strategy_id"] == "aurora"
        assert call_kw["side"] == "BUY"
        assert call_kw["per_symbol_regimes"] == {
            "BTCUSDT": {"regime": "TRENDING_UP"}}
