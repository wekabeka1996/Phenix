from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Any, Tuple

import pandas as pd

from apps.reference.config_loader import get_config
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from vfoundation.core.protocol import Message

from tools.regime_calibration.io import load_recorder_data
from tools.regime_calibration.metrics import compute_metrics, format_confusion_matrix
from tools.regime_calibration.oracle import compute_oracle_labels


class MockFSM:
    def __init__(self):
        self.emissions = []

    def listen(self, *args, **kwargs): pass

    def emit(self, verb, payload, why=None):
        self.emissions.append(payload)


class FakeClock:
    def __init__(self): self.t = 0
    def now_ms(self): return self.t
    def monotonic(self): return self.t / 1000.0


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


@dataclass(frozen=True)
class Split:
    train: pd.DataFrame
    test: pd.DataFrame
    train_days: list[str]
    test_days: list[str]


def evaluate_overlay(
    df: pd.DataFrame,
    y_true: pd.Series,
    overlay: Dict[str, Any],
    basis_tf_sec: int
) -> Tuple[float, Dict[str, Any], pd.Series]:
    """
    Evaluates a set of parameters on the given dataframe.
    Returns: (score, metrics_dict, y_pred)
    """
    base_cfg = get_config()
    cfg_dict = base_cfg.model_dump()

    def set_path(d, path, val):
        parts = path.split('.')
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = val

    for k, v in overlay.items():
        set_path(cfg_dict, k, v)

    from apps.reference.config_models import AuroraConfig as PydanticAuroraConfig
    try:
        new_cfg = PydanticAuroraConfig(**cfg_dict)
    except Exception:
        # Invalid configuration
        preds = pd.Series(['UNCERTAIN']*len(df), index=df.index)
        return -1000.0, compute_metrics(y_true.to_numpy(), preds.to_numpy()), preds

    fsm = MockFSM()
    clock = FakeClock()
    detector = RegimeDetector(new_cfg, fsm, clock=clock)

    preds = []
    for idx, row in df.iterrows():
        clock.t = int(row['timestamp']) if pd.notnull(row['timestamp']) else 0

        features = {'price': float(row['close'])}
        if 'high' in row:
            features['high'] = float(row['high'])
        if 'low' in row:
            features['low'] = float(row['low'])

        # Inject SMAs if available in logs
        if 'feat_sma_short' in row and pd.notnull(row['feat_sma_short']):
            features['sma_short'] = float(row['feat_sma_short'])
        if 'feat_sma_long' in row and pd.notnull(row['feat_sma_long']):
            features['sma_long'] = float(row['feat_sma_long'])

        msg = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="tools.regime_calibration.search",
            dst="any",
            pld={
                "symbol": row['symbol'],
                "ts": clock.t,
                "tf_sec": basis_tf_sec,
                "features": features
            }
        )
        detector.handle_event(msg)

        if fsm.emissions:
            preds.append(fsm.emissions[-1].get('regime', 'UNCERTAIN'))
        else:
            preds.append('UNCERTAIN')

    y_pred = pd.Series(preds, index=df.index)

    # Align and calculate metrics
    # Drop where y_true is UNCERTAIN from macro_f1 calculation?
    # Our compute_metrics function handles UNCERTAIN correctly.
    metrics = compute_metrics(y_true.to_numpy(), y_pred.to_numpy())

    # Calculate objective score
    # score = +1.0*macro_f1 + 0.5*balanced_accuracy - 0.8*uncertain_ratio - 0.5*(churn_per_1000/1000)
    score = (
        1.0 * metrics['macro_f1']
        - 0.8 * metrics['uncertain_ratio']
        - 0.5 * (metrics['churn_per_1000'] / 1000.0)
    )

    return score, metrics, y_pred


def generate_random_overlay() -> Dict[str, Any]:
    short = random.randint(3, 20)
    long_p = random.randint(max(10, short + 2), 80)

    return {
        "uncertain_cutoff": round(random.uniform(0.40, 0.80), 2),
        "hysteresis_bars": random.randint(1, 30),
        "models.sma_trend.sma_short_period": short,
        "models.sma_trend.sma_long_period": long_p,
        "models.sma_trend.confidence_multiplier": round(random.uniform(0.8, 40.0), 1),
        "models.volatility.threshold_multiplier": round(random.uniform(0.8, 2.5), 2),
        "models.volatility.low_vol_multiplier": round(random.uniform(0.3, 1.2), 2),
        "models.mean_reversion.threshold": round(random.uniform(0.001, 0.015), 4),
        "models.mean_reversion.confidence_multiplier": round(random.uniform(10.0, 150.0), 1),
    }


def passes_gates(metrics: Dict[str, Any], max_uncertain: float, max_churn: float, min_coverage: float) -> bool:
    if metrics['uncertain_ratio'] > max_uncertain:
        return False
    if metrics['churn_per_1000'] > max_churn:
        return False

    for cls in ['TREND_UP', 'TREND_DOWN', 'HIGH_VOLATILITY', 'LOW_VOLATILITY', 'MEAN_REVERSION']:
        if cls in metrics['coverages']:
            if metrics['coverages'][cls] < min_coverage:
                return False

    return True


def _split_by_day(df: pd.DataFrame, *, train_frac: float) -> Split:
    if "datetime" in df.columns:
        # recorder uses ISO datetime with a date prefix, use that for split if available
        day_series = df["datetime"].astype(str).str.slice(0, 10)
    else:
        # fallback to timestamp-derived day (less readable)
        day_series = df["timestamp"].astype(str)
    df = df.copy()
    df["__day"] = day_series

    days = sorted(set(df["__day"].astype(str).tolist()))
    if len(days) < 2:
        return Split(train=df, test=df.iloc[0:0].copy(), train_days=days, test_days=[])

    if not (0.0 < train_frac < 1.0):
        raise ValueError("train_frac must be between 0 and 1 (exclusive).")

    split_idx = int(len(days) * train_frac)
    split_idx = max(1, min(len(days) - 1, split_idx))
    train_days = days[:split_idx]
    test_days = days[split_idx:]

    train = df[df["__day"].astype(str).isin(train_days)].copy()
    test = df[df["__day"].astype(str).isin(test_days)].copy()
    return Split(train=train, test=test, train_days=train_days, test_days=test_days)


def _compute_y_true(df: pd.DataFrame, *, horizon_bars: int) -> pd.Series:
    # compute_oracle_labels writes into a numpy array indexed by df.index values,
    # so we require a 0..N-1 RangeIndex.
    df0 = df.reset_index(drop=True)
    y_true = compute_oracle_labels(df0, horizon_bars=horizon_bars)
    return y_true.fillna("UNCERTAIN").astype(str)


def _eval(df: pd.DataFrame, *, overlay: Dict[str, Any], tf_sec: int, horizon_bars: int) -> tuple[float, Dict[str, Any]]:
    df0 = df.reset_index(drop=True)
    y_true = _compute_y_true(df0, horizon_bars=horizon_bars)
    score, metrics, _ = evaluate_overlay(
        df0, y_true, overlay, basis_tf_sec=tf_sec)
    return score, metrics


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Random-search calibration for RegimeDetector (regime.yaml).")
    ap.add_argument("--recorder-dir", default="data/recorder",
                    help="Recorder root dir")
    ap.add_argument("--symbols", nargs="*",
                    default=["BTCUSDT", "SOLUSDT"], help="Symbols to include")
    ap.add_argument("--tf-sec", type=int, default=300,
                    help="Timeframe seconds (basis_tf_sec)")
    ap.add_argument("--start", type=_parse_date, default=None,
                    help="Start date inclusive (YYYY-MM-DD)")
    ap.add_argument("--end", type=_parse_date, default=None,
                    help="End date exclusive (YYYY-MM-DD)")
    ap.add_argument("--horizon-bars", type=int, default=12,
                    help="Oracle lookahead horizon in bars")
    ap.add_argument("--iters", type=int, default=200,
                    help="Random overlays to evaluate")
    ap.add_argument("--seed", type=int, default=1337, help="RNG seed")
    ap.add_argument("--train-frac", type=float, default=0.7,
                    help="Train fraction by day (chronological)")
    ap.add_argument("--max-uncertain", type=float, default=0.55,
                    help="Gate: max uncertain_ratio")
    ap.add_argument("--max-churn", type=float, default=800.0,
                    help="Gate: max churn_per_1000")
    args = ap.parse_args()

    random.seed(int(args.seed))

    symbols = {s.upper() for s in args.symbols}
    df = load_recorder_data(
        Path(args.recorder_dir),
        start=args.start,
        end=args.end,
        symbols=symbols,
        tf_sec=int(args.tf_sec),
    )
    if df.empty:
        raise SystemExit(
            "No recorder rows loaded for requested range/symbols.")

    split = _split_by_day(df, train_frac=float(args.train_frac))
    if split.test.empty:
        raise SystemExit("Not enough unique days to create a test split.")

    baseline_overlay: Dict[str, Any] = {}
    _, m_train0 = _eval(split.train, overlay=baseline_overlay, tf_sec=int(
        args.tf_sec), horizon_bars=int(args.horizon_bars))
    _, m_test0 = _eval(split.test, overlay=baseline_overlay, tf_sec=int(
        args.tf_sec), horizon_bars=int(args.horizon_bars))

    best = {"score": float("-inf"), "overlay": {}, "metrics_train": None}

    for _ in range(int(args.iters)):
        overlay = generate_random_overlay()
        score_train, m_train = _eval(split.train, overlay=overlay, tf_sec=int(
            args.tf_sec), horizon_bars=int(args.horizon_bars))
        if not passes_gates(m_train, max_uncertain=float(args.max_uncertain), max_churn=float(args.max_churn), min_coverage=0.0):
            continue
        if score_train > best["score"]:
            best = {"score": score_train,
                    "overlay": overlay, "metrics_train": m_train}

    if not best["overlay"]:
        raise SystemExit(
            "No overlay passed gates. Try increasing --iters or relaxing gates.")

    # Evaluate test only once for the winning overlay — never inside the selection loop.
    _, m_test_best = _eval(split.test, overlay=best["overlay"], tf_sec=int(
        args.tf_sec), horizon_bars=int(args.horizon_bars))

    print("\n" + "=" * 80)
    print(
        f"Regime calibration (symbols={sorted(symbols)}, tf_sec={int(args.tf_sec)}, horizon_bars={int(args.horizon_bars)})")
    print(
        f"Split: train_days={len(split.train_days)} test_days={len(split.test_days)} (train_frac={float(args.train_frac):.2f})")
    print("-" * 80)
    print("BASELINE (train):", {k: m_train0[k] for k in [
          "macro_f1", "uncertain_ratio", "churn_per_1000", "avg_regime_duration_bars"]})
    print("BASELINE (test): ", {k: m_test0[k] for k in [
          "macro_f1", "uncertain_ratio", "churn_per_1000", "avg_regime_duration_bars"]})
    print("-" * 80)
    print("BEST (train):    ", {k: best["metrics_train"][k] for k in [
          "macro_f1", "uncertain_ratio", "churn_per_1000", "avg_regime_duration_bars"]})
    print("BEST (test):     ", {k: m_test_best[k] for k in [
          "macro_f1", "uncertain_ratio", "churn_per_1000", "avg_regime_duration_bars"]})
    print(f"Objective(train)={best['score']:.6f}")
    print("-" * 80)
    print("Suggested overlay (apply to config/aurora/regime.yaml):")
    for k in sorted(best["overlay"].keys()):
        print(f"  {k}: {best['overlay'][k]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
