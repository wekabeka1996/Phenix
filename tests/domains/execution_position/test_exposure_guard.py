import pytest
import time
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard, _normalize_pct_decimal

@pytest.fixture
def mock_config():
    return {
        "trading": {
            "risk": {
                "exposure": {
                    "caps": {
                        "max_equity_utilization_ratio": "0.9",
                        "max_portfolio_fraction": "0.5",
                        "max_side_utilization_ratio": {
                            "long": "0.6",
                            "short": "0.6"
                        },
                        "max_directional_ratio": "3.0",
                        "per_symbol_cap_ratio": "0.2"
                    },
                    "reservations": {
                        "pending_ttl_sec": 5,
                        "post_fill_hold_ttl_sec": 10,
                        "positions_stale_ttl_sec": 60
                    },
                    "count_pending_orders": True,
                    "exclude_reduce_only": True,
                    "fallback": {
                        "enabled": True,
                        "policy": "reduce_risk",
                        "risk_reduction_pct": "0.5",
                        "max_attempts": 3
                    }
                },
                "soft_limits": {
                    "mode": "clip",
                    "clip_min_notional_usdt": "10",
                    "directional_ratio_max": "3.0",
                    "side_exposure_usdt": "600",
                    "margin_exposure_usdt": "1100"
                }
            }
        }
    }

@pytest.fixture
def guard(mock_config):
    # Mock resolve_exposure_policy to return values matching mock_config
    with patch("apps.reference.domains.execution_position.exposure_guard.resolve_exposure_policy") as mock_resolve:
        policy = MagicMock()
        policy.source = "mock"
        policy.caps.max_equity_utilization_ratio = Decimal("0.9")
        policy.caps.max_portfolio_fraction = Decimal("0.5")
        policy.caps.max_side_utilization_ratio = {"long": Decimal("0.6"), "short": Decimal("0.6")}
        policy.caps.max_directional_ratio = Decimal("3.0")
        policy.caps.per_symbol_cap_ratio = Decimal("0.2")

        policy.reservations.pending_ttl_sec = 5
        policy.reservations.post_fill_hold_ttl_sec = 10
        policy.reservations.positions_stale_ttl_sec = 60

        policy.count_pending_orders = True
        policy.exclude_reduce_only = True

        policy.fallback.enabled = True
        policy.fallback.policy = "reduce_risk"
        policy.fallback.risk_reduction_pct = Decimal("0.5")
        policy.fallback.max_attempts = 3
        policy.fallback.backoff_sequence.return_value = [100, 200]

        # Mock leverage defaults
        policy.leverage_defaults.resolve_for.return_value = Decimal("20")

        mock_resolve.return_value = policy

        # Also mock resolve_risk_soft_limits
        with patch("apps.reference.domains.execution_position.exposure_guard.resolve_risk_soft_limits") as mock_soft:
            soft = MagicMock()
            soft.mode = "clip"
            soft.clip_min_notional_usdt = Decimal("10")
            soft.directional_ratio_max = Decimal("3.0")
            soft.side_exposure_usdt = Decimal("600")
            soft.margin_exposure_usdt = Decimal("1100")
            mock_soft.return_value = soft

            yield ExposureGuard(config=mock_config)

def test_initialization(guard):
    assert guard.max_equity_utilization_pct == Decimal("0.9")
    assert guard.pending_ttl_sec == 5
    assert guard.soft_limit_config.mode == "clip"
    assert guard.fallback_config["enabled"] is True

def test_can_open_stale_portfolio(guard):
    # Portfolio state with old timestamp
    portfolio = {
        "positions_last_ts_ms": (time.time() - 100) * 1000, # 100s ago
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions": []
    }

    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "PORTFOLIO_STALE"

def test_can_open_allowed(guard):
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions": []
    }

    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is True
    # reason might not be present on success, check allowed only
    assert res.get("reason") is None or res["reason"] == "OK"

def test_reserve_and_expire(guard):
    guard.reserve("req1", Decimal("100"))
    assert "req1" in guard.state.reservations
    assert guard.state.reservations["req1"] == Decimal("100")

    # Simulate time passing
    with patch("time.time", return_value=time.time() + 10):
        expired = guard.expire_stale()
        assert "req1" in expired
        assert "req1" not in guard.state.reservations

def test_on_fill_creates_hold(guard):
    guard.reserve("req1", Decimal("100"))
    guard.on_fill("req1", Decimal("100"))

    assert "req1" not in guard.state.reservations
    assert "req1" in guard.state.postfill_reservations
    assert guard.state.postfill_reservations["req1"]["notional"] == Decimal("100")

def test_soft_clip(guard):
    # Set soft limit to 500
    guard.soft_limit_config.side_exposure_usdt = Decimal("500")

    # Set up portfolio to be AT the hard limit (600)
    # max_side_utilization_ratio = 0.6, equity = 1000 -> limit = 600
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "600",
        "positions_by_side": {
            "long_margin": "0",
            "short_margin": "600"
        },
        "positions": []
    }

    # Request 100 more. This exceeds hard limit (600 + 5 > 600).
    # allowed_extra = 600 - 600 = 0.
    # So it should call soft_clip_engine.

    with patch.object(guard.soft_clip_engine, "calculate_clipped_size") as mock_clip:
        # Mock soft clip engine to allow it but clip it (maybe due to soft limits or just allowing a small amount?)
        # Actually if we are at hard limit, we probably shouldn't allow more unless it's reducing risk?
        # But for the purpose of testing the PATH, we just want to see if it returns the mocked result.
        mock_clip.return_value = MagicMock(allowed=True, clipped_notional=Decimal("50"), clip_reasons=["SIDE_LIMIT"])

        res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)

        assert res["allowed"] is True
        assert res["shrink_notional"] == Decimal("50")
        assert res["reason"] == "CLIPPED_SIDE"

def test_fail_closed_equity_zero(guard):
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "0",
        "open_positions_margin_usd": "0",
        "positions": []
    }
    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "EQUITY_UNKNOWN"

def test_fail_closed_positions_unknown(guard):
    portfolio = {
        "positions_last_ts_ms": 0,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": None,
        "positions": []
    }
    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "PORTFOLIO_UNKNOWN"

def test_fallback_mode_lifecycle(guard):
    assert not guard.is_fallback_mode_active()

    guard.enter_fallback_mode("TEST_REASON")
    assert guard.is_fallback_mode_active()
    assert guard.fallback_state.reason == "TEST_REASON"

    # Re-entry should be ignored
    guard.enter_fallback_mode("ANOTHER_REASON")
    assert guard.fallback_state.reason == "TEST_REASON"

    guard.exit_fallback_mode()
    assert not guard.is_fallback_mode_active()
    assert guard.fallback_state.reason == ""

def test_fallback_mode_fail_closed_policy(guard):
    guard.fallback_config["policy"] = "fail_closed"
    guard.enter_fallback_mode("TEST_FAIL")

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions": []
    }

    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is False
    assert "FALLBACK_FAIL_CLOSED" in res["reason"]

def test_fallback_mode_risk_reduction_policy(guard):
    guard.fallback_config["policy"] = "risk_reduction"
    guard.fallback_config["risk_reduction_pct"] = Decimal("0.5")
    guard.enter_fallback_mode("TEST_REDUCE")

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions": []
    }

    # Should allow but reduce notional
    # Note: can_open doesn't return the reduced notional in the result dict unless it shrinks/clips
    # But we can check logs or verify if it passes checks with reduced amount

    # Let's try to trigger a limit that would fail with full amount but pass with reduced
    # Limit = 900 (0.9 * 1000)
    # Request 1600 -> reduced to 800. 800/20 = 40 margin. 40 < 900. OK.

    res = guard.can_open("BTCUSDT", Decimal("1600"), portfolio)
    assert res["allowed"] is True
    # It doesn't return "SHRUNK_TO_FIT" because it's not a margin limit shrink, it's a pre-check reduction.
    # The code modifies `notional_usd` local variable.

def test_margin_limit_shrink_to_fit(guard):
    # Equity 1000, Max Util 0.9 -> Limit 900 margin
    # Current margin 800
    # Allowed extra 100 margin
    # Leverage 20 -> Allowed extra notional 2000

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "800",
        "positions": []
    }

    # Request 3000 notional (150 margin). 800 + 150 = 950 > 900.
    # Should shrink to 2000 notional (100 margin).

    res = guard.can_open("BTCUSDT", Decimal("3000"), portfolio)
    assert res["allowed"] is True
    assert res["reason"] == "SHRUNK_TO_FIT"
    assert res["shrink_notional"] == Decimal("2000")

def test_margin_limit_reject(guard):
    # Equity 1000, Max Util 0.9 -> Limit 900 margin
    # Current margin 900 (Full)

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "900",
        "positions": []
    }

    # Disable soft clip for rejection test
    guard.soft_limit_config.mode = "reject"

    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "EXPOSURE_LIMIT_EXCEEDED"

def test_side_limit_shrink_to_fit(guard):
    # Equity 1000, Max Side 0.6 -> Limit 600 margin
    # Current Short Margin 500
    # Allowed extra 100 margin -> 2000 notional

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "500",
        "positions_by_side": {
            "long_margin": "0",
            "short_margin": "500"
        },
        "positions": []
    }

    # Request 3000 notional (150 margin) SELL. 500 + 150 = 650 > 600.
    # Should shrink to 2000.

    # We need to ensure order_side is inferred as SELL.
    # The code infers side from pending_exposure if available, else defaults to SELL.
    # Since we don't have pending exposure matching this, it defaults to SELL.

    res = guard.can_open("BTCUSDT", Decimal("3000"), portfolio)
    assert res["allowed"] is True
    assert res["reason"] == "SHRUNK_TO_FIT_SIDE"
    assert res["shrink_notional"] == Decimal("2000")

def test_directional_ratio_reject(guard):
    # Max Ratio 3.0
    # Long Margin 300
    # Short Margin 100
    # Ratio 3.0 (OK)

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "400",
        "positions_by_side": {
            "long_margin": "300",
            "short_margin": "100"
        },
        "positions": []
    }

    # Request BUY. New Long = 300 + 100 = 400. Short = 100. Ratio 4.0 > 3.0.
    # Need to force side=BUY.
    # We can do this by reserving a pending order with side=BUY and matching margin.

    notional = Decimal("2000") # Margin 100
    guard.reserve("test_buy", notional, side="BUY")

    # Disable soft clip
    guard.soft_limit_config.mode = "reject"

    res = guard.can_open("BTCUSDT", notional, portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "DIRECTIONAL_RATIO_EXCEEDED"

def test_regime_adaptation(guard):
    guard.soft_limit_config.regime_adaptation = MagicMock()
    guard.soft_limit_config.regime_adaptation.bounds = [2.0, 5.0]
    guard.soft_limit_config.regime_adaptation.trend_up_delta = 1.0

    guard.on_regime_changed("TREND_UP")
    assert guard.max_directional_ratio == Decimal("4.0") # 3.0 + 1.0

def test_cleanup_all_pending(guard):
    guard.reserve("p1", Decimal("100"))
    guard.reserve("p2", Decimal("200"))
    assert len(guard.state.reservations) == 2

    guard.cleanup_all_pending()
    assert len(guard.state.reservations) == 0
    assert len(guard.state.pending_exposure) == 0

def test_cleanup_in_can_open(guard):
    # Add expired postfill
    guard.state.postfill_reservations["expired"] = {
        "exp_ts": time.time() - 10,
        "margin": Decimal("10")
    }

    # Add stale pending
    guard.state.pending_exposure["stale"] = {
        "ts": time.time() - 10,
        "margin": Decimal("10")
    }

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions": []
    }

    guard.can_open("BTCUSDT", Decimal("100"), portfolio)

    assert "expired" not in guard.state.postfill_reservations
    assert "stale" not in guard.state.pending_exposure

def test_get_exposure_summary(guard):
    guard.reserve("p1", Decimal("100"))
    summary = guard.get_exposure_summary()
    assert summary["reservations_count"] == 1
    assert summary["reservations_usd"] == 100.0

def test_normalize_pct_decimal():
    assert _normalize_pct_decimal("0.5") == Decimal("0.5")
    assert _normalize_pct_decimal("50") == Decimal("0.5")
    assert _normalize_pct_decimal(None, "0.1") == Decimal("0.1")
    assert _normalize_pct_decimal("invalid", "0.2") == Decimal("0.2")
    assert _normalize_pct_decimal(0.5) == Decimal("0.5")
    assert _normalize_pct_decimal(50) == Decimal("0.5")

def test_soft_limit_config_defaults(mock_config):
    # Force resolve_risk_soft_limits to raise exception
    with patch("apps.reference.domains.execution_position.exposure_guard.resolve_risk_soft_limits", side_effect=Exception("Test")):
        with patch("apps.reference.domains.execution_position.exposure_guard.resolve_exposure_policy") as mock_resolve:
             # Need to mock policy as well since it's called in __init__
            policy = MagicMock()
            policy.caps.max_equity_utilization_ratio = Decimal("0.9")
            policy.caps.max_portfolio_fraction = Decimal("0.5")
            policy.caps.max_side_utilization_ratio = {"long": Decimal("0.6"), "short": Decimal("0.6")}
            policy.caps.max_directional_ratio = Decimal("3.0")
            policy.caps.per_symbol_cap_ratio = Decimal("0.2")
            policy.reservations.pending_ttl_sec = 5
            policy.reservations.post_fill_hold_ttl_sec = 10
            policy.reservations.positions_stale_ttl_sec = 60
            policy.leverage_defaults.resolve_for.return_value = Decimal("20")
            mock_resolve.return_value = policy

            guard = ExposureGuard(config=mock_config)
            # Should fall back to defaults
            assert guard.soft_limit_config.mode == "clip"
            assert guard.soft_limit_config.clip_min_notional_usdt == Decimal("10")

def test_event_emission_on_fail_closed(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "0", # Trigger fail closed
        "open_positions_margin_usd": "0",
        "positions": []
    }

    guard.can_open("BTCUSDT", Decimal("100"), portfolio)

    # Verify _safe_create_task was called (which implies emit_compat was called)
    assert guard._safe_create_task.called

def test_event_emission_on_fallback(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()

    # Create a mock module for alert_manager
    mock_alert_manager_module = MagicMock()
    mock_alert_manager_class = MagicMock()
    mock_alert_manager_module.AlertManager = mock_alert_manager_class

    # Patch sys.modules to include vfoundation.core.alert_manager
    with patch.dict(sys.modules, {"vfoundation.core.alert_manager": mock_alert_manager_module}):
        guard.enter_fallback_mode("TEST")

        assert guard._safe_create_task.called # Event emission
        assert mock_alert_manager_class.get_instance.return_value.alert.called # Alert emission

        guard._safe_create_task.reset_mock()
        mock_alert_manager_class.get_instance.return_value.alert.reset_mock()

        guard.exit_fallback_mode()
        assert guard._safe_create_task.called
        assert mock_alert_manager_class.get_instance.return_value.alert.called

    # Cleanup coroutines to avoid RuntimeWarning
    for call in guard._safe_create_task.call_args_list:
        arg = call[0][0]
        if hasattr(arg, 'close'):
            arg.close()

def test_event_emission_on_soft_clip_success(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "600", # At limit
        "positions_by_side": {"long_margin": "0", "short_margin": "600"},
        "positions": []
    }

    with patch.object(guard.soft_clip_engine, "calculate_clipped_size") as mock_clip:
        mock_clip.return_value = MagicMock(allowed=True, clipped_notional=Decimal("50"), clip_reasons=["SIDE_LIMIT"])

        guard.can_open("BTCUSDT", Decimal("100"), portfolio)

        assert guard._safe_create_task.called # Should emit ORDER_CLIPPED

def test_event_emission_on_rejection(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()
    guard.soft_limit_config.mode = "reject"

    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "900", # At limit
        "positions": []
    }

    guard.can_open("BTCUSDT", Decimal("100"), portfolio)

    assert guard._safe_create_task.called # Should emit ORDER_REJECTED

def test_safe_create_task(guard):
    # Test with running loop
    async def dummy(): pass

    with patch("asyncio.get_running_loop") as mock_loop:
        guard._safe_create_task(dummy())
        assert mock_loop.return_value.create_task.called

    # Test without running loop but with event loop
    with patch("asyncio.get_running_loop", side_effect=RuntimeError):
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.is_closed.return_value = False
            guard._safe_create_task(dummy())
            assert mock_loop.return_value.create_task.called

def test_on_portfolio(guard):
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions": []
    }
    guard.on_portfolio(portfolio)
    assert guard._latest_portfolio_state == portfolio

def test_increment_metric_legacy(guard):
    # Manually set a metric to int to trigger legacy conversion
    guard.metrics["test_metric"] = 5
    guard._increment_metric("test_metric", "reason1")

    assert isinstance(guard.metrics["test_metric"], dict)
    assert guard.metrics["test_metric"]["__legacy_total"] == 5
    assert guard.metrics["test_metric"]["reason1"] == 1

def test_can_open_margin_fallback(guard):
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        # open_positions_margin_usd MISSING
        "open_positions_usd": "2000", # 2000 / 20 (lev) = 100 margin
        "positions": []
    }

    # Request 100 notional (5 margin). Total margin 105. Limit 900. OK.
    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is True

    # Verify margin calculation in logs or by checking if it blocks when near limit
    # Limit 900. Existing 100. Request 17000 (850 margin). Total 950 > 900.
    # Allowed extra = 900 - 100 = 800 > 0. So it SHRINKS, not rejects.

    # To force reject, we need existing margin >= limit.
    portfolio_full = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        # open_positions_margin_usd MISSING
        "open_positions_usd": "18000", # 18000 / 20 = 900 margin (Full limit)
        "positions": []
    }

    # Disable soft clip to force reject
    guard.soft_limit_config.mode = "reject"

    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio_full)
    assert res["allowed"] is False
    assert res["reason"] == "EXPOSURE_LIMIT_EXCEEDED"

def test_side_limit_reject_with_event(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()

    # Equity 1000, Max Side 0.6 -> Limit 600 margin
    # Current Short Margin 600 (Full)
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "600",
        "positions_by_side": {
            "long_margin": "0",
            "short_margin": "600"
        },
        "positions": []
    }

    # Disable soft clip
    guard.soft_limit_config.mode = "reject"

    # Request SELL.
    res = guard.can_open("BTCUSDT", Decimal("100"), portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "SIDE_EXPOSURE_EXCEEDED"
    assert guard._safe_create_task.called

def test_directional_ratio_reject_with_event(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()

    # Max Ratio 3.0
    # Long 300, Short 100. Ratio 3.0.
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "400",
        "positions_by_side": {
            "long_margin": "300",
            "short_margin": "100"
        },
        "positions": []
    }

    # Force BUY side
    guard.reserve("test_buy", Decimal("2000"), side="BUY") # 100 margin

    # Disable soft clip
    guard.soft_limit_config.mode = "reject"

    res = guard.can_open("BTCUSDT", Decimal("2000"), portfolio)
    assert res["allowed"] is False
    assert res["reason"] == "DIRECTIONAL_RATIO_EXCEEDED"
    assert guard._safe_create_task.called

def test_directional_ratio_soft_clip(guard):
    guard.fsm = MagicMock()
    guard._safe_create_task = MagicMock()

    # Max Ratio 3.0
    # Long 300, Short 100. Ratio 3.0.
    portfolio = {
        "positions_last_ts_ms": time.time() * 1000,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "400",
        "positions_by_side": {
            "long_margin": "300",
            "short_margin": "100"
        },
        "positions": []
    }

    # Force BUY side. 2000 notional (100 margin).
    # New Long 400. Short 100. Ratio 4.0 > 3.0.
    guard.reserve("test_buy", Decimal("2000"), side="BUY")

    # Enable soft clip (default)
    guard.soft_limit_config.mode = "clip"

    # Mock soft clip engine to return success
    with patch.object(guard.soft_clip_engine, "calculate_clipped_size") as mock_clip:
        mock_clip.return_value = MagicMock(allowed=True, clipped_notional=Decimal("1000"), clip_reasons=["DIRECTIONAL_RATIO"])

        res = guard.can_open("BTCUSDT", Decimal("2000"), portfolio)

        assert res["allowed"] is True
        assert res["reason"] == "CLIPPED_DIRECTIONAL"
        assert res["shrink_notional"] == Decimal("1000")
        assert guard._safe_create_task.called # Event emission
