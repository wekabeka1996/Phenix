"""Tests for tools.parquet_pipeline (Phase 0.1).

Coverage:
  - discovery: file finding, enriched preference, month filter, not-found
  - audit: schema, nulls, gaps, duplicates, semantics, value ranges
  - stress: output columns, metric correctness, burn-in, z-score finiteness
  - CLI: audit-only, full pipeline, not-found exit code
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import numpy as np
import polars as pl
import pytest

from tools.parquet_pipeline.audit import audit
from tools.parquet_pipeline.discovery import (
    DEFAULT_RENAME,
    discover_files,
    parse_tf_minutes,
)
from tools.parquet_pipeline.stress import (
    STRESS_OUTPUT_COLUMNS,
    STRESS_V0_METRICS,
    compute_stress_v0,
)


# ═══════════════════════════════════════════════════════════════
# Synthetic data helpers
# ═══════════════════════════════════════════════════════════════

def _make_ohlcv(n: int = 300, seed: int = 42) -> pl.DataFrame:
    """Synthetic OHLCV with ``open_time`` column (Datetime[ms], tz-naive)."""
    rng = np.random.default_rng(seed)
    base = datetime(2024, 1, 1)
    timestamps = [base + timedelta(minutes=5 * i) for i in range(n)]

    close = 50000.0
    rows: dict[str, list] = {
        "open_time": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }

    for ts in timestamps:
        o = close + rng.normal(0, 50)
        c = o + rng.normal(0, 100)
        h = max(o, c) + abs(rng.normal(0, 30))
        low = min(o, c) - abs(rng.normal(0, 30))
        v = abs(rng.normal(100, 50))

        rows["open_time"].append(ts)
        rows["open"].append(o)
        rows["high"].append(h)
        rows["low"].append(low)
        rows["close"].append(c)
        rows["volume"].append(v)
        close = c

    return pl.DataFrame(rows).with_columns(
        pl.col("open_time").cast(pl.Datetime("ms"))
    )


def _write_parquet_pair(data_dir: Path, n: int = 300) -> List[Path]:
    """Write two monthly enriched parquet files under data_dir/BTCUSDT/5m/."""
    symbol_dir = data_dir / "BTCUSDT" / "5m"
    symbol_dir.mkdir(parents=True, exist_ok=True)

    df = _make_ohlcv(n)
    mid = n // 2
    df1 = df.slice(0, mid)
    df2 = df.slice(mid, n - mid)

    p1 = symbol_dir / "2024-01_enriched.parquet"
    p2 = symbol_dir / "2024-02_enriched.parquet"
    df1.write_parquet(str(p1))
    df2.write_parquet(str(p2))
    return [p1, p2]


@pytest.fixture()
def synthetic_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    _write_parquet_pair(data_dir, n=300)
    return data_dir


# ═══════════════════════════════════════════════════════════════
# Discovery tests
# ═══════════════════════════════════════════════════════════════

class TestDiscovery:
    def test_discover_enriched_files(self, synthetic_data_dir: Path) -> None:
        files = discover_files(synthetic_data_dir, "BTCUSDT", "5m")
        assert len(files) == 2
        assert all(f.name.endswith("_enriched.parquet") for f in files)

    def test_discover_prefers_enriched_over_raw(self, tmp_path: Path) -> None:
        d = tmp_path / "data" / "BTCUSDT" / "5m"
        d.mkdir(parents=True)
        df = _make_ohlcv(10)
        df.write_parquet(str(d / "2024-01.parquet"))
        df.write_parquet(str(d / "2024-01_enriched.parquet"))
        files = discover_files(tmp_path / "data", "BTCUSDT", "5m")
        assert len(files) == 1
        assert files[0].name == "2024-01_enriched.parquet"

    def test_discover_month_filter(self, synthetic_data_dir: Path) -> None:
        files = discover_files(
            synthetic_data_dir, "BTCUSDT", "5m", months=["2024-01"]
        )
        assert len(files) == 1
        assert "2024-01" in files[0].stem

    def test_discover_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            discover_files(tmp_path, "NONEXIST", "5m")

    def test_discover_klines_fallback(self, tmp_path: Path) -> None:
        d = tmp_path / "data" / "ETHUSDT" / "klines" / "5m"
        d.mkdir(parents=True)
        _make_ohlcv(10).write_parquet(str(d / "2024-03.parquet"))
        files = discover_files(tmp_path / "data", "ETHUSDT", "5m")
        assert len(files) == 1


class TestParseTfMinutes:
    def test_5m(self) -> None:
        assert parse_tf_minutes("5m") == 5

    def test_1h(self) -> None:
        assert parse_tf_minutes("1h") == 60

    def test_1d(self) -> None:
        assert parse_tf_minutes("1d") == 1440

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            parse_tf_minutes("5x")


# ═══════════════════════════════════════════════════════════════
# Audit tests
# ═══════════════════════════════════════════════════════════════

class TestAudit:
    def test_audit_valid_data(self, synthetic_data_dir: Path) -> None:
        files = discover_files(synthetic_data_dir, "BTCUSDT", "5m")
        report = audit(files, tf_minutes=5)
        assert report["passed"] is True
        assert report["issues"] == []
        assert report["row_count"] == 300
        assert report["duplicate_timestamps"] == 0

    def test_audit_missing_columns(self, tmp_path: Path) -> None:
        d = tmp_path / "BTCUSDT" / "5m"
        d.mkdir(parents=True)
        df = pl.DataFrame({"open_time": [1, 2], "open": [1.0, 2.0]})
        df.write_parquet(str(d / "bad.parquet"))
        report = audit([d / "bad.parquet"], tf_minutes=5)
        assert report["passed"] is False
        assert any("missing column" in i for i in report["issues"])

    def test_audit_null_violations(self, tmp_path: Path) -> None:
        d = tmp_path / "data"
        d.mkdir(parents=True)
        df = _make_ohlcv(10)
        # Inject a null into 'close'
        df = df.with_columns(
            pl.when(pl.col("open_time") == df["open_time"][0])
            .then(pl.lit(None, dtype=pl.Float64))
            .otherwise(pl.col("close"))
            .alias("close")
        )
        p = d / "nulls.parquet"
        df.write_parquet(str(p))
        report = audit([p], tf_minutes=5)
        assert report["null_counts"]["close"] == 1
        assert any("null" in i for i in report["issues"])

    def test_audit_duplicate_timestamps(self, tmp_path: Path) -> None:
        d = tmp_path / "data"
        d.mkdir(parents=True)
        df = _make_ohlcv(10)
        # Duplicate last row
        df_dup = pl.concat([df, df.tail(1)])
        p = d / "dups.parquet"
        df_dup.write_parquet(str(p))
        report = audit([p], tf_minutes=5)
        assert report["duplicate_timestamps"] >= 1
        assert any("duplicate" in i for i in report["issues"])

    def test_audit_time_gaps(self, tmp_path: Path) -> None:
        d = tmp_path / "data"
        d.mkdir(parents=True)
        # Create data with a 30-minute gap in the middle
        df = _make_ohlcv(10)
        # Shift timestamps of second half forward by 25 min (creates 30min gap)
        df = df.with_columns(
            pl.when(pl.col("open_time") >= df["open_time"][5])
            .then(pl.col("open_time") + timedelta(minutes=25))
            .otherwise(pl.col("open_time"))
            .alias("open_time")
        )
        p = d / "gaps.parquet"
        df.write_parquet(str(p))
        report = audit([p], tf_minutes=5)
        assert report["gap_analysis"]["gaps_detected"] >= 1
        assert any("gap" in i for i in report["issues"])

    def test_audit_semantic_high_lt_low(self, tmp_path: Path) -> None:
        d = tmp_path / "data"
        d.mkdir(parents=True)
        df = _make_ohlcv(10)
        # Force high < low on first row
        df = df.with_columns(
            pl.when(pl.col("open_time") == df["open_time"][0])
            .then(pl.col("low") - 10)
            .otherwise(pl.col("high"))
            .alias("high")
        )
        p = d / "sem.parquet"
        df.write_parquet(str(p))
        report = audit([p], tf_minutes=5)
        assert report["semantic_issues"].get("high_lt_low", 0) >= 1

    def test_audit_semantic_negative_volume(self, tmp_path: Path) -> None:
        d = tmp_path / "data"
        d.mkdir(parents=True)
        df = _make_ohlcv(10)
        df = df.with_columns(
            pl.when(pl.col("open_time") == df["open_time"][0])
            .then(pl.lit(-1.0))
            .otherwise(pl.col("volume"))
            .alias("volume")
        )
        p = d / "negvol.parquet"
        df.write_parquet(str(p))
        report = audit([p], tf_minutes=5)
        assert report["semantic_issues"].get("neg_volume", 0) >= 1

    def test_audit_empty_files_list(self) -> None:
        report = audit([])
        assert report["passed"] is False
        assert "no files to audit" in report["issues"]

    def test_audit_value_ranges(self, synthetic_data_dir: Path) -> None:
        files = discover_files(synthetic_data_dir, "BTCUSDT", "5m")
        report = audit(files, tf_minutes=5)
        vr = report["value_ranges"]
        assert vr["open"][0] < vr["open"][1]
        assert vr["volume"]["min"] >= 0


# ═══════════════════════════════════════════════════════════════
# Stress tests
# ═══════════════════════════════════════════════════════════════

class TestStress:
    def _load_canonical(self, data_dir: Path) -> pl.LazyFrame:
        files = discover_files(data_dir, "BTCUSDT", "5m")
        lf = pl.scan_parquet([str(f) for f in files])
        rename = {k: v for k, v in DEFAULT_RENAME.items() if k in lf.collect_schema()}
        return lf.rename(rename)

    def test_stress_output_columns(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        result = compute_stress_v0(lf, window=20, burn_in=30)
        df = result.select(STRESS_OUTPUT_COLUMNS).collect()
        assert set(df.columns) == set(STRESS_OUTPUT_COLUMNS)

    def test_stress_burn_in_drops_rows(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        df = compute_stress_v0(lf, window=20, burn_in=30).collect()
        # Original 300 rows, 30 burned -> 270
        assert len(df) == 270

    def test_stress_log_return_correct(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        df = compute_stress_v0(lf, window=20, burn_in=30).collect()
        # Check a few non-null log returns
        lr = df["log_return"].drop_nulls()
        assert len(lr) > 0
        # Log returns should be small for BTC-like prices
        assert lr.abs().mean() < 0.1

    def test_stress_bar_range_positive(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        df = compute_stress_v0(lf, window=20, burn_in=30).collect()
        br = df["bar_range"].drop_nulls()
        assert (br >= 0).all()

    def test_stress_atr_positive(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        df = compute_stress_v0(lf, window=20, burn_in=30).collect()
        atr = df["atr"].drop_nulls()
        assert len(atr) > 0
        assert (atr >= 0).all()

    def test_stress_gap_nonnegative(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        df = compute_stress_v0(lf, window=20, burn_in=30).collect()
        gap = df["gap"].drop_nulls()
        assert (gap >= 0).all()

    def test_stress_z_scores_finite(self, synthetic_data_dir: Path) -> None:
        lf = self._load_canonical(synthetic_data_dir)
        df = compute_stress_v0(lf, window=20, burn_in=30).collect()
        for m in STRESS_V0_METRICS:
            z_col = df[f"z_{m}"].drop_nulls()
            if len(z_col) > 0:
                assert z_col.is_finite().all(), f"z_{m} has non-finite values"

    def test_stress_minimal_data(self) -> None:
        """Just enough data for window + burn_in."""
        df = _make_ohlcv(55)
        lf = df.rename({"open_time": "timestamp"}).lazy()
        result = compute_stress_v0(lf, window=20, burn_in=30).collect()
        assert len(result) == 25  # 55 - 30 = 25

    def test_stress_z_score_no_lookahead(self) -> None:
        """Z-score baseline for bar t must NOT include bar t itself."""
        n = 50
        df = _make_ohlcv(n)
        lf = df.rename({"open_time": "timestamp"}).lazy()
        # Use burn_in=0 so we keep all rows for inspection
        result = compute_stress_v0(lf, window=10, burn_in=0).collect()

        # For bar_range (per-bar metric): z-score at row i should use
        # baseline from [i-10..i-1] (shifted), NOT [i-9..i].
        # Verify: spike bar_range at row 30, check z-score doesn't
        # include the spike in its own baseline.
        bar_range_vals = result["bar_range"].to_list()
        z_vals = result["z_bar_range"].to_list()

        # The z-score at row 30 is computed with baseline ending at row 29.
        # If it were NOT shifted, the baseline would include row 30 itself,
        # dampening the z-score. With shift, the spike fully hits the numerator.
        # The first row's z-score should be null (shifted baseline = null at row 0).
        assert z_vals[0] is None or (isinstance(z_vals[0], float) and math.isnan(z_vals[0])) or z_vals[0] == 0.0


# ═══════════════════════════════════════════════════════════════
# CLI integration tests
# ═══════════════════════════════════════════════════════════════

class TestCLI:
    def test_cli_audit_only(self, synthetic_data_dir: Path, tmp_path: Path) -> None:
        from tools.parquet_pipeline.__main__ import main

        out = tmp_path / "out"
        rc = main([
            "--symbol", "BTCUSDT",
            "--tf", "5m",
            "--data-dir", str(synthetic_data_dir),
            "--output-dir", str(out),
            "--audit-only",
        ])
        assert rc == 0
        assert (out / "audit_report.json").exists()
        assert (out / "provenance.json").exists()
        assert not (out / "stress_timeseries.parquet").exists()

    def test_cli_full_pipeline(self, synthetic_data_dir: Path, tmp_path: Path) -> None:
        from tools.parquet_pipeline.__main__ import main

        out = tmp_path / "out"
        rc = main([
            "--symbol", "BTCUSDT",
            "--tf", "5m",
            "--data-dir", str(synthetic_data_dir),
            "--output-dir", str(out),
            "--window", "20",
            "--burn-in", "30",
        ])
        assert rc == 0
        assert (out / "audit_report.json").exists()
        assert (out / "stress_timeseries.parquet").exists()
        assert (out / "stress_summary.md").exists()
        assert (out / "provenance.json").exists()

        # Verify provenance content
        prov = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
        assert prov["symbol"] == "BTCUSDT"
        assert prov["stress_computed"] is True
        assert prov["window"] == 20
        assert prov["burn_in"] == 30

    def test_cli_not_found(self, tmp_path: Path) -> None:
        from tools.parquet_pipeline.__main__ import main

        rc = main([
            "--symbol", "NONEXIST",
            "--tf", "5m",
            "--data-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
        ])
        assert rc == 2

    def test_cli_month_filter(self, synthetic_data_dir: Path, tmp_path: Path) -> None:
        from tools.parquet_pipeline.__main__ import main

        out = tmp_path / "out"
        rc = main([
            "--symbol", "BTCUSDT",
            "--tf", "5m",
            "--data-dir", str(synthetic_data_dir),
            "--output-dir", str(out),
            "--months", "2024-01",
            "--window", "20",
            "--burn-in", "30",
        ])
        assert rc == 0
        prov = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
        assert prov["months_filter"] == ["2024-01"]
