"""Offline-only P13 threshold sensitivity diagnostics over packet observations."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .scenario_corpus import HORIZONS, PacketObservation, classify_scenario_with_thresholds


CONFIGS = {
    "p12_baseline": (1.0, 0.25),
    "directional_lower": (0.75, 0.25),
    "directional_higher": (1.25, 0.25),
    "volatility_lower": (1.0, 0.20),
    "volatility_higher": (1.0, 0.30),
}


def spread_pairs(observations: list[PacketObservation], window_count: int) -> list[tuple[PacketObservation, PacketObservation]]:
    count = min(window_count, len(observations) // 2)
    if count < 1:
        return []
    width = len(observations) / count
    return [
        (observations[int(index * width)], observations[min(len(observations) - 1, int((index + 1) * width) - 1)])
        for index in range(count)
    ]


def run_threshold_sensitivity(
    observations: Iterable[PacketObservation],
    *,
    window_count: int,
    symbols: Iterable[str] = ("BTCUSDT", "ETHUSDT"),
) -> dict[str, Any]:
    """Compare bounded threshold variants without mutating reviews or production rules."""

    rows = list(observations)
    symbol_list = tuple(symbols)
    pairs = spread_pairs(rows, window_count)
    if not pairs:
        raise ValueError("at least two observations are required")
    distributions: dict[str, dict[str, int]] = {}
    for name, (directional_scale, volatility_threshold) in CONFIGS.items():
        counts: Counter[str] = Counter()
        for before, after in pairs:
            for symbol in symbol_list:
                for horizon in HORIZONS:
                    scenario, _ = classify_scenario_with_thresholds(
                        before, after, symbol=symbol, horizon=horizon,
                        directional_scale=directional_scale,
                        volatility_threshold=volatility_threshold,
                    )
                    counts[scenario] += 1
        distributions[name] = dict(sorted(counts.items()))
    baseline = distributions["p12_baseline"]
    continuation = baseline.get("continuation", 0)
    expansion = baseline.get("volatility_expansion", 0) + baseline.get("volatility_compression", 0)
    lower_directional = distributions["directional_lower"].get("continuation", 0)
    higher_directional = distributions["directional_higher"].get("continuation", 0)
    lower_volatility = sum(distributions["volatility_lower"].get(key, 0) for key in ("volatility_expansion", "volatility_compression"))
    higher_volatility = sum(distributions["volatility_higher"].get(key, 0) for key in ("volatility_expansion", "volatility_compression"))
    directional_finding = (
        "current_threshold_may_be_insensitive" if lower_directional > continuation
        else "current_threshold_may_be_sensitive" if higher_directional < continuation
        else "inconclusive"
    )
    volatility_finding = (
        "current_threshold_may_be_insensitive" if lower_volatility > expansion
        else "current_threshold_may_be_sensitive" if higher_volatility < expansion
        else "inconclusive"
    )
    return {
        "schema_version": "threshold-sensitivity/p13",
        "diagnostic_only": True,
        "packet_count": len(rows),
        "window_count": len(pairs),
        "classification_count_per_config": len(pairs) * len(symbol_list) * len(HORIZONS),
        "configs": {
            name: {"directional_scale": values[0], "volatility_threshold": values[1]}
            for name, values in CONFIGS.items()
        },
        "distributions": distributions,
        "directional_finding": directional_finding,
        "volatility_finding": volatility_finding,
        "production_heuristics_changed": False,
        "existing_reviews_rewritten": False,
    }


__all__ = ["CONFIGS", "run_threshold_sensitivity", "spread_pairs"]
