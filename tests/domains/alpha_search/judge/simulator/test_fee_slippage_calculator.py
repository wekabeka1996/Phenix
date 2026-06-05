import math

import pytest

from apps.reference.domains.alpha_search.judge.simulator.fee_slippage_calculator import (
    compute_fee_cost_bps,
    compute_net_return,
    compute_slippage_cost_pct,
)


class TestFeeSlippageCalculator:
    def test_long_positive_case(self):
        result = compute_net_return(100.0, 110.0, "LONG", 0.0, 0.0)

        assert math.isclose(result, 0.1)

    def test_long_negative_case(self):
        result = compute_net_return(100.0, 90.0, "LONG", 0.0, 0.0)

        assert math.isclose(result, -0.1)

    def test_short_positive_case(self):
        result = compute_net_return(100.0, 90.0, "SHORT", 0.0, 0.0)

        assert math.isclose(result, 0.1)

    def test_short_negative_case(self):
        result = compute_net_return(100.0, 110.0, "SHORT", 0.0, 0.0)

        assert math.isclose(result, -0.1)

    def test_zero_fee_and_zero_slippage_case(self):
        assert compute_fee_cost_bps(0.0) == 0.0
        assert compute_slippage_cost_pct(0.0) == 0.0
        assert math.isclose(
            compute_net_return(100.0, 110.0, "LONG", 0.0, 0.0),
            0.1,
        )

    def test_nonzero_fee_reduces_return_correctly(self):
        result = compute_net_return(100.0, 110.0, "LONG", 25.0, 0.0)

        assert math.isclose(result, 0.0975)

    def test_nonzero_slippage_reduces_return_correctly(self):
        result = compute_net_return(100.0, 110.0, "LONG", 0.0, 0.1)

        assert math.isclose(result, 0.099)

    def test_invalid_side_rejected(self):
        with pytest.raises(ValueError, match="Unsupported side"):
            compute_net_return(100.0, 110.0, "SIDEWAYS", 0.0, 0.0)

    @pytest.mark.parametrize(
        ("entry_price", "exit_price"),
        [
            (0.0, 110.0),
            (-1.0, 110.0),
            (100.0, 0.0),
            (100.0, -1.0),
        ],
    )
    def test_invalid_prices_rejected(self, entry_price: float, exit_price: float):
        with pytest.raises(ValueError, match="price must be > 0"):
            compute_net_return(entry_price, exit_price, "LONG", 0.0, 0.0)

    def test_negative_fee_rejected(self):
        with pytest.raises(ValueError, match="fee_per_cycle_bps must be >= 0"):
            compute_fee_cost_bps(-0.01)

    def test_negative_slippage_rejected(self):
        with pytest.raises(ValueError, match="slippage_pct must be >= 0"):
            compute_slippage_cost_pct(-0.01)
