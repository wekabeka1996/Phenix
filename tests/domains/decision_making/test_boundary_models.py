"""Tests for Pydantic v2 boundary models (Package 1).

Covers parse-success, parse-rejection, and property behaviour for:
  - ProcessStrategyBoundary
  - RegimeDetectedBoundary
  - TradeIntentRoutingEnvelope
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.reference.domains.decision_making.contracts.boundary_models import (
    ProcessStrategyBoundary,
    RegimeDetectedBoundary,
    TradeIntentRoutingEnvelope,
)


# ──────────────────────────────────────────────────────────────
# ProcessStrategyBoundary
# ──────────────────────────────────────────────────────────────

class TestProcessStrategyBoundary:
    def test_minimal_valid(self):
        b = ProcessStrategyBoundary.model_validate({"symbol": "BTCUSDT"})
        assert b.symbol == "BTCUSDT"
        assert b.tf_sec is None
        assert b.bar_close_ts is None
        assert b.rid is None
        assert b.features is None
        assert b.warmup is None
        assert b.price_motion is None
        assert b.regime is None
        assert b.structural_regime is None

    def test_full_payload(self):
        b = ProcessStrategyBoundary.model_validate({
            "symbol": "ETHUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000,
            "rid": "req-1",
            "features": {"pillar_sum": 0.5, "atr": 0.01},
            "warmup": {"full_ready": True, "ticks_seen": 321, "ready": {}},
            "price_motion": {"pm_norm_300s": 0.7, "ret_300s": 0.002},
            "regime": {"regime": "HIGH_VOLATILITY", "confidence": 0.8},
            "structural_regime": "TREND_UP",
        })
        assert b.symbol == "ETHUSDT"
        assert b.tf_sec == 300
        assert b.bar_close_ts == 1700000000
        assert b.rid == "req-1"
        assert b.features == {"pillar_sum": 0.5, "atr": 0.01}
        assert b.warmup["full_ready"] is True
        assert b.price_motion == {"pm_norm_300s": 0.7, "ret_300s": 0.002}
        assert b.regime["regime"] == "HIGH_VOLATILITY"
        assert b.structural_regime == "TREND_UP"

    def test_extra_fields_ignored(self):
        """extra="ignore" — unknown fields must not cause a failure."""
        b = ProcessStrategyBoundary.model_validate({
            "symbol": "BTCUSDT",
            "bar": {"open": 100, "close": 101},
            "diagnostics": {"some_key": 1},
            "source_mode": "live",
        })
        assert b.symbol == "BTCUSDT"

    def test_missing_symbol_raises(self):
        with pytest.raises(ValidationError):
            ProcessStrategyBoundary.model_validate({"tf_sec": 300})

    def test_frozen(self):
        b = ProcessStrategyBoundary.model_validate({"symbol": "BTCUSDT"})
        with pytest.raises(Exception):  # frozen=True raises ValidationError or TypeError
            b.symbol = "ETHUSDT"  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
# RegimeDetectedBoundary
# ──────────────────────────────────────────────────────────────

class TestRegimeDetectedBoundary:
    def test_minimal_valid(self):
        b = RegimeDetectedBoundary.model_validate({
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
        })
        assert b.symbol == "BTCUSDT"
        assert b.regime == "TREND_UP"
        assert b.confidence is None
        assert b.changed is None

    def test_full_payload(self):
        b = RegimeDetectedBoundary.model_validate({
            "symbol": "ETHUSDT",
            "regime": "TREND_DOWN",
            "confidence": "0.91",
            "ts": 1700000000000000,
            "ts_ms": 1700000000000,
            "changed": True,
            "last_update_ts_ms": 1699999999000,
            "structural_regime_ref": "BEAR_TREND",
            "raw_regime": "BEAR_TREND",
            "raw_confidence": "0.87",
            "stable_confidence": "0.88",
            "storm_rejected": False,
        })
        assert b.regime == "TREND_DOWN"
        assert b.confidence == "0.91"  # raw string preserved at boundary
        assert b.changed is True
        assert b.ts_ms == 1700000000000

    def test_extra_fields_allowed(self):
        """extra="allow" — diagnostic fields (vol_ratio, etc.) must not fail."""
        b = RegimeDetectedBoundary.model_validate({
            "symbol": "BTCUSDT",
            "regime": "UNCERTAIN",
            "vol_ratio": 1.23,
            "vol_ratio_slope": -0.5,
            "custom_diagnostic": "foo",
        })
        assert b.symbol == "BTCUSDT"
        assert b.regime == "UNCERTAIN"

    def test_missing_symbol_raises(self):
        with pytest.raises(ValidationError):
            RegimeDetectedBoundary.model_validate({"regime": "TREND_UP"})

    def test_missing_regime_raises(self):
        with pytest.raises(ValidationError):
            RegimeDetectedBoundary.model_validate({"symbol": "BTCUSDT"})

    def test_confidence_int_coercion(self):
        """Confidence may arrive as int (0 or 1)."""
        b = RegimeDetectedBoundary.model_validate({
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 1,
        })
        assert b.confidence == 1

    def test_confidence_float(self):
        b = RegimeDetectedBoundary.model_validate({
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 0.75,
        })
        assert b.confidence == 0.75


# ──────────────────────────────────────────────────────────────
# TradeIntentRoutingEnvelope
# ──────────────────────────────────────────────────────────────

class TestTradeIntentRoutingEnvelope:
    def test_resolved_symbol_prefers_instrument(self):
        e = TradeIntentRoutingEnvelope.model_validate({
            "instrument": "BTCUSDT",
            "symbol": "ETHUSDT",
        })
        assert e.resolved_symbol == "BTCUSDT"

    def test_resolved_symbol_falls_back_to_symbol(self):
        e = TradeIntentRoutingEnvelope.model_validate({"symbol": "ETHUSDT"})
        assert e.resolved_symbol == "ETHUSDT"

    def test_resolved_symbol_empty_when_absent(self):
        e = TradeIntentRoutingEnvelope.model_validate({})
        assert e.resolved_symbol == ""

    def test_resolved_strategy_id_prefers_strategy(self):
        e = TradeIntentRoutingEnvelope.model_validate({
            "strategy": "aurora",
            "strategy_id": "aurora_v2",
        })
        assert e.resolved_strategy_id == "aurora"

    def test_resolved_strategy_id_none_when_absent(self):
        e = TradeIntentRoutingEnvelope.model_validate({})
        assert e.resolved_strategy_id is None

    def test_resolved_rid_fallback(self):
        e = TradeIntentRoutingEnvelope.model_validate({})
        assert e.resolved_rid == "unknown"

    def test_resolved_rid_present(self):
        e = TradeIntentRoutingEnvelope.model_validate({"rid": "req-42"})
        assert e.resolved_rid == "req-42"

    def test_is_reduce_only_top_level_flag(self):
        e = TradeIntentRoutingEnvelope.model_validate({"reduce_only": True})
        assert e.is_reduce_only is True

    def test_is_reduce_only_nested_reduce_only(self):
        e = TradeIntentRoutingEnvelope.model_validate({
            "order": {"reduce_only": True}
        })
        assert e.is_reduce_only is True

    def test_is_reduce_only_nested_reduceOnly(self):
        e = TradeIntentRoutingEnvelope.model_validate({
            "order": {"reduceOnly": True}
        })
        assert e.is_reduce_only is True

    def test_is_reduce_only_false_by_default(self):
        e = TradeIntentRoutingEnvelope.model_validate({
            "instrument": "BTCUSDT",
        })
        assert e.is_reduce_only is False

    def test_extra_fields_ignored(self):
        """Routing envelope is extract-only; unknown payload fields are silently dropped."""
        e = TradeIntentRoutingEnvelope.model_validate({
            "instrument": "BTCUSDT",
            "strategy": "aurora",
            "risk_budget": {"max": 100},
            "entry_plan": {"entry_price": "42000"},
        })
        assert e.resolved_symbol == "BTCUSDT"

    def test_frozen(self):
        e = TradeIntentRoutingEnvelope.model_validate(
            {"instrument": "BTCUSDT"})
        with pytest.raises(Exception):
            e.instrument = "ETHUSDT"  # type: ignore[misc]
