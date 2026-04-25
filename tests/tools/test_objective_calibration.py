from __future__ import annotations

import json
import runpy
import sqlite3
from math import sin
from pathlib import Path

import pandas as pd

from tools.objective_calibration.dataset import build_objective_dataset, load_objective_dataset
from tools.objective_calibration.overlay import write_overlay_bundle
from tools.objective_calibration.report import render_objective_calibration_report
from tools.objective_calibration.search import search_objective_candidates


def _write_recorder_csv(root: Path) -> None:
    day_dir = root / "2026-03-10"
    day_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "timestamp": 1_700_000_000_000,
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10.0,
                "trade_count": 100,
                "regime": "TREND_UP",
                "regime_conf": 0.8,
                "feat_price": 100.5,
                "feat_spread_bps": 1.2,
                "feat_liquidity_kappa": 2.5,
                "feat_volatility_state": "NORMAL",
                "ready": True,
            }
        ]
    )
    df.to_csv(day_dir / "BTCUSDT_300.csv", index=False)


def _write_wal(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "verb": "TRADE_INTENT_PROPOSED",
            "timestamp": 1_700_000_000_000,
            "pld": {
                "rid": "entry-rid-1",
                "strategy": "aurora",
                "instrument": "BTCUSDT",
                "side": "BUY",
                "regime": "TREND_UP",
                "order": {"price_ref": "100.0", "reduce_only": False},
                "trace": {
                    "objective": {
                        "trace_id": "obj-1",
                        "multiplier": 0.9,
                        "objective_score": 0.45,
                        "components": {
                            "cost": -0.1,
                            "risk": -0.05,
                            "edge": 0.3,
                            "execution": 0.2,
                            "information": 0.1,
                            "behavior": -0.02,
                        },
                        "raw_metrics": {"spread_bps": 1.2},
                    },
                    "alpha_search": {"signal_id": "sig-1"},
                },
            },
        },
        {
            "verb": "OBJECTIVE_REALIZED_V1",
            "timestamp": 1_700_000_600_000,
            "pld": {
                "strategy_id": "aurora",
                "symbol": "BTCUSDT",
                "entry_rid": "entry-rid-1",
                "close_rid": "close-rid-1",
                "signal_id": "sig-1",
                "regime_entry": "TREND_UP",
                "regime_exit": "MEAN_REVERSION",
                "pretrade_objective_trace": {
                    "trace_id": "obj-1",
                    "multiplier": 0.9,
                    "objective_score": 0.45,
                    "components": {
                        "cost": -0.1,
                        "risk": -0.05,
                        "edge": 0.3,
                        "execution": 0.2,
                        "information": 0.1,
                        "behavior": -0.02,
                    },
                    "raw_metrics": {"spread_bps": 1.2},
                },
                "realized_components": {
                    "duration_efficiency": 0.7,
                    "regime_path_stability": 0.8,
                    "mae_efficiency": 0.6,
                },
                "realized_quality_score": 0.72,
                "realized_pnl": 15.0,
                "fees": 0.5,
                "duration_sec": 600.0,
                "mae": -1.0,
                "mfe": 2.0,
                "close_reason": "TP_HIT",
            },
        },
    ]
    with (root / "2026-03-10.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def _write_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE orders (order_id TEXT, client_order_id TEXT, symbol TEXT, side TEXT, order_type TEXT, status TEXT, role TEXT, entry_client_id TEXT, created_at INTEGER, updated_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ord-1",
                "close-rid-1",
                "BTCUSDT",
                "SELL",
                "LIMIT",
                "FILLED",
                "EXIT",
                "entry-rid-1",
                1_700_000_000_000,
                1_700_000_600_000,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _dataset_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    recorder_dir = tmp_path / "recorder"
    wal_dir = tmp_path / "wal"
    ledger_path = tmp_path / "order_ledger.db"
    _write_recorder_csv(recorder_dir)
    _write_wal(wal_dir)
    _write_ledger(ledger_path)
    return recorder_dir, wal_dir, ledger_path


def test_build_objective_dataset_roundtrip(tmp_path: Path) -> None:
    recorder_dir, wal_dir, ledger_path = _dataset_fixture(tmp_path)
    dataset = build_objective_dataset(
        recorder_dir=recorder_dir,
        wal_dir=wal_dir,
        ledger_path=ledger_path,
        symbols=["BTCUSDT"],
        start=None,
        end=None,
        tf_sec=300,
    )
    assert not dataset.attempted_entries.empty
    assert not dataset.realized_trades.empty
    out_dir = dataset.write(tmp_path / "dataset")
    reloaded = load_objective_dataset(out_dir)
    assert len(reloaded.attempted_entries) == len(dataset.attempted_entries)
    assert len(reloaded.realized_trades) == len(dataset.realized_trades)
    assert reloaded.manifest["symbols"] == ["BTCUSDT"]


def test_search_candidates_is_deterministic_and_writes_overlays(tmp_path: Path) -> None:
    recorder_dir, wal_dir, ledger_path = _dataset_fixture(tmp_path)
    dataset = build_objective_dataset(
        recorder_dir=recorder_dir,
        wal_dir=wal_dir,
        ledger_path=ledger_path,
        symbols=["BTCUSDT"],
        start=None,
        end=None,
        tf_sec=300,
    )
    config_snapshot = Path(
        "config/aurora/domains.yaml").read_text(encoding="utf-8")
    candidates_a = search_objective_candidates(
        realized_df=dataset.realized_trades,
        attempted_df=dataset.attempted_entries,
        config_root=Path("config/aurora"),
        strategy_bundle_path=None,
        trials=5,
        top_k=3,
        seed=42,
        min_trade_count=1,
    )
    candidates_b = search_objective_candidates(
        realized_df=dataset.realized_trades,
        attempted_df=dataset.attempted_entries,
        config_root=Path("config/aurora"),
        strategy_bundle_path=None,
        trials=5,
        top_k=3,
        seed=42,
        min_trade_count=1,
    )
    assert [candidate.score for candidate in candidates_a] == [
        candidate.score for candidate in candidates_b]

    out_dir = tmp_path / "objective_report"
    overlay_paths = write_overlay_bundle(
        out_dir, best_candidate=candidates_a[0], candidates=candidates_a)
    report_path = render_objective_calibration_report(
        out_dir,
        scope="unit-test",
        dataset_manifest=dataset.manifest,
        best_candidate=candidates_a[0],
        candidate_count=len(candidates_a),
        overlay_paths=overlay_paths,
    )
    assert report_path.exists()
    assert (out_dir / "best_trial.json").exists()
    assert (out_dir / "candidate_bundle.json").exists()
    assert Path(
        "config/aurora/domains.yaml").read_text(encoding="utf-8") == config_snapshot


def test_objective_stack_cli_builds_dataset_and_joint_artifacts(tmp_path: Path) -> None:
    recorder_dir, wal_dir, ledger_path = _dataset_fixture(tmp_path)
    module = runpy.run_path(
        str(Path("tools/calibration/calibrate_objective_stack.py")))
    main = module["main"]

    dataset_dir = tmp_path / "dataset_cli"
    rc = main(
        [
            "--config-root",
            "config/aurora",
            "build-dataset",
            "--recorder-dir",
            str(recorder_dir),
            "--wal-dir",
            str(wal_dir),
            "--ledger-path",
            str(ledger_path),
            "--symbols",
            "BTCUSDT",
            "--tf-sec",
            "300",
            "--out-dir",
            str(dataset_dir),
        ]
    )
    assert rc == 0
    assert (dataset_dir / "attempted_entries.csv").exists()

    joint_dir = tmp_path / "joint_cli"
    rc = main(
        [
            "--config-root",
            "config/aurora",
            "joint",
            "--dataset-dir",
            str(dataset_dir),
            "--top-k",
            "2",
            "--trials",
            "3",
            "--min-trade-count",
            "1",
            "--out-dir",
            str(joint_dir),
        ]
    )
    assert rc == 0
    assert (joint_dir / "strategy_stage" / "candidate_bundle.json").exists()
    assert (joint_dir / "objective_stage" / "best_trial.json").exists()
    assert (joint_dir / "objective_stage" / "report.md").exists()


def test_mean_reversion_calibrator_emits_overlay_and_report(tmp_path: Path) -> None:
    recorder_dir = tmp_path / "mr_recorder"
    for offset in range(8):
        day = f"2026-03-{10 + offset:02d}"
        day_dir = recorder_dir / day
        day_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        base_ts = int(pd.Timestamp(f"{day}T00:00:00Z").value // 1_000_000)
        for idx in range(96):
            price = 100.0 + (4.0 * sin((idx + (offset * 3)) / 6.0))
            rows.append(
                {
                    "timestamp": base_ts + idx * 300_000,
                    "symbol": "DOGEUSDT",
                    "tf_sec": 300,
                    "open": price - 0.3,
                    "high": price + 0.6,
                    "low": price - 0.6,
                    "close": price,
                    "volume": 10.0,
                    "trade_count": 100,
                    "regime": "MEAN_REVERSION",
                    "regime_conf": 0.8,
                    "feat_price": price,
                    "feat_spread_bps": 1.5,
                    "feat_liquidity_kappa": 2.0,
                    "feat_volatility_state": "NORMAL",
                    "ready": True,
                }
            )
        pd.DataFrame(rows).to_csv(day_dir / "DOGEUSDT_300.csv", index=False)

    module = runpy.run_path(
        str(Path("tools/calibration/calibrate_mean_reversion_params.py")))
    main = module["main"]
    out_dir = tmp_path / "mr_calibration"
    registry_path = tmp_path / "strategies_registry.yaml"
    registry_path.write_text(
        "version: \"1.0.0\"\nassignments:\n  DOGEUSDT:\n    - mean_reversion\n",
        encoding="utf-8",
    )
    rc = main(
        [
            "--mr-yaml",
            "config/aurora/strategies/mean_reversion.yaml",
            "--strategies-registry",
            str(registry_path),
            "--recorder-dir",
            str(recorder_dir),
            "--symbols",
            "DOGEUSDT",
            "--start",
            "2026-03-10",
            "--end",
            "2026-03-18",
            "--tf-sec",
            "300",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--trials",
            "5",
            "--top-k",
            "2",
            "--min-trades",
            "1",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert (out_dir / "report.md").exists()
    assert (out_dir / "run_manifest.json").exists()
    assert (out_dir / "baseline_metrics.json").exists()
    assert (out_dir / "candidate_metrics.json").exists()
    assert (out_dir / "validation_metrics.json").exists()
    assert (out_dir / "forward_metrics.json").exists()
    assert (out_dir / "best_trial.json").exists()
    assert (out_dir / "candidate_bundle.json").exists()
    assert (out_dir / "candidate_mean_reversion_overlay.yaml").exists()
    assert (out_dir / "candidate_mean_reversion_strategy_overlay.yaml").exists()
