from __future__ import annotations

import json
from pathlib import Path
import runpy

import pandas as pd

from apps.reference.config_loader import get_config
from tools.system_stress_calibration.core import (
    build_dataset_bundle,
    build_evaluation_config,
    build_walkforward_windows,
    compute_future_label_scores,
    generate_weight_candidates,
    load_recorder_dataset,
    simulate_stress_states,
    validate_dataset_manifest,
)


def _write_recorder_day(root: Path, *, day: str, closes: list[float], tf_sec: int = 300) -> None:
    day_dir = root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    base_ts = int(pd.Timestamp(f"{day}T00:00:00Z").value // 1_000_000)
    rows = []
    previous_close = closes[0]
    for idx, close in enumerate(closes):
        open_price = previous_close
        rows.append(
            {
                "timestamp": base_ts + idx * tf_sec * 1000,
                "tf_sec": tf_sec,
                "symbol": "BTCUSDT",
                "open": open_price,
                "high": max(open_price, close) + 0.8,
                "low": min(open_price, close) - 0.8,
                "close": close,
                "volume": 100 + idx,
            }
        )
        previous_close = close
    pd.DataFrame(rows).to_csv(day_dir / f"BTCUSDT_{tf_sec}.csv", index=False)


def _build_recorder_fixture(root: Path) -> None:
    templates = [
        [100.0, 101.8, 99.1, 102.5, 98.4, 103.6, 97.8, 104.2],
        [104.2, 102.1, 105.4, 101.3, 106.5, 100.9, 107.0, 100.1],
        [100.1, 99.3, 101.8, 98.7, 102.9, 98.2, 103.4, 97.9],
        [97.9, 99.8, 96.6, 100.7, 95.7, 101.1, 95.2, 101.9],
        [101.9, 103.4, 100.8, 104.7, 99.7, 105.1, 99.2, 105.8],
        [105.8, 104.1, 106.4, 103.2, 107.3, 102.6, 108.1, 102.0],
    ]
    for day_idx, closes in enumerate(templates, start=1):
        _write_recorder_day(root, day=f"2026-04-0{day_idx}", closes=closes)


def test_generate_weight_candidates_covers_simplex() -> None:
    candidates = generate_weight_candidates(
        ["atr", "vol", "gap", "range"], step=0.5)
    assert len(candidates) == 10
    assert all(abs(sum(candidate.values()) - 1.0)
               < 1e-9 for candidate in candidates)
    assert {"atr": 0.5, "vol": 0.5, "gap": 0.0, "range": 0.0} in candidates


def test_compute_future_label_scores_future_range() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["BTCUSDT"] * 5,
            "timestamp": [1, 2, 3, 4, 5],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 103.0, 108.0, 105.0, 106.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.0, 102.0, 103.0, 104.0, 105.0],
        }
    )
    scores = compute_future_label_scores(
        df, mode="future_range", horizon_bars=2)
    assert round(float(scores.iloc[0]), 4) == 0.08
    assert round(float(scores.iloc[1]), 4) == round((108.0 - 101.0) / 102.0, 4)
    assert scores.iloc[-1] != scores.iloc[-1]


def test_simulate_stress_states_transitions_after_crash_bars() -> None:
    quiet_rows = []
    ts = 1_704_067_500_000
    for offset, close in enumerate([
        100.0,
        99.0,
        101.0,
        100.5,
        99.5,
        100.2,
        99.8,
        100.1,
        99.7,
        100.4,
        99.9,
        100.3,
    ]):
        quiet_rows.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": ts + offset * 300_000,
                "open": close,
                "high": close + 1.5,
                "low": close - 1.5,
                "close": close,
            }
        )
    crash_rows = []
    base_ts = ts + len(quiet_rows) * 300_000
    for offset in range(2):
        crash_rows.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": base_ts + offset * 300_000,
                "open": 150.0,
                "high": 160.0,
                "low": 40.0,
                "close": 50.0,
            }
        )
    df = pd.DataFrame(quiet_rows + crash_rows)

    base_cfg_dict = get_config().model_dump()
    cfg = build_evaluation_config(
        base_cfg_dict,
        tf_sec=300,
        weights={"atr": 0.25, "vol": 0.25, "gap": 0.25, "range": 0.25},
        baseline_window=10,
        burn_in_bars=10,
    )
    cfg.system_stress.state_mapping.enter_stress = 0.5
    cfg.system_stress.state_mapping.enter_extreme = 0.9
    cfg.system_stress.state_mapping.exit_stress = 0.3
    cfg.system_stress.state_mapping.exit_extreme = 0.7
    cfg.system_stress.state_mapping.consecutive_bars_enter = 2
    cfg.system_stress.state_mapping.consecutive_bars_exit = 2
    cfg.system_stress.state_mapping.min_duration_bars = 2

    preds = simulate_stress_states(df, config=cfg)
    assert preds["eligible"].iloc[9]
    assert preds["pred_state"].iloc[-1] in {"STRESS", "EXTREME"}


def test_load_recorder_dataset_can_skip_bad_csv(tmp_path) -> None:
    day_dir = tmp_path / "2026-04-01"
    day_dir.mkdir(parents=True)
    bad_csv = day_dir / "BTCUSDT_300.csv"
    bad_csv.write_text(
        "close,datetime,open\n100,2026-04-01T00:00:00,99\n101,2026-04-01T00:05:00,100,extra\n",
        encoding="utf-8",
    )

    skipped: list[str] = []
    df = load_recorder_dataset(
        tmp_path,
        start=None,
        end=None,
        symbols=["BTCUSDT"],
        tf_sec=300,
        skip_bad_csvs=True,
        skipped_paths=skipped,
    )

    assert df.empty
    assert len(skipped) == 1
    assert "BTCUSDT_300.csv" in skipped[0]


def test_load_recorder_dataset_accepts_float_tf_sec(tmp_path) -> None:
    day_dir = tmp_path / "2026-04-02"
    day_dir.mkdir(parents=True)
    csv_path = day_dir / "BTCUSDT_300.csv"
    csv_path.write_text(
        "timestamp,tf_sec,open,high,low,close\n1712016000000,300.0,100,101,99,100.5\n",
        encoding="utf-8",
    )

    df = load_recorder_dataset(
        tmp_path,
        start=None,
        end=None,
        symbols=["BTCUSDT"],
        tf_sec=300,
    )

    assert len(df) == 1
    assert int(df.iloc[0]["tf_sec"]) == 300
    assert int(df.iloc[0]["timestamp"]) == 1712016000000


def test_build_dataset_bundle_manifest_is_deterministic(tmp_path: Path) -> None:
    _build_recorder_fixture(tmp_path)

    bundle_a = build_dataset_bundle(
        tmp_path,
        start=None,
        end=None,
        symbols=["BTCUSDT"],
        tf_sec=300,
    )
    bundle_b = build_dataset_bundle(
        tmp_path,
        start=None,
        end=None,
        symbols=["BTCUSDT"],
        tf_sec=300,
    )

    assert bundle_a.manifest["fingerprint"] == bundle_b.manifest["fingerprint"]
    assert validate_dataset_manifest(
        bundle_a.manifest, bundle_b.manifest, strict=True) == []


def test_build_walkforward_windows_is_deterministic(tmp_path: Path) -> None:
    _build_recorder_fixture(tmp_path)
    frame = load_recorder_dataset(
        tmp_path,
        start=None,
        end=None,
        symbols=["BTCUSDT"],
        tf_sec=300,
    )

    windows_a = build_walkforward_windows(
        frame,
        train_windows=2,
        validate_windows=1,
        test_windows=1,
        step_windows=1,
    )
    windows_b = build_walkforward_windows(
        frame,
        train_windows=2,
        validate_windows=1,
        test_windows=1,
        step_windows=1,
    )

    assert windows_a == windows_b
    assert len(windows_a) == 3
    assert windows_a[0].train_days == ["2026-04-01", "2026-04-02"]
    assert windows_a[0].validate_days == ["2026-04-03"]
    assert windows_a[0].test_days == ["2026-04-04"]


def test_research_cli_writes_contract_artifacts(tmp_path: Path) -> None:
    _build_recorder_fixture(tmp_path / "recorder")
    module = runpy.run_path(
        str(Path("calibrators/policy_gates/calibrate_system_stress_weights.py")))
    main = module["main"]
    out_dir = tmp_path / "artifacts"
    frozen_manifest = tmp_path / "frozen_manifest.json"

    rc = main(
        [
            "--mode",
            "research",
            "--recorder-dir",
            str(tmp_path / "recorder"),
            "--symbols",
            "BTCUSDT",
            "--tf-sec",
            "300",
            "--baseline-window",
            "10",
            "--burn-in-bars",
            "10",
            "--search-steps",
            "0.5",
            "--final-rounding-step",
            "0.5",
            "--top-k",
            "2",
            "--dataset-manifest",
            str(frozen_manifest),
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    assert json.loads(
        (out_dir / "candidate_summary.json").read_text(encoding="utf-8"))["mode"] == "research"
    assert (out_dir / "candidate_metrics.json").exists()
    assert (out_dir / "walkforward_metrics.csv").exists()
    assert (out_dir / "yaml_patch_snippet.yaml").exists()
    assert (out_dir / "report.md").exists()
    assert frozen_manifest.exists()


def test_acceptance_cli_fails_closed_without_gates(tmp_path: Path) -> None:
    _build_recorder_fixture(tmp_path / "recorder")
    manifest_path = tmp_path / "manifest.json"
    manifest = build_dataset_bundle(
        tmp_path / "recorder",
        start=None,
        end=None,
        symbols=["BTCUSDT"],
        tf_sec=300,
    ).manifest
    manifest_path.write_text(json.dumps(
        manifest, indent=2, sort_keys=True), encoding="utf-8")

    module = runpy.run_path(
        str(Path("calibrators/policy_gates/calibrate_system_stress_weights.py")))
    main = module["main"]
    rc = main(
        [
            "--mode",
            "acceptance",
            "--recorder-dir",
            str(tmp_path / "recorder"),
            "--symbols",
            "BTCUSDT",
            "--tf-sec",
            "300",
            "--dataset-manifest",
            str(manifest_path),
            "--strict-dataset",
            "--oracle-primary",
            "future_vol",
            "--forecast-horizon-bars",
            "2",
            "--stress-label-policy",
            "primary_quantile",
            "--primary-label-quantile",
            "0.8",
            "--wf-train-windows",
            "2",
            "--wf-validate-windows",
            "1",
            "--wf-test-windows",
            "1",
            "--wf-step-windows",
            "1",
            "--baseline-window",
            "10",
            "--burn-in-bars",
            "10",
            "--out-dir",
            str(tmp_path / "acceptance_artifacts"),
        ]
    )

    assert rc == 1
