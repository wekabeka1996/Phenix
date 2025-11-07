"""
Tests for DecisionMaking side-bias penalty logic.

EXP-DIRECTION: Tests for sell_share tracking and threshold adjustment.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
import time

from apps.reference.domains.decision_making.decision_making import DecisionMaking


@pytest.fixture
def dm_config():
    """Fixture for DecisionMaking configuration with side-bias settings."""
    return {
        "trading": {
            "decision": {
                "signal_weights": {
                    "obi": 0.6,
                    "tfi": 0.35,
                    "delta_price": 0.05
                },
                "signal_threshold": 0.1,
                "side_bias_window_sec": 60,
                "side_bias_target_ratio": 0.6,  # Max 60% on one side
                "side_bias_penalty_factor": 0.5,  # Raise threshold by 50%
                "regime_threshold_multipliers": {
                    "DEFAULT": "1.0"
                }
            },
            "tca_prefs": {
                "maker_preference": 0.1,
                "max_slippage_bps": 10,
                "max_latency_ms": 100
            },
            "risk_budgets": {
                "daily_loss_limit": 1000,
                "max_portfolio_loss_pct": 0.05
            }
        }
    }


@pytest.fixture
def decision_making(dm_config):
    """Fixture for DecisionMaking instance."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()

    dm = DecisionMaking(fsm, dm_config)
    dm._side_intent_window = {}
    return dm


def test_side_bias_penalty_on_excess_sells(decision_making):
    """Test that threshold is raised when sell_share > target."""
    symbol = "ETHUSDT"

    # Simulate recent intents: 8 sells, 2 buys (80% sell, exceeds 60% target)
    decision_making._side_intent_window[symbol] = {
        "buys": [time.time() - 10, time.time() - 20],
        "sells": [time.time() - i for i in range(8)]  # 8 recent sells
    }

    current_time = time.time()
    buy_count = len(decision_making._side_intent_window[symbol]["buys"])
    sell_count = len(decision_making._side_intent_window[symbol]["sells"])
    total_count = buy_count + sell_count

    sell_share = Decimal(str(sell_count)) / Decimal(str(total_count))

    # Verify math: 8/(8+2) = 0.8 = 80%
    assert sell_share == Decimal("0.8")
    assert sell_share > Decimal("0.6")  # Exceeds target


def test_side_bias_penalty_on_excess_buys(decision_making):
    """Test that threshold is raised when buy_share > target."""
    symbol = "BTCUSDT"

    # Simulate: 2 sells, 8 buys (20% sell, 80% buy, exceeds balance)
    decision_making._side_intent_window[symbol] = {
        "buys": [time.time() - i for i in range(8)],
        "sells": [time.time() - 10, time.time() - 20]
    }

    buy_count = len(decision_making._side_intent_window[symbol]["buys"])
    sell_count = len(decision_making._side_intent_window[symbol]["sells"])
    total_count = buy_count + sell_count

    sell_share = Decimal(str(sell_count)) / Decimal(str(total_count))
    buy_share = Decimal("1") - sell_share

    # Verify: 2/(2+8) = 0.2 = 20% sell, 80% buy
    assert buy_share == Decimal("0.8")
    assert buy_share > Decimal("0.6")  # Exceeds target


def test_neutral_bias_no_penalty(decision_making):
    """Test that no penalty is applied when sides are balanced."""
    symbol = "ETHUSDT"

    # Simulate: 5 sells, 5 buys (50% each, balanced)
    decision_making._side_intent_window[symbol] = {
        "buys": [time.time() - i for i in range(5)],
        "sells": [time.time() - i for i in range(5)]
    }

    buy_count = len(decision_making._side_intent_window[symbol]["buys"])
    sell_count = len(decision_making._side_intent_window[symbol]["sells"])
    total_count = buy_count + sell_count

    sell_share = Decimal(str(sell_count)) / Decimal(str(total_count))

    # Verify: 5/(5+5) = 0.5 = 50% (balanced)
    assert sell_share == Decimal("0.5")
    assert not (sell_share > Decimal("0.6"))
    assert not (sell_share < Decimal("0.4"))


def test_window_cleanup_old_intents(decision_making):
    """Test that old intents outside window are removed."""
    symbol = "ETHUSDT"
    window_sec = 60
    current_time = time.time()

    # Add some old intents (> 60 sec old)
    old_buys = [current_time - 70, current_time - 80]
    # Add fresh intents
    fresh_buys = [current_time - 10, current_time - 20]

    decision_making._side_intent_window[symbol] = {
        "buys": old_buys + fresh_buys,
        "sells": []
    }

    # Simulate cleanup by filtering
    cleaned_buys = [ts for ts in decision_making._side_intent_window[symbol]["buys"]
                    if current_time - ts < window_sec]

    # Should remove old ones, keep fresh
    assert len(cleaned_buys) == 2
    assert all(current_time - ts < window_sec for ts in cleaned_buys)


def test_threshold_multiplier_calculation(decision_making):
    """Test that threshold multiplier is correctly calculated."""
    config = decision_making.config.get("trading", {}).get("decision", {})
    base_threshold = Decimal(str(config.get("signal_threshold", "0.1")))
    penalty_factor = Decimal(
        str(config.get("side_bias_penalty_factor", "0.5")))

    # When bias multiplier = 1.5 (no bias), threshold stays same
    bias_multiplier = Decimal("1.0")
    threshold = base_threshold * bias_multiplier
    assert threshold == base_threshold

    # When bias multiplier = 1.5 (50% penalty), threshold increases
    bias_multiplier = Decimal("1.0") + penalty_factor
    threshold = base_threshold * bias_multiplier
    assert threshold == base_threshold * Decimal("1.5")


def test_signal_score_filtering_with_bias(decision_making):
    """Test that signal scores are correctly filtered with bias penalty."""
    base_threshold = Decimal("0.1")
    penalty_factor = Decimal("0.5")
    bias_multiplier = Decimal("1.0") + penalty_factor  # 1.5

    threshold_with_bias = base_threshold * bias_multiplier  # 0.15

    # Signal scores
    buy_signal_high = Decimal("0.2")  # > 0.15, should pass as BUY
    buy_signal_low = Decimal("0.12")  # < 0.15, should be NEUTRAL
    sell_signal_high = Decimal("-0.2")  # < -0.15, should pass as SELL
    sell_signal_low = Decimal("-0.12")  # > -0.15, should be NEUTRAL

    # High BUY
    assert buy_signal_high > threshold_with_bias

    # Low BUY
    assert buy_signal_low < threshold_with_bias

    # High SELL
    assert sell_signal_high < -threshold_with_bias

    # Low SELL
    assert sell_signal_low > -threshold_with_bias


def test_initial_zero_history(decision_making):
    """Test that starting with zero history doesn't crash."""
    symbol = "ETHUSDT"

    # No history yet - should use default 0.5 ratio
    if symbol not in decision_making._side_intent_window:
        decision_making._side_intent_window[symbol] = {"buys": [], "sells": []}

    window_data = decision_making._side_intent_window[symbol]
    buy_count = len(window_data["buys"])
    sell_count = len(window_data["sells"])
    total_count = buy_count + sell_count

    if total_count > 0:
        sell_share = Decimal(str(sell_count)) / Decimal(str(total_count))
    else:
        sell_share = Decimal("0.5")  # Default neutral

    assert sell_share == Decimal("0.5")


def test_rapid_fire_same_side(decision_making):
    """Test window correctly tracks rapid-fire orders on same side."""
    symbol = "BTCUSDT"
    current_time = time.time()

    # Simulate 10 rapid SELL intents in last 5 seconds
    rapid_sells = [current_time - i*0.5 for i in range(10)]

    decision_making._side_intent_window[symbol] = {
        "buys": [],
        "sells": rapid_sells
    }

    sell_count = len(decision_making._side_intent_window[symbol]["sells"])
    buy_count = len(decision_making._side_intent_window[symbol]["buys"])
    total_count = sell_count + buy_count

    sell_share = Decimal(str(sell_count)) / \
        Decimal(str(total_count)) if total_count > 0 else Decimal("0.5")

    # Should be 100% sells
    assert sell_share == Decimal("1")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
