#!/usr/bin/env python3
"""
Build Monthly Parquet Files for Backtesting
============================================

Pipeline (one symbol at a time to avoid memory overload):
  1. Scan data/ for Binance ZIP files (SYMBOL-TYPE-YYYY-MM.zip)
  2. Convert each (symbol, data_type) group → raw Parquets via DataConverter
  3. Delete ZIPs after successful conversion
  4. Enrich klines with aggTrades + bookTicker → YYYY-MM_enriched.parquet
  5. Delete raw type parquets (aggTrades, bookTicker, fundingRate, raw klines if enriched exists)
  6. Report per-symbol month coverage and gaps
  7. Skip (symbol, month) pairs where klines are missing

Final output: data/processed/{SYMBOL}/klines/5m/YYYY-MM_enriched.parquet
              data/processed/{SYMBOL}/klines/5m/YYYY-MM.parquet  (if no aggTrades)

Usage:
    python scripts/build_monthly_parquet.py
    python scripts/build_monthly_parquet.py --dry-run
    python scripts/build_monthly_parquet.py --symbols BTCUSDT ETHUSDT
    python scripts/build_monthly_parquet.py --no-delete-zips --no-delete-raw
"""

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    from tqdm import tqdm
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm

from backtest_engine.data_processing.data_converter import DataConverter
from backtest_engine.data_processing.enricher import enrich_symbol_timeframe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOG = logging.getLogger("BuildMonthlyParquet")

KLINES_TF = "5m"

# Pattern: SYMBOL-TYPEORTF-YYYY-MM.zip
_ZIP_RE = re.compile(r"^([A-Z0-9]+)-([A-Za-z0-9]+)-(\d{4}-\d{2})\.zip$")
_KNOWN_NON_KLINES = {"aggTrades", "bookTicker", "fundingRate", "trades"}
_TF_RE = re.compile(r"^\d+[mhdwM]$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_zip(name: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
    """
    Parse a Binance ZIP filename.
    Returns (symbol, data_type, month, timeframe_or_None) or None.
    """
    m = _ZIP_RE.match(name)
    if not m:
        return None
    symbol, tok, month = m.group(1), m.group(2), m.group(3)

    if tok in _KNOWN_NON_KLINES:
        return symbol, tok, month, None
    if _TF_RE.match(tok):
        return symbol, "klines", month, tok
    return None  # unknown token → skip


def scan_data_dir(
    data_dir: Path,
) -> Dict[str, Dict[str, Dict[str, Path]]]:
    """
    Scan flat data_dir for ZIP files.

    Returns:
        {symbol: {data_type_key: {month: zip_path}}}
        data_type_key: "klines_5m" | "aggTrades" | "bookTicker" | "fundingRate"
    """
    result: Dict[str, Dict[str, Dict[str, Path]]] = defaultdict(
        lambda: defaultdict(dict)
    )

    for zf in sorted(data_dir.glob("*.zip")):
        parsed = parse_zip(zf.name)
        if parsed is None:
            LOG.debug(f"Skipping unrecognized ZIP: {zf.name}")
            continue
        symbol, dtype, month, tf = parsed

        # We only process the target timeframe for klines
        if dtype == "klines" and tf != KLINES_TF:
            LOG.debug(f"Skipping non-{KLINES_TF} klines: {zf.name}")
            continue

        key = f"klines_{tf}" if dtype == "klines" else dtype
        result[symbol][key][month] = zf

    return dict(result)


def month_from_zip(zip_path: Path) -> Optional[str]:
    """Extract YYYY-MM from ZIP filename."""
    m = re.search(r"(\d{4}-\d{2})$", zip_path.stem)
    return m.group(1) if m else None


def expected_raw_parquet(
    processed_dir: Path,
    symbol: str,
    dtype: str,
    month: str,
    timeframe: Optional[str] = None,
) -> Path:
    """Return expected output parquet path for a raw (non-enriched) file."""
    if dtype == "klines" and timeframe:
        return processed_dir / symbol / "klines" / timeframe / f"{month}.parquet"
    return processed_dir / symbol / dtype / f"{month}.parquet"


def next_month(m: str) -> str:
    """Increment YYYY-MM by one month."""
    y, mo = int(m[:4]), int(m[5:7])
    mo += 1
    if mo > 12:
        mo, y = 1, y + 1
    return f"{y:04d}-{mo:02d}"


# ---------------------------------------------------------------------------
# Per-type conversion
# ---------------------------------------------------------------------------

def convert_type(
    *,
    symbol: str,
    dtype: str,
    timeframe: Optional[str],
    data_dir: Path,
    processed_dir: Path,
    zips_for_type: Dict[str, Path],
    delete_zips: bool,
    dry_run: bool,
) -> Dict[str, bool]:
    """
    Convert all ZIPs for one (symbol, dtype) to raw parquets.

    Returns {month: success_bool}
    """
    results: Dict[str, bool] = {}

    if not zips_for_type:
        return results

    converter = DataConverter()

    # We pass the flat data_dir as source; DataConverter will glob for matching files.
    # To process one ZIP at a time, we filter by calling convert() and checking output.
    # DataConverter.convert() iterates all matching ZIPs in source_dir.
    # Since all symbol ZIPs are in data_dir flat, we just call once per type.
    #
    # After the call, we verify which months appeared in output and delete their ZIPs.

    # Snapshot output dir BEFORE conversion to find newly created files
    out_dir: Path
    if dtype == "klines" and timeframe:
        out_dir = processed_dir / symbol / "klines" / timeframe
    else:
        out_dir = processed_dir / symbol / dtype

    existing_before: Set[str] = set()
    if out_dir.exists():
        existing_before = {f.name for f in out_dir.glob("*.parquet")}

    if dry_run:
        LOG.info(f"  [DRY-RUN] Would convert {len(zips_for_type)} {dtype} ZIPs for {symbol}")
        for month in sorted(zips_for_type):
            results[month] = False  # dry run: not actually done
        return results

    LOG.info(f"  Converting {len(zips_for_type)} {dtype} ZIPs for {symbol}...")

    try:
        converter.convert(
            symbol=symbol,
            data_type=dtype,
            source_dir=str(data_dir),
            target_dir=str(processed_dir),
            timeframe=timeframe,
        )
    except Exception as exc:
        LOG.error(f"  ❌ DataConverter.convert() raised: {exc}")

    # Check which months were successfully written
    for month, zip_path in sorted(zips_for_type.items()):
        out_file = expected_raw_parquet(processed_dir, symbol, dtype, month, timeframe)
        success = out_file.exists()
        results[month] = success

        if success:
            LOG.info(f"    ✅ {dtype} {month} → {out_file.relative_to(processed_dir)}")
            if delete_zips:
                zip_path.unlink()
                LOG.info(f"    🗑  Deleted: {zip_path.name}")
        else:
            LOG.warning(f"    ⚠  Output missing for {dtype} {month}: {out_file}")

    return results


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------

def report_coverage(processed_dir: Path, symbols: List[str]) -> None:
    LOG.info("\n" + "=" * 60)
    LOG.info("COVERAGE REPORT")
    LOG.info("=" * 60)

    for symbol in sorted(symbols):
        klines_dir = processed_dir / symbol / "klines" / KLINES_TF
        if not klines_dir.exists():
            LOG.warning(f"  {symbol}: no klines directory")
            continue

        all_parquets = sorted(klines_dir.glob("*.parquet"))
        enriched = [f for f in all_parquets if f.name.endswith("_enriched.parquet")]
        raw_only = [f for f in all_parquets if "_enriched" not in f.name]

        months: List[str] = []
        for f in all_parquets:
            stem = f.stem.replace("_enriched", "")
            if stem not in months:
                months.append(stem)
        months = sorted(set(months))

        if not months:
            LOG.warning(f"  {symbol}: no monthly parquets!")
            continue

        # Detect gaps
        gaps: List[str] = []
        for i in range(len(months) - 1):
            exp = next_month(months[i])
            if months[i + 1] != exp:
                gaps.append(f"{months[i]} → {months[i + 1]}")

        LOG.info(
            f"  {symbol:20s}: {len(months)} months  "
            f"[{months[0]} .. {months[-1]}]  "
            f"enriched={len(enriched)}  raw-only={len(raw_only)}"
        )
        if gaps:
            LOG.warning(f"  {'':20s}  GAPS DETECTED: {gaps}")
        else:
            LOG.info(f"  {'':20s}  No gaps")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build monthly Parquet files for backtesting (ZIP → Parquet + enrich)"
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="Flat directory containing Binance ZIP files (default: data/)"
    )
    parser.add_argument(
        "--processed-dir", default="data/processed",
        help="Output directory for processed Parquets (default: data/processed/)"
    )
    parser.add_argument(
        "--symbols", nargs="*",
        help="Only process these symbols (default: all found)"
    )
    parser.add_argument(
        "--no-delete-zips", action="store_true",
        help="Keep original ZIP files after successful conversion"
    )
    parser.add_argument(
        "--no-delete-raw", action="store_true",
        help="Keep raw type parquets after enrichment"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without executing"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    processed_dir = Path(args.processed_dir)
    if not data_dir.is_absolute():
        data_dir = project_root / data_dir
    if not processed_dir.is_absolute():
        processed_dir = project_root / processed_dir

    if not data_dir.exists():
        LOG.error(f"Data directory not found: {data_dir}")
        sys.exit(1)

    processed_dir.mkdir(parents=True, exist_ok=True)
    delete_zips = not args.no_delete_zips
    delete_raw = not args.no_delete_raw
    dry_run = args.dry_run

    if dry_run:
        LOG.info("DRY-RUN mode: no files will be written or deleted")

    # ── Step 1: Scan ──────────────────────────────────────────────────────
    LOG.info(f"Scanning ZIP files in: {data_dir}")
    zip_map = scan_data_dir(data_dir)

    if not zip_map:
        LOG.warning("No ZIP files found – nothing to do.")
        sys.exit(0)

    symbols = sorted(zip_map.keys())
    if args.symbols:
        symbols = [s for s in symbols if s in args.symbols]
        unknown = set(args.symbols) - set(zip_map.keys())
        if unknown:
            LOG.warning(f"Requested symbols not found in data/: {sorted(unknown)}")

    LOG.info(f"Symbols found: {symbols}")

    total_converted = 0
    total_enriched = 0
    total_deleted_zips = 0
    total_deleted_raw = 0

    # ── Step 2: Process one symbol at a time ──────────────────────────────
    for symbol in symbols:
        LOG.info(f"\n{'='*60}")
        LOG.info(f"SYMBOL: {symbol}")
        LOG.info(f"{'='*60}")

        sym = zip_map[symbol]
        klines_key = f"klines_{KLINES_TF}"

        klines_months = set(sym.get(klines_key, {}).keys())
        if not klines_months:
            LOG.warning(f"  No {KLINES_TF} klines ZIPs found for {symbol} – skipping entire symbol.")
            continue

        LOG.info(f"  Klines months: {sorted(klines_months)}")

        # -- Convert klines ------------------------------------------------
        klines_ok = convert_type(
            symbol=symbol,
            dtype="klines",
            timeframe=KLINES_TF,
            data_dir=data_dir,
            processed_dir=processed_dir,
            zips_for_type=sym.get(klines_key, {}),
            delete_zips=delete_zips,
            dry_run=dry_run,
        )
        total_converted += sum(1 for ok in klines_ok.values() if ok)
        if not dry_run and delete_zips:
            total_deleted_zips += sum(1 for ok in klines_ok.values() if ok)

        # -- Convert aggTrades ---------------------------------------------
        at_ok = convert_type(
            symbol=symbol,
            dtype="aggTrades",
            timeframe=None,
            data_dir=data_dir,
            processed_dir=processed_dir,
            zips_for_type=sym.get("aggTrades", {}),
            delete_zips=delete_zips,
            dry_run=dry_run,
        )
        total_converted += sum(1 for ok in at_ok.values() if ok)
        if not dry_run and delete_zips:
            total_deleted_zips += sum(1 for ok in at_ok.values() if ok)

        # -- Convert bookTicker --------------------------------------------
        bt_ok = convert_type(
            symbol=symbol,
            dtype="bookTicker",
            timeframe=None,
            data_dir=data_dir,
            processed_dir=processed_dir,
            zips_for_type=sym.get("bookTicker", {}),
            delete_zips=delete_zips,
            dry_run=dry_run,
        )
        total_converted += sum(1 for ok in bt_ok.values() if ok)
        if not dry_run and delete_zips:
            total_deleted_zips += sum(1 for ok in bt_ok.values() if ok)

        # -- Convert fundingRate -------------------------------------------
        fr_ok = convert_type(
            symbol=symbol,
            dtype="fundingRate",
            timeframe=None,
            data_dir=data_dir,
            processed_dir=processed_dir,
            zips_for_type=sym.get("fundingRate", {}),
            delete_zips=delete_zips,
            dry_run=dry_run,
        )
        total_converted += sum(1 for ok in fr_ok.values() if ok)
        if not dry_run and delete_zips:
            total_deleted_zips += sum(1 for ok in fr_ok.values() if ok)

        if dry_run:
            continue

        # -- Enrich klines with aggTrades + bookTicker ---------------------
        LOG.info(f"\n  Enriching {symbol} ({KLINES_TF}) ...")
        enrich_results = []
        try:
            enrich_results = enrich_symbol_timeframe(
                processed_dir=processed_dir,
                raw_dir=processed_dir,
                symbol=symbol,
                timeframe=KLINES_TF,
            )
            total_enriched += len(enrich_results)
            if enrich_results:
                enriched_months = sorted(r.month for r in enrich_results)
                LOG.info(f"  ✅ Enriched months: {enriched_months}")
            else:
                LOG.info(f"  ℹ  No months could be enriched (no aggTrades overlap?)")
        except Exception as exc:
            LOG.error(f"  ❌ Enrichment failed: {exc}")

        # -- Cleanup raw type parquets -------------------------------------
        if delete_raw:
            LOG.info(f"  Cleaning up raw type parquets for {symbol}...")

            for dtype_dir_name in ("aggTrades", "bookTicker", "fundingRate"):
                dtype_dir = processed_dir / symbol / dtype_dir_name
                if dtype_dir.exists():
                    removed = 0
                    for f in list(dtype_dir.glob("*.parquet")):
                        f.unlink()
                        removed += 1
                        total_deleted_raw += 1
                    try:
                        dtype_dir.rmdir()
                    except OSError:
                        pass  # Not empty – leave it
                    if removed:
                        LOG.info(f"    🗑  {dtype_dir_name}: deleted {removed} parquets")

            # Delete raw klines only when an enriched version exists
            klines_dir = processed_dir / symbol / "klines" / KLINES_TF
            if klines_dir.exists():
                enriched_months_set = {
                    f.stem[: -len("_enriched")]
                    for f in klines_dir.glob("*_enriched.parquet")
                }
                removed = 0
                for f in list(klines_dir.glob("*.parquet")):
                    if "_enriched" in f.name:
                        continue  # keep enriched
                    if f.stem in enriched_months_set:
                        f.unlink()
                        removed += 1
                        total_deleted_raw += 1
                    else:
                        LOG.info(f"    ℹ  Kept raw klines (no enriched exists): {f.name}")
                if removed:
                    LOG.info(f"    🗑  Raw klines: deleted {removed} parquets")

    # ── Step 3: Coverage report ───────────────────────────────────────────
    if not dry_run:
        report_coverage(processed_dir, symbols)

    # ── Summary ───────────────────────────────────────────────────────────
    LOG.info("\n" + "=" * 60)
    LOG.info("SUMMARY")
    LOG.info("=" * 60)
    LOG.info(f"  Symbols processed:    {len(symbols)}")
    LOG.info(f"  Parquets created:     {total_converted}")
    LOG.info(f"  Enriched months:      {total_enriched}")
    LOG.info(f"  ZIPs deleted:         {total_deleted_zips}")
    LOG.info(f"  Raw parquets deleted: {total_deleted_raw}")
    LOG.info("=" * 60)


if __name__ == "__main__":
    main()
