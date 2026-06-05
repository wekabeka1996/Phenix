from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

import pytest

from apps.reference.domains.alpha_search.judge.config_models import JudgeCortexConfig
from tools.alpha_search import alpha_factory as mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _make_calibration_row(
    verdict_id: str,
    *,
    symbol: str = "BTCUSDT",
    tf_sec: int = 180,
    ts: int = 1_779_000_179_999,
    confidence: float = 0.8,
    net_return: float | None = 0.01,
    entry_verdict: str = "OPEN_LONG",
    provenance_class: str = "replay_derived",
) -> dict:
    return {
        "schema_version": "1",
        "strategy_id": "aurora",
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": ts,
        "verdict_id": verdict_id,
        "entry_verdict": entry_verdict,
        "confidence": confidence,
        "dissent_noted": False,
        "matched_trade": net_return is not None,
        "raw_return": net_return,
        "fee_cost": 0.0025 if net_return is not None else None,
        "slippage_cost": 0.001 if net_return is not None else None,
        "net_return": net_return,
        "optimal_action": entry_verdict if net_return and net_return > 0 else "NO_ENTRY",
        "has_disagreement": False,
        "cohort": "CORRECT_ENTRY" if net_return and net_return > 0 else "INCORRECT_ENTRY",
        "provenance_class": provenance_class,
    }


def _write_verdict_log(path: Path, rows: list[dict]) -> None:
    _write_jsonl(path, rows)


def _write_raw_cache(path: Path, symbol: str, open_times: list[int]) -> None:
    rows = [
        [open_ms, "100.0", "101.0", "99.0", "100.5", "10.0", open_ms + 60_000 - 1, "1005.0", 5]
        for open_ms in open_times
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"symbol": symbol, "interval": "1m", "klines": rows}), encoding="utf-8")


def test_db_schema_creation_has_required_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "alpha_factory.sqlite"
    mod.ensure_schema(db_path)
    with sqlite3.connect(db_path) as con:
        names = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {
        "dataset_manifest",
        "candle_coverage",
        "artifact_index",
        "outcome_index",
        "search_run",
        "candidate_result",
        "provenance_event",
        "feature_matrix_index",
        "failure_diagnosis",
        "ceiling_result",
        "walkforward_split",
        "learned_policy_candidate",
        "policy_decision_trace",
    }.issubset(names)


def test_build_dataset_writes_manifest_and_coverage_index(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    raw = tmp_path / "raw"
    _write_verdict_log(
        logs / "verdict_BTCUSDT_2026-05-17.jsonl",
        [{"ts_ms": 59_999, "tf_sec": 60}],
    )
    _write_raw_cache(raw / "BTCUSDT" / "BTCUSDT_1m_0_119999.json", "BTCUSDT", [0])

    db_path = tmp_path / "factory.sqlite"
    rc = mod.run_build_dataset(
        argparse.Namespace(
            db=str(db_path),
            dataset_id="ds_test",
            data_root=str(tmp_path / "factory_data"),
            judge_log_dir=str(logs),
            raw_1m_dir=str(raw),
            recorder_1m_dir=str(tmp_path / "recorder"),
            horizon_bars=1,
            symbols="BTCUSDT",
            days_back=0,
        )
    )
    assert rc == 0
    manifest_path = tmp_path / "factory_data" / "datasets" / "ds_test" / "dataset_manifest.json"
    coverage_path = tmp_path / "factory_data" / "datasets" / "ds_test" / "coverage_report.json"
    assert manifest_path.exists()
    assert coverage_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["dataset_id"] == "ds_test"
    assert manifest["provenance_policy"]["synthetic_stress_official_metrics"] == "forbidden"
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            "SELECT missing_minutes FROM candle_coverage WHERE dataset_id=? AND symbol=?",
            ("ds_test", "BTCUSDT"),
        ).fetchone()
    assert row is not None
    assert row[0] >= 0


def test_build_dataset_defaults_to_completed_utc_days_when_days_back_set(tmp_path: Path) -> None:
    db_path = tmp_path / "factory.sqlite"
    rc = mod.run_build_dataset(
        argparse.Namespace(
            db=str(db_path),
            dataset_id="ds_completed",
            data_root=str(tmp_path / "factory_data"),
            judge_log_dir=str(tmp_path / "logs"),
            raw_1m_dir=str(tmp_path / "raw"),
            recorder_1m_dir=str(tmp_path / "recorder"),
            horizon_bars=12,
            symbols="BTCUSDT",
            days_back=1,
        )
    )
    assert rc == 0
    manifest = json.loads(
        (tmp_path / "factory_data" / "datasets" / "ds_completed" / "dataset_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    coverage = json.loads(
        (tmp_path / "factory_data" / "datasets" / "ds_completed" / "coverage_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["coverage_mode"] == "completed_utc_days"
    assert manifest["completed_utc_window"]["days_back"] == 1
    assert manifest["official_default_days_back"] == 90
    assert coverage["effective_horizon_bars"] == 0
    assert coverage["symbols"]["BTCUSDT"]["required_minutes"] == 1440


def test_official_metrics_reject_synthetic_stress() -> None:
    rows = [
        _make_calibration_row("real", net_return=0.01),
        _make_calibration_row("synthetic", net_return=0.50, provenance_class="synthetic_stress"),
    ]
    with pytest.raises(ValueError, match="non-official provenance"):
        mod.assert_official_metric_rows(rows)

    result = mod.evaluate_candidate(
        rows,
        params={
            "confidence_min": 0.0,
            "symbol": "*",
            "tf_sec": "*",
            "regime": "*",
            "min_spacing_bars": 0,
            "tp_offset_pct": "existing",
            "sl_offset_pct": "existing",
            "hold_horizon_bars": "existing",
        },
        target_win_rate=0.70,
        min_selected=1,
    )
    assert result["selected_count"] == 1
    assert result["positive_net_count"] == 1


def test_deterministic_candidate_search_outputs_are_stable(tmp_path: Path) -> None:
    calibration = tmp_path / "calibration.jsonl"
    rows = [
        _make_calibration_row("a", ts=179_999, confidence=0.9, net_return=0.01),
        _make_calibration_row("b", ts=359_999, confidence=0.7, net_return=-0.02),
        _make_calibration_row("c", ts=539_999, confidence=0.95, net_return=0.03),
    ]
    _write_jsonl(calibration, rows)
    common = {
        "db": str(tmp_path / "factory.sqlite"),
        "dataset_id": "ds",
        "calibration_path": str(calibration),
        "path_diagnostics": None,
        "target_win_rate": 0.70,
        "min_selected": 2,
        "confidence_thresholds": "0.0,0.8",
        "symbols": "*",
        "tf_secs": "*",
        "regimes": "*",
        "min_spacing_bars": "0",
        "tp_offsets": "existing",
        "sl_offsets": "existing",
        "hold_horizons": "existing",
    }
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    rc_a = mod.run_search_candidates(argparse.Namespace(**common, run_id="run_a", output_dir=str(out_a)))
    rc_b = mod.run_search_candidates(argparse.Namespace(**common, run_id="run_b", output_dir=str(out_b)))
    assert rc_a == 0
    assert rc_b == 0
    assert (out_a / "search_results.jsonl").read_text(encoding="utf-8") == (
        out_b / "search_results.jsonl"
    ).read_text(encoding="utf-8")
    summary = json.loads((out_a / "search_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "CANDIDATE_FOUND_SHADOW_ONLY"


def test_candle_row_bar_close_and_ohlc_invariants() -> None:
    assert mod.validate_candle_row(
        {
            "timestamp": 119_999,
            "open": "100",
            "high": "102",
            "low": "99",
            "close": "101",
            "volume": "5",
        }
    ) == []
    errors = mod.validate_candle_row(
        {
            "timestamp": 120_000,
            "open": "100",
            "high": "99",
            "low": "101",
            "close": "100",
            "volume": "-1",
        }
    )
    assert "bar_close_timestamp_not_1m_close" in errors
    assert "ohlc_geometry_invalid" in errors
    assert "negative_volume" in errors


def test_validate_synthetic_requires_tag_and_excludes_from_official_metrics(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic.csv"
    with synthetic.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "provenance_class"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": 59_999,
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100.5",
                "volume": "10",
                "provenance_class": "synthetic_stress",
            }
        )
    out_dir = tmp_path / "out"
    rc = mod.run_validate_synthetic(
        argparse.Namespace(
            db=str(tmp_path / "factory.sqlite"),
            dataset_id="ds",
            run_id="synthetic_run",
            synthetic_path=str(synthetic),
            real_reference_path=None,
            output_dir=str(out_dir),
        )
    )
    assert rc == 0
    report = json.loads((out_dir / "synthetic_validation.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS_STRESS_DATASET"
    assert report["official_metric_eligibility"] == "forbidden"


def test_generate_synthetic_always_tags_stress_provenance(tmp_path: Path) -> None:
    real = tmp_path / "real.csv"
    with real.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "symbol", "tf_sec", "open", "high", "low", "close", "volume"],
            lineterminator="\n",
        )
        writer.writeheader()
        for idx, close in enumerate([100.0, 101.0, 100.5, 102.0]):
            ts = 59_999 + idx * 60_000
            writer.writerow(
                {
                    "timestamp": ts,
                    "symbol": "BTCUSDT",
                    "tf_sec": 60,
                    "open": close - 0.3,
                    "high": close + 0.5,
                    "low": close - 0.7,
                    "close": close,
                    "volume": 10 + idx,
                }
            )
    out = tmp_path / "synthetic.csv"
    rc = mod.run_generate_synthetic(
        argparse.Namespace(
            db=str(tmp_path / "factory.sqlite"),
            dataset_id="ds",
            run_id="synthetic_gen",
            real_reference_path=str(real),
            output_path=str(out),
            rows=5,
            seed=123,
            start_timestamp=None,
        )
    )
    assert rc == 0
    generated = list(csv.DictReader(out.open("r", encoding="utf-8", newline="")))
    assert len(generated) == 5
    assert {row["provenance_class"] for row in generated} == {"synthetic_stress"}
    assert all(mod.validate_candle_row(row) == [] for row in generated)
    manifest = json.loads((tmp_path / "synthetic.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["official_metric_eligibility"] == "forbidden"


def test_report_returns_insufficient_evidence_without_passing_candidate() -> None:
    text = mod.render_factory_report(
        dataset_manifest={"dataset_id": "ds", "status": "missing_candles", "universe": ["BTCUSDT"]},
        coverage_report={"totals": {"required_minutes": 10, "present_minutes": 1, "missing_minutes": 9}},
        search_summary={"candidate_count": 1, "pass_count": 0, "target_win_rate": 0.7, "status": "INSUFFICIENT_EVIDENCE"},
    )
    assert "Executive verdict: INSUFFICIENT_EVIDENCE" in text
    assert "## FACTS" in text
    assert "## INFERENCES" in text
    assert "## ASSUMPTIONS" in text
    assert "## UNKNOWNS" in text
    assert "does not authorize live admission" in text


def test_judge_authority_boundary_still_rejects_non_shadow_modes() -> None:
    assert JudgeCortexConfig(mode="off").mode == "off"
    assert JudgeCortexConfig(mode="shadow").mode == "shadow"
    with pytest.raises(ValueError, match="not admitted"):
        JudgeCortexConfig(mode="hybrid_advisory")
    with pytest.raises(ValueError, match="not admitted"):
        JudgeCortexConfig(mode="guarded_entry_authority")


def test_failure_taxonomy_labels_fee_slippage_and_confidence() -> None:
    failure, tags = mod.classify_failure(
        {
            "entry_verdict": "OPEN_LONG",
            "optimal_action": "OPEN_LONG",
            "confidence": 0.9,
            "raw_return": 0.002,
            "fee_cost": 0.0025,
            "slippage_cost": 0.001,
            "net_return": -0.0015,
            "provenance_class": "replay_derived",
            "regime": "LOW_VOLATILITY",
        },
        {"exit_classification": "TIMEOUT"},
    )
    assert failure == "FEE_SLIPPAGE_KILLED"
    assert "CONFIDENCE_MISORDERED" in tags


def test_no_entry_oracle_is_marked_as_tautology_control() -> None:
    rows = [
        {
            "verdict_id": "a",
            "entry_verdict": "OPEN_LONG",
            "net_return": 0.01,
            "raw_return": 0.0135,
            "fee_cost": 0.0025,
            "slippage_cost": 0.001,
            "provenance_class": "replay_derived",
        },
        {
            "verdict_id": "b",
            "entry_verdict": "OPEN_LONG",
            "net_return": -0.01,
            "raw_return": -0.0065,
            "fee_cost": 0.0025,
            "slippage_cost": 0.001,
            "provenance_class": "replay_derived",
        },
    ]
    ceilings = {row["ceiling_name"]: row for row in mod.compute_ceiling_rows(rows, min_selected=1, target_win_rate=0.7)}
    assert ceilings["oracle_no_entry_filter"]["status"] == "TAUTOLOGY_CONTROL"
    assert ceilings["oracle_no_entry_filter"]["official_acceptance_eligible"] is False
    assert ceilings["oracle_no_entry_filter"]["metric_role"] == "tautology_control"


def test_learning_pipeline_fixture_outputs_are_deterministic(tmp_path: Path) -> None:
    dataset_id = "ds_learning"
    data_root = tmp_path / "factory_data"
    dataset_root = data_root / "datasets" / dataset_id
    outcomes_dir = dataset_root / "outcomes"
    outcomes_dir.mkdir(parents=True)
    raw_root = tmp_path / "raw"
    open_times = [idx * 60_000 for idx in range(40)]
    _write_raw_cache(raw_root / "BTCUSDT" / "BTCUSDT_1m_0_2399999.json", "BTCUSDT", open_times)

    calibration = tmp_path / "calibration.jsonl"
    rows = [
        _make_calibration_row("a", ts=20 * 60_000 + 59_999, confidence=0.90, net_return=0.010),
        _make_calibration_row("b", ts=21 * 60_000 + 59_999, confidence=0.10, net_return=-0.020),
        _make_calibration_row("c", ts=22 * 60_000 + 59_999, confidence=0.85, net_return=0.020),
        _make_calibration_row("d", ts=23 * 60_000 + 59_999, confidence=0.80, net_return=0.010),
        _make_calibration_row("e", ts=24 * 60_000 + 59_999, confidence=0.90, net_return=0.030),
        _make_calibration_row("f", ts=25 * 60_000 + 59_999, confidence=0.95, net_return=0.020),
    ]
    _write_jsonl(calibration, rows)
    diagnostics = outcomes_dir / "outcomes_diagnostics.jsonl"
    _write_jsonl(
        diagnostics,
        [
            {
                "verdict_id": row["verdict_id"],
                "correlation_key": {
                    "symbol": row["symbol"],
                    "tf_sec": row["tf_sec"],
                    "bar_close_ts": row["bar_close_ts"],
                },
                "entry_price": 100.0,
                "mfe": 2.0 if row["net_return"] > 0 else 0.1,
                "mae": 0.1 if row["net_return"] > 0 else 2.0,
                "exit_classification": "FILLED_TP" if row["net_return"] > 0 else "FILLED_SL",
                "regime": "LOW_VOLATILITY",
                "regime_confidence": 0.5,
                "regime_stale_bars": 0,
            }
            for row in rows
        ],
    )
    manifest = {
        "schema_version": "alpha_factory_dataset_manifest_v1",
        "dataset_id": dataset_id,
        "status": "ready",
        "universe": ["BTCUSDT"],
    }
    (dataset_root / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    db_path = tmp_path / "factory.sqlite"
    assert mod.run_diagnose_failures(
        argparse.Namespace(
            db=str(db_path),
            dataset_id=dataset_id,
            data_root=str(data_root),
            calibration_path=str(calibration),
            outcomes_diagnostics_path=str(diagnostics),
            output_dir=None,
        )
    ) == 0
    assert mod.run_build_feature_matrix(
        argparse.Namespace(
            db=str(db_path),
            dataset_id=dataset_id,
            data_root=str(data_root),
            calibration_path=str(calibration),
            outcomes_diagnostics_path=str(diagnostics),
            raw_1m_dir=str(raw_root),
            output_dir=None,
        )
    ) == 0
    assert mod.run_compute_ceilings(
        argparse.Namespace(
            db=str(db_path),
            dataset_id=dataset_id,
            run_id="ceil",
            data_root=str(data_root),
            feature_matrix=None,
            target_win_rate=0.70,
            min_selected=2,
            output_dir=None,
        )
    ) == 0
    exit_dir = tmp_path / "exit"
    assert mod.run_search_exit_templates(
        argparse.Namespace(
            db=str(db_path),
            dataset_id=dataset_id,
            run_id="exit",
            data_root=str(data_root),
            feature_matrix=None,
            target_win_rate=0.70,
            min_selected=2,
            confidence_thresholds="0.75",
            tp_pcts="0.005",
            sl_pcts="0.005",
            output_dir=str(exit_dir),
        )
    ) == 0
    confidence_dir = tmp_path / "confidence"
    assert mod.run_calibrate_confidence(
        argparse.Namespace(
            db=str(db_path),
            dataset_id=dataset_id,
            run_id="confidence",
            data_root=str(data_root),
            feature_matrix=None,
            output_dir=str(confidence_dir),
        )
    ) == 0

    walk_a = tmp_path / "walk_a"
    walk_b = tmp_path / "walk_b"
    common_walk = {
        "db": str(db_path),
        "dataset_id": dataset_id,
        "data_root": str(data_root),
        "feature_matrix": None,
        "split_mode": "ratio",
        "train_days": 60,
        "validation_days": 15,
        "holdout_days": 15,
        "target_win_rate": 0.70,
        "min_selected": 2,
        "min_validation_win_rate": 0.65,
        "max_validation_holdout_drop": 0.15,
        "confidence_thresholds": "0.75",
    }
    assert mod.run_walkforward(argparse.Namespace(**common_walk, run_id="walk_a", output_dir=str(walk_a))) == 0
    assert mod.run_walkforward(argparse.Namespace(**common_walk, run_id="walk_b", output_dir=str(walk_b))) == 0
    assert (walk_a / "walkforward_results.jsonl").read_text(encoding="utf-8") == (
        walk_b / "walkforward_results.jsonl"
    ).read_text(encoding="utf-8")
    learned_policy = json.loads((walk_a / "learned_policy.json").read_text(encoding="utf-8"))
    assert learned_policy["status"] == "PASS_SHADOW_CANDIDATE"
    assert learned_policy["authority"] == "shadow_only"

    fixed_window = tmp_path / "walk_fixed"
    fixed_walk = dict(common_walk)
    fixed_walk["split_mode"] = "fixed-days"
    assert mod.run_walkforward(
        argparse.Namespace(**fixed_walk, run_id="walk_fixed", output_dir=str(fixed_window))
    ) == 0
    fixed_policy = json.loads((fixed_window / "learned_policy.json").read_text(encoding="utf-8"))
    assert fixed_policy["status"] == "INSUFFICIENT_DATA_WINDOW"
    assert fixed_policy["data_window_status"] == "INSUFFICIENT_DATA_WINDOW"
    assert "empty_train_split" in fixed_policy["data_window_details"]["reasons"]

    report_path = tmp_path / "ALPHA_SEARCH_LEARNING_REPORT.md"
    assert mod.run_write_learning_report(
        argparse.Namespace(
            db=str(db_path),
            dataset_id=dataset_id,
            run_id="learning_report",
            data_root=str(data_root),
            dataset_manifest=None,
            failure_summary=None,
            ceiling_report=None,
            confidence_summary=str(confidence_dir / "confidence_calibration_summary.json"),
            learned_policy=str(walk_a / "learned_policy.json"),
            output_path=str(report_path),
        )
    ) == 0
    text = report_path.read_text(encoding="utf-8")
    assert "## FACTS" in text
    assert "## INFERENCES" in text
    assert "## ASSUMPTIONS" in text
    assert "## UNKNOWNS" in text
    assert "PASS_SHADOW_CANDIDATE" in text
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM failure_diagnosis").fetchone()[0] == 6
        assert con.execute("SELECT COUNT(*) FROM feature_matrix_index").fetchone()[0] == 6
        assert con.execute("SELECT COUNT(*) FROM policy_decision_trace").fetchone()[0] == 10
