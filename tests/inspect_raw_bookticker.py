"""Inspect raw bookTicker parquet schema and sample row."""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl


def _find_bookticker_file(base_dir: Path, symbol: str) -> Path:
    candidates = [
        base_dir / "data" / "processed" / symbol / "bookTicker",
        base_dir / "data" / "raw" / symbol / "bookTicker",
        base_dir / "data" / "processed" / symbol,
        base_dir / "data" / "raw" / symbol,
    ]

    for folder in candidates:
        if not folder.exists():
            continue
        files = sorted(folder.glob("*.parquet"))
        if files:
            return files[0]

    raise FileNotFoundError("No bookTicker parquet found under processed/raw paths")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=".", help="Repo base path")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    symbol = str(args.symbol).upper()

    file_path = _find_bookticker_file(base, symbol)
    df = pl.read_parquet(str(file_path))

    print(f"file={file_path}")
    print(f"columns={df.columns}")
    print("first_row=", df.head(1).to_dicts()[0] if df.height > 0 else None)


if __name__ == "__main__":
    main()
