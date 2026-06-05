from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from tools.analysis import md_amr_integrated_validation as validator


def _write_md_amr_recorder(root: Path, *, symbol: str, start_day: date, day_count: int) -> None:
    pattern = [
        100.0,
        101.0,
        102.0,
        103.0,
        104.0,
        105.0,
        106.0,
        107.0,
        108.0,
        109.0,
        110.0,
        111.0,
        112.0,
        88.0,
        94.0,
        100.0,
    ]
    regimes = ["MEAN_REVERSION", "LOW_VOLATILITY",
               "TREND_UP", "HIGH_VOLATILITY"]
    for offset in range(day_count):
        day = start_day + timedelta(days=offset)
        day_dir = root / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        base_ts = int(pd.Timestamp(
            f"{day.isoformat()}T00:00:00Z").value // 1_000_000)
        rows = []
        previous_close = pattern[0] + (offset * 0.2)
        for bar_idx in range(96):
            close_price = pattern[bar_idx % len(pattern)] + (offset * 0.2)
            open_price = previous_close
            rows.append(
                {
                    "timestamp": base_ts + bar_idx * 900_000,
                    "tf_sec": 900,
                    "symbol": symbol,
                    "open": open_price,
                    "high": max(open_price, close_price) + 1.5,
                    "low": min(open_price, close_price) - 1.5,
                    "close": close_price,
                    "volume": 1000 + bar_idx,
                    "regime": regimes[bar_idx % len(regimes)],
                    "regime_conf": 0.65,
                }
            )
            previous_close = close_price
        pd.DataFrame(rows).to_csv(day_dir / f"{symbol}_900.csv", index=False)


def test_md_amr_integrated_validation_writes_required_artifacts(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder(recorder_root, symbol="XRPUSDT",
                           start_day=date(2026, 4, 1), day_count=8)
    _write_md_amr_recorder(recorder_root, symbol="SOLUSDT",
                           start_day=date(2026, 4, 1), day_count=8)

    by_symbol_out = tmp_path / "reports" / "by_symbol.csv"
    cohorts_out = tmp_path / "reports" / "cohorts.csv"
    summary_out = tmp_path / "reports" / "summary.csv"
    report_out = tmp_path / "config" / "docs" / "report.md"

    rc = validator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "XRPUSDT",
            "SOLUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--by-symbol-out",
            str(by_symbol_out),
            "--cohorts-out",
            str(cohorts_out),
            "--summary-out",
            str(summary_out),
            "--report-out",
            str(report_out),
        ]
    )

    assert rc == 0
    assert by_symbol_out.exists()
    assert cohorts_out.exists()
    assert summary_out.exists()
    assert report_out.exists()

    by_symbol = pd.read_csv(by_symbol_out)
    summary = pd.read_csv(summary_out)
    report = report_out.read_text(encoding="utf-8")

    assert set(by_symbol["arm"]) == {"baseline_a1", "integrated_c1234"}
    assert set(by_symbol["symbol"]) == {"XRPUSDT", "SOLUSDT"}
    assert "COMBINED" in set(summary["scope"])
    combined = summary.loc[summary["scope"] == "COMBINED"].iloc[0]
    assert float(combined["exact_trade_match_rate"]) == 1.0
    assert float(combined["net_return_ratio_delta"]) == 0.0
    assert "## FACT" in report
    assert "## Verdict" in report
