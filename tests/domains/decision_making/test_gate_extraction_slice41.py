"""Tests for extracted gate modules — Slice 4.1.

Each test class covers one gate's PASS / REJECT / DEFER paths using
lightweight mock objects that reproduce the StrategyGateway delegate calls.
"""
import decimal
import pytest
from unittest.mock import MagicMock, PropertyMock
from types import SimpleNamespace

from apps.reference.domains.decision_making.gate_protocol import (
    GateContext, GateOutcome, GateResult,
)
from apps.reference.domains.decision_making.gates import (
    arbitration_gate,
    risk_gate,
    flip_gate,
    qos_gate,
    exposure_gate,
    ttl_gate,
    warmup_gate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, ms: int = 1_000_000):
        self._ms = ms

    def now_ms(self):
        return self._ms


def _ctx(*, dm=None, config=None, clock=None, pld=None, **kw) -> GateContext:
    defaults = dict(
        symbol="BTCUSDT",
        strategy_id="aurora",
        side="BUY",
        rid="test-rid",
        pld=pld or {"ts_ms": 1_000_000},
        config=config or SimpleNamespace(
            domains=SimpleNamespace(
                risk_management=SimpleNamespace(
                    trading_allowed_thresholds=SimpleNamespace(max_risk_score=0.8)),
                decision_making=SimpleNamespace(
                    risk_skew=SimpleNamespace(
                        max_skew_sec=10,
                        max_defer_count=5,
                        defer_window_sec=60,
                        defer_cooldown_sec=2,
                        until_refresh_max_hold_sec=300,
                        until_refresh_retry_sec=5,
                    )),
                position_tracking=SimpleNamespace(positions_stale_ttl_sec=30),
            ),
            strategies=SimpleNamespace(aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0),
                safety_gates=SimpleNamespace(system_stress_policy="off"),
            )),
            system=SimpleNamespace(market_data=None),
        ),
        clock=clock or FakeClock(),
        dm=dm or MagicMock(),
        symbol_states={"BTCUSDT": {}},
        ts_ms=1_000_000,
    )
    defaults.update(kw)
    return GateContext(**defaults)


# ---------------------------------------------------------------------------
# Arbitration gate
# ---------------------------------------------------------------------------

class TestArbitrationGate:
    def test_pass_when_allowed(self):
        dm = MagicMock()
        dm._check_strategy_arbitration.return_value = {"allowed": True}
        r = arbitration_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.PASS

    def test_reject_when_blocked(self):
        dm = MagicMock()
        dm._check_strategy_arbitration.return_value = {
            "allowed": False, "reason": "cooldown"}
        r = arbitration_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "ARBITRATION_BLOCKED"
        assert r.details["arbitration_reason"] == "cooldown"


# ---------------------------------------------------------------------------
# Risk gate
# ---------------------------------------------------------------------------

class TestRiskGate:
    def test_defer_when_no_risk_data(self):
        dm = MagicMock()
        dm.symbol_states = {"BTCUSDT": {}}
        r = risk_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.DEFER
        assert r.reason_code == "NRR-DATA-NOT-READY"

    def test_defer_when_risk_score_none(self):
        dm = MagicMock()
        dm.symbol_states = {"BTCUSDT": {
            "risk": {"risk_parameters": {"risk_score": None}}}}
        r = risk_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.DEFER
        assert r.reason_code == "RISK_SCORE_MISSING"

    def test_reject_when_trading_not_allowed(self):
        dm = MagicMock()
        dm.symbol_states = {"BTCUSDT": {
            "risk": {"risk_parameters": {"risk_score": 0.1, "is_trading_allowed": False}}}}
        dm._get_aurora_instrument_cfg.return_value = None
        r = risk_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "RISK_TRADING_NOT_ALLOWED"

    def test_reject_when_risk_too_high(self):
        dm = MagicMock()
        dm.symbol_states = {"BTCUSDT": {
            "risk": {"risk_parameters": {"risk_score": 0.95, "is_trading_allowed": True}}}}
        dm._get_aurora_instrument_cfg.return_value = None
        r = risk_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "RISK_SCORE_TOO_HIGH"

    def test_pass_when_risk_ok(self):
        dm = MagicMock()
        dm.symbol_states = {"BTCUSDT": {
            "risk": {"risk_parameters": {"risk_score": 0.3, "is_trading_allowed": True}}}}
        dm._get_aurora_instrument_cfg.return_value = None
        ctx = _ctx(dm=dm)
        r = risk_gate.check(ctx)
        assert r.outcome == GateOutcome.PASS
        assert ctx.accumulated["risk_score"] == 0.3


# ---------------------------------------------------------------------------
# Flip gate
# ---------------------------------------------------------------------------

class TestFlipGate:
    def test_pass_when_no_flip(self):
        dm = MagicMock()
        dm._handle_flip_orchestration.return_value = None
        r = flip_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.PASS

    def test_defer_on_portfolio_unknown(self):
        dm = MagicMock()
        dm._handle_flip_orchestration.return_value = "NRR-PORTFOLIO-UNKNOWN"
        r = flip_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.DEFER
        assert r.reason_code == "NRR-PORTFOLIO-UNKNOWN"

    def test_reject_on_other_flip_result(self):
        dm = MagicMock()
        dm._handle_flip_orchestration.return_value = "ANTI_PYRAMIDING_BLOCK"
        r = flip_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "FLIP_GATE_UNKNOWN"


# ---------------------------------------------------------------------------
# QoS gate
# ---------------------------------------------------------------------------

class TestQosGate:
    def test_pass_when_qos_disabled(self):
        dm = MagicMock()
        dm._qos_enabled_for_strategy.return_value = False
        ctx = _ctx(dm=dm)
        r = qos_gate.check(ctx)
        assert r.outcome == GateOutcome.PASS
        assert ctx.accumulated["_qos_enabled"] is False

    def test_pass_when_qos_allows(self):
        dm = MagicMock()
        dm._qos_enabled_for_strategy.return_value = True
        dm._qos_allow.return_value = (True, None)
        r = qos_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.PASS

    def test_pass_on_shadow_mode(self):
        dm = MagicMock()
        dm._qos_enabled_for_strategy.return_value = True
        dm._qos_allow.return_value = (False, "cooldown")
        dm.qos_mode = "shadow"
        dm.qos_enforce = False
        r = qos_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.PASS

    def test_defer_on_defer_mode(self):
        dm = MagicMock()
        dm._qos_enabled_for_strategy.return_value = True
        dm._qos_allow.return_value = (False, "cooldown")
        dm.qos_mode = "defer"
        dm.qos_enforce = False
        dm._calculate_next_allowed_time.return_value = 2_000_000
        r = qos_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.DEFER
        assert "qos" in r.why_extra

    def test_reject_on_enforce_mode(self):
        dm = MagicMock()
        dm._qos_enabled_for_strategy.return_value = True
        dm._qos_allow.return_value = (False, "cooldown")
        dm.qos_mode = "enforce"
        dm.qos_enforce = False
        r = qos_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "QOS_RATE_LIMIT"


# ---------------------------------------------------------------------------
# Exposure gate
# ---------------------------------------------------------------------------

class TestExposureGate:
    def _dm_for_sizing(self, qty=decimal.Decimal("0.5")):
        dm = MagicMock()
        dm.symbol_states = {"BTCUSDT": {"features": {}}}
        dm.latest_portfolio = {"total_equity": 10000}
        dm._get_aurora_instrument_cfg.return_value = None
        dm._calculate_position_size.return_value = (
            qty, "kelly:0.25", None, None)
        dm._precheck_exposure_cache.return_value = True
        return dm

    def test_reject_on_missing_entry_price(self):
        dm = MagicMock()
        r = exposure_gate.check(_ctx(dm=dm, pld={"ts_ms": 1000}))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "MISSING_ENTRY_PRICE"

    def test_reject_on_missing_portfolio(self):
        dm = MagicMock()
        dm.latest_portfolio = None
        pld = {"ts_ms": 1000, "price_ctx": {"entry_price": "42000"}}
        r = exposure_gate.check(_ctx(dm=dm, pld=pld))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "LATEST_PORTFOLIO_MISSING"

    def test_reject_on_sizing_error(self):
        dm = self._dm_for_sizing()
        dm._calculate_position_size.side_effect = ValueError("bad size")
        pld = {"ts_ms": 1000, "price_ctx": {"entry_price": "42000"}}
        r = exposure_gate.check(_ctx(dm=dm, pld=pld))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "SIZING_ERROR"

    def test_reject_on_exposure_precheck_fail(self):
        dm = self._dm_for_sizing()
        dm._precheck_exposure_cache.return_value = False
        pld = {"ts_ms": 1000, "price_ctx": {"entry_price": "42000"}}
        r = exposure_gate.check(_ctx(dm=dm, pld=pld))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "EXPOSURE_PRECHECK_FAILED"

    def test_pass_with_valid_sizing(self):
        dm = self._dm_for_sizing()
        pld = {"ts_ms": 1000, "price_ctx": {"entry_price": "42000"}}
        ctx = _ctx(dm=dm, pld=pld)
        r = exposure_gate.check(ctx)
        assert r.outcome == GateOutcome.PASS
        assert ctx.accumulated["qty_dec"] == decimal.Decimal("0.5")
        assert ctx.accumulated["entry_price_dec"] == decimal.Decimal("42000")


# ---------------------------------------------------------------------------
# TTL gate
# ---------------------------------------------------------------------------

class TestTtlGate:
    def test_pass_when_fresh(self):
        dm = MagicMock()
        dm.features_ttl_sec = 60
        r = ttl_gate.check(
            _ctx(dm=dm, ts_ms=999_000, clock=FakeClock(1_000_000)))
        assert r.outcome == GateOutcome.PASS

    def test_reject_when_stale(self):
        dm = MagicMock()
        dm.features_ttl_sec = 60
        # Signal from 120 seconds ago
        r = ttl_gate.check(
            _ctx(dm=dm, ts_ms=880_000, clock=FakeClock(1_000_000)))
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "SIGNAL_STALE"

    def test_uses_bar_ttl_when_tf_sec_present(self):
        dm = MagicMock()
        dm.features_ttl_sec = 60
        pld = {"ts_ms": 999_000, "tf_sec": 300}
        # bar_ttl = 300*1000*2 = 600_000
        r = ttl_gate.check(
            _ctx(dm=dm, pld=pld, ts_ms=999_000, clock=FakeClock(1_000_000)))
        assert r.outcome == GateOutcome.PASS


# ---------------------------------------------------------------------------
# Warmup gate
# ---------------------------------------------------------------------------

class TestWarmupGate:
    def test_pass_when_warmup_ready(self):
        dm = MagicMock()
        dm._warmup_gate_before_trade_intent.return_value = False
        r = warmup_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.PASS

    def test_block_when_warmup_not_ready(self):
        dm = MagicMock()
        dm._warmup_gate_before_trade_intent.return_value = True
        r = warmup_gate.check(_ctx(dm=dm))
        assert r.outcome == GateOutcome.BLOCK
        assert r.reason_code == "WARMUP_NOT_READY"
