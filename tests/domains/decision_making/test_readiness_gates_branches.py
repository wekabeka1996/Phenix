"""
Phase-3 coverage: ReadinessGates — warmup gate branches + exposure precheck.

Current coverage of gates/readiness_gates.py: 57% (90 miss lines).
This test file targets the untested error paths of:
  - warmup_gate_before_trade_intent (9 blocking branches)
  - precheck_exposure_cache (3 blocking branches)
  - degraded_context_gate_should_defer (disabled fast-path)

All injected dependencies are minimal mocks; no FSM or real config required.
"""
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch
import time
import pytest

from apps.reference.domains.decision_making.gates.readiness_gates import ReadinessGates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clock(now_ms: int = 1_700_000_000_000, now_sec: float | None = None):
    clock = MagicMock()
    clock.now_ms.return_value = now_ms
    clock.now_sec.return_value = now_sec if now_sec is not None else now_ms / 1000.0
    return clock


def _make_config(enforcement_mode: str = "strict"):
    """Build a minimal AuroraConfig-like mock."""
    cfg = MagicMock()
    # domains.decision_making.warmup.enforcement_mode
    cfg.domains.decision_making.warmup.enforcement_mode = enforcement_mode
    # system.market_data (used by features_ready bar-TTL path)
    cfg.system = None
    return cfg


def _make_gates(
    *,
    clock=None,
    portfolio_fn=None,
    exposure_cache_fn=None,
    symbol_states: dict | None = None,
    per_symbol_regimes: dict | None = None,
    enforcement_mode: str = "strict",
    fail_closed_on_degraded: bool = False,
    features_ttl_sec: int = 10,
) -> ReadinessGates:
    if clock is None:
        clock = _make_clock()

    def _default_portfolio():
        return {
            "equity_free_usdt": "10000",
            "positions": [],
        }

    def _default_exposure_cache():
        return ({}, 0.0)

    cfg = _make_config(enforcement_mode=enforcement_mode)

    rg = ReadinessGates(
        clock=clock,
        config=cfg,
        features_ttl_sec=features_ttl_sec,
        symbol_states=symbol_states if symbol_states is not None else {},
        per_symbol_regimes=per_symbol_regimes if per_symbol_regimes is not None else {},
        get_portfolio=portfolio_fn or _default_portfolio,
        get_exposure_cache=exposure_cache_fn or _default_exposure_cache,
        emit_intent_deferred_v1=MagicMock(),
        record_blocked_intent=MagicMock(),
        fail_closed_on_degraded_context=fail_closed_on_degraded,
        degraded_context_critical_keys=None,
        degraded_context_critical_keys_by_strategy=None,
        logger=MagicMock(),
    )
    return rg


def _fresh_features(now_ms: int) -> dict:
    """Features event fresh enough to pass TTL (ts = now_ms)."""
    return {
        "ts": now_ms,
        "tf_sec": 0,
        "warmup": {"full_ready": True},
    }


def _full_regime(symbol: str = "BTCUSDT") -> dict:
    return {symbol: {"warmup": {"full_ready": True, "ticks_seen": 500}}}


# ---------------------------------------------------------------------------
# warmup_gate_before_trade_intent — reduce_only bypass
# ---------------------------------------------------------------------------

class TestWarmupGateReduceOnly:
    def test_reduce_only_bypasses_all_checks(self):
        rg = _make_gates(portfolio_fn=lambda: None)  # would normally block
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=True, context="test"
        )
        assert not blocked, "reduce_only must never block"


# ---------------------------------------------------------------------------
# warn_only mode
# ---------------------------------------------------------------------------

class TestWarmupGateWarnOnly:
    def test_warn_only_bypasses_gate(self):
        rg = _make_gates(
            portfolio_fn=lambda: None,  # would block in strict mode
            enforcement_mode="warn_only",
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert not blocked


# ---------------------------------------------------------------------------
# portfolio_missing → blocks
# ---------------------------------------------------------------------------

class TestWarmupGatePortfolioMissing:
    def test_none_portfolio_blocks(self):
        rg = _make_gates(portfolio_fn=lambda: None)
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked

    def test_empty_portfolio_blocks(self):
        rg = _make_gates(portfolio_fn=lambda: {})
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# features_missing → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateFeaturesMissing:
    def test_no_symbol_in_states_blocks(self):
        rg = _make_gates(symbol_states={})  # symbol absent
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked

    def test_state_has_no_features_key_blocks(self):
        rg = _make_gates(symbol_states={"BTCUSDT": {}})
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked

    def test_features_is_not_dict_blocks(self):
        rg = _make_gates(symbol_states={"BTCUSDT": {"features": "string_not_dict"}})
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# features_stale → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateFeaturesStale:
    def test_features_outside_ttl_blocks(self):
        now_ms = 1_700_000_000_000
        stale_ts = now_ms - 60_000  # 60 seconds ago, TTL=10s
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            features_ttl_sec=10,
            symbol_states={"BTCUSDT": {"features": {"ts": stale_ts, "tf_sec": 0, "warmup": {"full_ready": True}}}},
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# risk_missing → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateRiskMissing:
    def test_no_risk_in_state_blocks(self):
        now_ms = 1_700_000_000_000
        features = _fresh_features(now_ms)
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features}},  # no "risk" key
            per_symbol_regimes=_full_regime(),
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# regime_warmup_missing → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateRegimeMissing:
    def test_symbol_absent_from_per_symbol_regimes_blocks(self):
        now_ms = 1_700_000_000_000
        features = _fresh_features(now_ms)
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features, "risk": {"ok": True}}},
            per_symbol_regimes={},  # BTCUSDT not here
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked

    def test_warmup_key_absent_from_regime_blocks(self):
        now_ms = 1_700_000_000_000
        features = _fresh_features(now_ms)
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features, "risk": {"ok": True}}},
            per_symbol_regimes={"BTCUSDT": {}},  # no "warmup" key
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# regime_not_ready → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateRegimeNotReady:
    def test_full_ready_false_blocks(self):
        now_ms = 1_700_000_000_000
        features = _fresh_features(now_ms)
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features, "risk": {"ok": True}}},
            per_symbol_regimes={"BTCUSDT": {"warmup": {"full_ready": False, "ticks_seen": 10}}},
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# features_warmup_missing → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateFeaturesWarmupMissing:
    def test_no_warmup_key_in_features_blocks(self):
        now_ms = 1_700_000_000_000
        features = {"ts": now_ms, "tf_sec": 0}  # no "warmup" key
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features, "risk": {"ok": True}}},
            per_symbol_regimes=_full_regime(),
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# features_not_ready → blocks
# ---------------------------------------------------------------------------

class TestWarmupGateFeaturesNotReady:
    def test_fe_full_ready_false_blocks(self):
        now_ms = 1_700_000_000_000
        features = {"ts": now_ms, "tf_sec": 0, "warmup": {"full_ready": False}}
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features, "risk": {"ok": True}}},
            per_symbol_regimes=_full_regime(),
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert blocked


# ---------------------------------------------------------------------------
# Happy path — all gates pass
# ---------------------------------------------------------------------------

class TestWarmupGateHappyPath:
    def test_all_checks_satisfied_passes(self):
        now_ms = 1_700_000_000_000
        features = _fresh_features(now_ms)
        rg = _make_gates(
            clock=_make_clock(now_ms=now_ms),
            symbol_states={"BTCUSDT": {"features": features, "risk": {"ok": True}}},
            per_symbol_regimes=_full_regime(),
        )
        blocked = rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        assert not blocked


# ---------------------------------------------------------------------------
# precheck_exposure_cache
# ---------------------------------------------------------------------------

class TestPrecheckExposureCache:
    def test_empty_cache_blocks(self):
        rg = _make_gates(exposure_cache_fn=lambda: ({}, time.time()))
        result = rg.precheck_exposure_cache("BTCUSDT", "BUY", 1000.0)
        assert not result

    def test_none_cache_blocks(self):
        rg = _make_gates(exposure_cache_fn=lambda: (None, time.time()))
        result = rg.precheck_exposure_cache("BTCUSDT", "BUY", 1000.0)
        assert not result

    def test_stale_cache_blocks(self):
        now_sec = time.time()
        stale_ts = now_sec - 60.0  # 60 seconds ago > 30s threshold
        cache = {"BTCUSDT": {"current_exposure_usd": 0.0, "max_exposure_usd": 10000.0}}
        rg = _make_gates(
            clock=_make_clock(now_sec=now_sec),
            exposure_cache_fn=lambda: (cache, stale_ts),
        )
        result = rg.precheck_exposure_cache("BTCUSDT", "BUY", 1000.0)
        assert not result

    def test_over_max_exposure_blocks(self):
        now_sec = time.time()
        cache = {"BTCUSDT": {"current_exposure_usd": 9500.0, "max_exposure_usd": 10000.0}}
        rg = _make_gates(
            clock=_make_clock(now_sec=now_sec),
            exposure_cache_fn=lambda: (cache, now_sec),
        )
        # projected = 9500 + 1000 = 10500 > 10000
        result = rg.precheck_exposure_cache("BTCUSDT", "BUY", 1000.0)
        assert not result

    def test_within_max_exposure_passes(self):
        now_sec = time.time()
        cache = {"BTCUSDT": {"current_exposure_usd": 1000.0, "max_exposure_usd": 10000.0}}
        rg = _make_gates(
            clock=_make_clock(now_sec=now_sec),
            exposure_cache_fn=lambda: (cache, now_sec),
        )
        result = rg.precheck_exposure_cache("BTCUSDT", "BUY", 500.0)
        assert result

    def test_cache_exception_blocks(self):
        """A cache with non-numeric exposure values causes an exception → fail-closed."""
        now_sec = time.time()
        # current_exposure_usd is not a float → arithmetic raises TypeError
        cache = {"BTCUSDT": {"current_exposure_usd": "NOT_A_NUMBER", "max_exposure_usd": 10000.0}}
        rg = _make_gates(
            clock=_make_clock(now_sec=now_sec),
            exposure_cache_fn=lambda: (cache, now_sec),
        )
        result = rg.precheck_exposure_cache("BTCUSDT", "BUY", 500.0)
        # Should not raise; should return False (fail-closed on exception)
        assert not result


# ---------------------------------------------------------------------------
# degraded_context_gate_should_defer — disabled fast-path
# ---------------------------------------------------------------------------

class TestDegradedContextGate:
    def test_disabled_returns_false_immediately(self):
        rg = _make_gates(fail_closed_on_degraded=False)
        ctx = MagicMock()
        result = rg.degraded_context_gate_should_defer(
            symbol="BTCUSDT", rid="R1", ctx=ctx,
            features_evt={"ts": 1_700_000_000_000},
        )
        assert not result

    def test_enabled_no_contract_returns_false(self):
        """Enabled but no critical_keys configured → pass-through."""
        rg = _make_gates(fail_closed_on_degraded=True)
        ctx = MagicMock()
        ctx.missing_fields = {}
        result = rg.degraded_context_gate_should_defer(
            symbol="BTCUSDT", rid="R1", ctx=ctx,
            features_evt={"ts": 1_700_000_000_000},
        )
        assert not result


# ---------------------------------------------------------------------------
# get_live_blocker_evidence
# ---------------------------------------------------------------------------

class TestGetLiveBlockerEvidence:
    def test_empty_returns_empty_dict(self):
        rg = _make_gates()
        result = rg.get_live_blocker_evidence()
        assert result == {}

    def test_after_block_evidence_recorded(self):
        rg = _make_gates(portfolio_fn=lambda: None)
        rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        evidence = rg.get_live_blocker_evidence(symbol="BTCUSDT")
        assert "BTCUSDT" in evidence
        assert evidence["BTCUSDT"]["last_blocking_reason_code"] == "portfolio_missing"

    def test_symbol_filter_works(self):
        rg = _make_gates(portfolio_fn=lambda: None)
        rg.warmup_gate_before_trade_intent(
            symbol="BTCUSDT", rid="R1", reduce_only=False, context="test"
        )
        evidence = rg.get_live_blocker_evidence(symbol="ETHUSDT")
        assert "BTCUSDT" not in evidence
        assert evidence == {}
