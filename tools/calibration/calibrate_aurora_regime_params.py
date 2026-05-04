#!/usr/bin/env python3
"""Research calibrator for Aurora regime overlays.

This tool explores regime overlay candidates for Aurora regime-detection behavior.
It is not the stage-1 Aurora production threshold calibrator.
"""
from tools.regime_calibration.search import generate_random_overlay, evaluate_overlay, passes_gates
from tools.regime_calibration.metrics import format_confusion_matrix
from tools.regime_calibration.oracle import compute_oracle_labels
from tools.regime_calibration.io import load_recorder_data
import argparse
import sys
import json
import yaml
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Research calibrator for Aurora regime overlays. "
            "Not the stage-1 Aurora production threshold calibrator."
        )
    )
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--tf-sec", type=int, default=300)
    parser.add_argument("--train-split", type=float, default=0.7)
    parser.add_argument("--horizon-bars", type=int, default=12)
    parser.add_argument("--n-trials", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=str, default=None)
    parser.add_argument("--max-uncertain", type=float, default=0.60)
    parser.add_argument("--max-churn-per-1000", type=float, default=50.0)
    parser.add_argument("--min-class-coverage", type=float, default=0.02)

    args = parser.parse_args()

    np.random.seed(args.seed)
    import random
    random.seed(args.seed)

    print(
        f"Loading data from {args.start} to {args.end} for {args.symbols}...")
    df = load_recorder_data(Path("data/recorder"), args.start,
                            args.end, set(args.symbols), args.tf_sec)
    if df.empty:
        print("No data found. Exiting.")
        sys.exit(1)

    print(f"Loaded {len(df)} rows. Computing oracle labels...")
    y_true = compute_oracle_labels(df, args.horizon_bars)

    # Split train/test
    split_idx = int(len(df) * args.train_split)
    df_train = df.iloc[:split_idx].copy()
    y_true_train = y_true.iloc[:split_idx]

    df_test = df.iloc[split_idx:].copy()
    y_true_test = y_true.iloc[split_idx:]

    print("Evaluating baseline on train...")
    baseline_overlay = {}
    base_score, base_metrics, base_pred = evaluate_overlay(
        df_train, y_true_train, baseline_overlay, args.tf_sec)

    best_score = base_score
    best_overlay = baseline_overlay
    best_metrics = base_metrics

    print(
        f"Baseline train score: {base_score:.4f} (macro_f1: {base_metrics['macro_f1']:.4f})")

    valid_trials = 0
    for i in range(args.n_trials):
        cand_overlay = generate_random_overlay()
        score, metrics, _ = evaluate_overlay(
            df_train, y_true_train, cand_overlay, args.tf_sec)

        if passes_gates(metrics, args.max_uncertain, args.max_churn_per_1000, args.min_class_coverage):
            valid_trials += 1
            if score > best_score:
                best_score = score
                best_overlay = cand_overlay
                best_metrics = metrics
                print(
                    f"Trial {i+1}: New best score {score:.4f} (macro_f1: {metrics['macro_f1']:.4f})")

    print(
        f"Completed {args.n_trials} trials. {valid_trials} passed hard gates.")
    print("Evaluating best candidate on test set...")

    base_test_score, base_test_metrics, _ = evaluate_overlay(
        df_test, y_true_test, baseline_overlay, args.tf_sec)
    test_score, test_metrics, _ = evaluate_overlay(
        df_test, y_true_test, best_overlay, args.tf_sec)

    if not args.out_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        syms = "_".join(args.symbols)
        out_dir = Path(f"reports/regime_calibration/{ts}_{syms}")
    else:
        out_dir = Path(args.out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)

    report = f"""# Regime Parameter Calibration Report

## Context
- Calibration class: research.
- Production note: this tool is not the Aurora threshold-surface production calibrator.
- Symbols: {args.symbols}
- Dates: {args.start} to {args.end}
- TF: {args.tf_sec}s
- Horizon: {args.horizon_bars} bars
- Train Split: {args.train_split}
- Seed: {args.seed}
- Trials: {args.n_trials} ({valid_trials} valid)

## Baseline Train Summary
- Score: {base_score:.4f}
- Macro F1: {base_metrics['macro_f1']:.4f}
- Trend F1: {base_metrics['f1_trend']:.4f}
- Uncertain Ratio: {base_metrics['uncertain_ratio']:.4f}
- Churn per 1000: {base_metrics['churn_per_1000']:.4f}
- Avg Regime Duration: {base_metrics['avg_regime_duration_bars']:.1f} bars

## Best Candidate Train Summary
- Score: {best_score:.4f} (Δ {best_score - base_score:+.4f})
- Macro F1: {best_metrics['macro_f1']:.4f} (Δ {best_metrics['macro_f1'] - base_metrics['macro_f1']:+.4f})
- Trend F1: {best_metrics['f1_trend']:.4f}
- Uncertain Ratio: {best_metrics['uncertain_ratio']:.4f}
- Churn per 1000: {best_metrics['churn_per_1000']:.4f}
- Avg Regime Duration: {best_metrics['avg_regime_duration_bars']:.1f} bars

## Baseline Test Summary
- Macro F1: {base_test_metrics['macro_f1']:.4f}
- Uncertain Ratio: {base_test_metrics['uncertain_ratio']:.4f}
- Churn per 1000: {base_test_metrics['churn_per_1000']:.4f}

## Best Candidate Test Summary
- Macro F1: {test_metrics['macro_f1']:.4f} (Δ {test_metrics['macro_f1'] - base_test_metrics['macro_f1']:+.4f})
- Trend F1: {test_metrics['f1_trend']:.4f}
- Uncertain Ratio: {test_metrics['uncertain_ratio']:.4f}
- Churn per 1000: {test_metrics['churn_per_1000']:.4f}

## Confusion Matrix (Train)
```text
{format_confusion_matrix(best_metrics['confusion_matrix'])}
```

## Recommended YAML Overlay
```yaml
{yaml.dump(best_overlay, default_flow_style=False)}
```

## Promotion Note
- Research-only output. Separate active-surface proof and production validation are required before any promotion.
"""

    with open(out_dir / "report.md", "w", encoding='utf-8') as f:
        f.write(report)

    with open(out_dir / "candidate_regime_overlay.yaml", "w", encoding='utf-8') as f:
        yaml.dump(best_overlay, f)

    with open(out_dir / "best_trial.json", "w", encoding='utf-8') as f:
        json.dump({
            "overlay": best_overlay,
            "metrics_train": best_metrics,
            "metrics_test": test_metrics,
            "seed": args.seed
        }, f, indent=2)

    print(f"Done. Report saved to {out_dir}")


if __name__ == "__main__":
    main()
