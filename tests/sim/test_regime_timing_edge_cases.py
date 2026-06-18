from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from apps.reference.bootstrap.startup_warmup import (
    resolve_feature_engineering_backfill_plan,
)
from apps.reference.config_loader import get_config
from apps.reference.contracts.runtime_regime_layers import attach_regime_provenance
from apps.reference.contracts.runtime_regime_layers import (
    is_structural_regime_payload,
    structural_regime_ref,
)
from apps.reference.contracts.strategy_compatibility_matrix import (
    regime_detector_required_bars,
)
from apps.reference.core.time.clock import MockClock
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.domains.strategies.runtimes.mean_reversion.handler import (
    MeanReversionHandler,
)
from apps.reference.domains.decision_making.gates.readiness_gates import ReadinessGates
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector


class RecordingFSM:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any], str | None]] = []

    def emit(self, event_name: str, payload: Any = None, why: str | None = None, *_args, **_kwargs) -> None:
        self.events.append((event_name, payload or {}, why))

    def listen(self, _event_name: str, _callback) -> None:
        return


class RegimeInjectionBridge:
    def __init__(self) -> None:
        self.last_regime: dict[str, dict[str, Any]] = {}

    def on_regime_detected(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or not is_structural_regime_payload(payload):
            return
        symbol = str(payload.get("symbol") or "")
        if symbol:
            self.last_regime[symbol] = dict(payload)

    def build_cmd(
        self,
        *,
        symbol: str,
        tf_sec: int,
        bar_close_ts: int,
        price: float = 100.0,
    ) -> dict[str, Any]:
        regime_snapshot = self.last_regime.get(symbol)
        if isinstance(regime_snapshot, dict):
            regime_snapshot = attach_regime_provenance(
                regime_snapshot,
                bar_close_ts_ms=int(bar_close_ts),
            )
        return {
            "symbol": symbol,
            "tf_sec": int(tf_sec),
            "bar_close_ts": int(bar_close_ts),
            "bar": _make_bar_payload(bar_close_ts=bar_close_ts, price=price),
            "features": {
                "price": str(price),
                "obi": "0.10",
                "tfi": "0.10",
            },
            "warmup": {"full_ready": True, "ready": {}},
            "structural_regime": (
                str(regime_snapshot.get("regime") or "UNCERTAIN")
                if isinstance(regime_snapshot, dict)
                else "UNCERTAIN"
            ),
            "regime": regime_snapshot,
        }


@dataclass(frozen=True)
class HysteresisStep:
    raw_regime: str
    stable_regime: str
    carried_previous_stable: bool


def _simulate_detector_hysteresis(raw_regimes: list[str], hysteresis_bars: int) -> list[HysteresisStep]:
    stable_regime = "UNCERTAIN"
    stable_confidence = Decimal("0.15")
    pending_regime = "UNCERTAIN"
    confirm_count = 0
    steps: list[HysteresisStep] = []

    for raw_regime in raw_regimes:
        raw_confidence = Decimal(
            "0.85") if raw_regime != "UNCERTAIN" else Decimal("0.15")

        if raw_regime == pending_regime:
            confirm_count += 1
        else:
            pending_regime = raw_regime
            confirm_count = 1

        if confirm_count >= hysteresis_bars:
            stable_regime = raw_regime
            stable_confidence = raw_confidence

        carried_previous_stable = bool(
            confirm_count < hysteresis_bars
            and (stable_regime != raw_regime or stable_confidence != raw_confidence)
        )
        steps.append(
            HysteresisStep(
                raw_regime=raw_regime,
                stable_regime=stable_regime,
                carried_previous_stable=carried_previous_stable,
            )
        )

    return steps


def _make_bar_payload(*, bar_close_ts: int, price: float) -> dict[str, Any]:
    return {
        "open": price,
        "high": price + 1.0,
        "low": price - 1.0,
        "close": price,
        "volume": 1000.0,
        "start_ts_ms": int(bar_close_ts) - 60_000,
        "trade_count": 10,
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


def _make_regime_event(
    *,
    symbol: str,
    regime: str,
    ts_ms: int,
    confidence: float = 0.85,
    heartbeat_ms: int | None = None,
) -> dict[str, Any]:
    payload = {
        "symbol": symbol,
        "ts": int(ts_ms),
        "ts_ms": int(ts_ms),
        "bar_close_ts_ms": int(ts_ms),
        "regime": regime,
        "confidence": float(confidence),
        "changed": True,
        "regime_layer": "structural",
        "regime_scope": "per_symbol",
        "regime_clock": "bar",
        "structural_regime_ref": structural_regime_ref(symbol, ts_ms),
        "last_update_ts_ms": int(heartbeat_ms if heartbeat_ms is not None else ts_ms),
    }
    return attach_regime_provenance(payload, bar_close_ts_ms=int(ts_ms))


def _build_mean_reversion_harness(symbols: list[str]) -> tuple[MeanReversionHandler, dict[str, MagicMock]]:
    handler = MeanReversionHandler(fsm=RecordingFSM(), config=get_config())
    handler._enabled = True
    handler._enabled_symbols = set(symbols)
    handler._apply_directional_bias = lambda *_args, **_kwargs: None

    strategies: dict[str, MagicMock] = {}
    for symbol in symbols:
        strategy = MagicMock()
        strategy.on_bar.return_value = None
        strategy.set_regime = MagicMock()
        strategy.config = SimpleNamespace(
            entry_threshold_long=None,
            entry_threshold_short=None,
            allowed_regimes=[
                "LOW_VOLATILITY",
                "TREND_DOWN",
                "MEAN_REVERSION",
                "UNCERTAIN",
            ],
        )
        strategies[symbol] = strategy

    handler._strategies = strategies
    return handler, strategies


def _build_aurora_harness() -> tuple[AuroraHandler, str, list[tuple[str, dict[str, Any]]], dict[str, Any], int]:
    emitted: list[tuple[str, dict[str, Any]]] = []
    wall_time_sec = 1_700_000_000.0
    monotonic_sec = 42_000.0
    captured_compute: dict[str, Any] = {}

    handler = AuroraHandler(
        config=get_config(),
        emit_fn=lambda event_name, payload: emitted.append(
            (event_name, payload)),
        strategy_id="aurora",
        monotonic_fn=lambda: monotonic_sec,
        wall_time_fn=lambda: wall_time_sec,
    )
    if not handler._enabled_symbols:
        raise AssertionError(
            "Aurora handler has no enabled symbols in runtime config")

    class TestKernel:
        @staticmethod
        def compute(**kwargs):
            captured_compute["kwargs"] = kwargs
            return SimpleNamespace(
                deferred=True,
                defer_reason="NRR-DATA-NOT-READY",
                side="NEUTRAL",
                score=Decimal("0"),
                raw_score=Decimal("0"),
                decision_score=Decimal("0"),
                sizing_score=Decimal("0"),
                shield_multiplier=1.0,
                admission_shield_multiplier=1.0,
                threshold_factor=1.0,
                thr_buy=Decimal("0.10"),
                thr_sell=Decimal("-0.10"),
                psi_vector={},
            )

    handler.scoring_kernel_cls = TestKernel
    handler._basis_required_bars_override = 1
    symbol = sorted(handler._enabled_symbols)[0]
    return handler, symbol, emitted, captured_compute, int(monotonic_sec * 1000)


def _make_aurora_cmd(*, symbol: str, tf_sec: int, bar_close_ts: int, regime: Any = None) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "tf_sec": int(tf_sec),
        "bar_close_ts": int(bar_close_ts),
        "bar": _make_bar_payload(bar_close_ts=bar_close_ts, price=100.0),
        "features": {
            "price": "100.0",
            "obi": "0.0",
            "tfi": "0.0",
            "delta_price": "0.0",
            "macro_resid": "0.0",
        },
        "warmup": {"full_ready": True, "ready": {}},
        "regime": regime,
    }


def _run_duplicate_and_skipped_sequence() -> list[str]:
    symbol = "BTCUSDT"
    handler, strategies = _build_mean_reversion_harness([symbol])
    bridge = RegimeInjectionBridge()
    used_regimes: list[str] = []
    strategies[symbol].set_regime.side_effect = lambda _symbol, regime: used_regimes.append(
        regime)

    base_ts = 1_700_000_000_000
    tf_sec = handler.timeframe_sec

    bridge.on_regime_detected(_make_regime_event(
        symbol=symbol, regime="LOW_VOLATILITY", ts_ms=base_ts))
    bridge.on_regime_detected(_make_regime_event(
        symbol=symbol, regime="LOW_VOLATILITY", ts_ms=base_ts))
    handler._on_process_strategy(
        SimpleNamespace(pld=bridge.build_cmd(
            symbol=symbol, tf_sec=tf_sec, bar_close_ts=base_ts + tf_sec * 1000))
    )

    handler._on_process_strategy(
        SimpleNamespace(pld=bridge.build_cmd(
            symbol=symbol, tf_sec=tf_sec, bar_close_ts=base_ts + 2 * tf_sec * 1000))
    )

    bridge.on_regime_detected(
        _make_regime_event(symbol=symbol, regime="TREND_DOWN",
                           ts_ms=base_ts + 2 * tf_sec * 1000)
    )
    handler._on_process_strategy(
        SimpleNamespace(pld=bridge.build_cmd(
            symbol=symbol, tf_sec=tf_sec, bar_close_ts=base_ts + 3 * tf_sec * 1000))
    )
    return used_regimes


def test_detector_alternating_stale_ready_cadence_is_explicit() -> None:
    cfg = get_config()
    required_bars = regime_detector_required_bars(cfg)
    bar_ttl_ms = int(cfg.system.market_data.bar_ttl_ms)
    clock = MockClock(start_ms=1_700_000_000_000)
    fsm = RecordingFSM()
    detector = RegimeDetector(config=cfg, fsm=fsm, clock=clock)
    symbol = "BTCUSDT"

    for idx in range(required_bars):
        detector.feed_warmup_bar(
            symbol,
            {
                "close": 100.0 + idx * 0.01,
                "high": 101.0 + idx * 0.01,
                "low": 99.0 + idx * 0.01,
                "open_ts": clock.now_ms() - (required_bars - idx) * int(cfg.basis_tf_sec) * 1000,
            },
        )

    clock.advance_ms(int(cfg.basis_tf_sec) * 1000)

    payloads: list[dict[str, Any]] = []
    for stale in (False, True, False, True):
        ts_ms = clock.now_ms() - (bar_ttl_ms + 1 if stale else max(bar_ttl_ms - 1, 0))
        detector.handle_event(
            _make_detector_event(
                symbol=symbol,
                ts_ms=ts_ms,
                price=101.0,
                tf_sec=int(cfg.basis_tf_sec),
            )
        )
        payloads.append(fsm.events[-1][1])
        clock.advance_ms(int(cfg.basis_tf_sec) * 1000)

    stale_payloads = payloads[1::2]
    fresh_payloads = payloads[0::2]

    assert all(payload["regime"] == "UNCERTAIN" for payload in stale_payloads)
    assert all(
        "stale_features" in payload["data_quality"]["drops"] for payload in stale_payloads)
    assert all(
        "stale_features" not in payload["data_quality"]["drops"] for payload in fresh_payloads)


def test_hysteresis_raw_regime_churn_can_look_missing_without_dropped_emission() -> None:
    steps = _simulate_detector_hysteresis(
        ["LOW_VOLATILITY", "TREND_DOWN", "LOW_VOLATILITY", "TREND_DOWN"],
        hysteresis_bars=2,
    )

    assert len(steps) == 4
    assert all(step.stable_regime == "UNCERTAIN" for step in steps)
    assert all(step.carried_previous_stable for step in steps)
    assert {step.raw_regime for step in steps} == {
        "LOW_VOLATILITY", "TREND_DOWN"}


def test_startup_required_bars_boundary_becomes_ready_at_threshold_and_buffer_only_expands_plan() -> None:
    cfg = get_config()
    required_bars = regime_detector_required_bars(cfg)
    plan = resolve_feature_engineering_backfill_plan(cfg)
    symbol = "BTCUSDT"
    start_ms = 1_700_100_000_000

    def _seed(detector: RegimeDetector, bars: int) -> None:
        for idx in range(bars):
            detector.feed_warmup_bar(
                symbol,
                {
                    "close": 100.0 + idx * 0.01,
                    "high": 101.0 + idx * 0.01,
                    "low": 99.0 + idx * 0.01,
                    "open_ts": start_ms - (bars - idx) * int(cfg.basis_tf_sec) * 1000,
                },
            )

    almost_ready_fsm = RecordingFSM()
    almost_ready_clock = MockClock(start_ms=start_ms)
    almost_ready_detector = RegimeDetector(
        cfg, almost_ready_fsm, clock=almost_ready_clock)
    _seed(almost_ready_detector, required_bars - 1)
    almost_ready_clock.advance_ms(int(cfg.basis_tf_sec) * 1000)
    almost_ready_detector.handle_event(
        _make_detector_event(
            symbol=symbol,
            ts_ms=almost_ready_clock.now_ms() - 1,
            price=102.0,
            tf_sec=int(cfg.basis_tf_sec),
        )
    )

    ready_fsm = RecordingFSM()
    ready_clock = MockClock(start_ms=start_ms)
    ready_detector = RegimeDetector(cfg, ready_fsm, clock=ready_clock)
    _seed(ready_detector, required_bars)
    ready_clock.advance_ms(int(cfg.basis_tf_sec) * 1000)
    ready_detector.handle_event(
        _make_detector_event(
            symbol=symbol,
            ts_ms=ready_clock.now_ms() - 1,
            price=102.0,
            tf_sec=int(cfg.basis_tf_sec),
        )
    )

    assert almost_ready_fsm.events[-1][1]["warmup"]["full_ready"] is False
    assert ready_fsm.events[-1][1]["warmup"]["full_ready"] is True
    assert plan.regime_basis_candles == required_bars + \
        int(cfg.basis_import_buffer)


def test_mr_one_bar_delayed_regime_event_uses_previous_cached_cmd_regime() -> None:
    symbol = "BTCUSDT"
    handler, strategies = _build_mean_reversion_harness([symbol])
    bridge = RegimeInjectionBridge()
    tf_sec = handler.timeframe_sec
    base_ts = 1_700_000_000_000

    bridge.on_regime_detected(_make_regime_event(
        symbol=symbol, regime="LOW_VOLATILITY", ts_ms=base_ts))

    first_cmd = bridge.build_cmd(
        symbol=symbol, tf_sec=tf_sec, bar_close_ts=base_ts + tf_sec * 1000)
    handler._on_process_strategy(
        SimpleNamespace(
            pld=first_cmd
        )
    )
    bridge.on_regime_detected(
        _make_regime_event(
            symbol=symbol,
            regime="TREND_DOWN",
            ts_ms=base_ts + tf_sec * 1000,
        )
    )
    second_cmd = bridge.build_cmd(
        symbol=symbol,
        tf_sec=tf_sec,
        bar_close_ts=base_ts + 2 * tf_sec * 1000,
    )
    handler._on_process_strategy(
        SimpleNamespace(
            pld=second_cmd
        )
    )

    assert strategies[symbol].set_regime.call_args_list[0].args == (
        symbol, "LOW_VOLATILITY")
    assert strategies[symbol].set_regime.call_args_list[1].args == (
        symbol, "TREND_DOWN")
    assert first_cmd["regime"]["regime_source"] == "cached_previous_bar"
    assert first_cmd["regime"]["regime_same_bar"] is False
    assert first_cmd["regime"]["regime_provenance_reason"] == "cached_previous_bar_regime"
    assert second_cmd["regime"]["regime_source"] == "cached_previous_bar"
    assert second_cmd["regime"]["regime_same_bar"] is False
    assert second_cmd["regime"]["regime_event_ts_ms"] == base_ts + tf_sec * 1000


def test_explicit_uncertain_regime_provenance_is_machine_readable() -> None:
    bridge = RegimeInjectionBridge()
    symbol = "BTCUSDT"
    bar_close_ts = 1_700_000_000_000

    bridge.on_regime_detected(
        _make_regime_event(
            symbol=symbol, regime="UNCERTAIN", ts_ms=bar_close_ts)
    )

    cmd = bridge.build_cmd(symbol=symbol, tf_sec=180,
                           bar_close_ts=bar_close_ts)

    assert cmd["regime"]["regime"] == "UNCERTAIN"
    assert cmd["regime"]["regime_source"] == "same_bar_detector"
    assert cmd["regime"]["regime_same_bar"] is True
    assert cmd["regime"]["regime_provenance_reason"] == "explicit_uncertain_same_bar"


def test_mr_cmd_before_features_event_does_not_reprocess_same_bar() -> None:
    symbol = "BTCUSDT"
    handler, strategies = _build_mean_reversion_harness([symbol])
    bridge = RegimeInjectionBridge()
    tf_sec = handler.timeframe_sec
    bar_close_ts = 1_700_000_180_000

    handler._on_process_strategy(
        SimpleNamespace(
            pld=bridge.build_cmd(
                symbol=symbol, tf_sec=tf_sec, bar_close_ts=bar_close_ts)
        )
    )
    assert strategies[symbol].on_bar.call_count == 1

    handler._on_features_calculated(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "tf_sec": tf_sec,
                "ts": bar_close_ts,
                "features": {"tfi": "0.25", "obi": "0.10"},
            }
        )
    )

    assert strategies[symbol].on_bar.call_count == 1
    assert handler._last_cmd_features[symbol] == {"tfi": "0.25", "obi": "0.10"}


def test_mr_cross_symbol_delays_are_isolated_per_symbol() -> None:
    symbol_a = "BTCUSDT"
    symbol_b = "ETHUSDT"
    handler, strategies = _build_mean_reversion_harness([symbol_a, symbol_b])
    bridge = RegimeInjectionBridge()
    tf_sec = handler.timeframe_sec
    base_ts = 1_700_000_000_000

    bridge.on_regime_detected(_make_regime_event(
        symbol=symbol_a, regime="LOW_VOLATILITY", ts_ms=base_ts))
    bridge.on_regime_detected(_make_regime_event(
        symbol=symbol_b, regime="TREND_DOWN", ts_ms=base_ts))
    bridge.on_regime_detected(
        _make_regime_event(
            symbol=symbol_b, regime="MEAN_REVERSION", ts_ms=base_ts + tf_sec * 1000)
    )

    handler._on_process_strategy(
        SimpleNamespace(pld=bridge.build_cmd(symbol=symbol_a,
                        tf_sec=tf_sec, bar_close_ts=base_ts + tf_sec * 1000))
    )
    handler._on_process_strategy(
        SimpleNamespace(pld=bridge.build_cmd(symbol=symbol_b,
                        tf_sec=tf_sec, bar_close_ts=base_ts + tf_sec * 1000))
    )

    assert strategies[symbol_a].set_regime.call_args_list[-1].args == (
        symbol_a, "LOW_VOLATILITY")
    assert strategies[symbol_b].set_regime.call_args_list[-1].args == (
        symbol_b, "MEAN_REVERSION")


def test_mr_duplicate_and_skipped_regime_events_replay_deterministically() -> None:
    first_run = _run_duplicate_and_skipped_sequence()
    second_run = _run_duplicate_and_skipped_sequence()

    assert first_run == ["LOW_VOLATILITY", "LOW_VOLATILITY", "TREND_DOWN"]
    assert second_run == first_run


def test_aurora_missing_regime_without_cache_blocks_with_canonical_reason() -> None:
    handler, symbol, emitted, _captured_compute, _heartbeat_ms = _build_aurora_harness()
    cmd = _make_aurora_cmd(
        symbol=symbol,
        tf_sec=int(handler.timeframe_sec),
        bar_close_ts=1_700_000_300_000,
        regime=None,
    )

    handler.on_process_strategy(cmd)

    blocked = [payload for event_name,
               payload in emitted if event_name == "EVT:STRATEGY_DECISION_BLOCKED"]
    deferred = [payload for event_name,
                payload in emitted if event_name == "EVT:INTENT_DEFERRED"]

    assert len(blocked) == 1
    assert blocked[0]["reason_code"] == "NRR-REGIME-NO-HEARTBEAT"
    assert blocked[0]["details"]["regime_source"] == "missing_detector_heartbeat"
    assert blocked[0]["details"]["regime_event_ts_ms"] is None
    assert blocked[0]["details"]["regime_same_bar"] is None
    assert blocked[0]["details"]["regime_provenance_reason"] == "missing_detector_heartbeat_fail_closed"
    assert deferred == []


def test_aurora_missing_regime_payload_uses_cached_previous_regime_with_traceable_ts() -> None:
    handler, symbol, emitted, captured_compute, heartbeat_ms = _build_aurora_harness()
    previous_bar_ts = 1_700_000_300_000
    current_bar_ts = previous_bar_ts + int(handler.timeframe_sec) * 1000
    handler._check_liquidity_gate = lambda **_kwargs: (True, {})

    handler.on_regime_detected(
        _make_regime_event(
            symbol=symbol,
            regime="LOW_VOLATILITY",
            ts_ms=previous_bar_ts,
            heartbeat_ms=heartbeat_ms,
        )
    )

    cmd = _make_aurora_cmd(
        symbol=symbol,
        tf_sec=int(handler.timeframe_sec),
        bar_close_ts=current_bar_ts,
        regime=None,
    )

    with patch(
        "apps.reference.domains.strategies.runtimes.aurora.decision.evaluate_quadratic_shadow",
        return_value=None,
    ), patch(
        "apps.reference.domains.strategies.runtimes.aurora.decision.write_intent_deferred",
        side_effect=lambda **kwargs: kwargs,
    ):
        handler.on_process_strategy(cmd)

    compute_kwargs = captured_compute["kwargs"]
    features = compute_kwargs["features"]
    blocked = [payload for event_name,
               payload in emitted if event_name == "EVT:STRATEGY_DECISION_BLOCKED"]
    deferred = [payload for event_name,
                payload in emitted if event_name == "EVT:INTENT_DEFERRED"]

    assert features["regime"] == "LOW_VOLATILITY"
    assert features["regime_ts_ms"] == previous_bar_ts
    assert features["bar_close_ts"] == current_bar_ts
    assert features["regime_source"] == "cached_previous_bar"
    assert features["regime_event_ts_ms"] == previous_bar_ts
    assert features["regime_same_bar"] is False
    assert features["regime_provenance_reason"] == "cached_previous_bar_regime"
    assert blocked == []
    assert len(deferred) == 1


def test_mr_cached_previous_bar_regime_surfaces_in_signal_payload() -> None:
    from tests.conftest import make_mr_signal

    symbol = "BTCUSDT"
    handler, strategies = _build_mean_reversion_harness([symbol])
    handler.config.domains.objective_engine.enabled = False
    handler._check_liquidity_gate = lambda _symbol: True
    bridge = RegimeInjectionBridge()
    tf_sec = handler.timeframe_sec
    base_ts = 1_700_000_000_000
    bar_close_ts = base_ts + tf_sec * 1000

    bridge.on_regime_detected(
        _make_regime_event(
            symbol=symbol, regime="LOW_VOLATILITY", ts_ms=base_ts)
    )
    strategies[symbol].on_bar.return_value = make_mr_signal(
        symbol=symbol,
        timestamp_ms=bar_close_ts,
        why="mr_cached_regime_provenance",
        flat_regime=SimpleNamespace(name="FLAT_LOW"),
    )

    handler._on_process_strategy(
        SimpleNamespace(
            pld=bridge.build_cmd(
                symbol=symbol, tf_sec=tf_sec, bar_close_ts=bar_close_ts)
        )
    )

    signal_payloads = [
        payload
        for event_name, payload, _why in handler.fsm.events
        if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED"
    ]

    assert len(signal_payloads) == 1
    regime_ctx = signal_payloads[0]["regime_ctx"]
    assert regime_ctx["regime"] == "LOW_VOLATILITY"
    assert regime_ctx["regime_source"] == "cached_previous_bar"
    assert regime_ctx["regime_event_ts_ms"] == base_ts
    assert regime_ctx["regime_same_bar"] is False
    assert regime_ctx["regime_provenance_reason"] == "cached_previous_bar_regime"


def test_bar_ttl_edge_is_inclusive_and_one_ms_over_fails_in_close_ts_mode() -> None:
    now_ms = 1_768_309_581_000
    ttl_ms = 10_000

    class DummyDecisionMaking:
        def __init__(self) -> None:
            self._clock = SimpleNamespace(now_ms=lambda: now_ms)
            self.config = SimpleNamespace(
                system=SimpleNamespace(
                    market_data=SimpleNamespace(
                        bar_ttl_ms=ttl_ms,
                        bar_event_age_mode="close_ts",
                    )
                )
            )
            self.features_ttl_sec = 2.0
            self.logger = MagicMock()

    dm = DummyDecisionMaking()

    at_boundary = {
        "ts": now_ms - ttl_ms,
        "tf_sec": 300,
        "bar_close_ts": now_ms - ttl_ms,
    }
    over_boundary = {
        "ts": now_ms - ttl_ms - 1,
        "tf_sec": 300,
        "bar_close_ts": now_ms - ttl_ms - 1,
    }

    assert ReadinessGates.features_ready(dm, "SOLUSDT", at_boundary) is True
    assert ReadinessGates.features_ready(dm, "SOLUSDT", over_boundary) is False
