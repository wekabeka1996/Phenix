#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from _decision_ledger_baseline import (
    DEFAULT_DATASET_PATH,
    DEFAULT_LEDGER_PATH,
    DEFAULT_METADATA_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_REPORT_PATH,
    compute_roc_auc,
    load_dataset_frame,
    prepare_dataset,
    precision_at_recall,
    render_table,
    save_dataset_artifacts,
    score_toxic_probability,
    simulate_blocking,
    split_dataset_chronologically,
    tune_threshold,
    build_model_pipeline,
    write_report_json,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and evaluate a simple baseline blocker on the decision ledger.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH,
                        help="Path to decision_ledger_v1.jsonl")
    parser.add_argument("--dataset", type=Path,
                        default=DEFAULT_DATASET_PATH, help="Prepared dataset CSV path")
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA_PATH,
                        help="Prepared dataset metadata JSON path")
    parser.add_argument("--report-output", type=Path,
                        default=DEFAULT_REPORT_PATH, help="JSON report output path")
    parser.add_argument("--model-output", type=Path,
                        default=DEFAULT_MODEL_PATH, help="Serialized baseline model artifact path")
    parser.add_argument("--refresh-dataset", action="store_true",
                        help="Rebuild the prepared dataset before evaluation")
    parser.add_argument("--train-ratio", type=float,
                        default=0.70, help="Chronological train split ratio")
    parser.add_argument("--recall-target", type=float,
                        default=0.20, help="Recall target for precision@recall")
    parser.add_argument("--max-intervention-rate", type=float, default=0.30,
                        help="Maximum allowed block rate during threshold tuning")
    parser.add_argument("--default-block-threshold", type=float, default=0.70,
                        help="Fallback toxic-probability threshold when tuning cannot find a candidate")
    parser.add_argument("--min-real-rows", type=int, default=240,
                        help="Minimum real executed rows before synthetic fallback is disabled")
    parser.add_argument("--synthetic-rows", type=int, default=420,
                        help="Synthetic rows to generate when the live ledger is insufficient")
    parser.add_argument("--seed", type=int, default=7,
                        help="Random seed for synthetic fallback generation")
    parser.add_argument("--toxic-pnl-threshold", type=float, default=0.0,
                        help="Trades with pnl <= threshold are labeled toxic")
    return parser.parse_args()


def _load_or_prepare_dataset(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, Any]]:
    if args.refresh_dataset or not args.dataset.exists():
        result = prepare_dataset(
            ledger_path=args.ledger,
            min_real_rows=args.min_real_rows,
            synthetic_rows=args.synthetic_rows,
            seed=args.seed,
            toxic_pnl_threshold=args.toxic_pnl_threshold,
        )
        save_dataset_artifacts(
            result.frame, result.metadata, args.dataset, args.metadata)
        return result.frame, result.metadata

    dataset = load_dataset_frame(args.dataset)
    if args.metadata.exists():
        with args.metadata.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    else:
        metadata = {
            "total_rows": int(len(dataset)),
            "real_executed_rows": int((dataset["source_kind"] == "real").sum()) if "source_kind" in dataset else 0,
            "synthetic_rows": int((dataset["source_kind"] == "synthetic").sum()) if "source_kind" in dataset else 0,
            "used_synthetic_fallback": bool((dataset["source_kind"] == "synthetic").any()) if "source_kind" in dataset else False,
        }
    return dataset, metadata


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_pct_from_fraction(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def _fmt_pct_value(value: float) -> str:
    return f"{value:.2f}%"


def _fmt_metric(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"{value:.3f}"


def _pass_fail(value: bool) -> str:
    return "PASS" if value else "FAIL"


def main() -> int:
    args = _parse_args()
    dataset, metadata = _load_or_prepare_dataset(args)
    split = split_dataset_chronologically(
        dataset, train_ratio=args.train_ratio)

    X_train = split.train[split.feature_columns]
    y_train = split.train["toxic_label"].astype(int).to_numpy()
    train_pnl = split.train["realized_pnl_net"].astype(float).to_numpy()

    X_test = split.test[split.feature_columns]
    y_test = split.test["toxic_label"].astype(int).to_numpy()
    test_pnl = split.test["realized_pnl_net"].astype(float).to_numpy()

    threshold_fit_cut = int(math.floor(len(split.train) * 0.80))
    threshold_fit_cut = max(1, min(threshold_fit_cut, len(split.train) - 1))
    threshold_fit_frame = split.train.iloc[:threshold_fit_cut].reset_index(
        drop=True)
    threshold_tune_frame = split.train.iloc[threshold_fit_cut:].reset_index(
        drop=True)
    threshold_tuning_mode = "train_tail_holdout"

    can_holdout_tune = (
        len(threshold_fit_frame) >= 20
        and len(threshold_tune_frame) >= 20
        and threshold_fit_frame["toxic_label"].nunique() >= 2
        and threshold_tune_frame["toxic_label"].nunique() >= 2
    )
    if can_holdout_tune:
        threshold_model = build_model_pipeline(
            threshold_fit_frame[split.feature_columns])
        threshold_model.fit(
            threshold_fit_frame[split.feature_columns],
            threshold_fit_frame["toxic_label"].astype(int),
        )
        threshold_toxic_probability = score_toxic_probability(
            threshold_model,
            threshold_tune_frame[split.feature_columns],
        )
        tuned_train_simulation = tune_threshold(
            threshold_tune_frame["realized_pnl_net"].astype(float).to_numpy(),
            threshold_tune_frame["toxic_label"].astype(int).to_numpy(),
            threshold_toxic_probability,
            max_intervention_rate=args.max_intervention_rate,
            default_threshold=args.default_block_threshold,
        )
    else:
        threshold_tuning_mode = "full_train_fallback"
        train_toxic_probability = np.zeros(len(X_train), dtype=float)
        model_for_tuning = build_model_pipeline(X_train)
        model_for_tuning.fit(X_train, y_train)
        train_toxic_probability = score_toxic_probability(
            model_for_tuning, X_train)
        tuned_train_simulation = tune_threshold(
            train_pnl,
            y_train,
            train_toxic_probability,
            max_intervention_rate=args.max_intervention_rate,
            default_threshold=args.default_block_threshold,
        )

    model = build_model_pipeline(X_train)
    model.fit(X_train, y_train)

    threshold_provenance = (
        "training.tail_holdout"
        if threshold_tuning_mode == "train_tail_holdout"
        else "training.calibration_search"
    )
    sentinel_policy = "fail_closed_no_synthetic_flat"

    model_artifact = {
        "artifact_version": "baseline_logreg_v1",
        "model_kind": "sklearn_logistic_regression_pipeline",
        "model": model,
        "feature_columns": list(split.feature_columns),
        "feature_names": list(split.feature_columns),
        "threshold": float(tuned_train_simulation.threshold),
        "threshold_provenance": threshold_provenance,
        "toxic_label": 1,
        "sentinel_policy": sentinel_policy,
        "schema_passport": {
            "passport_id": "neocortex.baseline_model_artifact_schema.v1",
            "threshold_provenance": threshold_provenance,
            "sentinel_policy": sentinel_policy,
        },
        "decision": {
            "allow": "ALLOW",
            "block": "BLOCK",
            "threshold_comparison": "p_toxic > threshold",
        },
        "training": {
            "train_rows": int(len(split.train)),
            "threshold_tuning_mode": threshold_tuning_mode,
            "threshold_tune_rows": int(len(threshold_tune_frame)) if can_holdout_tune else 0,
            "used_synthetic_fallback": bool(metadata.get("used_synthetic_fallback", False)),
        },
    }
    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_artifact, args.model_output)

    test_toxic_probability = score_toxic_probability(model, X_test)
    roc_auc = compute_roc_auc(y_test, test_toxic_probability)
    precision_at_target_recall, precision_threshold = precision_at_recall(
        y_test,
        test_toxic_probability,
        args.recall_target,
    )
    test_simulation = simulate_blocking(
        test_pnl,
        y_test,
        test_toxic_probability,
        tuned_train_simulation.threshold,
    )

    pnl_comparison = pd.DataFrame(
        [
            {
                "policy": "baseline",
                "test_pnl": _fmt_money(test_simulation.baseline_pnl),
                "blocked_trades": 0,
                "budget": "0.00%",
            },
            {
                "policy": "logreg_blocker",
                "test_pnl": _fmt_money(test_simulation.counterfactual_pnl),
                "blocked_trades": test_simulation.blocked_count,
                "budget": _fmt_pct_from_fraction(test_simulation.intervention_rate),
            },
        ]
    )
    metric_summary = pd.DataFrame(
        [
            {
                "roc_auc_toxicity": _fmt_metric(roc_auc),
                "precision_at_recall_0_2": _fmt_metric(precision_at_target_recall),
                "precision_threshold": "n/a" if precision_threshold is None else f"{precision_threshold:.3f}",
                "train_tuned_block_threshold": f"{tuned_train_simulation.threshold:.3f}",
                "threshold_tuning_mode": threshold_tuning_mode,
            }
        ]
    )
    policy_detail = pd.DataFrame(
        [
            {
                "baseline_pnl": _fmt_money(test_simulation.baseline_pnl),
                "classifier_pnl": _fmt_money(test_simulation.counterfactual_pnl),
                "pnl_lift_abs": _fmt_money(test_simulation.pnl_lift_abs),
                "pnl_lift_pct": _fmt_pct_value(test_simulation.pnl_lift_pct),
                "prevented_toxic_loss": _fmt_money(test_simulation.prevented_toxic_loss),
                "missed_good_pnl": _fmt_money(test_simulation.missed_good_pnl),
                "blocked_trade_precision": "n/a" if test_simulation.toxic_block_precision is None else _fmt_pct_from_fraction(test_simulation.toxic_block_precision),
            }
        ]
    )

    pnl_gate_pass = test_simulation.pnl_lift_pct > 5.0
    budget_gate_pass = test_simulation.intervention_rate < args.max_intervention_rate
    gate_summary = pd.DataFrame(
        [
            {
                "criterion": "OOS pnl improvement > 5%",
                "result": _pass_fail(pnl_gate_pass),
            },
            {
                "criterion": "intervention budget < 30%",
                "result": _pass_fail(budget_gate_pass),
            },
        ]
    )
    dataset_summary = pd.DataFrame(
        [
            {
                "total_rows": int(metadata.get("total_rows", len(dataset))),
                "train_rows": int(len(split.train)),
                "test_rows": int(len(split.test)),
                "feature_cols": int(len(split.feature_columns)),
                "real_rows": int(metadata.get("real_executed_rows", 0)),
                "synthetic_rows": int(metadata.get("synthetic_rows", 0)),
                "used_synthetic_fallback": bool(metadata.get("used_synthetic_fallback", False)),
                "threshold_tune_rows": int(len(threshold_tune_frame)) if can_holdout_tune else 0,
                "model_artifact": str(args.model_output),
            }
        ]
    )

    print(render_table("=== Dataset Summary ===", dataset_summary))
    print()
    print(render_table("=== Test PnL Comparison ===", pnl_comparison))
    print()
    print(render_table("=== Test Classification Metrics ===", metric_summary))
    print()
    print(render_table("=== Bounded Controller Detail ===", policy_detail))
    print()
    print(render_table("=== Go / No-Go Gate ===", gate_summary))

    report = {
        "dataset": {
            "total_rows": int(metadata.get("total_rows", len(dataset))),
            "train_rows": int(len(split.train)),
            "test_rows": int(len(split.test)),
            "feature_columns": int(len(split.feature_columns)),
            "real_rows": int(metadata.get("real_executed_rows", 0)),
            "synthetic_rows": int(metadata.get("synthetic_rows", 0)),
            "used_synthetic_fallback": bool(metadata.get("used_synthetic_fallback", False)),
        },
        "metrics": {
            "roc_auc_toxicity": roc_auc,
            "precision_at_recall_0_2": precision_at_target_recall,
            "precision_threshold": precision_threshold,
            "train_tuned_block_threshold": tuned_train_simulation.threshold,
            "threshold_tuning_mode": threshold_tuning_mode,
            "threshold_tune_rows": int(len(threshold_tune_frame)) if can_holdout_tune else 0,
            "model_artifact": str(args.model_output),
        },
        "policy": {
            "baseline_pnl": test_simulation.baseline_pnl,
            "classifier_pnl": test_simulation.counterfactual_pnl,
            "pnl_lift_abs": test_simulation.pnl_lift_abs,
            "pnl_lift_pct": test_simulation.pnl_lift_pct,
            "blocked_trades": test_simulation.blocked_count,
            "intervention_rate": test_simulation.intervention_rate,
            "prevented_toxic_loss": test_simulation.prevented_toxic_loss,
            "missed_good_pnl": test_simulation.missed_good_pnl,
            "blocked_trade_precision": test_simulation.toxic_block_precision,
        },
        "gate": {
            "pnl_improvement_gt_5pct": pnl_gate_pass,
            "budget_lt_30pct": budget_gate_pass,
        },
    }
    write_report_json(args.report_output, report)
    print()
    print(f"Model PKL  : {args.model_output}")
    print(f"Report JSON: {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
