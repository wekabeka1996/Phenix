from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class _MockSMAConfig:
    sma_short_period = 3
    sma_long_period = 8
    confidence_multiplier = 20.0
    confidence_min = 0.15
    confidence_max = 0.85


class _MockVolatilityConfig:
    enabled = False
    atr_period = 5
    atr_sma_length = 10
    allow_close_to_close_atr = False
    threshold_multiplier = 1.5
    low_vol_multiplier = 0.6
    high_vol_confidence_multiplier = 2.0
    low_vol_confidence_multiplier = 3.0


class _MockMeanReversionConfig:
    threshold = 0.005
    confidence_multiplier = 100.0


class _MockModelsConfig:
    sma_trend = _MockSMAConfig()
    volatility = _MockVolatilityConfig()
    mean_reversion = _MockMeanReversionConfig()


class _MockSystemMarketData:
    bar_ttl_ms = 10_000
    tick_ttl_ms = 2_000


class _MockSystem:
    market_data = _MockSystemMarketData()


class _MockAuroraConfig:
    basis_tf_sec = 300
    uncertain_cutoff = 0.22
    liveness_factor = 3
    hysteresis_bars = 1
    vol_slope_gate_enabled = False
    vol_slope_gate_eps = 0.0
    vol_slope_gate_confirm_bars = 2
    models = _MockModelsConfig()
    system = _MockSystem()


class _MockFSM:
    def __init__(self) -> None:
        self.emitted: list[dict] = []
        self.listeners: dict[str, object] = {}

    def emit(self, verb, payload, why="", **kwargs):
        self.emitted.append(
            {"verb": verb, "payload": payload, "why": why, "kwargs": kwargs}
        )

    def listen(self, verb, handler):
        self.listeners[verb] = handler


class _MockClock:
    def __init__(self, now_ms_val: int = 1_700_000_000_000) -> None:
        self._now_ms = now_ms_val
        self._monotonic = now_ms_val / 1000.0

    def now_ms(self):
        return self._now_ms

    def monotonic(self):
        return self._monotonic

    def advance(self, ms: int) -> None:
        self._now_ms += ms
        self._monotonic += ms / 1000.0


def _features_event(
    *,
    ts_ms: int,
    price: float,
    sma_short: float,
    sma_long: float,
    symbol: str = "BTCUSDT",
) -> SimpleNamespace:
    return SimpleNamespace(
        verb="FEATURES_CALCULATED",
        pld={
            "symbol": symbol,
            "ts": ts_ms,
            "tf_sec": 300,
            "features": {
                "price": price,
                "sma_short": sma_short,
                "sma_long": sma_long,
            },
        },
    )


def test_regime_detector_emits_canonical_bar_close_audit_with_boundaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    audit_path = tmp_path / "regime_confidence_audit_v1.jsonl"
    monkeypatch.setenv("REGIME_CONFIDENCE_AUDIT_LOG_FILE", str(audit_path))

    detector = RegimeDetector(_MockAuroraConfig(), _MockFSM(), clock=_MockClock())

    detector.handle_event(
        _features_event(
            ts_ms=1_700_000_000_000,
            price=54_100.0,
            sma_short=54_000.0,
            sma_long=50_000.0,
        )
    )
    detector.handle_event(
        _features_event(
            ts_ms=1_700_000_300_000,
            price=54_150.0,
            sma_short=54_000.0,
            sma_long=50_000.0,
        )
    )
    detector.handle_event(
        _features_event(
            ts_ms=1_700_000_600_000,
            price=50_350.0,
            sma_short=50_010.0,
            sma_long=50_000.0,
        )
    )

    records = _read_jsonl(audit_path)
    assert len(records) == 3

    strong_transition = records[0]
    strong_heartbeat = records[1]
    floor_demotion = records[2]

    assert strong_transition["record_type"] == "bar_close"
    assert strong_transition["changed"] is True
    assert strong_transition["regime"] == "TREND_UP"
    assert strong_transition["raw_regime"] == "TREND_UP"
    assert strong_transition["emitted_confidence"] == 0.85
    assert strong_transition["pre_cutoff_clamped_to_max"] is True
    assert strong_transition["pre_cutoff_boundary_reason"] == "trend_ceiling_clamp"
    assert strong_transition["demoted_to_uncertain"] is False

    assert strong_heartbeat["changed"] is False
    assert strong_heartbeat["regime"] == "TREND_UP"
    assert strong_heartbeat["emitted_confidence"] == 0.85
    assert strong_heartbeat["emitted_confidence_kind"] == "stable_heartbeat"

    assert floor_demotion["changed"] is True
    assert floor_demotion["regime"] == "UNCERTAIN"
    assert floor_demotion["pre_cutoff_regime"] == "TREND_UP"
    assert floor_demotion["pre_cutoff_confidence"] == 0.15
    assert floor_demotion["raw_confidence"] == 0.15
    assert floor_demotion["stable_confidence"] == 0.15
    assert floor_demotion["emitted_confidence"] == 0.15
    assert floor_demotion["pre_cutoff_clamped_to_min"] is True
    assert floor_demotion["pre_cutoff_boundary_reason"] == "trend_floor_clamp"
    assert floor_demotion["demoted_to_uncertain"] is True
    assert floor_demotion["uncertain_cutoff"] == 0.22
    assert floor_demotion["bar_close_ts_ms"] in {1_700_000_600_000, 1_700_000_600_001}
    assert "uncertain_cutoff" in floor_demotion["reason_summary"]
