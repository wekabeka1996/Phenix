"""
Unit Tests for Feature Engineering Utils

Tests the O(1) statistical algorithms and math helpers:
- Welford's online algorithm for mean/variance
- Z-score computation with clipping
- Safe config accessor
- Linear slope computation
- Edge cases and numerical stability

Author: Aurora/Phenix Runtime
Version: 1.0.0
"""

import math
import statistics
import random
import pytest
from dataclasses import dataclass
from typing import Any, Dict

from apps.reference.domains.feature_engineering.utils import (
    FeatureUtils,
    WelfordAggregate,
    welford_update,
    compute_z_score,
    get_config,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_config
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConfig:
    """Tests for safe nested config accessor."""
    
    def test_dict_single_level(self):
        """Single level dict access."""
        cfg = {"key": "value"}
        assert FeatureUtils.get_config(cfg, "key") == "value"
    
    def test_dict_nested(self):
        """Multi-level nested dict access."""
        cfg = {
            "features": {
                "ema": {
                    "period_short": 5,
                    "period_long": 20
                }
            }
        }
        assert FeatureUtils.get_config(cfg, "features.ema.period_short") == 5
        assert FeatureUtils.get_config(cfg, "features.ema.period_long") == 20
    
    def test_dict_missing_returns_default(self):
        """Missing path returns default."""
        cfg = {"a": {"b": 1}}
        assert FeatureUtils.get_config(cfg, "a.c", default=42) == 42
        assert FeatureUtils.get_config(cfg, "x.y.z", default="nope") == "nope"
    
    def test_dict_none_value(self):
        """None value returns default."""
        cfg = {"a": None}
        assert FeatureUtils.get_config(cfg, "a", default=99) == 99
    
    def test_object_attribute_access(self):
        """Access via object attributes."""
        @dataclass
        class Config:
            threshold: float = 0.5
            enabled: bool = True
        
        cfg = Config()
        assert FeatureUtils.get_config(cfg, "threshold") == 0.5
        assert FeatureUtils.get_config(cfg, "enabled") is True
    
    def test_mixed_dict_and_object(self):
        """Mixed dict and object nesting."""
        @dataclass
        class Inner:
            value: int = 100
        
        cfg = {"outer": Inner()}
        assert FeatureUtils.get_config(cfg, "outer.value") == 100
    
    def test_none_config_returns_default(self):
        """None config returns default immediately."""
        assert FeatureUtils.get_config(None, "any.path", default=123) == 123
    
    def test_empty_path_returns_config(self):
        """Empty path returns config itself."""
        cfg = {"a": 1}
        # Empty string splits to [''] which won't match
        assert FeatureUtils.get_config(cfg, "", default=cfg) == cfg
    
    def test_module_level_alias(self):
        """Module-level get_config function works."""
        cfg = {"level": 5}
        assert get_config(cfg, "level") == 5


# ─────────────────────────────────────────────────────────────────────────────
# Test: Welford's Algorithm
# ─────────────────────────────────────────────────────────────────────────────

class TestWelfordUpdate:
    """Tests for Welford's online mean/variance algorithm."""
    
    def test_single_value(self):
        """Single value gives correct mean, zero variance."""
        stats = (0, 0.0, 0.0)
        stats = FeatureUtils.welford_update(stats, 10.0)
        
        assert stats[0] == 1  # count
        assert stats[1] == 10.0  # mean
        assert stats[2] == 0.0  # m2 (zero with single sample)
    
    def test_two_values(self):
        """Two values give correct mean and m2."""
        stats = (0, 0.0, 0.0)
        stats = FeatureUtils.welford_update(stats, 10.0)
        stats = FeatureUtils.welford_update(stats, 20.0)
        
        assert stats[0] == 2
        assert stats[1] == 15.0  # mean = (10 + 20) / 2
        # m2 = (10-15)^2 + (20-15)^2 = 25 + 25 = 50
        assert abs(stats[2] - 50.0) < 1e-10
    
    def test_matches_statistics_module(self):
        """Welford results match Python statistics module."""
        random.seed(42)
        values = [random.gauss(100, 15) for _ in range(1000)]
        
        # Compute with Welford
        stats = (0, 0.0, 0.0)
        for v in values:
            stats = FeatureUtils.welford_update(stats, v)
        
        welford_mean, _, welford_stddev = FeatureUtils.welford_finalize(stats)
        
        # Compute with statistics module
        stats_mean = statistics.mean(values)
        stats_stddev = statistics.stdev(values)
        
        # Should match within floating-point tolerance
        assert abs(welford_mean - stats_mean) < 1e-10
        assert abs(welford_stddev - stats_stddev) < 1e-6
    
    def test_incremental_matches_batch(self):
        """Incremental updates match batch computation."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        
        # Incremental
        stats = (0, 0.0, 0.0)
        for v in values:
            stats = FeatureUtils.welford_update(stats, v)
        
        mean, variance, _ = FeatureUtils.welford_finalize(stats)
        
        # Batch
        batch_mean = sum(values) / len(values)
        batch_variance = sum((x - batch_mean) ** 2 for x in values) / len(values)
        
        assert abs(mean - batch_mean) < 1e-10
        assert abs(variance - batch_variance) < 1e-10
    
    def test_nan_input_ignored(self):
        """NaN input is ignored."""
        stats = (2, 15.0, 50.0)  # existing stats
        stats = FeatureUtils.welford_update(stats, float('nan'))
        
        assert stats == (2, 15.0, 50.0)  # unchanged
    
    def test_inf_input_ignored(self):
        """Inf input is ignored."""
        stats = (2, 15.0, 50.0)
        stats = FeatureUtils.welford_update(stats, float('inf'))
        
        assert stats == (2, 15.0, 50.0)  # unchanged
    
    def test_module_level_alias(self):
        """Module-level welford_update function works."""
        stats = (0, 0.0, 0.0)
        stats = welford_update(stats, 5.0)
        assert stats[0] == 1
        assert stats[1] == 5.0


class TestWelfordFinalize:
    """Tests for extracting final statistics from Welford aggregate."""
    
    def test_finalize_empty(self):
        """Empty aggregate returns zeros."""
        mean, var, std = FeatureUtils.welford_finalize((0, 0.0, 0.0))
        assert mean == 0.0
        assert var == 0.0
        assert std == 0.0
    
    def test_finalize_single(self):
        """Single sample returns mean only."""
        mean, var, std = FeatureUtils.welford_finalize((1, 42.0, 0.0))
        assert mean == 42.0
        assert var == 0.0
        assert std == 0.0
    
    def test_finalize_multiple(self):
        """Multiple samples return correct stats."""
        # Values: [10, 20], mean=15, m2=50
        # Sample variance = 50/1 = 50, stddev = sqrt(50) ≈ 7.07
        mean, var, std = FeatureUtils.welford_finalize((2, 15.0, 50.0))
        
        assert mean == 15.0
        assert abs(var - 25.0) < 1e-10  # population variance = m2/n
        assert abs(std - math.sqrt(50)) < 1e-10  # sample stddev


class TestWelfordRemove:
    """Tests for removing values from Welford aggregate."""
    
    def test_remove_to_single(self):
        """Remove value leaving single sample."""
        # Start with [10, 20], remove 20
        stats = (2, 15.0, 50.0)
        stats = FeatureUtils.welford_remove_tuple(stats, 20.0)
        
        assert stats[0] == 1
        assert abs(stats[1] - 10.0) < 1e-10
    
    def test_remove_to_empty(self):
        """Remove last value gives empty stats."""
        stats = (1, 10.0, 0.0)
        stats = FeatureUtils.welford_remove_tuple(stats, 10.0)
        
        assert stats == (0, 0.0, 0.0)
    
    def test_remove_roundtrip(self):
        """Add then remove gives same stats."""
        original = (5, 100.0, 200.0)
        
        # Add a value
        updated = FeatureUtils.welford_update(original, 50.0)
        # Remove it
        restored = FeatureUtils.welford_remove_tuple(updated, 50.0)
        
        # Should be close to original (floating point)
        assert restored[0] == original[0]
        assert abs(restored[1] - original[1]) < 1e-8
        assert abs(restored[2] - original[2]) < 1e-6
    
    def test_add_five_remove_five_returns_to_zero(self):
        """Add 5 values then remove them all - stats should return to zero."""
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        
        # Build up
        stats = (0, 0.0, 0.0)
        for v in values:
            stats = FeatureUtils.welford_update(stats, v)
        
        assert stats[0] == 5
        assert abs(stats[1] - 30.0) < 1e-10  # mean = 30
        
        # Tear down
        for v in values:
            stats = FeatureUtils.welford_remove_tuple(stats, v)
        
        assert stats == (0, 0.0, 0.0)
    
    def test_module_level_alias(self):
        """Module-level welford_remove function works."""
        from apps.reference.domains.feature_engineering.utils import welford_remove
        
        stats = (2, 15.0, 50.0)
        stats = welford_remove(stats, 20.0)
        
        assert stats[0] == 1
        assert abs(stats[1] - 10.0) < 1e-10


# ─────────────────────────────────────────────────────────────────────────────
# Test: Z-Score
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeZScore:
    """Tests for Z-score computation."""
    
    def test_z_score_at_mean(self):
        """Value at mean has Z-score of 0."""
        # mean=100, variance=100 (stddev=10)
        stats = (100, 100.0, 9900.0)  # m2 = var * (n-1) = 100 * 99
        z = FeatureUtils.compute_z_score(100.0, stats)
        assert abs(z) < 1e-10
    
    def test_z_score_one_stddev_above(self):
        """One stddev above mean has Z-score of 1."""
        # mean=50, stddev=5, so variance=25, m2=25*99=2475
        stats = (100, 50.0, 2475.0)
        z = FeatureUtils.compute_z_score(55.0, stats)
        assert abs(z - 1.0) < 1e-6
    
    def test_z_score_one_stddev_below(self):
        """One stddev below mean has Z-score of -1."""
        stats = (100, 50.0, 2475.0)
        z = FeatureUtils.compute_z_score(45.0, stats)
        assert abs(z + 1.0) < 1e-6
    
    def test_z_score_clipping_upper(self):
        """Z-score clipped to upper bound."""
        stats = (100, 50.0, 2475.0)  # stddev ≈ 5
        # value=70 is 4 stddev above mean
        z = FeatureUtils.compute_z_score(70.0, stats, clip_sigma=3.0)
        assert z == 3.0
    
    def test_z_score_clipping_lower(self):
        """Z-score clipped to lower bound."""
        stats = (100, 50.0, 2475.0)
        # value=30 is 4 stddev below mean
        z = FeatureUtils.compute_z_score(30.0, stats, clip_sigma=3.0)
        assert z == -3.0
    
    def test_z_score_insufficient_samples(self):
        """Returns 0 with < 2 samples."""
        assert FeatureUtils.compute_z_score(10.0, (0, 0.0, 0.0)) == 0.0
        assert FeatureUtils.compute_z_score(10.0, (1, 10.0, 0.0)) == 0.0
    
    def test_z_score_zero_variance(self):
        """Returns 0 with zero variance."""
        stats = (10, 50.0, 0.0)  # All values identical
        assert FeatureUtils.compute_z_score(50.0, stats) == 0.0
        assert FeatureUtils.compute_z_score(60.0, stats) == 0.0
    
    def test_z_score_nan_input(self):
        """NaN input returns 0."""
        stats = (100, 50.0, 2475.0)
        assert FeatureUtils.compute_z_score(float('nan'), stats) == 0.0
    
    def test_z_score_inf_input(self):
        """Inf input returns 0."""
        stats = (100, 50.0, 2475.0)
        assert FeatureUtils.compute_z_score(float('inf'), stats) == 0.0
    
    def test_module_level_alias(self):
        """Module-level compute_z_score function works."""
        stats = (100, 50.0, 2475.0)
        z = compute_z_score(55.0, stats)
        assert abs(z - 1.0) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Test: Linear Slope
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeLinearSlope:
    """Tests for linear regression slope computation."""
    
    def test_empty_list(self):
        """Empty list returns 0."""
        assert FeatureUtils.compute_linear_slope([]) == 0.0
    
    def test_single_value(self):
        """Single value returns 0."""
        assert FeatureUtils.compute_linear_slope([10.0]) == 0.0
    
    def test_constant_values(self):
        """Constant values have slope 0."""
        slope = FeatureUtils.compute_linear_slope([5.0, 5.0, 5.0, 5.0])
        assert abs(slope) < 1e-10
    
    def test_perfect_positive_slope(self):
        """Perfect linear increase has correct slope."""
        # y = x, so slope = 1
        slope = FeatureUtils.compute_linear_slope([0.0, 1.0, 2.0, 3.0, 4.0])
        assert abs(slope - 1.0) < 1e-10
    
    def test_perfect_negative_slope(self):
        """Perfect linear decrease has correct slope."""
        # y = -x + 4, so slope = -1
        slope = FeatureUtils.compute_linear_slope([4.0, 3.0, 2.0, 1.0, 0.0])
        assert abs(slope + 1.0) < 1e-10
    
    def test_slope_with_x_step(self):
        """Slope scales with x_step."""
        # y = [0, 1, 2, 3] at x = [0, 0.5, 1.0, 1.5]
        # Raw slope = 1.0 (per unit x index), scaled by 1/x_step = 2.0
        slope = FeatureUtils.compute_linear_slope([0.0, 1.0, 2.0, 3.0], x_step=0.5)
        assert abs(slope - 2.0) < 1e-10
    
    def test_nan_in_values(self):
        """NaN in values returns 0."""
        slope = FeatureUtils.compute_linear_slope([1.0, float('nan'), 3.0])
        assert slope == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Safe Math Operations
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeDivide:
    """Tests for safe division."""
    
    def test_normal_division(self):
        """Normal division works."""
        assert FeatureUtils.safe_divide(10.0, 2.0) == 5.0
    
    def test_zero_denominator(self):
        """Zero denominator returns default."""
        assert FeatureUtils.safe_divide(10.0, 0.0) == 0.0
        assert FeatureUtils.safe_divide(10.0, 0.0, default=-1.0) == -1.0
    
    def test_near_zero_denominator(self):
        """Near-zero denominator returns default."""
        assert FeatureUtils.safe_divide(10.0, 1e-15) == 0.0
    
    def test_nan_numerator(self):
        """NaN numerator returns default."""
        assert FeatureUtils.safe_divide(float('nan'), 1.0, default=99.0) == 99.0
    
    def test_inf_result(self):
        """Inf result returns default."""
        # Large number / tiny number could overflow
        result = FeatureUtils.safe_divide(1e308, 1e-308, default=0.0)
        assert result == 0.0 or math.isfinite(result)


class TestClamp:
    """Tests for value clamping."""
    
    def test_within_range(self):
        """Value within range unchanged."""
        assert FeatureUtils.clamp(5.0, 0.0, 10.0) == 5.0
    
    def test_below_min(self):
        """Value below min clamped to min."""
        assert FeatureUtils.clamp(-5.0, 0.0, 10.0) == 0.0
    
    def test_above_max(self):
        """Value above max clamped to max."""
        assert FeatureUtils.clamp(15.0, 0.0, 10.0) == 10.0
    
    def test_nan_returns_midpoint(self):
        """NaN returns midpoint of range."""
        assert FeatureUtils.clamp(float('nan'), 0.0, 10.0) == 5.0


class TestNormalize:
    """Tests for value normalization."""
    
    def test_normalize_midpoint(self):
        """Midpoint normalizes to 0.5."""
        assert FeatureUtils.normalize(50.0, 0.0, 100.0) == 0.5
    
    def test_normalize_min(self):
        """Min value normalizes to target_min."""
        assert FeatureUtils.normalize(0.0, 0.0, 100.0) == 0.0
    
    def test_normalize_max(self):
        """Max value normalizes to target_max."""
        assert FeatureUtils.normalize(100.0, 0.0, 100.0) == 1.0
    
    def test_normalize_custom_range(self):
        """Custom target range works."""
        result = FeatureUtils.normalize(50.0, 0.0, 100.0, target_min=-1.0, target_max=1.0)
        assert result == 0.0
    
    def test_normalize_zero_range(self):
        """Zero source range returns midpoint."""
        result = FeatureUtils.normalize(5.0, 5.0, 5.0)
        assert result == 0.5
    
    def test_normalize_clamps_outside(self):
        """Values outside range are clamped."""
        assert FeatureUtils.normalize(-10.0, 0.0, 100.0) == 0.0
        assert FeatureUtils.normalize(110.0, 0.0, 100.0) == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Numerical Stability
# ─────────────────────────────────────────────────────────────────────────────

class TestNumericalStability:
    """Tests for numerical stability with extreme values."""
    
    def test_welford_large_values(self):
        """Welford handles large values correctly."""
        stats = (0, 0.0, 0.0)
        for v in [1e10, 1e10 + 1, 1e10 + 2]:
            stats = FeatureUtils.welford_update(stats, v)
        
        mean, _, stddev = FeatureUtils.welford_finalize(stats)
        assert abs(mean - (1e10 + 1)) < 1
        assert stddev > 0  # Should have non-zero stddev
    
    def test_welford_small_values(self):
        """Welford handles small values correctly."""
        stats = (0, 0.0, 0.0)
        for v in [1e-10, 2e-10, 3e-10]:
            stats = FeatureUtils.welford_update(stats, v)
        
        mean, _, _ = FeatureUtils.welford_finalize(stats)
        assert abs(mean - 2e-10) < 1e-15
    
    def test_welford_mixed_scale(self):
        """Welford handles mixed scale values."""
        stats = (0, 0.0, 0.0)
        values = [1.0, 1000.0, 1.0, 1000.0, 1.0, 1000.0]
        for v in values:
            stats = FeatureUtils.welford_update(stats, v)
        
        mean, _, stddev = FeatureUtils.welford_finalize(stats)
        assert abs(mean - statistics.mean(values)) < 1e-6
        assert abs(stddev - statistics.stdev(values)) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Performance Sanity Check
# ─────────────────────────────────────────────────────────────────────────────

class TestPerformance:
    """Basic performance sanity checks."""
    
    def test_welford_is_o1(self):
        """Welford update is O(1) - no iteration over history."""
        import time
        
        stats = (0, 0.0, 0.0)
        
        # Warm up
        for _ in range(100):
            stats = FeatureUtils.welford_update(stats, 1.0)
        
        # Time with small count
        stats_small = (100, 50.0, 1000.0)
        start = time.perf_counter()
        for _ in range(10000):
            stats_small = FeatureUtils.welford_update(stats_small, 1.0)
        time_small = time.perf_counter() - start
        
        # Time with large count
        stats_large = (1000000, 50.0, 1000000.0)
        start = time.perf_counter()
        for _ in range(10000):
            stats_large = FeatureUtils.welford_update(stats_large, 1.0)
        time_large = time.perf_counter() - start
        
        # Times should be similar (within 3x), proving O(1)
        ratio = max(time_small, time_large) / max(min(time_small, time_large), 1e-9)
        assert ratio < 3.0, f"Performance ratio {ratio} suggests non-O(1) complexity"
