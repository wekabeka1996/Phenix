"""Tests for boundary mappers (Package 1).

Covers:
  - map_process_strategy_boundary_to_cmd: field fidelity, warmup mapping,
    MappingProxyType wrapping, raw pass-through.
  - map_regime_boundary_to_event: regime normalization, timestamp resolution,
    confidence float-resolution, raw_confidence string preservation.
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from apps.reference.domains.decision_making.contracts.boundary_mappers import (
    _map_warmup,
    _resolve_confidence,
    map_process_strategy_boundary_to_cmd,
    map_regime_boundary_to_event,
)
from apps.reference.domains.decision_making.contracts.boundary_models import (
    ProcessStrategyBoundary,
    RegimeDetectedBoundary,
)
from apps.reference.domains.decision_making.contracts.core_models import (
    ProcessStrategyCmd,
    RegimeEvent,
    WarmupState,
)


# ──────────────────────────────────────────────────────────────
# _map_warmup
# ──────────────────────────────────────────────────────────────

class TestMapWarmup:
    def test_none_input_produces_zero_state(self):
        ws = _map_warmup(None)
        assert ws.full_ready is False
        assert ws.ticks_seen == 0
        assert dict(ws.ready) == {}
        assert ws.reasons == ()

    def test_full_warmup(self):
        ws = _map_warmup({
            "full_ready": True,
            "ticks_seen": 321,
            "ready": {"atr_ready": True, "obi_ready": False},
            "reasons": ["waiting_for_obi"],
        })
        assert ws.full_ready is True
        assert ws.ticks_seen == 321
        assert ws.ready["atr_ready"] is True
        assert ws.ready["obi_ready"] is False
        assert ws.reasons == ("waiting_for_obi",)

    def test_ready_is_mapping_proxy(self):
        ws = _map_warmup({"ready": {"atr_ready": True}})
        assert isinstance(ws.ready, MappingProxyType)

    def test_frozen_dataclass(self):
        ws = _map_warmup({})
        with pytest.raises(Exception):
            ws.full_ready = True  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
# _resolve_confidence
# ──────────────────────────────────────────────────────────────

class TestResolveConfidence:
    def test_none_returns_none(self):
        assert _resolve_confidence(None) is None

    def test_float_passthrough(self):
        assert _resolve_confidence(0.75) == pytest.approx(0.75)

    def test_string_coerced(self):
        assert _resolve_confidence("0.91") == pytest.approx(0.91)

    def test_int_coerced(self):
        assert _resolve_confidence(1) == pytest.approx(1.0)

    def test_invalid_string_returns_none(self):
        assert _resolve_confidence("not_a_number") is None

    def test_scientific_notation(self):
        assert _resolve_confidence("5.5511E-17") == pytest.approx(5.5511e-17)


# ──────────────────────────────────────────────────────────────
# map_process_strategy_boundary_to_cmd
# ──────────────────────────────────────────────────────────────

class TestMapProcessStrategyBoundaryToCmd:
    def _make_boundary(self, payload: dict) -> ProcessStrategyBoundary:
        return ProcessStrategyBoundary.model_validate(payload)

    def test_basic_mapping(self):
        raw = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000,
            "rid": "req-1",
            "features": {"pillar_sum": 0.5},
            "warmup": {"full_ready": True, "ticks_seen": 10, "ready": {}},
        }
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        assert isinstance(cmd, ProcessStrategyCmd)
        assert cmd.symbol == "BTCUSDT"
        assert cmd.tf_sec == 300
        assert cmd.bar_close_ts == 1700000000
        assert cmd.rid == "req-1"

    def test_features_is_mapping_proxy(self):
        raw = {"symbol": "BTCUSDT", "features": {"atr": 0.01}}
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        assert isinstance(cmd.features, MappingProxyType)
        assert cmd.features["atr"] == pytest.approx(0.01)

    def test_raw_is_mapping_proxy(self):
        raw = {"symbol": "BTCUSDT", "bar": {"close": 42000}}
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        assert isinstance(cmd.raw, MappingProxyType)
        assert cmd.raw["bar"]["close"] == 42000

    def test_none_features_produces_empty_mapping(self):
        raw = {"symbol": "BTCUSDT"}
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        assert dict(cmd.features) == {}

    def test_none_tf_sec_preserved(self):
        raw = {"symbol": "BTCUSDT"}
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        assert cmd.tf_sec is None

    def test_warmup_typed(self):
        raw = {
            "symbol": "BTCUSDT",
            "warmup": {"full_ready": True, "ticks_seen": 321, "ready": {"atr_ready": True}},
        }
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        assert isinstance(cmd.warmup, WarmupState)
        assert cmd.warmup.full_ready is True
        assert cmd.warmup.ticks_seen == 321
        assert cmd.warmup.ready["atr_ready"] is True

    def test_features_mutable_copy(self):
        """dict(cmd.features) must produce a mutable copy — not raise."""
        raw = {"symbol": "BTCUSDT", "features": {"x": 1}}
        boundary = self._make_boundary(raw)
        cmd = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        mutable = dict(cmd.features)
        mutable["new_key"] = 99  # must not raise
        assert "new_key" not in cmd.features  # original unchanged


# ──────────────────────────────────────────────────────────────
# map_regime_boundary_to_event
# ──────────────────────────────────────────────────────────────

class TestMapRegimeBoundaryToEvent:
    def _make_boundary(self, payload: dict) -> RegimeDetectedBoundary:
        return RegimeDetectedBoundary.model_validate(payload)

    def test_basic_mapping(self):
        raw = {"symbol": "BTCUSDT", "regime": "TREND_UP", "confidence": "0.85"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert isinstance(evt, RegimeEvent)
        assert evt.symbol == "BTCUSDT"
        assert evt.confidence == pytest.approx(0.85)

    def test_regime_normalization_bull_trend(self):
        """BULL_TREND → TREND_UP via normalize_structural_regime_label."""
        raw = {"symbol": "BTCUSDT", "regime": "BULL_TREND"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.regime == "TREND_UP"

    def test_regime_normalization_bear_trend(self):
        raw = {"symbol": "BTCUSDT", "regime": "BEAR_TREND"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.regime == "TREND_DOWN"

    def test_unknown_regime_passes_through(self):
        raw = {"symbol": "BTCUSDT", "regime": "UNCERTAIN"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.regime == "UNCERTAIN"

    def test_ts_ms_preferred_over_ts(self):
        raw = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "ts": 1700000000000000,   # microseconds
            "ts_ms": 1700000000999,   # milliseconds — should win
        }
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.ts_ms == 1700000000999

    def test_ts_fallback_to_ts_div_1000(self):
        raw = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "ts": 1700000000123456,  # microseconds
        }
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        # ts // 1000 = 1700000000123
        assert evt.ts_ms == 1700000000123

    def test_missing_timestamps_produces_zero(self):
        raw = {"symbol": "BTCUSDT", "regime": "TREND_UP"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.ts_ms == 0

    def test_raw_confidence_preserved_as_string_in_raw(self):
        """raw.get('raw_confidence') must return the original string, not float."""
        raw = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "raw_confidence": "0.91",
        }
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        # evt.raw_confidence is float-resolved
        assert evt.raw_confidence == pytest.approx(0.91)
        # evt.raw carries the original string
        assert evt.raw.get("raw_confidence") == "0.91"

    def test_raw_is_mapping_proxy(self):
        raw = {"symbol": "BTCUSDT", "regime": "TREND_UP", "extra_field": "x"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert isinstance(evt.raw, MappingProxyType)
        assert evt.raw.get("extra_field") == "x"

    def test_confidence_none_when_absent(self):
        raw = {"symbol": "BTCUSDT", "regime": "TREND_UP"}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.confidence is None

    def test_changed_field(self):
        raw = {"symbol": "BTCUSDT", "regime": "TREND_UP", "changed": False}
        boundary = self._make_boundary(raw)
        evt = map_regime_boundary_to_event(boundary, raw=raw)
        assert evt.changed is False
