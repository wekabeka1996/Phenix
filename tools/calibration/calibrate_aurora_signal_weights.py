#!/usr/bin/env python3
"""Research-only calibration of legacy Aurora weight surfaces.

This script explores deprecated Aurora scoring surfaces:
- signal_weights
- direction_strength_scoring
- feature_neutrals

It is not the active Aurora production calibration path.
Current live Aurora calibration is threshold-surface only via calibrate_aurora_thresholds.py.

Recorder data is used here to fit legacy direction and strength weights for research overlays.
The script does not prove promotability, does not replay live regime gating, and does not write canonical YAML.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class AuroraScoreCfg:
    weights: dict[str, float]
    neutrals: dict[str, float]
    directional_features: list[str]
    strength_features: list[str]
    essential_features: set[str]
    normalize_mode: str
    delta_price_cap_pct: float
    strength_alpha: float
    strength_cap: float


def _require_ml_deps() -> tuple[Any, Any]:
    try:
        from sklearn.linear_model import Ridge  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            f"scikit-learn is required for legacy Aurora direction fitting. Import error: {exc}"
        ) from exc

    try:
        from scipy.optimize import nnls  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            f"scipy is required for legacy Aurora strength fitting. Import error: {exc}"
        ) from exc

    return Ridge, nnls


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _iter_recorder_csvs(
    *,
    recorder_dir: Path,
    start: date | None,
    end: date | None,
    symbols: set[str],
    tf_sec: int,
) -> list[Path]:
    out: list[Path] = []
    if not recorder_dir.exists():
        raise FileNotFoundError(f"Recorder dir not found: {recorder_dir}")

    for day_dir in sorted([p for p in recorder_dir.iterdir() if p.is_dir()]):
        try:
            day = _parse_date(day_dir.name)
        except ValueError:
            continue

        if start and day < start:
            continue
        if end and day >= end:
            continue

        for sym in sorted(symbols):
            p = day_dir / f"{sym}_{tf_sec}.csv"
            if p.exists():
                out.append(p)

    return out


def _load_recorder(paths: Iterable[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in paths:
        df = pd.read_csv(p)
        if "symbol" not in df.columns:
            # Fallback: infer from filename.
            df["symbol"] = p.name.split("_", 1)[0]
        # Track source day for out-of-sample splits (parent dir is YYYY-MM-DD).
        df["day"] = p.parent.name
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(
            df["timestamp"], errors="coerce").astype("Int64")
    if "tf_sec" in df.columns:
        df["tf_sec"] = pd.to_numeric(
            df["tf_sec"], errors="coerce").astype("Int64")
    return df


def _load_aurora_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "aurora" not in raw:
        raise SystemExit(
            f"Invalid aurora strategy YAML (expected top-level 'aurora'): {path}")
    aurora = raw["aurora"]
    if not isinstance(aurora, dict):
        raise SystemExit(f"Invalid aurora strategy YAML structure: {path}")
    return aurora


def _get_decision_block(aurora: dict[str, Any]) -> dict[str, Any]:
    decision = aurora.get("decision")
    if not isinstance(decision, dict):
        raise SystemExit("aurora.decision missing/invalid in strategy profile")
    return decision


def _get_direction_strength_block(decision: dict[str, Any]) -> dict[str, Any]:
    ds = decision.get("direction_strength_scoring")
    if not isinstance(ds, dict):
        return {}
    return ds


def _pick_effective_weights_neutrals(aurora: dict[str, Any], symbol: str) -> tuple[dict[str, float], dict[str, float]]:
    decision = _get_decision_block(aurora)
    assets = aurora.get("assets") or {}
    asset = assets.get(symbol) or {}

    # Per-symbol override key name in SSOT is `weights:` (not `signal_weights:`)
    w = asset.get("weights") or decision.get("signal_weights") or {}
    n = asset.get("feature_neutrals") or decision.get("feature_neutrals") or {}

    if not isinstance(w, dict) or not w:
        raise SystemExit(
            f"Missing weights for {symbol} (aurora.assets.{symbol}.weights or aurora.decision.signal_weights)")
    if not isinstance(n, dict) or not n:
        raise SystemExit(
            "Missing feature_neutrals (aurora.decision.feature_neutrals)")

    return {str(k): float(v) for k, v in w.items()}, {str(k): float(v) for k, v in n.items()}


def _load_score_cfg(aurora: dict[str, Any], symbol: str) -> AuroraScoreCfg:
    decision = _get_decision_block(aurora)
    signals = decision.get("signals") or {}
    ds = _get_direction_strength_block(decision)

    weights, neutrals = _pick_effective_weights_neutrals(aurora, symbol)

    directional_features = [str(x)
                            for x in (ds.get("directional_features") or [])]
    strength_features = [str(x) for x in (ds.get("strength_features") or [])]
    essential_features = set(str(x)
                             for x in (decision.get("essential_features") or []))
    normalize_mode = str((signals.get("normalize_signals_mode") or "off"))

    delta_price_cap_pct = float(signals.get("delta_price_cap_pct") or 0.0)
    strength_alpha = float(ds.get("strength_alpha") or 0.0)
    strength_cap = float(ds.get("strength_cap") or 1.0)

    return AuroraScoreCfg(
        weights=weights,
        neutrals=neutrals,
        directional_features=directional_features,
        strength_features=strength_features,
        essential_features=essential_features,
        normalize_mode=normalize_mode,
        delta_price_cap_pct=delta_price_cap_pct,
        strength_alpha=strength_alpha,
        strength_cap=strength_cap,
    )


def _clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def _clip11(x: np.ndarray) -> np.ndarray:
    return np.clip(x, -1.0, 1.0)


def _delta_price_norm(*, price: np.ndarray, dp_raw: np.ndarray, cap_pct: float) -> np.ndarray:
    if cap_pct <= 0:
        return np.zeros_like(dp_raw, dtype=float)
    price_safe = np.where(price > 0, price, np.nan)
    dp_pct = dp_raw / price_safe
    dp_pct = np.clip(dp_pct, -cap_pct, cap_pct)
    dp_norm = dp_pct / cap_pct
    return np.nan_to_num(dp_norm, nan=0.0, posinf=0.0, neginf=0.0)


def _feature_centered(
    *,
    raw: np.ndarray,
    neutral: float,
    signed_v2: bool,
    apply_signed_v2: bool,
) -> np.ndarray:
    x = raw.astype(float)
    if signed_v2 and apply_signed_v2:
        if math.isclose(neutral, 0.5):
            x = (2.0 * _clip01(x)) - 0.5
        elif math.isclose(neutral, 0.0):
            x = _clip11(x)
    return x - float(neutral)


def _build_xy(
    df: pd.DataFrame,
    *,
    cfg: AuroraScoreCfg,
    tf_sec: int,
    horizon_bars: int,
) -> tuple[pd.DataFrame, dict[str, np.ndarray], np.ndarray]:
    """
    Returns:
      - filtered df (sorted, with forward return columns)
      - centered feature arrays per feature
      - target y (forward return in bps)
    """
    if df.empty:
        return df, {}, np.array([], dtype=float)

    required_cols = {"symbol", "timestamp", "close", "ready"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(
            f"Recorder CSV missing required columns: {sorted(missing)}")

    df = df.copy()
    df = df[df["tf_sec"].astype(int) == int(tf_sec)]
    df = df[df["ready"] == True]  # noqa: E712 (pandas)

    # Fail-closed: if recorder says not_ready_reasons, drop it (avoid hidden warmup issues).
    if "not_ready_reasons" in df.columns:
        reasons = df["not_ready_reasons"].fillna("").astype(str)
        df = df[reasons.str.len() == 0]

    df["timestamp"] = df["timestamp"].astype("int64")
    df["close"] = pd.to_numeric(df["close"], errors="coerce").astype(float)
    df = df.dropna(subset=["close"])

    df = df.sort_values(["symbol", "timestamp"],
                        kind="mergesort").reset_index(drop=True)

    # Forward return in bps (per symbol)
    fwd = df.groupby("symbol", sort=False)["close"].shift(-horizon_bars)
    y = ((fwd / df["close"]) - 1.0) * 10_000.0
    df["fwd_ret_bps"] = y
    df = df.dropna(subset=["fwd_ret_bps"]).reset_index(drop=True)
    y_arr = df["fwd_ret_bps"].to_numpy(dtype=float)

    price = df["close"].to_numpy(dtype=float)

    centered: dict[str, np.ndarray] = {}
    signed_v2 = cfg.normalize_mode == "signed_v2"
    dir_set = set(cfg.directional_features)

    for feat in sorted(cfg.weights.keys()):
        col = f"feat_{feat}"
        if feat == "delta_price":
            if "feat_delta_price" not in df.columns:
                raise SystemExit(
                    "Recorder CSV missing feat_delta_price for delta_price weight")
            dp_raw = pd.to_numeric(df["feat_delta_price"], errors="coerce").fillna(
                0.0).to_numpy(dtype=float)
            raw = _delta_price_norm(
                price=price, dp_raw=dp_raw, cap_pct=cfg.delta_price_cap_pct)
        elif feat == "absorption":
            # P2: Recorder older slices may have feat_absorption missing or all zeros (mode=disabled).
            # Recompute a proxy consistent with production FE math (without dedup).
            raw_abs: np.ndarray | None = None
            if "feat_absorption" in df.columns:
                raw_abs = pd.to_numeric(df["feat_absorption"], errors="coerce").fillna(
                    0.0).to_numpy(dtype=float)

            recompute = raw_abs is None or float(np.nanstd(raw_abs)) < 1e-12
            if recompute:
                if "feat_tfi" not in df.columns:
                    raise SystemExit(
                        "Recorder CSV missing feat_tfi required to reconstruct absorption")
                if "feat_delta_price" not in df.columns:
                    raise SystemExit(
                        "Recorder CSV missing feat_delta_price required to reconstruct absorption")

                tfi_raw = pd.to_numeric(df["feat_tfi"], errors="coerce").fillna(
                    0.0).to_numpy(dtype=float)
                dp_raw = pd.to_numeric(df["feat_delta_price"], errors="coerce").fillna(
                    0.0).to_numpy(dtype=float)
                dp_norm = _delta_price_norm(
                    price=price, dp_raw=dp_raw, cap_pct=cfg.delta_price_cap_pct)

                conflict = (tfi_raw * dp_norm) < 0.0
                raw = np.zeros_like(tfi_raw, dtype=float)
                raw[conflict] = (
                    -np.sign(tfi_raw[conflict])
                    * np.abs(tfi_raw[conflict])
                    * (1.0 - np.abs(dp_norm[conflict]))
                )
                raw = _clip11(raw)
            else:
                raw = raw_abs
        else:
            if col not in df.columns:
                raise SystemExit(
                    f"Recorder CSV missing required feature column: {col}")
            raw = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)

        neutral = float(cfg.neutrals.get(feat, 0.0))
        centered[feat] = _feature_centered(
            raw=raw,
            neutral=neutral,
            signed_v2=signed_v2,
            apply_signed_v2=(feat in dir_set),
        )

    # Drop any row with non-finite centered values (conservative).
    ok = np.ones(len(df), dtype=bool)
    for arr in centered.values():
        ok &= np.isfinite(arr)
    ok &= np.isfinite(y_arr)

    df = df.loc[ok].reset_index(drop=True)
    y_arr = y_arr[ok]
    for k in list(centered.keys()):
        centered[k] = centered[k][ok]

    return df, centered, y_arr


def _compute_dir_strength_scores(
    *,
    centered: dict[str, np.ndarray],
    cfg: AuroraScoreCfg,
    weights_override: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    weights = weights_override or cfg.weights
    dir_feats = [f for f in cfg.directional_features if f in weights]
    str_feats = [f for f in cfg.strength_features if f in weights]

    def _score(feats: list[str]) -> np.ndarray:
        if not feats:
            return np.zeros(len(next(iter(centered.values()))), dtype=float)
        w = np.array([float(weights[f]) for f in feats], dtype=float)
        x = np.stack([centered[f] for f in feats], axis=1)
        wabs = np.sum(np.abs(w))
        if wabs <= 1e-12:
            return np.zeros(len(x), dtype=float)
        raw = x @ w
        return np.clip(raw / wabs, -1.0, 1.0)

    dir_score = _score(dir_feats)
    str_score = _score(str_feats)
    str_score = np.clip(str_score, 0.0, float(cfg.strength_cap))
    final = dir_score * (1.0 + (float(cfg.strength_alpha) * str_score))
    return dir_score, str_score, final


def _annualized_sharpe(pnl_bps: np.ndarray, *, tf_sec: int) -> float:
    if pnl_bps.size < 2:
        return 0.0
    mu = float(np.mean(pnl_bps))
    sd = float(np.std(pnl_bps, ddof=1))
    if sd <= 1e-12:
        return 0.0
    bars_per_day = 86_400.0 / float(tf_sec)
    ann_factor = math.sqrt(bars_per_day * 365.0)
    return (mu / sd) * ann_factor


def _simulate_threshold_strategy(
    *,
    score: np.ndarray,
    fwd_ret_bps: np.ndarray,
    threshold: float,
    cost_bps_roundtrip: float,
) -> dict[str, float]:
    if score.size == 0:
        return {"trades": 0.0, "total_pnl_bps": 0.0, "avg_pnl_bps": 0.0}

    thr = float(threshold)
    pos = np.where(score >= thr, 1.0, np.where(score <= -thr, -1.0, 0.0))

    # Transaction cost: assume cost_bps_roundtrip applies to enter+exit.
    one_way = float(cost_bps_roundtrip) / 2.0
    prev = np.concatenate([[0.0], pos[:-1]])
    turnover = np.abs(pos - prev)  # 0,1,2
    cost = one_way * turnover

    pnl = (pos * fwd_ret_bps) - cost
    trades = float(np.sum(turnover > 0))
    return {
        "trades": trades,
        "total_pnl_bps": float(np.sum(pnl)),
        "avg_pnl_bps": float(np.mean(pnl)),
    }


def _net_pnl_series(
    *,
    score: np.ndarray,
    fwd_ret_bps: np.ndarray,
    threshold: float,
    cost_bps_roundtrip: float,
) -> np.ndarray:
    thr = float(threshold)
    pos = np.where(score >= thr, 1.0, np.where(score <= -thr, -1.0, 0.0))
    one_way = float(cost_bps_roundtrip) / 2.0
    prev = np.concatenate([[0.0], pos[:-1]])
    turnover = np.abs(pos - prev)
    cost = one_way * turnover
    return (pos * fwd_ret_bps) - cost


def _fit_direction_ridge(X: np.ndarray, y: np.ndarray, *, alpha: float) -> np.ndarray:
    Ridge, _ = _require_ml_deps()
    model = Ridge(alpha=float(alpha), fit_intercept=False)
    model.fit(X, y)
    return np.asarray(model.coef_, dtype=float)


def _normalize_like_baseline(coef: np.ndarray, baseline_weights: np.ndarray) -> np.ndarray:
    base = float(np.sum(np.abs(baseline_weights)))
    denom = float(np.sum(np.abs(coef)))
    if denom <= 1e-12 or base <= 1e-12:
        return coef
    return coef * (base / denom)


def _fmt_weights_yaml(weights: dict[str, float], *, indent: int = 6) -> str:
    pad = " " * indent
    lines = ["weights:"]
    for k, v in sorted(weights.items()):
        lines.append(f"{pad}{k}: {v:.6g}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Research-only Aurora legacy weight calibrator for deprecated signal_weights, "
            "direction_strength_scoring, and feature_neutrals surfaces."
        ),
        epilog=(
            "Active production Aurora calibration is threshold-surface only via "
            "tools/calibration/calibrate_aurora_thresholds.py. Outputs from this script "
            "are not directly promotable and never mutate canonical YAML."
        ),
    )
    ap.add_argument("--aurora-yaml", default="config/aurora/strategies/aurora.yaml",
                    help="Aurora strategy SSOT YAML")
    ap.add_argument("--recorder-dir", default="data/recorder",
                    help="Recorder root dir")
    ap.add_argument("--symbols", nargs="*",
                    default=["BTCUSDT", "ETHUSDT", "SOLUSDT"], help="Symbols to calibrate")
    ap.add_argument("--tf-sec", type=int, default=300,
                    help="Timeframe seconds (e.g., 300)")
    ap.add_argument("--start", type=_parse_date, default=None,
                    help="Start date inclusive (YYYY-MM-DD)")
    ap.add_argument("--end", type=_parse_date, default=None,
                    help="End date exclusive (YYYY-MM-DD)")
    ap.add_argument("--train-frac", type=float, default=0.7,
                    help="Train fraction by unique days (chronological). Remainder is test.")
    ap.add_argument("--horizon-bars", type=int, default=1,
                    help="Forward return horizon in bars")
    ap.add_argument("--ridge-alpha", type=float, default=25.0,
                    help="Ridge alpha for direction fit")
    ap.add_argument("--cost-bps", type=float, default=4.0,
                    help="Round-trip transaction cost in bps (for eval)")
    ap.add_argument("--threshold", type=float, default=None,
                    help="Fixed threshold for eval (default: per-symbol cfg or global)")
    args = ap.parse_args()

    _, nnls = _require_ml_deps()

    print("WARNING: research-only Aurora legacy calibrator.")
    print("WARNING: active production Aurora calibration is threshold-surface only via calibrate_aurora_thresholds.py.")
    print("WARNING: outputs from this script are advisory legacy overlays and are not directly promotable.")

    aurora = _load_aurora_yaml(Path(args.aurora_yaml))
    recorder_dir = Path(args.recorder_dir)
    symbols = {s.upper() for s in args.symbols}

    paths = _iter_recorder_csvs(
        recorder_dir=recorder_dir,
        start=args.start,
        end=args.end,
        symbols=symbols,
        tf_sec=int(args.tf_sec),
    )
    if not paths:
        raise SystemExit(
            "No recorder CSV files found for the requested range/symbols.")

    df_all = _load_recorder(paths)

    for symbol in sorted(symbols):
        cfg = _load_score_cfg(aurora, symbol)

        # Build per-symbol dataset (keep multi-symbol order/joins simple).
        df_sym = df_all[df_all["symbol"].astype(str) == symbol].copy()
        # Out-of-sample split by day (chronological).
        train_frac = float(args.train_frac)
        if not (0.0 < train_frac < 1.0):
            raise SystemExit(
                "--train-frac must be between 0 and 1 (exclusive).")

        days = sorted(
            set(df_sym.get("day", pd.Series(dtype=str)).astype(str).tolist()))
        if len(days) < 2:
            # Fail soft: not enough unique days to split. Fall back to all-in-one.
            df_sym, centered, y = _build_xy(df_sym, cfg=cfg, tf_sec=int(
                args.tf_sec), horizon_bars=int(args.horizon_bars))
            if df_sym.empty:
                print(
                    f"[{symbol}] SKIP: no usable rows after filtering (ready+forward return).")
                continue
            df_train, centered_train, y_train = df_sym, centered, y
            df_test, centered_test, y_test = pd.DataFrame(), {}, np.array([], dtype=float)
            train_days = set(days)
            test_days: set[str] = set()
        else:
            split_idx = int(math.floor(len(days) * train_frac))
            split_idx = max(1, min(len(days) - 1, split_idx))
            train_days = set(days[:split_idx])
            test_days = set(days[split_idx:])

            df_train_raw = df_sym[df_sym["day"].astype(
                str).isin(train_days)].copy()
            df_test_raw = df_sym[df_sym["day"].astype(
                str).isin(test_days)].copy()

            df_train, centered_train, y_train = _build_xy(
                df_train_raw, cfg=cfg, tf_sec=int(args.tf_sec), horizon_bars=int(args.horizon_bars)
            )
            df_test, centered_test, y_test = _build_xy(
                df_test_raw, cfg=cfg, tf_sec=int(args.tf_sec), horizon_bars=int(args.horizon_bars)
            )

            if df_train.empty:
                print(
                    f"[{symbol}] SKIP: train split has no usable rows after filtering.")
                continue
            if df_test.empty:
                print(
                    f"[{symbol}] SKIP: test split has no usable rows after filtering.")
                continue

        # Split feature sets
        dir_feats = [f for f in cfg.directional_features if f in cfg.weights]
        str_feats = [f for f in cfg.strength_features if f in cfg.weights]

        X_dir = np.stack([centered_train[f] for f in dir_feats],
                         axis=1) if dir_feats else np.zeros((len(y_train), 0))
        X_str = np.stack([centered_train[f] for f in str_feats],
                         axis=1) if str_feats else np.zeros((len(y_train), 0))

        # Direction fit: ridge on signed forward return
        w_dir0 = np.array([cfg.weights[f] for f in dir_feats],
                          dtype=float) if dir_feats else np.array([], dtype=float)
        coef_dir = _fit_direction_ridge(X_dir, y_train, alpha=float(
            args.ridge_alpha)) if dir_feats else np.array([], dtype=float)
        coef_dir = _normalize_like_baseline(
            coef_dir, w_dir0) if dir_feats else coef_dir

        # Strength fit: NNLS on absolute forward return
        w_str0 = np.array([cfg.weights[f] for f in str_feats],
                          dtype=float) if str_feats else np.array([], dtype=float)
        coef_str = np.array([], dtype=float)
        if str_feats:
            coef_str, _ = nnls(X_str, np.abs(y_train))
            coef_str = _normalize_like_baseline(coef_str, w_str0)

        new_weights = dict(cfg.weights)
        for f, c in zip(dir_feats, coef_dir):
            new_weights[f] = float(c)
        for f, c in zip(str_feats, coef_str):
            new_weights[f] = float(c)

        # Evaluate baseline vs calibrated (train/test)
        _, _, score0_train = _compute_dir_strength_scores(
            centered=centered_train, cfg=cfg, weights_override=cfg.weights)
        _, _, score1_train = _compute_dir_strength_scores(
            centered=centered_train, cfg=cfg, weights_override=new_weights)
        _, _, score0_test = _compute_dir_strength_scores(
            centered=centered_test, cfg=cfg, weights_override=cfg.weights)
        _, _, score1_test = _compute_dir_strength_scores(
            centered=centered_test, cfg=cfg, weights_override=new_weights)

        # Eval threshold: prefer CLI override, else per-symbol block if present, else global decision.signal_threshold
        threshold = float(
            args.threshold) if args.threshold is not None else None
        if threshold is None:
            # Some symbols have `aurora.assets.<sym>.signal_threshold.value`
            sym_block = (aurora.get("assets") or {}).get(symbol) or {}
            st = sym_block.get("signal_threshold") or {}
            if isinstance(st, dict) and st.get("enabled") and st.get("value") is not None:
                try:
                    threshold = float(st.get("value"))
                except Exception:
                    threshold = None
        if threshold is None:
            decision = _get_decision_block(aurora)
            threshold = float(decision.get("signal_threshold") or 0.12)

        sim0_train = _simulate_threshold_strategy(
            score=score0_train,
            fwd_ret_bps=y_train,
            threshold=threshold,
            cost_bps_roundtrip=float(args.cost_bps),
        )
        sim1_train = _simulate_threshold_strategy(
            score=score1_train,
            fwd_ret_bps=y_train,
            threshold=threshold,
            cost_bps_roundtrip=float(args.cost_bps),
        )

        sim0_test = _simulate_threshold_strategy(
            score=score0_test,
            fwd_ret_bps=y_test,
            threshold=threshold,
            cost_bps_roundtrip=float(args.cost_bps),
        )
        sim1_test = _simulate_threshold_strategy(
            score=score1_test,
            fwd_ret_bps=y_test,
            threshold=threshold,
            cost_bps_roundtrip=float(args.cost_bps),
        )

        # Sharpe (annualized) for quick comparison
        pnl0_train = _net_pnl_series(score=score0_train, fwd_ret_bps=y_train,
                                     threshold=threshold, cost_bps_roundtrip=float(args.cost_bps))
        pnl1_train = _net_pnl_series(score=score1_train, fwd_ret_bps=y_train,
                                     threshold=threshold, cost_bps_roundtrip=float(args.cost_bps))
        sr0_train = _annualized_sharpe(pnl0_train, tf_sec=int(args.tf_sec))
        sr1_train = _annualized_sharpe(pnl1_train, tf_sec=int(args.tf_sec))

        pnl0_test = _net_pnl_series(score=score0_test, fwd_ret_bps=y_test,
                                    threshold=threshold, cost_bps_roundtrip=float(args.cost_bps))
        pnl1_test = _net_pnl_series(score=score1_test, fwd_ret_bps=y_test,
                                    threshold=threshold, cost_bps_roundtrip=float(args.cost_bps))
        sr0_test = _annualized_sharpe(pnl0_test, tf_sec=int(args.tf_sec))
        sr1_test = _annualized_sharpe(pnl1_test, tf_sec=int(args.tf_sec))

        print("\n" + "=" * 80)
        print(
            f"[{symbol}] days_train={len(train_days):,} days_test={len(test_days):,}  "
            f"rows_train={len(df_train):,} rows_test={len(df_test):,}  "
            f"horizon={int(args.horizon_bars)} bars  tf={int(args.tf_sec)}s"
        )
        print(
            f"  eval_threshold={threshold:.6g}  eval_cost_bps_rt={float(args.cost_bps):.3g}")
        print("-" * 80)
        print(
            f"  TRAIN BASELINE: trades={sim0_train['trades']:.0f}  total_pnl_bps={sim0_train['total_pnl_bps']:.2f}  avg_pnl_bps={sim0_train['avg_pnl_bps']:.4f}  sharpe~={sr0_train:.2f}")
        print(
            f"  TRAIN CALIBR.:  trades={sim1_train['trades']:.0f}  total_pnl_bps={sim1_train['total_pnl_bps']:.2f}  avg_pnl_bps={sim1_train['avg_pnl_bps']:.4f}  sharpe~={sr1_train:.2f}")
        print("-" * 80)
        print(
            f"  TEST  BASELINE: trades={sim0_test['trades']:.0f}  total_pnl_bps={sim0_test['total_pnl_bps']:.2f}  avg_pnl_bps={sim0_test['avg_pnl_bps']:.4f}  sharpe~={sr0_test:.2f}")
        print(
            f"  TEST  CALIBR.:  trades={sim1_test['trades']:.0f}  total_pnl_bps={sim1_test['total_pnl_bps']:.2f}  avg_pnl_bps={sim1_test['avg_pnl_bps']:.4f}  sharpe~={sr1_test:.2f}")
        print("-" * 80)
        print("  Suggested research-only legacy weights YAML (candidate overlay only; not direct production calibration):")
        print(_fmt_weights_yaml(
            {k: new_weights[k] for k in sorted(new_weights.keys())}, indent=8))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
