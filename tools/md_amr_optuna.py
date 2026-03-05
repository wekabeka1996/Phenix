from __future__ import annotations

import argparse
from datetime import date
import math
from pathlib import Path
from typing import Iterable, Optional

try:
    from tools.md_amr_data_adapter import load_recorder_900, compute_md_amr_features
    from tools.md_amr_vector_backtest import run_vector_backtest
except ModuleNotFoundError:  # pragma: no cover
    from md_amr_data_adapter import load_recorder_900, compute_md_amr_features
    from md_amr_vector_backtest import run_vector_backtest

try:
    import optuna
except Exception as exc:  # pragma: no cover
    optuna = None
    _OPTUNA_IMPORT_ERROR = exc
else:
    _OPTUNA_IMPORT_ERROR = None


MAX_DD_LIMIT = 0.35
MIN_TRADES = 20
WARMUP_BARS = 96


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _build_param_dict(trial: "optuna.trial.Trial") -> dict:
    hysteresis_mult = trial.suggest_float("hysteresis_mult", 1.05, 1.50)
    w_d1_raw = trial.suggest_float("w_d1_raw", 0.05, 0.70)
    w_h1_raw = trial.suggest_float("w_h1_raw", 0.05, 0.70)
    w_m30_raw = trial.suggest_float("w_m30_raw", 0.05, 0.70)
    w_m15_raw = trial.suggest_float("w_m15_raw", 0.05, 0.70)

    weight_sum = max(w_d1_raw + w_h1_raw + w_m30_raw + w_m15_raw, 1e-9)
    # SSOT: mandatory normalization inside objective.
    w_d1 = w_d1_raw / weight_sum
    w_h1 = w_h1_raw / weight_sum
    w_m30 = w_m30_raw / weight_sum
    w_m15 = w_m15_raw / weight_sum

    return {
        "hysteresis_mult": hysteresis_mult,
        "w_d1": w_d1,
        "w_h1": w_h1,
        "w_m30": w_m30,
        "w_m15": w_m15,
        "threshold_z": trial.suggest_float("threshold_z", 1.5, 3.0),
        "volatility_dampening_factor": trial.suggest_float("volatility_dampening_factor", 0.1, 0.9),
        "thr_base": trial.suggest_float("thr_base", 0.4, 0.7),
        "alpha": trial.suggest_float("alpha", 0.1, 0.5),
        "conf_min": trial.suggest_float("conf_min", 0.15, 0.40),
        "max_hold_bars": 16,
        "fee_bps": 4.0,
        "slippage_buffer_bps": 2.0,
        "scaleout_fraction": 0.5,
    }


def make_objective(df_features, oos_split_ratio: float = 0.30, min_oos_calmar_ratio: float = 0.3):
    def objective(trial: "optuna.trial.Trial") -> float:
        params = _build_param_dict(trial)

        if oos_split_ratio > 0:
            split_idx = int(len(df_features) * (1.0 - oos_split_ratio))
            df_is = df_features.iloc[:split_idx].copy()
            df_oos = df_features.iloc[split_idx:].copy()
        else:
            df_is = df_features
            df_oos = None

        result_is = run_vector_backtest(
            df_is,
            params=params,
            basis_tf_sec=900,
            warmup_bars=WARMUP_BARS,
        )

        trial.set_user_attr("is_net_profit", result_is.net_profit)
        trial.set_user_attr("is_max_dd", result_is.max_dd)
        trial.set_user_attr("is_total_trades", result_is.total_trades)
        trial.set_user_attr("is_calmar_ratio", result_is.calmar_ratio)

        if result_is.max_dd > MAX_DD_LIMIT or result_is.total_trades < MIN_TRADES:
            return -999.0

        if df_oos is not None and not df_oos.empty:
            result_oos = run_vector_backtest(
                df_oos,
                params=params,
                basis_tf_sec=900,
                warmup_bars=WARMUP_BARS,
            )
            trial.set_user_attr("oos_net_profit", result_oos.net_profit)
            trial.set_user_attr("oos_max_dd", result_oos.max_dd)
            trial.set_user_attr("oos_total_trades", result_oos.total_trades)
            trial.set_user_attr("oos_calmar_ratio", result_oos.calmar_ratio)
            
            if result_is.calmar_ratio > 0:
                is_oos_ratio = result_oos.calmar_ratio / result_is.calmar_ratio
                if is_oos_ratio < min_oos_calmar_ratio:
                    trial.set_user_attr("rejected_reason", "oos_overfit")
                    return -999.0

        calmar_ratio = result_is.calmar_ratio
        statistical_weight = math.log(result_is.total_trades / MIN_TRADES + 1.0)
        return float(calmar_ratio * statistical_weight)

    return objective


def run_study(
    *,
    recorder_dir: Path,
    symbols: Iterable[str],
    n_trials: int,
    start: Optional[date] = None,
    end: Optional[date] = None,
    seed: int = 42,
    oos_split_ratio: float = 0.30,
    min_oos_calmar_ratio: float = 0.3,
) -> "optuna.Study":
    if optuna is None:
        raise RuntimeError(f"optuna import failed: {_OPTUNA_IMPORT_ERROR}")

    df = load_recorder_900(recorder_dir, symbols=symbols, start=start, end=end)
    if df.empty:
        raise RuntimeError("No recorder 900s rows found for requested symbols/date range")
    if "segment_id" not in df.columns:
        raise RuntimeError("MD-AMR objective requires segment-aware adapter output (missing segment_id)")
    sort_cols = ["symbol", "segment_id", "timestamp"]
    df = df.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    df_features = compute_md_amr_features(df)

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(make_objective(df_features, oos_split_ratio, min_oos_calmar_ratio), n_trials=n_trials)
    return study


def main() -> int:
    ap = argparse.ArgumentParser(description="Optuna search for MD-AMR V1.1 objective")
    ap.add_argument("--recorder-dir", default="data/recorder")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"])
    ap.add_argument("--start", type=_parse_date, default=None)
    ap.add_argument("--end", type=_parse_date, default=None)
    ap.add_argument("--trials", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--oos-split", type=float, default=0.30)
    ap.add_argument("--min-oos-calmar", type=float, default=0.3)
    args = ap.parse_args()

    study = run_study(
        recorder_dir=Path(args.recorder_dir),
        symbols=args.symbols,
        n_trials=int(args.trials),
        start=args.start,
        end=args.end,
        seed=int(args.seed),
        oos_split_ratio=float(args.oos_split),
        min_oos_calmar_ratio=float(args.min_oos_calmar),
    )
    best = study.best_trial
    print("best_value:", best.value)
    print("best_params:")
    for k in sorted(best.params):
        print(f"  {k}: {best.params[k]}")
    print("best_metrics (IS):")
    for k in ("is_net_profit", "is_max_dd", "is_total_trades", "is_calmar_ratio"):
        print(f"  {k}: {best.user_attrs.get(k)}")
    if args.oos_split > 0:
        print("best_metrics (OOS):")
        for k in ("oos_net_profit", "oos_max_dd", "oos_total_trades", "oos_calmar_ratio"):
            print(f"  {k}: {best.user_attrs.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
