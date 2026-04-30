"""Regression tests for the portfolio position field-name split-brain fix.

Root cause: position_tracking domain emits ``net_position`` (per
portfolio_state_v1.json schema), but several execution_position consumers
read ``positionAmt`` (Binance REST field name).  The sidecar normalizer
already handled both via ``_first_present_value``, but the FSM handler's
``_get_portfolio_state_for_symbol()`` and ``build_position_signature()`` did
not — causing 100% false ``portfolio_flat_no_live_net_position`` suppression
of valid close requests in the first real enable runtime.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.config_models import PositionPolicySidecarConfig
from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.position_policy_sidecar import (
    PositionPolicySidecar,
)
from apps.reference.domains.execution_position.truth_hardening import (
    build_position_signature,
)
from tests.domains.execution_position.test_position_policy_sidecar import DummyManageFlow


# ---------------------------------------------------------------------------
# Test infrastructure (same patterns as test_position_policy_sidecar.py)
# ---------------------------------------------------------------------------


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []
        self.listeners: dict[str, list] = {}

    def listen(self, topic, handler):
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic, payload=None, **kwargs):
        payload = payload or {}
        self.events.append((topic, payload, kwargs))
        for handler in self.listeners.get(topic, []):
            handler(SimpleNamespace(pld=payload, verb=topic.split(":")[-1],
                                    rid=payload.get("rid")))


def _event(**payload):
    return SimpleNamespace(pld=payload)


def _topics(bus: RecordingBus) -> list[str]:
    return [topic for topic, _, _ in bus.events]


def _payloads(bus: RecordingBus, topic: str) -> list[dict]:
    return [p for t, p, _ in bus.events if t == topic]


def _sidecar_config(
    tmp_path: Path,
    *,
    mode: str = "enable",
    recommend_soft_close_at: float = 0.45,
) -> PositionPolicySidecarConfig:
    return PositionPolicySidecarConfig.model_validate(
        {
            "mode": mode,
            "freshness": {
                "portfolio_max_age_ms": 15_000,
                "features_max_age_ms": 15_000,
                "regime_max_age_ms": 15_000,
                "order_state_max_age_ms": 15_000,
            },
            "startup_grace": {
                "startup_grace_ms": 0,
                "post_fill_grace_ms": 0,
                "min_portfolio_updates": 1,
                "min_feature_updates": 1,
                "min_regime_updates": 1,
            },
            "profitability_guard": {
                "enabled": True,
                "min_unrealized_pnl_pct": 0.25,
                "min_unrealized_pnl_usdt": 0.0,
            },
            "scoring": {
                "weights": {
                    "microstructure_adverse_pressure": 0.30,
                    "regime_exhaustion_hint": 0.30,
                    "conviction_decay": 0.15,
                    "unrealized_loss_pressure": 0.25,
                },
                "caps": {
                    "microstructure_adverse_pressure": 1.0,
                    "regime_exhaustion_hint": 1.0,
                    "conviction_decay": 1.0,
                    "unrealized_loss_pressure": 1.0,
                },
            },
            "thresholds": {
                "recommend_soft_close_at": recommend_soft_close_at,
                "loss_bps_full_pressure": 50.0,
                "adverse_price_distance_bps_full_pressure": 25.0,
                "book_imbalance_full_pressure": 0.35,
                "regime_confidence_floor": 0.55,
                "signal_score_floor": 0.0,
                "adverse_regimes_long": ["TREND_DOWN"],
                "adverse_regimes_short": ["TREND_UP"],
            },
            "logging": {
                "emit_internal_bus_events": True,
                "write_trade_lifecycle_jsonl": True,
                "trade_lifecycle_log_path": str(tmp_path / "tl.jsonl"),
                "include_score_payloads": True,
            },
            "allowed_actions": {
                "soft_close_symbol_current_net_only": True,
                "partial_reduce": False,
                "bracket_mutation": False,
                "exact_targeting": False,
            },
            "peak_giveback_close": {
                "enabled": False,
                "edge_arm_usd": 25.0,
                "giveback_trigger_pct": 50.0,
            },
        }
    )


def _make_fsm(fsm_config, bus, tmp_path):
    """Build an ExecPosFSM with sidecar in enable mode."""
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    fsm_config.domains.execution_position.position_policy_sidecar = _sidecar_config(
        tmp_path, mode="enable"
    )
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)
    return fsm


def _seed_sidecar(sidecar, now_ms, *, portfolio_payload, symbol="BTCUSDT"):
    """Feed sidecar the 3-step sequence that triggers evaluation."""
    sidecar.on_portfolio_state_updated(_event(**portfolio_payload))
    sidecar.on_features_calculated(
        _event(
            symbol=symbol,
            ts_ms=now_ms + 1,
            orderbook_imbalance=-1.0,
            price_vs_vwap_bps=-80.0,
            signal_score=-0.5,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol=symbol, ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )


# ---------------------------------------------------------------------------
# Part 1: _get_portfolio_state_for_symbol — unit tests
# ---------------------------------------------------------------------------


class TestGetPortfolioStateForSymbol:
    """Direct unit tests for ExecPosFSM._get_portfolio_state_for_symbol."""

    def _make_fsm_bare(self, fsm_config, tmp_path):
        bus = RecordingBus()
        return _make_fsm(fsm_config, bus, tmp_path)

    def test_net_position_field_returns_short(self, fsm_config, tmp_path):
        """Canonical schema field ``net_position`` is correctly read."""
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "SOLUSDT", "net_position": "-15.87"}]
        }
        assert fsm._get_portfolio_state_for_symbol("SOLUSDT") == "SHORT"

    def test_net_position_field_returns_long(self, fsm_config, tmp_path):
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "ETHUSDT", "net_position": "3.8"}]
        }
        assert fsm._get_portfolio_state_for_symbol("ETHUSDT") == "LONG"

    def test_positionAmt_legacy_field_still_works(self, fsm_config, tmp_path):
        """Legacy Binance ``positionAmt`` is still supported as fallback."""
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "BTCUSDT", "positionAmt": "-0.05"}]
        }
        assert fsm._get_portfolio_state_for_symbol("BTCUSDT") == "SHORT"

    def test_net_position_preferred_over_positionAmt(self, fsm_config, tmp_path):
        """If both fields present, ``net_position`` wins."""
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [
                {"symbol": "BTCUSDT", "net_position": "1.0", "positionAmt": "-1.0"}
            ]
        }
        assert fsm._get_portfolio_state_for_symbol("BTCUSDT") == "LONG"

    def test_truly_flat_returns_flat(self, fsm_config, tmp_path):
        """A genuinely zero position is still classified FLAT."""
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "XRPUSDT", "net_position": "0.0"}]
        }
        assert fsm._get_portfolio_state_for_symbol("XRPUSDT") == "FLAT"

    def test_missing_portfolio_returns_unknown(self, fsm_config, tmp_path):
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {}
        assert fsm._get_portfolio_state_for_symbol("BTCUSDT") == "UNKNOWN"

    def test_empty_positions_list_returns_flat(self, fsm_config, tmp_path):
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {"positions": []}
        assert fsm._get_portfolio_state_for_symbol("BTCUSDT") == "FLAT"

    def test_symbol_absent_returns_flat(self, fsm_config, tmp_path):
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "BTCUSDT", "net_position": "1.0"}]
        }
        assert fsm._get_portfolio_state_for_symbol("MISSING_SYMBOL") == "FLAT"

    def test_neither_field_present_returns_flat_not_crash(self, fsm_config, tmp_path):
        """Position entry with no qty field: treated as zero (FLAT)."""
        fsm = self._make_fsm_bare(fsm_config, tmp_path)
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "BTCUSDT"}]
        }
        # No net_position or positionAmt → _read_position_amt returns None →
        # qty_raw = "0" fallback → FLAT
        assert fsm._get_portfolio_state_for_symbol("BTCUSDT") == "FLAT"


# ---------------------------------------------------------------------------
# Part 2: build_position_signature — unit tests
# ---------------------------------------------------------------------------


class TestBuildPositionSignatureField:
    """Verify build_position_signature reads canonical ``net_position``."""

    def test_net_position_returns_short_signature(self):
        payload = {
            "positions": [{"symbol": "SOLUSDT", "net_position": "-15.87"}]
        }
        sig = build_position_signature(payload, "SOLUSDT")
        assert sig is not None
        assert sig.startswith("SHORT:")

    def test_positionAmt_fallback_works(self):
        payload = {
            "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.05"}]
        }
        sig = build_position_signature(payload, "BTCUSDT")
        assert sig is not None
        assert sig.startswith("LONG:")

    def test_truly_flat_returns_flat_zero(self):
        payload = {
            "positions": [{"symbol": "ETHUSDT", "net_position": "0"}]
        }
        sig = build_position_signature(payload, "ETHUSDT")
        assert sig == "FLAT:0"

    def test_neither_field_returns_unknown(self):
        payload = {
            "positions": [{"symbol": "BTCUSDT"}]
        }
        sig = build_position_signature(payload, "BTCUSDT")
        assert sig == "UNKNOWN"


# ---------------------------------------------------------------------------
# Part 3: FSM integration — regression for the real runtime defect
# ---------------------------------------------------------------------------


def test_regression_net_position_field_not_falsely_suppressed_as_flat(
    fsm_config, tmp_path
):
    """Regression: the exact runtime defect from the first enable slice.

    position_tracking emits ``net_position`` (canonical schema).  Previously
    the FSM handler read only ``positionAmt``, causing 100% false-flat
    suppression.  After the fix, the request must proceed to
    ``close_command_emitted`` (not ``suppressed``).

    Uses a LONG BTCUSDT position against TREND_DOWN regime (adverse for longs)
    with full scoring-compatible fields so the sidecar reaches RECOMMEND.
    """
    bus = RecordingBus()
    fsm = _make_fsm(fsm_config, bus, tmp_path)
    now_ms = get_clock().now_ms()

    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0

    # Use canonical schema field name ``net_position`` — this is what
    # position_tracking actually emits in production.  Include scoring-
    # compatible fields so the sidecar can evaluate profitability.
    portfolio_payload = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "net_position": "0.10",
                "entryPrice": "100.0",
                "markPrice": "99.2",
                "unrealizedProfit": "-0.08",
            }
        ],
    }
    fsm._latest_portfolio_state = dict(portfolio_payload)

    sidecar = fsm._position_policy_sidecar
    assert sidecar is not None
    _seed_sidecar(sidecar, now_ms, portfolio_payload=portfolio_payload)

    # Verify the close request was emitted by the sidecar
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" in _topics(bus)

    # Verify the FSM handler processed it and did NOT suppress as flat
    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    assert len(states) >= 1

    # The request should reach close_command_emitted, NOT suppressed
    suppressed = [
        s for s in states
        if s.get("request_state") == "suppressed"
        and s.get("suppression_reason") == "portfolio_flat_no_live_net_position"
    ]
    assert len(suppressed) == 0, (
        f"Bug regression: request was falsely suppressed as flat. "
        f"States: {[s.get('request_state') for s in states]}"
    )

    emitted = [s for s in states if s.get(
        "request_state") == "close_command_emitted"]
    assert len(emitted) >= 1, (
        f"Expected at least one close_command_emitted but got: "
        f"{[s.get('request_state') for s in states]}"
    )

    # Verify bounded action scope integrity
    emitted_ctx = emitted[0].get("policy_context", {})
    scope = emitted_ctx.get("allowed_action_scope", {})
    assert scope.get("soft_close_symbol_current_net_only") is True
    assert scope.get("partial_reduce") is False
    assert scope.get("bracket_mutation") is False
    assert scope.get("exact_targeting") is False


def test_genuinely_flat_symbol_still_suppressed_net_position_zero(
    fsm_config, tmp_path
):
    """A genuinely flat symbol (``net_position: "0"``) must still be suppressed."""
    bus = RecordingBus()
    fsm = _make_fsm(fsm_config, bus, tmp_path)
    now_ms = get_clock().now_ms()

    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0

    portfolio_payload = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "net_position": "0",
                "avg_entry_price": "100.0",
                "venues": ["binance_futures"],
            }
        ],
    }
    fsm._latest_portfolio_state = dict(portfolio_payload)

    sidecar = fsm._position_policy_sidecar
    assert sidecar is not None
    _seed_sidecar(sidecar, now_ms, portfolio_payload=portfolio_payload)

    # Not all code paths may produce a request for a flat position (sidecar
    # itself may suppress earlier), but if a request reaches the FSM handler,
    # it must be suppressed.
    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    if states:
        for s in states:
            assert s.get("request_state") != "close_command_emitted", (
                "A flat symbol must not get close_command_emitted"
            )


def test_missing_portfolio_state_still_suppressed(fsm_config, tmp_path):
    """Empty/missing ``_latest_portfolio_state`` must suppress correctly."""
    bus = RecordingBus()
    fsm = _make_fsm(fsm_config, bus, tmp_path)
    now_ms = get_clock().now_ms()

    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0

    # Sidecar sees a position, but FSM portfolio state is empty
    sidecar_portfolio = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.10",
                "entryPrice": "100.0",
                "markPrice": "99.2",
                "unrealizedProfit": "-0.08",
            }
        ],
    }
    fsm._latest_portfolio_state = {}  # empty — stale/missing

    sidecar = fsm._position_policy_sidecar
    assert sidecar is not None
    _seed_sidecar(sidecar, now_ms, portfolio_payload=sidecar_portfolio)

    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    for s in states:
        assert s.get("request_state") != "close_command_emitted", (
            "Missing portfolio state must suppress, not allow close"
        )


def test_legacy_positionAmt_field_still_passes_request_handler(
    fsm_config, tmp_path
):
    """Backward compat: ``positionAmt`` payloads still pass the handler."""
    bus = RecordingBus()
    fsm = _make_fsm(fsm_config, bus, tmp_path)
    now_ms = get_clock().now_ms()

    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0

    portfolio_payload = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.10",
                "entryPrice": "100.0",
                "markPrice": "99.2",
                "unrealizedProfit": "-0.08",
            }
        ],
    }
    fsm._latest_portfolio_state = dict(portfolio_payload)

    sidecar = fsm._position_policy_sidecar
    assert sidecar is not None
    _seed_sidecar(sidecar, now_ms, portfolio_payload=portfolio_payload)

    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" in _topics(bus)

    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    emitted = [s for s in states if s.get(
        "request_state") == "close_command_emitted"]
    assert len(emitted) >= 1, (
        f"Legacy positionAmt should still work. Got: "
        f"{[s.get('request_state') for s in states]}"
    )


def test_bounded_action_laws_unchanged_after_fix(fsm_config, tmp_path):
    """Verify the fix does not widen the admitted action scope."""
    bus = RecordingBus()
    fsm = _make_fsm(fsm_config, bus, tmp_path)
    now_ms = get_clock().now_ms()

    manage_flow = fsm.manage_flow("ETHUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "ETHUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "3.8"
    manage_flow.position_entry_price = "2225.81"
    manage_flow.position_open_ts = 1_000.0

    # canonical ``net_position`` + scoring-compatible fields for sidecar eval
    portfolio_payload = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "ETHUSDT",
                "net_position": "3.8",
                "entryPrice": "2225.81",
                "markPrice": "2200.0",
                "unrealizedProfit": "-98.08",
            }
        ],
    }
    fsm._latest_portfolio_state = dict(portfolio_payload)

    sidecar = fsm._position_policy_sidecar
    assert sidecar is not None
    _seed_sidecar(sidecar, now_ms,
                  portfolio_payload=portfolio_payload, symbol="ETHUSDT")

    requests = _payloads(bus, "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST")
    assert len(requests) >= 1

    req = requests[-1]
    assert req["requested_action"] == "SOFT_CLOSE"
    assert req["target_mode"] == "symbol_current_net_only"
    assert req["policy_source"] == "position_policy_sidecar"
    assert req["allowed_action_scope"]["soft_close_symbol_current_net_only"] is True
    assert req["allowed_action_scope"]["partial_reduce"] is False
    assert req["allowed_action_scope"]["bracket_mutation"] is False
    assert req["allowed_action_scope"]["exact_targeting"] is False
    assert req.get("requested_qty") is None


def test_producer_style_economics_survive_into_sidecar_without_action(tmp_path: Path) -> None:
    """Producer-style portfolio fields must remain evaluable without creating a close command."""
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.peak_giveback_close.edge_arm_usd = 25.0
    cfg.peak_giveback_close.giveback_trigger_pct = 50.0
    cfg.profitability_guard.enabled = False

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"ETHUSDT"},
    )

    sidecar.on_portfolio_state_updated(_event(positions=[
        {
            "symbol": "ETHUSDT",
            "net_position": "1.0",
            "avg_entry_price": "100.0",
            "markPrice": "120.0",
            "unrealizedPnl": "20.0",
            "unrealizedPnlPct": "20.0",
            "venues": ["binance"],
        }
    ]))
    sidecar.on_features_calculated(_event(symbol="ETHUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="ETHUSDT", regime="MEAN_REVERSION", confidence=1.0)
    )

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    snapshot = evaluated["peak_giveback_snapshot"]

    assert snapshot["mark_price"] == 120.0
    assert snapshot["unrealized_pnl_usdt"] == 20.0
    assert snapshot["unrealized_pnl_pct"] == 20.0
    assert snapshot["peak_giveback_state"] == "peak_giveback_not_armed_below_edge"
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)
