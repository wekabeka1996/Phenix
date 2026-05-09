from __future__ import annotations

from datetime import date, timedelta
import json
from math import sin
from pathlib import Path

import pandas as pd
import pytest
import yaml

from calibrators.strategies import calibrate_mean_reversion_params as calibrator


def _write_mr_recorder(root: Path, *, symbol: str, start_day: date, day_count: int) -> None:
    for offset in range(day_count):
        day = start_day + timedelta(days=offset)
        day_dir = root / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        base_ts = int(pd.Timestamp(
            f"{day.isoformat()}T00:00:00Z").value // 1_000_000)
        rows = []
        for bar_idx in range(96):
            phase = (bar_idx + (offset * 3)) / 5.0
            close_price = 100.0 + (4.5 * sin(phase))
            open_price = 100.0 + (4.5 * sin(max(0.0, phase - 0.3)))
            rows.append(
                {
                    "timestamp": base_ts + bar_idx * 300_000,
                    "tf_sec": 300,
                    "symbol": symbol,
                    "open": open_price,
                    "high": max(open_price, close_price) + 0.9,
                    "low": min(open_price, close_price) - 0.9,
                    "close": close_price,
                    "volume": 1000 + bar_idx,
                    "trade_count": 100 + bar_idx,
                    "regime": "MEAN_REVERSION",
                    "regime_conf": 0.8,
                    "feat_price": close_price,
                    "feat_spread_bps": 1.5,
                    "feat_liquidity_kappa": 2.0,
                    "feat_volatility_state": "NORMAL",
                    "ready": True,
                }
            )
        pd.DataFrame(rows).to_csv(day_dir / f"{symbol}_300.csv", index=False)


def _write_mr_registry(path: Path, *, symbols: list[str]) -> None:
    payload = {
        "version": "1.0.0",
        "assignments": {
            str(symbol).upper(): ["mean_reversion"] for symbol in symbols
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_mean_reversion_calibrator_help_works(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        calibrator.main(["--help"])

    assert exc.value.code == 0
    stdout = capsys.readouterr().out
    assert "train/validation/forward" in stdout
    assert "--validation-days" in stdout


def test_mean_reversion_calibrator_writes_required_artifacts(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_mr_recorder(recorder_root, symbol="DOGEUSDT",
                       start_day=date(2026, 4, 1), day_count=8)
    out_dir = tmp_path / "artifacts"
    registry_path = tmp_path / "strategies_registry.yaml"
    _write_mr_registry(registry_path, symbols=["DOGEUSDT"])
    yaml_path = Path("config/aurora/strategies/mean_reversion.yaml")
    original_yaml = yaml_path.read_text(encoding="utf-8")

    rc = calibrator.main(
        [
            "--strategies-registry",
            str(registry_path),
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "DOGEUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--trials",
            "24",
            "--top-k",
            "3",
            "--min-trades",
            "1",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    required = [
        out_dir / "run_manifest.json",
        out_dir / "baseline_metrics.json",
        out_dir / "candidate_metrics.json",
        out_dir / "validation_metrics.json",
        out_dir / "forward_metrics.json",
        out_dir / "candidate_mean_reversion_strategy_overlay.yaml",
        out_dir / "report.md",
    ]
    for path in required:
        assert path.exists(), str(path)

    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["canonical_yaml_writeback"] is False
    assert manifest["verdict"] in {"GO_CANDIDATE", "NO_GO_CANDIDATE"}

    overlay = yaml.safe_load(
        (out_dir / "candidate_mean_reversion_strategy_overlay.yaml").read_text(encoding="utf-8"))
    assert list(overlay["mean_reversion"]["assets"].keys()) == ["DOGEUSDT"]
    assert sorted(overlay["mean_reversion"]["assets"]["DOGEUSDT"]["strategy"].keys()) == [
        "bb_num_std",
        "bb_window",
        "cooldown_sec",
        "entry_threshold",
        "max_bb_width",
        "min_bb_width",
        "sl_atr_mult",
    ]

    report = (out_dir / "report.md").read_text(encoding="utf-8")
    for section in [
        "## Scope",
        "## Dataset",
        "## Runtime Surface Under Calibration",
        "## Baseline",
        "## Candidate",
        "## Validation",
        "## Forward Evaluation",
        "## Guardrails",
        "## Risks",
        "## Verdict",
        "## Next Action",
    ]:
        assert section in report

    assert (out_dir / "candidate_mean_reversion_overlay.yaml").exists()
    assert (out_dir / "best_trial.json").exists()
    assert (out_dir / "candidate_bundle.json").exists()
    assert yaml_path.read_text(encoding="utf-8") == original_yaml


def test_mean_reversion_calibrator_fails_closed_when_data_insufficient(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_mr_recorder(recorder_root, symbol="DOGEUSDT",
                       start_day=date(2026, 4, 1), day_count=3)
    out_dir = tmp_path / "failed_artifacts"
    registry_path = tmp_path / "strategies_registry.yaml"
    _write_mr_registry(registry_path, symbols=["DOGEUSDT"])

    rc = calibrator.main(
        [
            "--strategies-registry",
            str(registry_path),
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "DOGEUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-04",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 2
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed_closed"
    assert manifest["verdict"] == "NO_GO_CANDIDATE"
    assert (out_dir / "report.md").exists()


def test_mean_reversion_guardrail_artifact_fails_closed_on_forward_degradation() -> None:
    guardrails = calibrator.GuardrailCfg(
        min_trades=5,
        max_drawdown_ratio=0.35,
        min_train_days=2,
        min_activity_ratio=0.5,
        max_activity_ratio=2.5,
    )
    baseline = {
        "selection_score": 1.2,
        "net_return_ratio": 0.10,
        "max_drawdown_ratio": 0.08,
        "total_trades": 8,
        "entry_count": 8,
        "win_rate": 0.5,
    }
    candidate = {
        "selection_score": 0.7,
        "net_return_ratio": 0.08,
        "max_drawdown_ratio": 0.09,
        "total_trades": 8,
        "entry_count": 8,
        "win_rate": 0.5,
    }

    artifact = calibrator._build_comparison_artifact(
        window_name="forward",
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        guardrails=guardrails,
    )

    assert artifact["all_passed"] is False
    failed_names = {item["name"]
                    for item in artifact["guardrails"] if not item["passed"]}
    assert "forward_no_degradation_vs_baseline" in failed_names


def test_csv_fallback_on_bad_lines(tmp_path: Path) -> None:
    """CSV with bad lines must not crash _validate_requested_recorder_csvs."""
    day_dir = tmp_path / "recorder" / "2026-04-01"
    day_dir.mkdir(parents=True)
    csv_path = day_dir / "DOGEUSDT_300.csv"
    # Write a CSV with a legitimate header + some good rows + a bad row
    csv_path.write_text(
        "timestamp,tf_sec,symbol,open,high,low,close,volume,regime,regime_conf\n"
        "1743465600000,300,DOGEUSDT,0.17,0.175,0.165,0.17,1000,MEAN_REVERSION,0.8\n"
        "badrow,extra_col,DOGEUSDT,oops,this,is,broken,row,with,too,many,cols\n"
        "1743465900000,300,DOGEUSDT,0.17,0.175,0.165,0.172,1100,MEAN_REVERSION,0.8\n",
        encoding="utf-8",
    )
    # Must not raise
    calibrator._validate_requested_recorder_csvs(
        tmp_path / "recorder",
        start=date(2026, 4, 1),
        end=date(2026, 4, 2),
        symbols=["DOGEUSDT"],
        tf_sec=300,
    )


def test_compute_regime_labels_300s_valid_labels() -> None:
    """_compute_regime_labels_300s must produce only valid regime strings."""
    valid_regimes = {
        "HIGH_VOLATILITY", "LOW_VOLATILITY", "MEAN_REVERSION",
        "TREND_UP", "TREND_DOWN", "UNCERTAIN",
    }
    # Build 500 bars of synthetic 5-min OHLCV with a trend then oscillation
    n = 500
    close = [100.0 + i * 0.3 for i in range(250)] + \
        [175.0 + 5 * ((-1) ** i) for i in range(250)]
    df = pd.DataFrame({
        "open": [close[max(0, i - 1)] for i in range(n)],
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
        "volume": [1000] * n,
    })
    result = calibrator._compute_regime_labels_300s(df)

    assert len(result) == n
    unique_labels = set(result.dropna().unique())
    assert unique_labels, "Expected at least one non-NaN regime label"
    assert unique_labels.issubset(
        valid_regimes), f"Invalid labels: {unique_labels - valid_regimes}"


def test_tpsl_surface_produces_artifacts(tmp_path: Path) -> None:
    """Run with --tpsl-surface → tpsl_surface.json + mfe_mae_analysis.json must exist."""
    recorder_root = tmp_path / "recorder"
    _write_mr_recorder(recorder_root, symbol="DOGEUSDT",
                       start_day=date(2026, 4, 1), day_count=8)
    out_dir = tmp_path / "tpsl_artifacts"
    registry_path = tmp_path / "strategies_registry.yaml"
    _write_mr_registry(registry_path, symbols=["DOGEUSDT"])

    rc = calibrator.main(
        [
            "--strategies-registry",
            str(registry_path),
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "DOGEUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--trials",
            "4",
            "--top-k",
            "2",
            "--min-trades",
            "1",
            "--tpsl-surface",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    tpsl_path = out_dir / "tpsl_surface.json"
    mfe_path = out_dir / "mfe_mae_analysis.json"
    assert tpsl_path.exists(), f"Missing {tpsl_path}"
    assert mfe_path.exists(), f"Missing {mfe_path}"

    tpsl = json.loads(tpsl_path.read_text(encoding="utf-8"))
    assert len(
        tpsl["grid"]) == 12, f"Expected 12 cells (6×2), got {len(tpsl['grid'])}"
    assert tpsl.get("best_cell") is not None
