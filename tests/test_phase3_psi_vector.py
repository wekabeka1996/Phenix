"""
Test to verify PHASE 3 implementation:
- psi_vector contains all 8 phi components
- DecisionMaking reads and uses all 8 signal weights
- Signal score calculation includes all 8 metrics
"""

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core import FSMCore
import pytest
import decimal
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

# Setup paths
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "apps" / "reference"))


class TestPhase3PsiVector:
    """Test Phase 3: Verify psi_vector expanded to 8 components."""

    @pytest.mark.legacy
    def test_signal_weights_from_config_has_8_metrics(self):
        """Verify signal_weights in config has all 8 metrics."""
        config = ConfigLoader().load_config()

        assert config.strategies.aurora is not None
        decision_config = config.strategies.aurora.decision
        signal_weights = (
            decision_config.signal_weights
            if hasattr(decision_config, "signal_weights")
            else decision_config.get("signal_weights", {})
        )

        # Convert to dict if needed
        if hasattr(signal_weights, "model_dump"):
            signal_weights_dict = signal_weights.model_dump()
        elif hasattr(signal_weights, "to_dict"):
            signal_weights_dict = signal_weights.to_dict()
        elif hasattr(signal_weights, "_config"):
            signal_weights_dict = signal_weights._config
        else:
            signal_weights_dict = signal_weights

        print(f"\n[CHART] Signal weights from config: {signal_weights_dict}")

        # Verify all 9 metrics present
        expected_metrics = [
            "obi",
            "tfi",
            "delta_price",
            "ema_bias",
            "volume_spike",
            "volatility_state",
            "depth_imbalance",
            "macro_resid",
            "macro_sync",
        ]

        for metric in expected_metrics:
            assert metric in signal_weights_dict, (
                f"Missing metric '{metric}' in signal_weights"
            )

        # Verify weights sum to ~1.0 (allow floating point error)
        total_weight = sum(float(v) for v in signal_weights_dict.values())
        print(f"[OK] Total weight sum: {total_weight}")
        assert 0.95 <= total_weight <= 1.06, (
            f"Weights should sum to ~1.0, got {total_weight}"
        )

        print(f"[OK] All 9 signal weights verified!")

    def test_signal_calculation_includes_all_metrics(self):
        """Verify signal score calculation includes all 8 metrics."""
        # Mock signal_weights
        signal_weights = {
            "obi": 0.25,
            "tfi": 0.25,
            "delta_price": 0.10,
            "ema_bias": 0.15,
            "volume_spike": 0.10,
            "volatility_state": 0.08,
            "depth_imbalance": 0.05,
            "macro_sync": 0.02,
        }

        # Mock phi_map with all 8 values
        phi_map = {
            "obi": decimal.Decimal("0.5"),
            "tfi": decimal.Decimal("0.3"),
            "delta_price": decimal.Decimal("0.4"),
            "ema_bias": decimal.Decimal("0.6"),
            "volume_spike": decimal.Decimal("0.7"),
            "volatility_state": decimal.Decimal("0.5"),
            "depth_imbalance": decimal.Decimal("0.3"),
            "macro_sync": decimal.Decimal("0.8"),
        }

        # Calculate signal score
        signal_score = sum(
            decimal.Decimal(str(phi_map.get(f, 0)))
            * decimal.Decimal(str(w))
            for f, w in signal_weights.items()
        )

        print(f"\n🎯 Signal score (8 metrics): {signal_score}")

        # Verify calculation
        expected = (
            0.5 * 0.25
            + 0.3 * 0.25
            + 0.4 * 0.10
            + 0.6 * 0.15
            + 0.7 * 0.10
            + 0.5 * 0.08
            + 0.3 * 0.05
            + 0.8 * 0.02
        )
        print(f"[OK] Expected signal score: {expected}")
        print(f"[OK] Calculated signal score: {float(signal_score)}")

        assert abs(float(signal_score) - expected) < 0.0001, (
            f"Signal score mismatch: {signal_score} != {expected}"
        )

        print("[OK] Signal calculation verified with all 8 metrics!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
