"""TICK-BAR-SPLIT-FIX-3: md_amr local tf_sec guard with cooldown.

Verifies that MDAMRHandler explicitly rejects invalid tf_sec values
(None, 0, negative) with visible WARNING logs, instead of silently dropping.
Also verifies the cooldown prevents log storm.
"""
from __future__ import annotations

import logging
import time
from types import SimpleNamespace

import pytest

from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler


class _FSMStub:
    def __init__(self) -> None:
        self.listeners: list[tuple[str, object]] = []
        self.emitted: list[tuple[str, dict, str | None, object]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.append((event, handler))

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))

    def get_domain(self, _name: str):
        return None


def _make_config(symbol: str = "BNBUSDT"):
    asset_cfg = SimpleNamespace(
        enabled=True,
        cooldown_sec=60,
        allowed_regimes=["MEAN_REVERSION", "LOW_VOLATILITY"],
        exit=SimpleNamespace(sl_pct=0.005, tp_rr=1.0, regime_tpsl=None),
    )
    md_amr_cfg = SimpleNamespace(
        enabled=True,
        timeframe_sec=900,
        defer_ttl_sec=60,
        channel_window_bars=12,
        channel_robust_pct=0.05,
        atr_window=14,
        atr_stats_window=64,
        hysteresis_mult=1.20,
        threshold_z=2.20,
        volatility_dampening_factor=0.50,
        thr_base=0.55,
        thr_floor=0.10,
        alpha=0.25,
        conf_min=0.22,
        hold_edge_min=-0.5,
        target_approach_pct=0.0,
        max_hold_bars=16,
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        fee_bps=4.0,
        slippage_buffer_bps=2.0,
        scaleout_fraction=0.50,
        scaleout_cost_model="round_trip",
        hold_quality=SimpleNamespace(
            expected_progress_grace_frac=0.25,
            time_decay_weight=0.35,
            progress_deficit_weight=0.45,
        ),
        weights=SimpleNamespace(d1=0.35, h1=0.30, m30=0.20, m15=0.15),
        objective=SimpleNamespace(enabled=False),
        execution=SimpleNamespace(
            gtx_retry_max=2,
            emit_market_fallback_marker_on_retry_exhaustion=True),
        llm_gate=SimpleNamespace(
            enabled=False, sentiment_block_threshold=-0.8, block_ttl_sec=14_400),
        concentration_guard=SimpleNamespace(
            enabled=False, max_simultaneous_entries_per_bar=2),
        assets={symbol: asset_cfg},
    )
    return SimpleNamespace(
        basis_import_buffer=20,
        regime=SimpleNamespace(
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(sma_long_period=64),
                volatility=SimpleNamespace(atr_period=14, atr_sma_length=20),
            )
        ),
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                position_sizing=SimpleNamespace(
                    min_position_size_usd=10,
                    liquidity_based_cap_usd=10_000,
                )
            )
        ),
        strategies_registry=SimpleNamespace(assignments={symbol: ["md_amr"]}),
        strategies=SimpleNamespace(md_amr=md_amr_cfg),
    )


def _make_handler(symbol: str = "BNBUSDT") -> tuple[MDAMRHandler, _FSMStub]:
    fsm = _FSMStub()
    handler = MDAMRHandler(fsm=fsm, config=_make_config(symbol))
    return handler, fsm


def _make_event(pld: dict):
    return SimpleNamespace(pld=pld, verb="FEATURES_CALCULATED")


def _make_cmd_event(pld: dict):
    return SimpleNamespace(pld=pld, verb="PROCESS_STRATEGY")


def _reject_warnings(caplog_records: list) -> list:
    """Extract REJECTED md_amr warnings from caplog records."""
    return [
        r for r in caplog_records
        if r.levelno >= logging.WARNING and "REJECTED md_amr" in r.message
    ]


# ── _on_features_calculated guards ──


class TestFeaturesCalculatedTfSecGuard:

    def test_tf_sec_none_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": None,
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1
        assert "tf_sec_is_None" in warns[0].message

    def test_tf_sec_zero_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": 0,
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1
        assert "tf_sec_non_positive" in warns[0].message

    def test_tf_sec_negative_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": -1,
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1

    def test_tf_sec_string_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": "bad",
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1
        assert "tf_sec_invalid" in warns[0].message

    def test_tf_sec_valid_not_rejected(self, caplog):
        """Valid tf_sec (matching handler's timeframe) must not be rejected."""
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT",
                "tf_sec": 900,
                "features": {},
                "bar": {
                    "open": "100", "high": "101", "low": "99", "close": "100",
                    "end_ts_ms": 1_700_000_000_000,
                },
                "warmup": {},
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 0


# ── _on_process_strategy guards ──


class TestProcessStrategyTfSecGuard:

    def test_tf_sec_none_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_process_strategy(_make_cmd_event({
                "symbol": "BNBUSDT", "tf_sec": None,
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1
        assert "tf_sec_is_None" in warns[0].message

    def test_tf_sec_zero_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_process_strategy(_make_cmd_event({
                "symbol": "BNBUSDT", "tf_sec": 0,
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1

    def test_tf_sec_negative_rejected(self, caplog):
        handler, fsm = _make_handler()
        with caplog.at_level(logging.WARNING):
            handler._on_process_strategy(_make_cmd_event({
                "symbol": "BNBUSDT", "tf_sec": -5,
            }))
        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1


# ── Cooldown mechanism ──


class TestTfSecRejectCooldown:

    def test_repeated_calls_only_log_once(self, caplog):
        """Within cooldown window, identical rejections must log only once."""
        handler, fsm = _make_handler()

        with caplog.at_level(logging.WARNING):
            for _ in range(10):
                handler._on_features_calculated(_make_event({
                    "symbol": "BNBUSDT", "tf_sec": None,
                }))

        warns = _reject_warnings(caplog.records)
        assert len(warns) == 1

    def test_different_reasons_log_separately(self, caplog):
        """Different rejection reasons should each get their own log."""
        handler, fsm = _make_handler()

        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": None,
            }))
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": 0,
            }))

        warns = _reject_warnings(caplog.records)
        assert len(warns) == 2

    def test_cooldown_expires(self, caplog):
        """After cooldown expires, the same rejection should log again."""
        handler, fsm = _make_handler()
        handler._TF_SEC_REJECT_COOLDOWN_SEC = 0.01  # 10ms for test speed

        with caplog.at_level(logging.WARNING):
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": None,
            }))
            time.sleep(0.02)  # Wait past cooldown
            handler._on_features_calculated(_make_event({
                "symbol": "BNBUSDT", "tf_sec": None,
            }))

        warns = _reject_warnings(caplog.records)
        assert len(warns) == 2
