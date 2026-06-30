import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from types import SimpleNamespace
from apps.reference.domains.execution_position.guards.exposure_guard import ExposureGuard
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.guards.soft_clip import (
    RegimeAdaptationConfig,
    SoftLimitConfigModel,
    SoftLimitConfig,
)
from apps.reference.core.types.regime_types import ExecutionRegimeBucket
from vfoundation.core.protocol import Message
from pydantic import ValidationError


class MockFSM:
    def __init__(self):
        self.listeners = {}
        self.order_index = MagicMock()

    def listen(self, evt, cb):
        self.listeners[evt] = cb

    def emit(self, *args, **kwargs): pass


@pytest.fixture
def mock_config():
    """EP-01: Mock config for ExecPosFSM that provides regime_adaptation for ExposureGuard."""
    cfg = MagicMock()

    # Use explicit namespace objects so fail-closed config readers only see
    # the declared fields instead of MagicMock auto-created attributes.
    trading_risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": 10.0,
            "directional_ratio_max": 3.0,
            "side_exposure_usdt": 600.0,
            "margin_exposure_usdt": 1000.0,
        },
        "regime_adaptation": {
            "trend_up_delta": 0.5,
            "trend_down_delta": 0.5,
            "flat_delta": -0.5,
            "bounds": [1.0, 5.0]
        }
    }

    exec_cfg = SimpleNamespace(
        exposure=SimpleNamespace(
            count_pending_orders=True,
            exclude_reduce_only=True,
        ),
        manage=SimpleNamespace(
            emergency=SimpleNamespace(
                enabled=False,
                wait_mode_bars=2,
                emergency_sl_bps=100,
            )
        ),
        cooldown_after_close_ms=1000,
        fsm_periodic_cleanup_enabled=False,
        order_guardian=SimpleNamespace(
            unified=True,
            ledger_db_path=":memory:",
        ),
    )
    watchdog_cfg = SimpleNamespace(
        ack_ttl_ms=500,
        fill_ttl_ms=1000,
        check_interval_ms=1000,
        rps_limit=10,
    )
    exec_cfg.watchdog = watchdog_cfg
    guardian_cfg = SimpleNamespace(
        poll_interval_ms=500,
        unified=True,
        emit_tidy_event=True,
        emit_tidy_monitoring_event=True,
        cleanup_ttl_ms=6000,
        symbol_cooldown_ms=4000,
    )
    dom_ep = SimpleNamespace(
        guardian=guardian_cfg,
        metrics_collector=SimpleNamespace(
            window_size_minutes=60,
            recent_rejections_minutes=5,
        ),
        idempotent_cancel=SimpleNamespace(max_retries=3),
        event_dedup=SimpleNamespace(max_size=100, ttl_ms=1000),
        fallback=SimpleNamespace(
            policy="fail_closed",
            risk_reduction_pct="0.5",
            backoff_ms=[200, 500, 1000],
        ),
        intent_boundary_audit=None,
    )
    cfg.trading = SimpleNamespace(
        risk=trading_risk,
        execution=exec_cfg,
    )
    cfg.domains = SimpleNamespace(execution_position=dom_ep)
    cfg.execution = None
    cfg.guardian = None

    return cfg


def test_exposure_guard_wiring(mock_config):
    fsm_core = MockFSM()

    # Patch DomainConfigResolver to bypass complex config resolution and provide valid values
    with patch("apps.reference.domains.execution_position.guards.exposure_guard.DomainConfigResolver") as MockResolver:
        mock_resolver_inst = MockResolver.return_value
        eg_mock = MagicMock()
        # Provide float/int values which _to_dec handles (str(val))
        eg_mock.max_equity_utilization_pct = 100.0
        eg_mock.max_portfolio_fraction = 1.0
        eg_mock.max_long_utilization_pct = 100.0
        eg_mock.max_short_utilization_pct = 100.0
        eg_mock.max_concentration_pct = 100.0
        # Use 3.0 to match SoftLimits config
        eg_mock.max_directional_ratio = 3.0
        eg_mock.directional_ratio_max = 3.0

        eg_mock.pending_ttl_sec = 60
        eg_mock.post_fill_ttl_sec = 60
        eg_mock.stale_ttl_sec = 60

        mock_resolver_inst.get_exposure_guard.return_value = eg_mock

        # Init FSM (shadow_mode=True to skip adapter)
        ep_fsm = ExecPosFSM(mock_config, fsm_core, shadow_mode=True)

        # Spy on ExposureGuard
        orig_method = ep_fsm.exposure_guard.on_regime_changed
        ep_fsm.exposure_guard.on_regime_changed = MagicMock(
            side_effect=orig_method)

        # Verify initial state matches our mocks
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("3.0")

        # Scenario: structural regime event should NOT mutate global exposure ratio
        payload = {
            "symbol": "BTCUSDT",
            "regime": "MEAN_REVERSION",
            "confidence": 0.9,
            "regime_layer": "structural",
            "regime_scope": "per_symbol",
            "regime_clock": "bar",
        }
        msg = Message(op="EVT", verb="REGIME_DETECTED",
                      pld=payload, src="rd", dst="ep")

        # Trigger Listener manually (simulating bus)
        listener = fsm_core.listeners.get("EVT:REGIME_DETECTED")
        assert listener is not None, "ExecPosFSM must subscribe to EVT:REGIME_DETECTED"

        listener(msg)

        ep_fsm.exposure_guard.on_regime_changed.assert_not_called()
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("3.0")

        # Scenario: explicit global execution-micro regime may adapt exposure
        payload_trend = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 0.9,
            "regime_layer": "execution_micro",
            "regime_scope": "global",
            "regime_clock": "event_driven",
        }
        msg_trend = Message(op="EVT", verb="REGIME_DETECTED",
                            pld=payload_trend, src="rd", dst="ep")
        listener(msg_trend)

        ep_fsm.exposure_guard.on_regime_changed.assert_called_with(
            ExecutionRegimeBucket.TREND_UP)
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("3.5")


def test_config_strictness(mock_config):
    """Verify that configuration prohibits unknown keys (Fail Fast)."""
    with pytest.raises(ValidationError) as excinfo:
        RegimeAdaptationConfig(
            trend_up_delta=0.1,
            trend_down_delta=0.1,
            flat_delta=0.1,
            bounds=[2.0, 4.0],
            ghost_key="I SHOULD NOT BE HERE"  # Forbidden
        )
    assert "Extra inputs are not permitted" in str(excinfo.value)
    assert "ghost_key" in str(excinfo.value)
