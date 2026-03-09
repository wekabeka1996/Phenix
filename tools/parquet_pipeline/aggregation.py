"""Aggregation: combine per-trigger z-scores into a single stress_level (0..1).

Supports three methods (from regime.yaml system_stress.aggregation.method):

  weighted_vote   Binary fire per trigger (z > sigma), then weighted sum.
  k_of_n          Count firing triggers / k, clamped to [0, 1].
  max             Max exceedance ratio (z / sigma), clamped to [0, 1].
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import polars as pl

# ── Trigger key -> z-score column + sigma attribute ──────────────────
TRIGGER_MAP: Dict[str, Dict[str, str]] = {
    "atr":    {"z_col": "z_atr",         "sigma": "atr_sigma"},
    "vol":    {"z_col": "z_realized_vol", "sigma": "vol_sigma"},
    "gap":    {"z_col": "z_gap",          "sigma": "gap_sigma"},
    "range":  {"z_col": "z_bar_range",    "sigma": "range_sigma"},
    "volume": {"z_col": "z_volume",       "sigma": "volume_sigma"},
    "spread": {"z_col": "z_spread",       "sigma": "spread_sigma"},
    "depth":  {"z_col": "z_depth_drop",   "sigma": "depth_drop_pct"},
}


def _active_triggers(
    thresholds: Dict[str, float],
    schema_cols: set[str],
) -> List[Tuple[str, str, float]]:
    """Return (trigger_key, z_col, sigma) for triggers that are active.

    A trigger is active when its sigma > 0 AND the z-score column exists
    in the LazyFrame schema.
    """
    result = []
    for key, mapping in TRIGGER_MAP.items():
        sigma = thresholds.get(mapping["sigma"], 0.0)
        if sigma <= 0:
            continue
        if mapping["z_col"] not in schema_cols:
            continue
        result.append((key, mapping["z_col"], sigma))
    return result


def compute_stress_level(
    lf: pl.LazyFrame,
    *,
    method: str,
    weights: Optional[Dict[str, float]] = None,
    thresholds: Dict[str, float],
    k: Optional[int] = None,
) -> pl.LazyFrame:
    """Add ``stress_level`` column (0..1) to LazyFrame.

    Args:
        lf:         LazyFrame with z-score columns.
        method:     ``"weighted_vote"`` | ``"k_of_n"`` | ``"max"``.
        weights:    Trigger weights (required for weighted_vote).
        thresholds: Flat dict of sigma thresholds, e.g.
                    ``{"atr_sigma": 2.0, "vol_sigma": 2.0, ...}``.
        k:          Minimum firing triggers (required for k_of_n).

    Returns:
        LazyFrame with ``stress_level`` appended.
    """
    schema_cols = set(lf.collect_schema().names())
    active = _active_triggers(thresholds, schema_cols)

    if not active:
        return lf.with_columns(pl.lit(0.0).alias("stress_level"))

    if method == "weighted_vote":
        return _weighted_vote(lf, active, weights or {})
    if method == "k_of_n":
        return _k_of_n(lf, active, k or 1)
    if method == "max":
        return _max_ratio(lf, active)
    raise ValueError(f"Unknown aggregation method: {method!r}")


def _weighted_vote(
    lf: pl.LazyFrame,
    active: List[Tuple[str, str, float]],
    weights: Dict[str, float],
) -> pl.LazyFrame:
    fire_exprs: list[pl.Expr] = []
    for key, z_col, sigma in active:
        w = weights.get(key, 0.0)
        if w <= 0:
            continue
        fire_exprs.append(
            pl.when(pl.col(z_col) > sigma)
            .then(pl.lit(w))
            .otherwise(pl.lit(0.0))
        )
    if not fire_exprs:
        return lf.with_columns(pl.lit(0.0).alias("stress_level"))
    return lf.with_columns(
        pl.sum_horizontal(*fire_exprs).alias("stress_level")
    )


def _k_of_n(
    lf: pl.LazyFrame,
    active: List[Tuple[str, str, float]],
    k: int,
) -> pl.LazyFrame:
    fire_exprs: list[pl.Expr] = []
    for _, z_col, sigma in active:
        fire_exprs.append(
            pl.when(pl.col(z_col) > sigma)
            .then(pl.lit(1.0))
            .otherwise(pl.lit(0.0))
        )
    fires = pl.sum_horizontal(*fire_exprs)
    return lf.with_columns(
        (fires / k).clip(0.0, 1.0).alias("stress_level")
    )


def _max_ratio(
    lf: pl.LazyFrame,
    active: List[Tuple[str, str, float]],
) -> pl.LazyFrame:
    ratio_exprs: list[pl.Expr] = []
    for _, z_col, sigma in active:
        ratio_exprs.append(pl.col(z_col) / sigma)
    return lf.with_columns(
        pl.max_horizontal(*ratio_exprs).clip(0.0, 1.0).alias("stress_level")
    )
