from decimal import Decimal

import pytest

from apps.reference.config_exposure_policy import resolve_exposure_policy


def test_resolve_exposure_policy_defaults():
    policy = resolve_exposure_policy({})

    assert policy.caps.max_equity_utilization_ratio == Decimal("0.20")
    assert policy.caps.max_directional_ratio == Decimal("2.0")
    assert policy.caps.max_side_utilization_ratio["long"] == Decimal("0.12")
    assert policy.caps.max_side_utilization_ratio["short"] == Decimal("0.12")
    assert policy.caps.per_symbol_cap_ratio == Decimal("0.08")
    assert policy.reservations.pending_ttl_sec == 90
    assert policy.reservations.post_fill_hold_ttl_sec == 5
    assert policy.reservations.positions_stale_ttl_sec == 5
    assert policy.count_pending_orders is True
    assert policy.exclude_reduce_only is True
    assert policy.leverage_defaults.default == Decimal("20")
    assert policy.leverage_defaults.per_symbol == {}
    assert policy.fallback.backoff_sequence() == (200, 500, 1000)
    assert policy.fallback.max_attempts == 4
    assert policy.fallback.enabled is True


@pytest.mark.parametrize(
    "equity_value, expected",
    [("45", Decimal("0.45")), ("0.35", Decimal("0.35")), ("120", Decimal("1.20"))],
)
def test_resolve_exposure_policy_percent_normalization(equity_value, expected):
    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_equity_utilization_pct": equity_value,
                }
            }
        }
    }

    policy = resolve_exposure_policy(config)
    assert policy.caps.max_equity_utilization_ratio == expected


def test_resolve_exposure_policy_custom_values():
    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_equity_utilization_pct": "45",
                    "max_portfolio_fraction": "0.50",
                    "max_directional_ratio": "4.0",
                    "max_side_utilization_pct": {
                        "long": "30",
                        "short": "15",
                    },
                    "per_symbol_cap_pct": "5",
                    "pending_ttl_sec": 120,
                    "post_fill_hold_ttl_sec": 9,
                    "positions_stale_ttl_sec": 25,
                    "count_pending_orders": False,
                    "exclude_reduce_only": False,
                    "leverage_defaults": {
                        "default": "25",
                        "BTCUSDT": "50",
                    },
                },
                "fallback": {
                    "policy": "risk_reduction",
                    "risk_reduction_pct": "25",
                    "backoff_ms": [100, 250],
                    "max_attempts": 5,
                    "enabled": False,
                },
            }
        }
    }

    policy = resolve_exposure_policy(config)

    assert policy.caps.max_equity_utilization_ratio == Decimal("0.45")
    assert policy.caps.max_portfolio_fraction == Decimal("0.50")
    assert policy.caps.max_directional_ratio == Decimal("4.0")
    assert policy.caps.max_side_utilization_ratio["long"] == Decimal("0.30")
    assert policy.caps.max_side_utilization_ratio["short"] == Decimal("0.15")
    assert policy.caps.per_symbol_cap_ratio == Decimal("0.05")
    assert policy.reservations.pending_ttl_sec == 120
    assert policy.reservations.post_fill_hold_ttl_sec == 9
    assert policy.reservations.positions_stale_ttl_sec == 25
    assert policy.count_pending_orders is False
    assert policy.exclude_reduce_only is False
    assert policy.leverage_defaults.default == Decimal("25")
    assert policy.leverage_defaults.resolve_for("BTCUSDT") == Decimal("50")
    assert policy.leverage_defaults.resolve_for("SOLUSDT") == Decimal("25")
    assert policy.fallback.policy == "risk_reduction"
    assert policy.fallback.risk_reduction_pct == Decimal("0.25")
    assert policy.fallback.backoff_sequence() == (100, 250)
    assert policy.fallback.max_attempts == 5
    assert policy.fallback.enabled is False
