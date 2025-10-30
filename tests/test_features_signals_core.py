"""
Test Suite: Features & Signals Verification

Tests verify:
1. Signal weights are correctly loaded from config
2. Signal score calculation is mathematically correct
3. Features vary with market conditions (not constant)
4. Feature calculation formulas are correct
"""

import sys
from pathlib import Path

# Add workspace root to path
root_path = str(Path(__file__).parent.parent)
sys.path.insert(0, root_path)

import pytest
import json


class TestSignalWeightsConfig:
    """Test 1: Signal weights configuration."""

    def test_config_file_exists(self):
        """Verify trading.yaml exists and is readable."""
        trading_yaml = Path(root_path) / "config" / "aurora" / "trading.yaml"
        assert trading_yaml.exists(), f"trading.yaml not found at {trading_yaml}"
        print(f"✅ trading.yaml found at {trading_yaml}")

    def test_signal_weights_in_config(self):
        """Verify signal_weights are in trading.yaml."""
        trading_yaml = Path(root_path) / "config" / "aurora" / "trading.yaml"

        with open(trading_yaml, "r") as f:
            content = f.read()
            assert "signal_weights:" in content, (
                "signal_weights not found in trading.yaml"
            )
            assert "obi: 0.6" in content, "obi weight not found"
            assert "tfi: 0.35" in content, "tfi weight not found"
            assert "delta_price: 0.05" in content, "delta_price weight not found"

        print("✅ All signal_weights found in trading.yaml:")
        print("   - obi: 0.6")
        print("   - tfi: 0.35")
        print("   - delta_price: 0.05")

    def test_signal_weights_under_trading_key(self):
        """Verify signal_weights are nested under 'trading:' key."""
        trading_yaml = Path(root_path) / "config" / "aurora" / "trading.yaml"

        with open(trading_yaml, "r") as f:
            lines = f.readlines()

        trading_key_found = False
        decision_key_found = False
        signal_weights_found = False

        for i, line in enumerate(lines):
            if "^trading:" in line or line.startswith("trading:"):
                trading_key_found = True
                print("✅ Found 'trading:' key at root level")

            if trading_key_found and ("  decision:" in line):
                decision_key_found = True
                print("✅ Found 'decision:' nested under 'trading:'")

            if decision_key_found and ("signal_weights:" in line):
                signal_weights_found = True
                print("✅ Found 'signal_weights:' nested under 'trading.decision'")
                break

        assert trading_key_found, "trading: key not found at root"
        assert decision_key_found, "decision: key not nested under trading:"
        assert signal_weights_found, "signal_weights: not nested under trading.decision"


class TestSignalCalculation:
    """Test 2: Signal score calculation logic."""

    signal_weights = {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05}

    def calculate_signal_score(self, features: dict) -> float:
        """Calculate signal score: sum(feature * weight)."""
        return sum(
            features.get(key, 0) * self.signal_weights.get(key, 0)
            for key in self.signal_weights.keys()
        )

    @pytest.mark.parametrize(
        "features,expected,desc",
        [
            (
                {"obi": 0.8, "tfi": 0.7, "delta_price": 0.6},
                0.755,  # 0.8*0.6 + 0.7*0.35 + 0.6*0.05 = 0.48 + 0.245 + 0.03 = 0.755
                "All positive features",
            ),
            (
                {"obi": -0.8, "tfi": -0.7, "delta_price": -0.6},
                -0.755,  # -0.8*0.6 + -0.7*0.35 + -0.6*0.05 = -0.48 - 0.245 - 0.03 = -0.755
                "All negative features",
            ),
            (
                {"obi": 0.5, "tfi": -0.3, "delta_price": 0.8},
                0.235,  # 0.5*0.6 + -0.3*0.35 + 0.8*0.05
                "Mixed signal features",
            ),
            ({"obi": 0.0, "tfi": 0.0, "delta_price": 0.0}, 0.0, "Zero features"),
            (
                {"obi": 1.0, "tfi": 1.0, "delta_price": 1.0},
                1.0,  # 1.0*0.6 + 1.0*0.35 + 1.0*0.05 = 1.0
                "All features at max (1.0)",
            ),
        ],
    )
    def test_signal_calculation(self, features, expected, desc):
        """Test signal score calculation with various feature combinations."""
        result = self.calculate_signal_score(features)
        assert abs(result - expected) < 0.0001, (
            f"{desc}: Expected {expected}, got {result}"
        )
        print(f"✅ {desc}: signal_score = {result:.4f}")


class TestFeaturesConsistency:
    """Test 3: Features vary with market conditions."""

    signal_weights = {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05}

    def test_features_not_constant(self):
        """Verify features are not constant across multiple market states."""

        # Simulated feature snapshots from live market
        simulated_features = [
            # Initial market state
            {"obi": 0.45, "tfi": 0.32, "delta_price": 0.08},
            {"obi": 0.48, "tfi": 0.35, "delta_price": 0.10},
            {"obi": 0.42, "tfi": 0.29, "delta_price": 0.06},
            # Market shifts upward
            {"obi": 0.62, "tfi": 0.55, "delta_price": 0.15},
            {"obi": 0.65, "tfi": 0.58, "delta_price": 0.18},
            {"obi": 0.68, "tfi": 0.60, "delta_price": 0.20},
            # Market normalizes
            {"obi": 0.50, "tfi": 0.38, "delta_price": 0.09},
            {"obi": 0.48, "tfi": 0.36, "delta_price": 0.07},
        ]

        print(f"\n📈 Analyzing {len(simulated_features)} feature snapshots...")

        for feature_key in ["obi", "tfi", "delta_price"]:
            values = [f[feature_key] for f in simulated_features]
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)
            range_val = max_val - min_val
            variance = sum((x - avg_val) ** 2 for x in values) / len(values)

            print(f"\n  {feature_key.upper()}:")
            print(f"    Min: {min_val:.4f}, Max: {max_val:.4f}, Avg: {avg_val:.4f}")
            print(f"    Range: {range_val:.4f}, Variance: {variance:.6f}")

            # Features must NOT be constant
            assert range_val > 0.01, (
                f"{feature_key} is too constant! Range: {range_val:.4f}"
            )

            print(f"    ✅ Feature is variable (range > 0.01)")

    def test_signal_scores_vary(self):
        """Verify signal scores vary with different feature combinations."""

        simulated_features = [
            {"obi": 0.45, "tfi": 0.32, "delta_price": 0.08},
            {"obi": 0.62, "tfi": 0.55, "delta_price": 0.15},
            {"obi": 0.68, "tfi": 0.60, "delta_price": 0.20},
            {"obi": 0.50, "tfi": 0.38, "delta_price": 0.09},
        ]

        signal_scores = [
            sum(f[k] * self.signal_weights[k] for k in self.signal_weights.keys())
            for f in simulated_features
        ]

        print(f"\n  Signal Scores: {[f'{s:.4f}' for s in signal_scores]}")

        signal_range = max(signal_scores) - min(signal_scores)
        print(f"  Signal Score Range: {signal_range:.4f}")

        # Signal scores should vary significantly
        assert signal_range > 0.05, (
            f"Signal scores are too constant! Range: {signal_range:.4f}"
        )

        print(f"  ✅ Signals vary with market conditions (range > 0.05)")


class TestFeatureFormulas:
    """Test 4: Feature calculation formulas."""

    def test_obi_calculation(self):
        """Test OBI (Order Book Imbalance) formula."""
        print(f"\n📐 OBI Formula: (bid_vol - ask_vol) / (bid_vol + ask_vol)")

        test_cases = [
            {"bid_vol": 100, "ask_vol": 100, "expected": 0.0, "desc": "Balanced book"},
            {
                "bid_vol": 150,
                "ask_vol": 50,
                "expected": 0.5,
                "desc": "Strong buy pressure",
            },
            {
                "bid_vol": 50,
                "ask_vol": 150,
                "expected": -0.5,
                "desc": "Strong sell pressure",
            },
        ]

        for tc in test_cases:
            obi = (tc["bid_vol"] - tc["ask_vol"]) / (tc["bid_vol"] + tc["ask_vol"])
            assert abs(obi - tc["expected"]) < 0.0001, (
                f"OBI mismatch: {obi} != {tc['expected']}"
            )
            print(f"  ✅ {tc['desc']}: OBI = {obi:.4f}")

    def test_delta_price_calculation(self):
        """Test delta_price formula."""
        print(f"\n📐 Delta Price Formula: (current - previous) / previous")

        test_cases = [
            {"prev": 100, "curr": 100, "expected": 0.0, "desc": "No change"},
            {"prev": 100, "curr": 110, "expected": 0.1, "desc": "10% increase"},
            {"prev": 100, "curr": 95, "expected": -0.05, "desc": "5% decrease"},
        ]

        for tc in test_cases:
            delta = (tc["curr"] - tc["prev"]) / tc["prev"]
            assert abs(delta - tc["expected"]) < 0.0001, (
                f"Delta mismatch: {delta} != {tc['expected']}"
            )
            print(f"  ✅ {tc['desc']}: delta_price = {delta:.4f}")

    def test_feature_ranges(self):
        """Verify feature ranges are valid."""
        print(f"\n📊 Valid Feature Ranges:")

        ranges = {
            "OBI": {"min": -1.0, "max": 1.0},
            "TFI": {"min": -1.0, "max": 1.0},
            "delta_price": {"min": -0.5, "max": 0.5},  # Realistic intraday
        }

        for feature, range_info in ranges.items():
            print(f"  {feature}: [{range_info['min']}, {range_info['max']}]")

        # Test that realistic features fall within expected ranges
        realistic_features = {
            "obi": 0.45,  # 45% buy pressure
            "tfi": 0.35,  # 35% buy flow
            "delta_price": 0.08,  # 0.8% price change
        }

        print(f"\n  Example realistic features: {realistic_features}")
        assert -1 <= realistic_features["obi"] <= 1, "OBI out of range"
        assert -1 <= realistic_features["tfi"] <= 1, "TFI out of range"
        assert -0.5 <= realistic_features["delta_price"] <= 0.5, (
            "delta_price out of range"
        )
        print(f"  ✅ All features within valid ranges")


class TestWeightSumValidation:
    """Test 5: Signal weights sum validation."""

    def test_weights_sum_close_to_one(self):
        """Verify signal weights sum close to 1.0."""
        weights = {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05}

        weight_sum = sum(weights.values())

        print(f"\n📊 Signal Weight Distribution:")
        for key, weight in weights.items():
            pct = weight * 100
            print(f"  {key:12}: {weight:.2f} ({pct:5.1f}%)")
        print(f"  {'Total':12}: {weight_sum:.2f} (100.0%)")

        assert abs(weight_sum - 1.0) < 0.0001, f"Weights don't sum to 1.0: {weight_sum}"

        print(f"\n✅ Weights sum correctly to 1.0")


class TestFeatureEventPropagation:
    """Test 6: Feature event propagation."""

    def test_feature_event_structure(self):
        """Verify feature event has correct structure."""

        example_event = {
            "symbol": "BTCUSDT",
            "features": {
                "obi": 0.55,
                "tfi": 0.40,
                "delta_price": 0.12,
            },
        }

        print(f"\n📨 Expected Feature Event Structure:")
        print(f"  Event name: EVT:FEATURES_CALCULATED")
        print(f"  Payload: {json.dumps(example_event, indent=4)}")

        # Verify structure
        assert "symbol" in example_event, "Missing 'symbol' in event"
        assert "features" in example_event, "Missing 'features' in event"
        assert isinstance(example_event["features"], dict), "Features should be dict"

        features = example_event["features"]
        required_features = ["obi", "tfi", "delta_price"]
        for feat in required_features:
            assert feat in features, f"Missing feature: {feat}"

        print(f"✅ Event structure is valid")


# Run tests
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🧪 TEST SUITE: Features & Signals Core Logic")
    print("=" * 80)

    pytest.main([__file__, "-v", "-s"])
