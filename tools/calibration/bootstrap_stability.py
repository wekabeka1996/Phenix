from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from statistics import mean


def bootstrap_expectancy_ci(
    values: list[float],
    *,
    draws: int = 1000,
    seed: int = 7,
    confidence: float = 0.95,
) -> dict[str, float]:
    if not values:
        return {
            "expectancy": 0.0,
            "lower": 0.0,
            "upper": 0.0,
            "width": 0.0,
        }
    rng = random.Random(seed)
    means: list[float] = []
    n = len(values)
    for _ in range(max(1, draws)):
        sample = [values[rng.randrange(0, n)] for _ in range(n)]
        means.append(mean(sample))
    means.sort()
    expectancy = mean(values)
    alpha = (1.0 - confidence) / 2.0
    lower_idx = min(len(means) - 1, max(0, int(alpha * len(means))))
    upper_idx = min(len(means) - 1, max(0, int((1.0 - alpha) * len(means)) - 1))
    lower = means[lower_idx]
    upper = means[upper_idx]
    return {
        "expectancy": expectancy,
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
    }


def stability_verdict(ci: dict[str, float]) -> dict[str, object]:
    expectancy = abs(float(ci.get("expectancy", 0.0)))
    width = float(ci.get("width", 0.0))
    lower = float(ci.get("lower", 0.0))
    stable = lower > 0 and (width <= (2.0 * expectancy if expectancy > 0 else 0.0))
    return {
        **ci,
        "stable": stable,
    }


def _load_values_from_csv(path: Path, column: str) -> list[float]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        values: list[float] = []
        for row in reader:
            raw = row.get(column)
            if raw in (None, "", "nan", "NaN"):
                continue
            values.append(float(raw))
        return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--column", default="net_pnl_roi_pct")
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    values = _load_values_from_csv(Path(args.csv), args.column)
    verdict = stability_verdict(
        bootstrap_expectancy_ci(values, draws=args.draws, seed=args.seed)
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
