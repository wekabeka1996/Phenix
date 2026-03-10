"""File discovery and column mapping for parquet pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

# Default rename: parquet column name -> canonical name.
# Tool layer handles the mapping; domain code always works with canonical names.
DEFAULT_RENAME: Dict[str, str] = {
    "open_time": "timestamp",
}


def discover_files(
    data_dir: Path,
    symbol: str,
    tf: str,
    *,
    months: Optional[List[str]] = None,
) -> List[Path]:
    """Find parquet files for symbol/TF.  Prefers *_enriched over raw.

        Search order matches the historical replay file layout:
      1) data_dir / symbol / tf
      2) data_dir / symbol / klines / tf

    Args:
        data_dir: Root data directory (e.g. ``data/processed``).
        symbol:   Trading pair (e.g. ``BTCUSDT``).
        tf:       Timeframe directory name (e.g. ``5m``).
        months:   Optional month filter, e.g. ``["2024-01", "2024-02"]``.

    Returns:
        Sorted list of Path objects (by month key).

    Raises:
        FileNotFoundError: If no matching files found.
    """
    candidates = [
        data_dir / symbol / tf,
        data_dir / symbol / "klines" / tf,
    ]

    for base in candidates:
        if not base.exists():
            continue

        all_files = sorted(base.glob("*.parquet"))
        month_to_file: dict[str, Path] = {}

        # Pass 1: enriched files win
        for f in all_files:
            if f.stem.endswith("_enriched"):
                month_to_file[f.stem[: -len("_enriched")]] = f
        # Pass 2: raw files fill gaps
        for f in all_files:
            if not f.stem.endswith("_enriched"):
                month_to_file.setdefault(f.stem, f)

        if months:
            month_to_file = {k: v for k,
                             v in month_to_file.items() if k in months}

        selected = [month_to_file[k] for k in sorted(month_to_file)]
        if selected:
            return selected

    raise FileNotFoundError(
        f"No parquet files for {symbol}/{tf} in {data_dir}"
    )


def parse_tf_minutes(tf: str) -> int:
    """Parse timeframe string to minutes.  '5m' -> 5, '1h' -> 60, '1d' -> 1440."""
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 1440
    raise ValueError(f"Cannot parse timeframe: {tf!r}")
