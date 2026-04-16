from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.config_loader import get_config
from apps.reference.contracts.strategy_compatibility_matrix import (
    regime_detector_required_bars,
)
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
)
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector


class _MockFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, event: str, handler) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        payload = payload or {}
        self.emitted.append((event_name, payload, why, data_ref))
        message = SimpleNamespace(
            pld=payload,
            verb=event_name.split(":")[-1],
            op=event_name.split(":")[0],
        )
        for handler in self.listeners.get(event_name, []):
            handler(message)


def _bar(symbol: str, tf_sec: int, ts_ms: int, close: str = "100.0") -> dict:
    return {
        "symbol": symbol,
        "timeframe_sec": tf_sec,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": "10.0",
        "end_ts_ms": ts_ms,
    }


def _make_detector_event(*, symbol: str, ts_ms: int, price: float, tf_sec: int) -> SimpleNamespace:
    return SimpleNamespace(
        verb="FEATURES_CALCULATED",
        pld={
            "symbol": symbol,
            "ts": int(ts_ms),
            "close_boundary_ts_ms": int(ts_ms),
            "tf_sec": int(tf_sec),
            "features": {
                "price": str(price),
                "high": str(price + 1.0),
                "low": str(price - 1.0),
            },
        },
    )


def _seed_detector(detector: RegimeDetector, cfg, *, symbol: str, start_ms: int) -> None:
    required_bars = regime_detector_required_bars(cfg)
    for idx in range(required_bars):
        detector.feed_warmup_bar(
            symbol,
            {
                "close": 100.0 + idx * 0.01,
                "high": 101.0 + idx * 0.01,
                "low": 99.0 + idx * 0.01,
                "open_ts": start_ms - (required_bars - idx) * int(cfg.basis_tf_sec) * 1000,
            },
        )


def _build_stack() -> tuple[_MockFSM, FeatureEngineering, RegimeDetector, AuroraHandler, str, dict[str, dict]]:
    cfg = get_config().model_copy(deep=True)
    cfg.domains.feature_engineering.enabled_timeframes_sec = [300]
    cfg.domains.feature_engineering.warmup.enforcement_mode = "disabled"
    cfg.strategies.aurora.decision.scoring_version = "quadratic"

    fsm = _MockFSM()
    fe = FeatureEngineering(fsm=fsm, config=cfg)
    fe._log_features_to_file = lambda *_a, **_kw: None
    detector = RegimeDetector(config=cfg, fsm=fsm)
    handler = AuroraHandler(config=cfg, emit_fn=fsm.emit, strategy_id="aurora")
    handler._basis_required_bars_override = 0
    handler._check_liquidity_gate = lambda **_kwargs: (True, {})

    fsm.listen("EVT:REGIME_DETECTED",
               lambda msg: handler.on_regime_detected(msg.pld))
    fsm.listen("CMD:PROCESS_STRATEGY",
               lambda msg: handler.on_process_strategy(msg.pld))

    symbol = "BTCUSDT"
    captured: dict[str, dict] = {}
    return fsm, fe, detector, handler, symbol, captured


def _assert_reason(regime_payload: dict, *, same_bar: bool) -> None:
    if regime_payload["regime"] == "UNCERTAIN":
        expected = "explicit_uncertain_same_bar" if same_bar else "explicit_uncertain_cached_regime"
    else:
        expected = "same_bar_detector_truth" if same_bar else "cached_previous_bar_regime"
    assert regime_payload["regime_provenance_reason"] == expected


def test_detector_fe_aurora_same_bar_regime_provenance_is_explicit() -> None:
    fsm, _fe, detector, handler, symbol, captured = _build_stack()
    current_bar_ts = 1_700_000_300_000

    _seed_detector(detector, handler.config,
                   symbol=symbol, start_ms=current_bar_ts)

    real_compute = QuadraticScoringKernel.compute

    def _spy_compute(**kwargs):
        captured["features"] = dict(kwargs.get("features", {}))
        return real_compute(**kwargs)

    with patch.object(QuadraticScoringKernel, "compute", side_effect=_spy_compute):
        detector.handle_event(
            _make_detector_event(
                symbol=symbol,
                ts_ms=current_bar_ts,
                price=101.0,
                tf_sec=int(handler.config.basis_tf_sec),
            )
        )
        handler._symbol_states[symbol].last_regime_heartbeat_ms = int(
            handler.monotonic_fn() * 1000)

        fsm.emit(
            "EVT:BAR_CLOSED",
            {"bar": _bar(symbol, int(handler.config.basis_tf_sec),
                         current_bar_ts, close="101.0")},
            why="same_bar_regime",
        )

    cmd_payload = [payload for event_name, payload, _why,
                   _data_ref in fsm.emitted if event_name == "CMD:PROCESS_STRATEGY"][-1]
    features = captured["features"]

    assert cmd_payload["regime"]["regime_source"] == "same_bar_detector"
    assert cmd_payload["regime"]["regime_event_ts_ms"] == current_bar_ts
    assert cmd_payload["regime"]["regime_same_bar"] is True
    _assert_reason(cmd_payload["regime"], same_bar=True)

    assert features["regime_source"] == "same_bar_detector"
    assert features["regime_event_ts_ms"] == current_bar_ts
    assert features["regime_same_bar"] is True
    assert features["regime_provenance_reason"] == cmd_payload["regime"]["regime_provenance_reason"]


def test_detector_fe_aurora_current_bar_detector_truth_overrides_previous_cache() -> None:
    fsm, _fe, detector, handler, symbol, captured = _build_stack()
    previous_bar_ts = 1_700_000_300_000
    current_bar_ts = previous_bar_ts + int(handler.config.basis_tf_sec) * 1000

    _seed_detector(detector, handler.config,
                   symbol=symbol, start_ms=previous_bar_ts)

    real_compute = QuadraticScoringKernel.compute

    def _spy_compute(**kwargs):
        captured["features"] = dict(kwargs.get("features", {}))
        return real_compute(**kwargs)

    with patch.object(QuadraticScoringKernel, "compute", side_effect=_spy_compute):
        detector.handle_event(
            _make_detector_event(
                symbol=symbol,
                ts_ms=previous_bar_ts,
                price=101.0,
                tf_sec=int(handler.config.basis_tf_sec),
            )
        )
        handler._symbol_states[symbol].last_regime_heartbeat_ms = int(
            handler.monotonic_fn() * 1000)

        fsm.emit(
            "EVT:BAR_CLOSED",
            {"bar": _bar(symbol, int(handler.config.basis_tf_sec),
                         current_bar_ts, close="102.0")},
            why="cached_previous_regime",
        )

    cmd_payload = [payload for event_name, payload, _why,
                   _data_ref in fsm.emitted if event_name == "CMD:PROCESS_STRATEGY"][-1]
    features = captured["features"]

    assert cmd_payload["regime"]["regime_source"] == "same_bar_detector"
    assert cmd_payload["regime"]["regime_event_ts_ms"] == current_bar_ts
    assert cmd_payload["regime"]["regime_same_bar"] is True
    _assert_reason(cmd_payload["regime"], same_bar=True)

    assert features["regime_source"] == "same_bar_detector"
    assert features["regime_event_ts_ms"] == current_bar_ts
    assert features["regime_same_bar"] is True
    assert features["regime_provenance_reason"] == cmd_payload["regime"]["regime_provenance_reason"]
