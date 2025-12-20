"""
Feature Engineering Utilities - O(1) Statistical Algorithms

This module provides stateless, high-performance math helpers for feature engineering.
All algorithms are O(1) per update to avoid O(N) loops in hot paths.

Key Components:
- Welford's Algorithm: Online mean/variance computation
- Safe config accessor: Nested dict/object navigation
- Z-score computation: With optional clipping
- Linear slope: For order book analysis (stub)

Usage:
    from apps.reference.domains.feature_engineering.utils import FeatureUtils
    
    # Welford's online stats
    stats = (0, 0.0, 0.0)  # (count, mean, m2)
    stats = FeatureUtils.welford_update(stats, 10.5)
    stats = FeatureUtils.welford_update(stats, 11.2)
    z = FeatureUtils.compute_z_score(12.0, stats)

Author: Aurora/Phenix Runtime
Version: 1.0.0
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple, Union


# Type alias for Welford aggregate: (count, mean, m2)
WelfordAggregate = Tuple[int, float, float]


class FeatureUtils:
    """
    Stateless utility class for feature engineering calculations.
    
    All methods are static - no instance state required.
    Designed for O(1) complexity per operation.
    """
    
    # ─────────────────────────────────────────────────────────────────────────
    # Config Accessor
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def get_config(config: Any, path: str, default: Any = None) -> Any:
        """
        Safe nested dictionary/object accessor.
        
        Supports both dict-style and attribute-style access.
        Path segments are separated by dots.
        
        Args:
            config: Root config object (dict, object, or nested structure)
            path: Dot-separated path (e.g., "features.ema.period_short")
            default: Value to return if path not found
            
        Returns:
            Value at path, or default if not found
            
        Examples:
            >>> cfg = {"features": {"ema": {"period_short": 5}}}
            >>> FeatureUtils.get_config(cfg, "features.ema.period_short", 10)
            5
            >>> FeatureUtils.get_config(cfg, "features.ema.missing", 10)
            10
        """
        if config is None:
            return default
            
        current = config
        segments = path.split(".")
        
        for segment in segments:
            if current is None:
                return default
                
            # Try dict-style access first
            if isinstance(current, dict):
                current = current.get(segment)
            # Then try attribute access
            elif hasattr(current, segment):
                current = getattr(current, segment)
            # Try __getitem__ for dict-like objects
            elif hasattr(current, "__getitem__"):
                try:
                    current = current[segment]
                except (KeyError, TypeError, IndexError):
                    return default
            else:
                return default
                
        return current if current is not None else default
    
    # ─────────────────────────────────────────────────────────────────────────
    # Welford's Online Algorithm
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def welford_update(
        existing_aggregate: WelfordAggregate,
        new_value: float
    ) -> WelfordAggregate:
        """
        Update running statistics using Welford's online algorithm.
        
        This is an O(1) algorithm for computing mean and variance incrementally,
        without storing all values. Numerically stable for large datasets.
        
        Algorithm:
            count += 1
            delta = new_value - mean
            mean += delta / count
            delta2 = new_value - mean
            m2 += delta * delta2
        
        Args:
            existing_aggregate: Tuple of (count, mean, m2) where:
                - count: Number of samples seen
                - mean: Current running mean
                - m2: Sum of squared differences from the mean
            new_value: New value to incorporate
            
        Returns:
            Updated (count, mean, m2) tuple
            
        Examples:
            >>> stats = (0, 0.0, 0.0)
            >>> stats = FeatureUtils.welford_update(stats, 10.0)
            >>> stats
            (1, 10.0, 0.0)
            >>> stats = FeatureUtils.welford_update(stats, 20.0)
            >>> stats[0], stats[1]  # count=2, mean=15.0
            (2, 15.0)
            
        References:
            Welford, B.P. (1962). "Note on a method for calculating 
            corrected sums of squares and products"
        """
        count, mean, m2 = existing_aggregate
        
        # Handle NaN/Inf input
        if not math.isfinite(new_value):
            return existing_aggregate
        
        count += 1
        delta = new_value - mean
        mean += delta / count
        delta2 = new_value - mean
        m2 += delta * delta2
        
        return (count, mean, m2)
    
    @staticmethod
    def welford_finalize(aggregate: WelfordAggregate) -> Tuple[float, float, float]:
        """
        Extract final statistics from Welford aggregate.
        
        Args:
            aggregate: Tuple of (count, mean, m2)
            
        Returns:
            Tuple of (mean, variance, sample_stddev)
            Returns (0.0, 0.0, 0.0) if count < 2
        """
        count, mean, m2 = aggregate
        
        if count < 2:
            return (mean if count == 1 else 0.0, 0.0, 0.0)
        
        variance = m2 / count  # Population variance
        sample_variance = m2 / (count - 1)  # Sample variance
        stddev = math.sqrt(sample_variance) if sample_variance > 0 else 0.0
        
        return (mean, variance, stddev)
    
    @staticmethod
    def welford_remove(
        count: int,
        mean: float,
        m2: float,
        x: float,
        eps: float = 1e-9,
    ) -> tuple[int, float, float]:
        """
        Remove a value `x` from the aggregate. Inverse of welford_update.
        
        Must handle count <= 1 and m2 drifting below zero due to
        floating-point errors in long-running sliding windows.
        
        Args:
            count: Current sample count
            mean: Current running mean
            m2: Current sum of squared differences from the mean
            x: Value to remove (must have been previously added)
            eps: Epsilon for float comparisons (default 1e-9)
            
        Returns:
            Tuple of (new_count, new_mean, new_m2)
            
        Examples:
            >>> # Start with [10, 20], mean=15, m2=50
            >>> c, m, m2 = FeatureUtils.welford_remove(2, 15.0, 50.0, 20.0)
            >>> c, m  # After removing 20
            (1, 10.0)
            
        References:
            Inverse of Welford (1962) online algorithm
        """
        # Handle edge cases
        if count <= 1:
            return (0, 0.0, 0.0)
        
        # Handle NaN/Inf input
        if not math.isfinite(x):
            return (count, mean, m2)
        
        # New count after removal
        n_new = count - 1
        
        # Formula: new_mean = (n * old_mean - x) / (n - 1)
        mean_new = (count * mean - x) / n_new
        
        # Formula: new_m2 = old_m2 - (x - old_mean) * (x - new_mean)
        delta = x - mean
        delta2 = x - mean_new
        m2_new = m2 - delta * delta2
        
        # Robustness guard: m2 can drift negative due to float errors
        if m2_new < eps or n_new < 1:
            m2_new = 0.0
            
        return (n_new, mean_new, m2_new)
    
    @staticmethod
    def welford_remove_tuple(
        existing_aggregate: WelfordAggregate,
        old_value: float,
        eps: float = 1e-9,
    ) -> WelfordAggregate:
        """
        Remove a value from Welford aggregate (tuple interface).
        
        Convenience wrapper around welford_remove for tuple-based API.
        
        Args:
            existing_aggregate: Tuple of (count, mean, m2)
            old_value: Value to remove
            eps: Epsilon for float comparisons
            
        Returns:
            Updated (count, mean, m2) tuple
        """
        count, mean, m2 = existing_aggregate
        return FeatureUtils.welford_remove(count, mean, m2, old_value, eps)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Z-Score Computation
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def compute_z_score(
        value: float,
        stats: WelfordAggregate,
        clip_sigma: Optional[float] = None
    ) -> float:
        """
        Compute Z-score from Welford aggregate statistics.
        
        Z-score = (value - mean) / stddev
        
        Args:
            value: Value to compute Z-score for
            stats: Welford aggregate (count, mean, m2)
            clip_sigma: If provided, clamp result to [-clip_sigma, +clip_sigma]
            
        Returns:
            Z-score (float). Returns 0.0 if:
            - count < 2 (insufficient data)
            - stddev ≈ 0 (zero variance)
            - value is NaN/Inf
            
        Examples:
            >>> stats = (100, 50.0, 2500.0)  # mean=50, variance=25, stddev=5
            >>> FeatureUtils.compute_z_score(55.0, stats)
            1.0
            >>> FeatureUtils.compute_z_score(45.0, stats)
            -1.0
            >>> FeatureUtils.compute_z_score(70.0, stats, clip_sigma=3.0)
            3.0  # Clipped from 4.0
        """
        # Handle NaN/Inf input
        if not math.isfinite(value):
            return 0.0
        
        count, mean, m2 = stats
        
        # Need at least 2 samples for meaningful stddev
        if count < 2:
            return 0.0
        
        # Compute sample standard deviation
        variance = m2 / (count - 1)
        if variance <= 0:
            return 0.0
        
        stddev = math.sqrt(variance)
        
        # Avoid division by near-zero
        if stddev < 1e-10:
            return 0.0
        
        z_score = (value - mean) / stddev
        
        # Apply clipping if requested
        if clip_sigma is not None and clip_sigma > 0:
            z_score = max(-clip_sigma, min(clip_sigma, z_score))
        
        return z_score
    
    # ─────────────────────────────────────────────────────────────────────────
    # Linear Slope (Order Book Analysis)
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def compute_linear_slope(
        y_values: List[float],
        x_step: float = 1.0
    ) -> float:
        """
        Compute linear regression slope for a series of y-values.
        
        Assumes evenly-spaced x-values: [0, x_step, 2*x_step, ...]
        Uses closed-form OLS formula (no iteration).
        
        Args:
            y_values: List of y-values (e.g., order book depths)
            x_step: Spacing between x-values (default: 1.0)
            
        Returns:
            Slope (float). Returns 0.0 if:
            - len(y_values) < 2
            - All y-values are identical
            
        Formula:
            slope = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)²)
            
        For evenly spaced x: [0, 1, 2, ..., n-1]:
            x̄ = (n-1)/2
            Σ(x - x̄)² = n(n²-1)/12
        """
        n = len(y_values)
        
        if n < 2:
            return 0.0
        
        # For evenly spaced x: [0, 1, 2, ..., n-1]
        # x_mean = (n - 1) / 2
        # sum_xx = n * (n^2 - 1) / 12
        x_mean = (n - 1) / 2.0
        sum_xx = n * (n * n - 1) / 12.0
        
        if sum_xx == 0:
            return 0.0
        
        # Compute y_mean and sum_xy in single pass
        y_sum = 0.0
        sum_xy = 0.0
        
        for i, y in enumerate(y_values):
            if not math.isfinite(y):
                return 0.0
            y_sum += y
            sum_xy += (i - x_mean) * y
        
        y_mean = y_sum / n
        
        # Adjust sum_xy for y_mean
        # sum_xy = Σ((x - x̄) * y) - ȳ * Σ(x - x̄)
        # But Σ(x - x̄) = 0 for symmetric x, so no adjustment needed
        
        # Actually, we need: Σ((x - x̄)(y - ȳ)) = Σ((x - x̄) * y) - ȳ * Σ(x - x̄)
        # Since Σ(x - x̄) = 0, this simplifies to Σ((x - x̄) * y)
        # Which is what we computed
        
        slope = sum_xy / sum_xx
        
        # Scale by x_step
        return slope / x_step if x_step != 0 else 0.0
    
    # ─────────────────────────────────────────────────────────────────────────
    # Safe Math Operations
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def safe_divide(
        numerator: float,
        denominator: float,
        default: float = 0.0
    ) -> float:
        """
        Safe division with explicit zero/invalid handling.
        
        Args:
            numerator: Dividend
            denominator: Divisor
            default: Value to return if division is undefined
            
        Returns:
            numerator / denominator, or default if:
            - denominator is zero or near-zero
            - Either input is NaN/Inf
        """
        if not math.isfinite(numerator) or not math.isfinite(denominator):
            return default
        
        if abs(denominator) < 1e-10:
            return default
        
        result = numerator / denominator
        return result if math.isfinite(result) else default
    
    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        """
        Clamp a value to a range.
        
        Args:
            value: Value to clamp
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            
        Returns:
            Clamped value in [min_val, max_val]
        """
        if not math.isfinite(value):
            return (min_val + max_val) / 2
        return max(min_val, min(max_val, value))
    
    @staticmethod
    def normalize(
        value: float,
        min_val: float,
        max_val: float,
        target_min: float = 0.0,
        target_max: float = 1.0
    ) -> float:
        """
        Normalize a value from one range to another.
        
        Args:
            value: Value to normalize
            min_val: Source range minimum
            max_val: Source range maximum
            target_min: Target range minimum (default: 0.0)
            target_max: Target range maximum (default: 1.0)
            
        Returns:
            Normalized value in [target_min, target_max]
            Returns midpoint if source range is zero
        """
        if max_val == min_val:
            return (target_min + target_max) / 2
        
        if not math.isfinite(value):
            return (target_min + target_max) / 2
        
        # Clamp to source range first
        value = max(min_val, min(max_val, value))
        
        # Linear interpolation
        ratio = (value - min_val) / (max_val - min_val)
        return target_min + ratio * (target_max - target_min)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience functions
# ─────────────────────────────────────────────────────────────────────────────

def welford_update(aggregate: WelfordAggregate, value: float) -> WelfordAggregate:
    """Module-level alias for FeatureUtils.welford_update."""
    return FeatureUtils.welford_update(aggregate, value)


def welford_remove(aggregate: WelfordAggregate, value: float) -> WelfordAggregate:
    """Module-level alias for FeatureUtils.welford_remove_tuple."""
    return FeatureUtils.welford_remove_tuple(aggregate, value)


def compute_z_score(
    value: float,
    stats: WelfordAggregate,
    clip_sigma: Optional[float] = None
) -> float:
    """Module-level alias for FeatureUtils.compute_z_score."""
    return FeatureUtils.compute_z_score(value, stats, clip_sigma)


def get_config(config: Any, path: str, default: Any = None) -> Any:
    """Module-level alias for FeatureUtils.get_config."""
    return FeatureUtils.get_config(config, path, default)


# ─────────────────────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "FeatureUtils",
    "WelfordAggregate",
    "welford_update",
    "welford_remove",
    "compute_z_score",
    "get_config",
]
