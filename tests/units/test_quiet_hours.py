"""
Unit tests for quiet hours functionality:
- _in_quiet() core logic with mocked time
- _quiet_hours_gate_allow() toggle/config
- FSM integration: TRADE_INTENT blocked during quiet hours
"""

from apps.reference.domains.execution_position.fsm import _in_quiet, _utc_hm
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _mock_utc(hour: int, minute: int = 0):
    """Patch _utc_hm to return a fixed (hour, minute) pair."""
    return patch(
        "apps.reference.domains.execution_position.fsm._utc_hm",
        return_value=(hour, minute),
    )


# ─── _in_quiet() core logic ──────────────────────────────────────────────────

class TestInQuietCore:
    """Pure unit tests for _in_quiet with mocked time."""

    def test_empty_list_always_false(self):
        assert _in_quiet([]) is False

    def test_full_day_always_true(self):
        with _mock_utc(12, 0):
            assert _in_quiet(["00:00-23:59"]) is True

    def test_normal_range_inside(self):
        with _mock_utc(14, 30):
            assert _in_quiet(["09:00-17:00"]) is True

    def test_normal_range_outside(self):
        with _mock_utc(8, 0):
            assert _in_quiet(["09:00-17:00"]) is False

    def test_normal_range_at_start_boundary(self):
        with _mock_utc(9, 0):
            assert _in_quiet(["09:00-17:00"]) is True

    def test_normal_range_at_end_boundary(self):
        with _mock_utc(17, 0):
            assert _in_quiet(["09:00-17:00"]) is True

    def test_midnight_wrap_late_night(self):
        with _mock_utc(23, 30):
            assert _in_quiet(["22:00-06:00"]) is True

    def test_midnight_wrap_early_morning(self):
        with _mock_utc(3, 0):
            assert _in_quiet(["22:00-06:00"]) is True

    def test_midnight_wrap_outside_daytime(self):
        with _mock_utc(12, 0):
            assert _in_quiet(["22:00-06:00"]) is False

    def test_multiple_ranges_match_second(self):
        with _mock_utc(23, 30):
            assert _in_quiet(["09:00-10:00", "23:00-23:59"]) is True

    def test_multiple_ranges_none_match(self):
        with _mock_utc(12, 0):
            assert _in_quiet(["09:00-10:00", "23:00-23:59"]) is False

    def test_narrow_range_inside(self):
        with _mock_utc(12, 0):
            assert _in_quiet(["12:00-12:01"]) is True

    def test_narrow_range_outside(self):
        with _mock_utc(12, 2):
            assert _in_quiet(["12:00-12:01"]) is False

    def test_malformed_range_skipped(self):
        """Malformed ranges are silently skipped, no crash."""
        with _mock_utc(12, 0):
            assert _in_quiet(["bad-format", "not_a_range"]) is False

    def test_malformed_mixed_with_valid(self):
        """Valid ranges still work even if some are malformed."""
        with _mock_utc(12, 0):
            assert _in_quiet(["bad-format", "11:00-13:00"]) is True

    def test_none_tolerant(self):
        """None or falsy input returns False."""
        assert _in_quiet(None) is False
        assert _in_quiet([]) is False


# ─── _quiet_hours_gate_allow() toggle logic ───────────────────────────────────

class TestQuietHoursGateAllow:
    """Tests for the FSM gate method using a minimal mock FSM."""

    def _make_fsm_stub(self, enabled: bool, windows: list):
        """Create a minimal object with the gate method's required attributes."""
        from apps.reference.domains.execution_position.fsm import ExecPosFSM

        stub = MagicMock(spec=ExecPosFSM)
        stub._quiet_hours_enabled = enabled
        stub._quiet_hours_windows = windows
        stub._gate_metrics = {
            "gate_entry_blocked_quiet_hours": 0,
            "gate_entry_allowed_quiet_hours": 0,
        }
        # Bind real method
        stub._quiet_hours_gate_allow = ExecPosFSM._quiet_hours_gate_allow.__get__(
            stub)
        return stub

    def test_disabled_always_allows(self):
        """When enabled=False, gate allows even during quiet window."""
        stub = self._make_fsm_stub(enabled=False, windows=["00:00-23:59"])
        with _mock_utc(12, 0):
            assert stub._quiet_hours_gate_allow() is True
        assert stub._gate_metrics["gate_entry_blocked_quiet_hours"] == 0

    def test_enabled_empty_windows_allows(self):
        """When enabled=True but no windows configured, gate allows."""
        stub = self._make_fsm_stub(enabled=True, windows=[])
        assert stub._quiet_hours_gate_allow() is True

    def test_enabled_inside_window_blocks(self):
        """When enabled=True and current time is inside window, gate blocks."""
        stub = self._make_fsm_stub(enabled=True, windows=["10:00-14:00"])
        with _mock_utc(12, 0):
            assert stub._quiet_hours_gate_allow() is False
        assert stub._gate_metrics["gate_entry_blocked_quiet_hours"] == 1

    def test_enabled_outside_window_allows(self):
        """When enabled=True and current time is outside window, gate allows."""
        stub = self._make_fsm_stub(enabled=True, windows=["10:00-14:00"])
        with _mock_utc(8, 0):
            assert stub._quiet_hours_gate_allow() is True
        assert stub._gate_metrics["gate_entry_allowed_quiet_hours"] == 1

    def test_metrics_accumulate(self):
        """Multiple calls accumulate metrics correctly."""
        stub = self._make_fsm_stub(enabled=True, windows=["10:00-14:00"])
        with _mock_utc(12, 0):
            stub._quiet_hours_gate_allow()
            stub._quiet_hours_gate_allow()
            stub._quiet_hours_gate_allow()
        assert stub._gate_metrics["gate_entry_blocked_quiet_hours"] == 3

    def test_midnight_wrap_blocks(self):
        """Midnight-wrapping window blocks correctly."""
        stub = self._make_fsm_stub(enabled=True, windows=["22:00-06:00"])
        with _mock_utc(1, 30):
            assert stub._quiet_hours_gate_allow() is False
        assert stub._gate_metrics["gate_entry_blocked_quiet_hours"] == 1


# ─── FSM integration: _on_trade_intent_proposed blocks during quiet hours ─────

class TestQuietHoursFSMIntegration:
    """Integration test: quiet hours gate blocks TRADE_INTENT -> CMD:OPEN."""

    @pytest.fixture
    def fsm_with_quiet_hours(self):
        """Create a real ExecPosFSM with quiet hours enabled."""
        from apps.reference.domains.execution_position.fsm import ExecPosFSM

        cfg = MagicMock()
        cfg.trading.execution.watchdog.ack_ttl_ms = 5000
        cfg.trading.execution.watchdog.fill_ttl_ms = 5000
        cfg.trading.execution.anti_race_close_ms = 800
        cfg.trading.execution.cooldown_after_close_ms = 10_000
        cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60

        event_dedup = MagicMock()
        event_dedup.max_size = 100000
        event_dedup.ttl_ms = 86400000
        cfg.domains.execution_position.event_dedup = event_dedup

        idempotent_cancel = MagicMock()
        idempotent_cancel.max_retries = 2
        cfg.domains.execution_position.idempotent_cancel = idempotent_cancel

        emergency = MagicMock()
        emergency.enabled = False
        emergency.wait_mode_bars = 2
        emergency.emergency_sl_bps = 100
        cfg.trading.execution.manage.emergency = emergency

        trailing = MagicMock()
        trailing.activation_pct = 0.003
        trailing.trail_pct = 0.006
        trailing.min_update_interval_sec = 5
        cfg.trailing = trailing

        cfg.trading.execution.manage.auto = True
        cfg.trading.execution.manage.brackets.enable = True
        cfg.trading.execution.manage.brackets.oco_emulation = True
        cfg.trading.execution.manage.brackets.sl.fixed_bps = 40
        cfg.trading.execution.manage.brackets.tp.fixed_bps = 80
        cfg.trading.execution.manage.brackets.offset_bps = 5

        from decimal import Decimal
        btc_spec = MagicMock()
        btc_spec.tick_size = Decimal("0.01")
        btc_spec.step_size = Decimal("0.001")
        btc_spec.min_qty = Decimal("0.001")
        btc_spec.min_notional = Decimal("5.0")
        btc_spec.execution = MagicMock()
        btc_spec.execution.target_leverage = 20
        cfg.instruments = {"BTCUSDT": btc_spec}

        btc_asset_config = MagicMock()
        btc_asset_config.exit = MagicMock()
        btc_asset_config.exit.sl_pct = 0.02
        btc_asset_config.exit.max_hold_sec = 600
        btc_asset_config.take_profit = MagicMock()
        btc_asset_config.take_profit.tp_low_ratio = 0.5
        btc_asset_config.take_profit.tp_high_ratio = 1.0
        btc_asset_config.take_profit.partial_exit_pct = 0.5
        btc_asset_config.trailing_stop = MagicMock()
        btc_asset_config.trailing_stop.enabled = False
        cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset_config}
        cfg.strategies.aurora.decision.bar_gating = None

        eg = cfg.domains.execution_position.exposure_guard
        eg.max_equity_utilization_pct = "95.0"
        eg.max_portfolio_fraction = "1.0"
        eg.max_long_utilization_pct = "100.0"
        eg.max_short_utilization_pct = "100.0"
        eg.max_directional_ratio = "5.0"
        eg.max_concentration_pct = "20.0"
        eg.pending_ttl_sec = 5
        eg.post_fill_ttl_sec = 5
        eg.stale_ttl_sec = 10

        fb = cfg.domains.execution_position.fallback
        fb.policy = "fail_closed"
        fb.risk_reduction_pct = "0.5"
        fb.backoff_ms = [200, 500, 1000]

        cfg.trading.execution.exposure.leverage_defaults = {
            "__default__": 20, "BTCUSDT": 20}
        cfg.trading.execution.exposure.count_pending_orders = True
        cfg.trading.execution.exposure.exclude_reduce_only = True

        cfg.trading.risk = {
            "soft_limits": {
                "mode": "clip",
                "clip_min_notional_usdt": "10.0",
                "directional_ratio_max": "3.0",
                "side_exposure_usdt": "600.0",
                "margin_exposure_usdt": "1100.0",
            }
        }

        storage_mock = MagicMock()
        storage_mock.order_history_db = ":memory:"
        cfg.ops.storage = storage_mock

        cfg.binance_api.testnet.api_key = ""
        cfg.binance_api.testnet.api_secret = ""
        cfg.binance_api.testnet.rest_url = ""
        cfg.binance_api.live.api_key = ""
        cfg.binance_api.live.api_secret = ""
        cfg.binance_api.live.rest_url = ""
        cfg.get_domain_mode.return_value = "testnet"
        cfg.trading.mode = "testnet"

        # QUIET HOURS config: enabled with a window that covers midday
        qh = MagicMock()
        qh.enabled = True
        qh.windows = ["10:00-14:00"]
        cfg.domains.execution_position.quiet_hours = qh

        class FakeBus:
            def __init__(self):
                self.events = []

            def emit(self, topic, *args, **kwargs):
                self.events.append((topic, args, kwargs))

            def listen(self, topic, handler):
                pass

        bus = FakeBus()

        with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"):
            fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)

        return fsm, bus

    def test_intent_blocked_during_quiet_hours(self, fsm_with_quiet_hours):
        """TRADE_INTENT_PROPOSED should be rejected during quiet hours."""
        from vfoundation.core.protocol import Message

        fsm, bus = fsm_with_quiet_hours

        intent_msg = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_position",
            rid="test-rid-001",
            pld={
                "instrument": "BTCUSDT",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "reduce_only": False,
                "strategy": "aurora",
                "order_info": {
                    "order_type": "MARKET",
                    "qty": "0.01",
                },
                "rid": "test-rid-001",
            },
        )

        with _mock_utc(12, 0):  # 12:00 UTC — inside [10:00-14:00]
            fsm._on_trade_intent_proposed(intent_msg)

        # Check bus for REJECTED event
        rejected = [
            ev for ev in bus.events
            if ev[0] == "EVT:TRADE_INTENT_REJECTED"
        ]
        assert len(
            rejected) >= 1, f"Expected REJECTED event, got: {bus.events}"
        reject_pld = rejected[0][1][0]  # first positional arg = payload dict
        assert reject_pld["reason"] == "QUIET_HOURS_BLOCKED"
        assert reject_pld["symbol"] == "BTCUSDT"

        # Check metrics
        assert fsm._gate_metrics["gate_entry_blocked_quiet_hours"] >= 1

    def test_intent_allowed_outside_quiet_hours(self, fsm_with_quiet_hours):
        """TRADE_INTENT_PROPOSED outside quiet hours should NOT be blocked by this gate."""
        from vfoundation.core.protocol import Message

        fsm, bus = fsm_with_quiet_hours

        intent_msg = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_position",
            rid="test-rid-002",
            pld={
                "instrument": "BTCUSDT",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "reduce_only": False,
                "strategy": "aurora",
                "order_info": {
                    "order_type": "MARKET",
                    "qty": "0.01",
                },
                "rid": "test-rid-002",
            },
        )

        with _mock_utc(8, 0):  # 08:00 UTC — outside [10:00-14:00]
            fsm._on_trade_intent_proposed(intent_msg)

        # Should NOT have a quiet-hours rejection
        quiet_rejects = [
            ev for ev in bus.events
            if ev[0] == "EVT:TRADE_INTENT_REJECTED"
            and ev[1][0].get("reason") == "QUIET_HOURS_BLOCKED"
        ]
        assert len(
            quiet_rejects) == 0, f"Unexpected quiet hours rejection: {bus.events}"

        # Quiet hours gate should have allowed
        assert fsm._gate_metrics["gate_entry_allowed_quiet_hours"] >= 1

    def test_quiet_hours_in_get_metrics(self, fsm_with_quiet_hours):
        """get_metrics() should expose quiet hours config and counters."""
        fsm, bus = fsm_with_quiet_hours

        metrics = fsm.get_metrics()
        assert "gate" in metrics
        assert metrics["gate"]["quiet_hours_enabled"] is True
        assert metrics["gate"]["quiet_hours_windows"] == ["10:00-14:00"]
        assert "gate_entry_blocked_quiet_hours" in metrics
        assert "gate_entry_allowed_quiet_hours" in metrics
