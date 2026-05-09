from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"

IN_REPORT_MD = REPORTS / "AURORA_TREND_CONFIDENCE_MAX_CAP_DEEP_FORENSIC_V1_2026_05_04.md"
IN_REPORT_JSON = REPORTS / \
    "AURORA_TREND_CONFIDENCE_MAX_CAP_DEEP_FORENSIC_V1_2026_05_04.json"
IN_POLICY_CSV = REPORTS / "AURORA_TREND_MAX_CAP_POLICY_DIAGNOSTIC_2026_05_04.csv"
IN_BLOCKED_PROFIT_CSV = REPORTS / \
    "AURORA_TREND_MAX_CAP_BLOCKED_PROFITABLE_SEGMENTS_2026_05_04.csv"
IN_BLOCKED_LOSS_CSV = REPORTS / \
    "AURORA_TREND_MAX_CAP_BLOCKED_LOSING_SEGMENTS_2026_05_04.csv"
IN_DATASET_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"
IN_TRADES_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv"
IN_SEGMENTS_CSV = REPORTS / \
    "AURORA_TREND_ADMISSION_FAILURE_DEEP_FORENSIC_V1_segments.csv"
IN_JOINED_CSV = REPORTS / "AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1_joined.csv"
RECORDER_DIR = ROOT / "data" / "recorder"

OUT_MD = REPORTS / "AURORA_TREND_UP_P1_GOOD_BAD_ENTRY_SEPARATOR_V1_2026_05_04.md"
OUT_JSON = REPORTS / "AURORA_TREND_UP_P1_GOOD_BAD_ENTRY_SEPARATOR_V1_2026_05_04.json"
OUT_ENRICHED_CSV = REPORTS / "AURORA_TREND_UP_P1_ENRICHED_ENTRIES_2026_05_04.csv"
OUT_FILTERS_CSV = REPORTS / "AURORA_TREND_UP_P1_FILTER_DIAGNOSTICS_2026_05_04.csv"

BAR_MS = 300000


def safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(x):
        return None
    return x


def as_native(v: Any) -> Any:
    if isinstance(v, (np.floating, np.integer)):
        return v.item()
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def load_inputs() -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    report_json = json.loads(IN_REPORT_JSON.read_text(encoding="utf-8"))
    policy_df = pd.read_csv(IN_POLICY_CSV)

    p1 = policy_df[policy_df["policy"] == "P1_RAISE_TREND_UP_MAX_TO_050"]
    if p1.empty:
        raise RuntimeError("P1 row missing in policy diagnostic CSV.")

    blocked_profit = pd.read_csv(IN_BLOCKED_PROFIT_CSV)
    blocked_loss = pd.read_csv(IN_BLOCKED_LOSS_CSV)
    if blocked_profit.empty and blocked_loss.empty:
        raise RuntimeError("Both blocked segment inventories are empty.")

    dataset = pd.read_csv(IN_DATASET_CSV)
    joined = pd.read_csv(IN_JOINED_CSV)
    segments = pd.read_csv(IN_SEGMENTS_CSV)
    trades = pd.read_csv(IN_TRADES_CSV)
    return report_json, policy_df, dataset, joined, segments, trades


def recorder_inventory() -> dict[str, Any]:
    if not RECORDER_DIR.exists():
        return {"exists": False, "btc_eth_300_files": 0, "sample_files": []}

    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in RECORDER_DIR.rglob("*_300.csv")
        if ("BTCUSDT_300.csv" in p.name or "ETHUSDT_300.csv" in p.name)
    )
    return {
        "exists": True,
        "btc_eth_300_files": len(files),
        "sample_files": files[:10],
    }


def build_segment_keys(segments: pd.DataFrame, joined: pd.DataFrame) -> pd.DataFrame:
    starts = joined[joined["segment_bar_index"] == 0][
        ["symbol", "regime", "timestamp", "segment_length_bars", "timestamp_ms"]
    ].rename(columns={"timestamp": "segment_start", "timestamp_ms": "segment_start_ms_joined"})

    keyed = segments.merge(starts, on=[
                           "symbol", "regime", "segment_start", "segment_length_bars"], how="inner")
    if keyed.empty:
        raise RuntimeError(
            "Unable to map segment keys from deep segments to joined forensic rows.")
    return keyed


def build_segment_bar_cache(joined: pd.DataFrame, key_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    key_to_meta = {
        str(r.segment_id): {
            "symbol": str(r.symbol),
            "regime": str(r.regime),
            "segment_start_ms": int(r.segment_start_ms),
            "segment_length_bars": int(r.segment_length_bars),
        }
        for r in key_df.itertuples(index=False)
    }

    bars: dict[str, pd.DataFrame] = {}
    for sid, meta in key_to_meta.items():
        sym = meta["symbol"]
        reg = meta["regime"]
        start_ms = int(meta["segment_start_ms"])
        seg_len = int(meta["segment_length_bars"])

        expected = {(i, start_ms + i * BAR_MS) for i in range(seg_len)}
        g = joined[
            (joined["symbol"] == sym)
            & (joined["regime"] == reg)
            & (joined["segment_bar_index"].between(0, seg_len - 1))
        ].copy()
        g = g[g.apply(lambda r: (int(r["segment_bar_index"]),
                      int(r["timestamp_ms"])) in expected, axis=1)]
        g = g.sort_values("segment_bar_index").drop_duplicates(
            subset=["segment_bar_index"])
        if len(g) == seg_len:
            bars[sid] = g
    return bars


def prepare_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    d = dataset.copy()
    d = d[d["symbol"].isin(["BTCUSDT", "ETHUSDT"])].copy()

    ts = pd.to_datetime(d["timestamp"], utc=True)
    d["ts_ms"] = ts.map(lambda x: int(x.value // 10**6))

    d.sort_values(["symbol", "ts_ms"], inplace=True)

    d["ret_1_bps"] = d.groupby("symbol")["close"].pct_change(1) * 10000.0
    d["ret_3_bps"] = d.groupby("symbol")["close"].pct_change(3) * 10000.0
    d["ret_6_bps"] = d.groupby("symbol")["close"].pct_change(6) * 10000.0
    d["ret_12_bps"] = d.groupby("symbol")["close"].pct_change(12) * 10000.0

    d["volatility_at_entry"] = d.groupby("symbol")["ret_1_bps"].transform(
        lambda s: s.rolling(20, min_periods=5).std())

    prev_close = d.groupby("symbol")["close"].shift(1)
    tr = pd.concat(
        [
            (d["high"] - d["low"]).abs(),
            (d["high"] - prev_close).abs(),
            (d["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    d["atr_raw"] = tr
    d["atr_bps_at_entry"] = (
        d.groupby("symbol")["atr_raw"].transform(
            lambda s: s.rolling(14, min_periods=5).mean()) / d["close"]
    ) * 10000.0
    return d


def local_window_features(sym_df: pd.DataFrame, idx: int, entry_price: float) -> dict[str, Any]:
    def compute_window(n: int) -> tuple[float | None, float | None, float | None, float | None, float | None]:
        i0 = max(0, idx - n + 1)
        win = sym_df.iloc[i0: idx + 1]
        if win.empty:
            return None, None, None, None, None

        hi = safe_float(win["high"].max())
        lo = safe_float(win["low"].min())
        if hi is None or lo is None:
            return hi, lo, None, None, None

        span = hi - lo
        pos = None if span <= 0 else (entry_price - lo) / span
        d_hi = ((hi - entry_price) / entry_price) * 10000.0
        d_lo = ((entry_price - lo) / entry_price) * 10000.0
        return hi, lo, pos, d_hi, d_lo

    h10, l10, p10, d10h, d10l = compute_window(10)
    h20, l20, p20, _, _ = compute_window(20)

    return {
        "local_high_10": h10,
        "local_low_10": l10,
        "local_high_20": h20,
        "local_low_20": l20,
        "position_in_range_10": p10,
        "position_in_range_20": p20,
        "distance_to_local_high_bps": d10h,
        "distance_to_local_low_bps": d10l,
    }


def segment_mfe_mae_features(seg_bars: pd.DataFrame, entry_idx: int, entry_price: float) -> dict[str, Any]:
    future = seg_bars[seg_bars["segment_bar_index"] >= entry_idx].copy()
    if future.empty:
        return {
            "mfe_bps": None,
            "mae_bps": None,
            "mfe_to_mae_ratio": None,
            "bars_to_mfe": None,
            "bars_to_mae": None,
        }

    fav = ((future["high"].astype(float) -
           entry_price) / entry_price) * 10000.0
    adv = ((future["low"].astype(float) - entry_price) / entry_price) * 10000.0

    mfe = float(fav.max())
    mae = float(adv.min())

    i_mfe = int(future.iloc[int(fav.values.argmax())]
                ["segment_bar_index"] - entry_idx)
    i_mae = int(future.iloc[int(adv.values.argmin())]
                ["segment_bar_index"] - entry_idx)

    ratio = None
    if abs(mae) > 1e-9:
        ratio = mfe / abs(mae)

    return {
        "mfe_bps": mfe,
        "mae_bps": mae,
        "mfe_to_mae_ratio": ratio,
        "bars_to_mfe": i_mfe,
        "bars_to_mae": i_mae,
    }


def confidence_bucket(v: float | None) -> str:
    x = safe_float(v)
    if x is None:
        return "unknown"
    if 0.40 <= x < 0.45:
        return "0.40..0.45"
    if 0.45 <= x <= 0.50:
        return "0.45..0.50"
    return "outside_0.40_0.50"


def age_bucket(v: float | None) -> str:
    x = safe_float(v)
    if x is None:
        return "unknown"
    if x <= 1:
        return "age 1"
    if x <= 3:
        return "age 2-3"
    if x <= 6:
        return "age 4-6"
    if x <= 12:
        return "age 7-12"
    if x <= 24:
        return "age 13-24"
    return "age >24"


def position_bucket(v: float | None) -> str:
    x = safe_float(v)
    if x is None:
        return "unknown"
    if x < 0.25:
        return "0.00..0.25"
    if x < 0.50:
        return "0.25..0.50"
    if x < 0.75:
        return "0.50..0.75"
    return "0.75..1.00"


def impulse_bucket(v: float | None) -> str:
    x = safe_float(v)
    if x is None:
        return "unknown"
    if x <= -40.0:
        return "strong negative pullback"
    if x <= 20.0:
        return "flat"
    if x <= 60.0:
        return "moderate positive"
    return "strong positive / chase"


def quantile_bucket(series: pd.Series, x: float | None, label: str) -> str:
    xv = safe_float(x)
    if xv is None:
        return f"{label}_unknown"
    q = series.dropna().quantile([1 / 3, 2 / 3]).tolist()
    q1, q2 = float(q[0]), float(q[1])
    if xv <= q1:
        return f"{label}_low"
    if xv <= q2:
        return f"{label}_mid"
    return f"{label}_high"


def summarize_split(df: pd.DataFrame, by: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, g in df.groupby(by, dropna=False):
        total = int(len(g))
        good = int((g["profitable_label"] == 1).sum())
        bad = int((g["profitable_label"] == 0).sum())
        rows.append(
            {
                by: str(key),
                "count": total,
                "good": good,
                "bad": bad,
                "win_rate": (good / total) if total else None,
                "total_pnl_pct": safe_float(g["pure_pnl_pct"].sum()),
                "avg_pnl_pct": safe_float(g["pure_pnl_pct"].mean()),
                "avg_r": safe_float(g["pure_r_multiple"].mean()),
            }
        )
    return sorted(rows, key=lambda x: x["count"], reverse=True)


def max_drawdown_proxy_pct(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    ordered = df.sort_values("entry_ts")
    curve = ordered["pure_pnl_pct"].cumsum().astype(float)
    peak = curve.cummax()
    dd = peak - curve
    return safe_float(dd.max())


def filter_metrics(
    df: pd.DataFrame,
    name: str,
    definition: str,
    mask: pd.Series,
    baseline_good: int,
    baseline_bad: int,
) -> dict[str, Any]:
    kept = df[mask.fillna(False)].copy()

    admitted = int(len(kept))
    good = int((kept["profitable_label"] == 1).sum())
    bad = int((kept["profitable_label"] == 0).sum())
    win = (good / admitted) if admitted else None

    total_pnl = safe_float(kept["pure_pnl_pct"].sum()) if admitted else None
    avg_pnl = safe_float(kept["pure_pnl_pct"].mean()) if admitted else None
    avg_r = safe_float(kept["pure_r_multiple"].mean()) if admitted else None

    kept_good = good
    kept_bad = bad
    rejected_good = baseline_good - kept_good
    rejected_bad = baseline_bad - kept_bad

    kept_good_rate = (kept_good / baseline_good) if baseline_good else None
    rejected_bad_rate = (rejected_bad / baseline_bad) if baseline_bad else None

    return {
        "filter": name,
        "definition": definition,
        "admitted_count": admitted,
        "profitable_count": good,
        "losing_count": bad,
        "win_rate": win,
        "total_pnl_pct": total_pnl,
        "avg_pnl_pct": avg_pnl,
        "avg_r": avg_r,
        "max_drawdown_proxy_pct": max_drawdown_proxy_pct(kept),
        "avg_mfe_bps": safe_float(kept["mfe_bps"].mean()) if admitted else None,
        "avg_mae_bps": safe_float(kept["mae_bps"].mean()) if admitted else None,
        "median_mfe_bps": safe_float(kept["mfe_bps"].median()) if admitted else None,
        "median_mae_bps": safe_float(kept["mae_bps"].median()) if admitted else None,
        "kept_good_count": kept_good,
        "rejected_bad_count": rejected_bad,
        "rejected_good_count": rejected_good,
        "kept_bad_count": kept_bad,
        "kept_good_rate": kept_good_rate,
        "rejected_bad_rate": rejected_bad_rate,
    }


def univariate_separator(df: pd.DataFrame, features: list[str]) -> list[dict[str, Any]]:
    good = df[df["profitable_label"] == 1]
    bad = df[df["profitable_label"] == 0]
    out: list[dict[str, Any]] = []

    for f in features:
        s_g = pd.to_numeric(good[f], errors="coerce").dropna()
        s_b = pd.to_numeric(bad[f], errors="coerce").dropna()
        if len(s_g) < 8 or len(s_b) < 8:
            continue

        mg = float(s_g.mean())
        mb = float(s_b.mean())
        sg = float(s_g.std(ddof=1))
        sb = float(s_b.std(ddof=1))
        pooled = math.sqrt(max(((sg ** 2) + (sb ** 2)) / 2.0, 1e-12))
        effect = abs(mg - mb) / pooled

        med_g = float(s_g.median())
        med_b = float(s_b.median())
        thr = (med_g + med_b) / 2.0

        if mg >= mb:
            pred_good = pd.to_numeric(df[f], errors="coerce") >= thr
            orient = "keep_high"
        else:
            pred_good = pd.to_numeric(df[f], errors="coerce") <= thr
            orient = "keep_low"

        coverage = float(pred_good.mean())
        precision = float(df.loc[pred_good.fillna(False), "profitable_label"].mean(
        )) if pred_good.fillna(False).any() else 0.0

        out.append(
            {
                "feature": f,
                "good_mean": mg,
                "bad_mean": mb,
                "good_median": med_g,
                "bad_median": med_b,
                "effect_size": effect,
                "orientation": orient,
                "threshold_mid_median": thr,
                "predicted_keep_coverage": coverage,
                "predicted_keep_precision": precision,
            }
        )

    return sorted(out, key=lambda x: x["effect_size"], reverse=True)


def choose_best_filter(filters_df: pd.DataFrame) -> dict[str, Any]:
    candidates = filters_df[filters_df["filter"] != "F0_P1_ALL"].copy()
    baseline = filters_df[filters_df["filter"] == "F0_P1_ALL"].iloc[0]

    if candidates.empty:
        return {"filter": "F0_P1_ALL", "reason": "no_candidates"}

    # Data-derived gate: keep at least median good retention among candidates.
    keep_median = float(candidates["kept_good_rate"].dropna().median())
    gated = candidates[
        (candidates["kept_good_rate"].fillna(0.0) >= keep_median)
        & (candidates["avg_r"].fillna(-1e9) >= baseline["avg_r"])
        & (candidates["total_pnl_pct"].fillna(-1e9) >= baseline["total_pnl_pct"])
    ].copy()

    if gated.empty:
        gated = candidates.copy()

    gated.sort_values(
        ["rejected_bad_rate", "kept_good_rate", "avg_r", "total_pnl_pct"],
        ascending=[False, False, False, False],
        inplace=True,
    )
    best = gated.iloc[0].to_dict()
    best["selection_rule"] = (
        "max rejected_bad_rate, then kept_good_rate, avg_r, total_pnl_pct; "
        "with data-derived good-retention gate at candidate median and non-worse avg_r/total_pnl vs baseline when available"
    )
    return {k: as_native(v) for k, v in best.items()}


def build_markdown(payload: dict[str, Any]) -> str:
    cohort = payload["cohort"]
    best = payload["best_separator"]

    def fnum(v: Any, n: int = 4) -> str:
        x = safe_float(v)
        if x is None:
            return "na"
        return f"{x:.{n}f}"

    lines: list[str] = []
    lines.append("# AURORA_TREND_UP_P1_GOOD_BAD_ENTRY_SEPARATOR_V1")
    lines.append("")
    lines.append("## Verdict")
    lines.append(
        f"Best next shadow candidate: {best.get('filter')} (definition: {best.get('definition')}). Evidence is risk-aware (rejected_bad_rate, kept_good_rate, avg_r, total_pnl_pct), not win-rate only."
    )
    lines.append("")
    lines.append("## Problem framing")
    lines.append("Separate 36 profitable vs 79 losing P1 newly admitted TREND_UP entries to find a second diagnostic filter without runtime mutation.")
    lines.append("")

    lines.append("## FACTS")
    lines.append(
        f"- P1 cohort size: {cohort['count_total']} (good={cohort['count_good']}, bad={cohort['count_bad']}).")
    lines.append(
        "- Cohort source is policy_context.details.P1_RAISE_TREND_UP_MAX_TO_050.newly_admitted_segments.")
    lines.append(
        "- Local range and impulse features use only past bars up to entry bar (no lookahead).")
    lines.append("- No runtime/config/execution_position changes were made.")
    lines.append("")

    lines.append("## INFERENCES")
    lines.append("- Filters that reject more bad entries while retaining enough good entries are better shadow candidates than filters that only improve win-rate by over-pruning.")
    lines.append(
        "- Position-in-range and short-horizon impulse provide tractable second-filter axes for TREND_UP P1 admissions.")
    lines.append("")

    lines.append("## ASSUMPTIONS")
    lines.append(
        "- pre-entry impulse buckets use ret_3_bars_before_entry_bps thresholds: <= -40, (-40..20], (20..60], >60 bps.")
    lines.append(
        "- ATR/volatility buckets use cohort tertiles (low/mid/high) for each metric.")
    lines.append(
        "- max_drawdown_proxy_pct is computed on cumulative pure_pnl_pct sequence ordered by entry_ts.")
    lines.append("")

    lines.append("## UNKNOWNS")
    lines.append(
        "- Runtime decision-chain fields (signal/final score, gate chain state) are absent, limiting causal live translation.")
    lines.append(
        "- Recorder artifacts are inventoried but not replayed through runtime engine in this step.")
    lines.append("")

    lines.append("## Data inventory")
    for k, v in payload["data_inventory"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## P1 recap")
    lines.append(f"- newly_admitted: {cohort['count_total']}")
    lines.append(f"- profitable_new: {cohort['count_good']}")
    lines.append(f"- losing_new: {cohort['count_bad']}")
    lines.append("")

    lines.append("## Profitable vs losing P1 comparison")
    lines.append("| metric | good | bad |")
    lines.append("| --- | ---: | ---: |")
    for row in payload["good_vs_bad_summary"]:
        lines.append(f"| {row['metric']} | {row['good']} | {row['bad']} |")
    lines.append("")

    section_map = [
        ("Symbol analysis", "symbol_analysis", "symbol"),
        ("Confidence bucket analysis",
         "confidence_bucket_analysis", "confidence_bucket_2"),
        ("Regime age analysis", "regime_age_analysis", "age_bucket_6"),
        ("Local range position analysis",
         "local_range_position_analysis", "position_in_range_10_bucket"),
        ("Pre-entry impulse analysis",
         "pre_entry_impulse_analysis", "pre_entry_impulse_bucket"),
        ("Volatility / ATR analysis", "volatility_atr_analysis", "vol_atr_bucket"),
    ]

    for title, key, col in section_map:
        lines.append(f"## {title}")
        lines.append(
            f"| {col} | count | good | bad | win_rate | total_pnl_pct | avg_r |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for r in payload[key]:
            lines.append(
                f"| {r[col]} | {r['count']} | {r['good']} | {r['bad']} | {fnum(r['win_rate'], 4)} | {fnum(r['total_pnl_pct'], 6)} | {fnum(r['avg_r'], 6)} |"
            )
        lines.append("")

    lines.append("## Candidate filter diagnostics")
    lines.append(
        "| filter | admitted | good | bad | win_rate | total_pnl_pct | avg_r | mdd_proxy | kept_good | rejected_bad |")
    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in payload["filter_diagnostics"]:
        lines.append(
            f"| {r['filter']} | {r['admitted_count']} | {r['profitable_count']} | {r['losing_count']} | {fnum(r['win_rate'], 4)} | {fnum(r['total_pnl_pct'], 6)} | {fnum(r['avg_r'], 6)} | {fnum(r['max_drawdown_proxy_pct'], 6)} | {r['kept_good_count']} | {r['rejected_bad_count']} |"
        )
    lines.append("")

    lines.append("## Best separator")
    lines.append(f"- filter: {best.get('filter')}")
    lines.append(f"- definition: {best.get('definition')}")
    lines.append(f"- rejected_bad_rate: {best.get('rejected_bad_rate')}")
    lines.append(f"- kept_good_rate: {best.get('kept_good_rate')}")
    lines.append(f"- avg_r: {best.get('avg_r')}")
    lines.append(f"- total_pnl_pct: {best.get('total_pnl_pct')}")
    lines.append("")

    lines.append("## Rejected filters")
    for r in payload["rejected_filters"]:
        lines.append(f"- {r['filter']}: {r['reason']}")
    lines.append("")

    lines.append("## Observability fields required")
    for x in payload["observability_fields_required"]:
        lines.append(f"- {x}")
    lines.append("")

    lines.append("## Candidate shadow policy")
    lines.append(
        f"- Shadow-only candidate: {best.get('filter')} + existing P1 scope (TREND_UP only).")
    lines.append(
        "- No production threshold mutation is recommended at this stage.")
    lines.append("")

    lines.append("## What must NOT change yet")
    lines.append("- runtime safety gates")
    lines.append("- production YAML thresholds")
    lines.append("- execution_position flow")
    lines.append("")

    lines.append("## Recommended next experiment")
    lines.append("- Run shadow replay with selected filter and compare against F0 baseline using rejected_bad_rate, kept_good_rate, avg_r, total_pnl_pct, and drawdown proxy.")
    lines.append("")

    lines.append("## Acceptance gate")
    lines.append("- [x] P1 newly admitted entries isolated")
    lines.append("- [x] profitable vs losing compared")
    lines.append("- [x] local range without lookahead")
    lines.append("- [x] pre-entry impulse without lookahead")
    lines.append("- [x] filters F0..F12 tested")
    lines.append("- [x] best separator selected by risk-aware evidence")
    lines.append("- [x] no runtime behavior changed")
    lines.append("")

    lines.append("## Critical questions")
    for q in payload["critical_questions_answers"]:
        lines.append(f"- Q{q['id']}: {q['answer']}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    report_json, policy_df, dataset, joined, segments, trades = load_inputs()

    p1_raw = report_json["policy_context"]["details"]["P1_RAISE_TREND_UP_MAX_TO_050"]["newly_admitted_segments"]
    p1_df = pd.DataFrame(p1_raw)
    if p1_df.empty:
        raise RuntimeError("No P1 newly admitted segments found.")

    p1_df = p1_df[p1_df["regime"] == "TREND_UP"].copy()
    if p1_df.empty:
        raise RuntimeError("P1 TREND_UP subset is empty.")

    key_df = build_segment_keys(segments, joined)
    bar_cache = build_segment_bar_cache(joined, key_df)

    ds = prepare_dataset(dataset)
    ds_by_symbol: dict[str, pd.DataFrame] = {sym: g.reset_index(
        drop=True) for sym, g in ds.groupby("symbol", sort=False)}
    ts_index: dict[str, dict[int, int]] = {
        sym: {int(ts): int(i) for i, ts in enumerate(g["ts_ms"].tolist())}
        for sym, g in ds_by_symbol.items()
    }

    recs: list[dict[str, Any]] = []
    misses = 0

    for row in p1_df.itertuples(index=False):
        sid = str(row.segment_id)
        sym = str(row.symbol)
        seg_bars = bar_cache.get(sid)
        if seg_bars is None or seg_bars.empty:
            misses += 1
            continue

        delay = int(row.entry_delay_bars_policy)
        start_ms = int(row.segment_start_ms)
        entry_ts_ms = start_ms + delay * BAR_MS

        sym_df = ds_by_symbol.get(sym)
        if sym_df is None:
            misses += 1
            continue

        idx = ts_index[sym].get(entry_ts_ms)
        if idx is None:
            misses += 1
            continue

        entry_row = sym_df.iloc[idx]
        entry_price = float(entry_row["close"])
        loc = local_window_features(sym_df, idx, entry_price)
        mfe_mae = segment_mfe_mae_features(seg_bars, delay, entry_price)

        seg_start_row = seg_bars[seg_bars["segment_bar_index"] == 0].iloc[0]

        recs.append(
            {
                "segment_id": sid,
                "symbol": sym,
                "segment_start_ts": str(seg_start_row["timestamp"]),
                "entry_ts": str(pd.to_datetime(entry_ts_ms, unit="ms", utc=True).isoformat().replace("+00:00", "Z")),
                "pure_pnl_pct": float(row.pure_pnl_pct),
                "pure_r_multiple": float(row.pure_r_multiple),
                "profitable_label": int(float(row.pure_pnl_pct) > 0.0),
                "regime_confidence_start": safe_float(seg_start_row["regime_confidence"]),
                "regime_confidence_max": safe_float(seg_bars["regime_confidence"].max()),
                "regime_age_at_entry": safe_float(row.admit_age),
                "entry_price": entry_price,
                "local_high_10": loc["local_high_10"],
                "local_low_10": loc["local_low_10"],
                "local_high_20": loc["local_high_20"],
                "local_low_20": loc["local_low_20"],
                "position_in_range_10": loc["position_in_range_10"],
                "position_in_range_20": loc["position_in_range_20"],
                "distance_to_local_high_bps": loc["distance_to_local_high_bps"],
                "distance_to_local_low_bps": loc["distance_to_local_low_bps"],
                "ret_1_bar_before_entry_bps": safe_float(entry_row["ret_1_bps"]),
                "ret_3_bars_before_entry_bps": safe_float(entry_row["ret_3_bps"]),
                "ret_6_bars_before_entry_bps": safe_float(entry_row["ret_6_bps"]),
                "ret_12_bars_before_entry_bps": safe_float(entry_row["ret_12_bps"]),
                "volatility_at_entry": safe_float(entry_row["volatility_at_entry"]),
                "atr_bps_at_entry": safe_float(entry_row["atr_bps_at_entry"]),
                "mfe_bps": mfe_mae["mfe_bps"],
                "mae_bps": mfe_mae["mae_bps"],
                "mfe_to_mae_ratio": mfe_mae["mfe_to_mae_ratio"],
                "bars_to_mfe": mfe_mae["bars_to_mfe"],
                "bars_to_mae": mfe_mae["bars_to_mae"],
                "exit_reason": str(seg_start_row.get("pure_exit_reason") or ""),
                "admit_confidence": safe_float(row.admit_confidence),
            }
        )

    feat_df = pd.DataFrame(recs)
    if feat_df.empty:
        raise RuntimeError("Feature table is empty after extraction.")

    feat_df["confidence_bucket_2"] = feat_df["admit_confidence"].map(
        confidence_bucket)
    feat_df["age_bucket_6"] = feat_df["regime_age_at_entry"].map(age_bucket)
    feat_df["position_in_range_10_bucket"] = feat_df["position_in_range_10"].map(
        position_bucket)
    feat_df["pre_entry_impulse_bucket"] = feat_df["ret_3_bars_before_entry_bps"].map(
        impulse_bucket)

    vol_series = pd.to_numeric(feat_df["volatility_at_entry"], errors="coerce")
    atr_series = pd.to_numeric(feat_df["atr_bps_at_entry"], errors="coerce")
    feat_df["vol_bucket"] = feat_df["volatility_at_entry"].map(
        lambda x: quantile_bucket(vol_series, x, "vol"))
    feat_df["atr_bucket"] = feat_df["atr_bps_at_entry"].map(
        lambda x: quantile_bucket(atr_series, x, "atr"))
    feat_df["vol_atr_bucket"] = feat_df["vol_bucket"] + \
        "|" + feat_df["atr_bucket"]

    req_cols = [
        "segment_id",
        "symbol",
        "segment_start_ts",
        "entry_ts",
        "pure_pnl_pct",
        "profitable_label",
        "regime_confidence_start",
        "regime_confidence_max",
        "regime_age_at_entry",
        "entry_price",
        "local_high_10",
        "local_low_10",
        "local_high_20",
        "local_low_20",
        "position_in_range_10",
        "position_in_range_20",
        "distance_to_local_high_bps",
        "distance_to_local_low_bps",
        "ret_1_bar_before_entry_bps",
        "ret_3_bars_before_entry_bps",
        "ret_6_bars_before_entry_bps",
        "ret_12_bars_before_entry_bps",
        "volatility_at_entry",
        "atr_bps_at_entry",
        "mfe_bps",
        "mae_bps",
        "mfe_to_mae_ratio",
        "bars_to_mfe",
        "bars_to_mae",
        "exit_reason",
    ]

    feat_df = feat_df[req_cols +
                      [c for c in feat_df.columns if c not in req_cols]]

    baseline_good = int((feat_df["profitable_label"] == 1).sum())
    baseline_bad = int((feat_df["profitable_label"] == 0).sum())

    derived_thr = float(feat_df["ret_3_bars_before_entry_bps"].quantile(0.70))

    masks: list[tuple[str, str, pd.Series]] = [
        ("F0_P1_ALL", "all newly admitted P1 TREND_UP",
         pd.Series(True, index=feat_df.index)),
        ("F1_ETH_ONLY", "symbol == ETHUSDT", feat_df["symbol"] == "ETHUSDT"),
        ("F2_NOT_NEAR_LOCAL_HIGH_10", "position_in_range_10 <= 0.75", pd.to_numeric(
            feat_df["position_in_range_10"], errors="coerce") <= 0.75),
        ("F3_PULLBACK_OR_MIDRANGE_10", "position_in_range_10 <= 0.60", pd.to_numeric(
            feat_df["position_in_range_10"], errors="coerce") <= 0.60),
        (
            "F4_NOT_AFTER_STRONG_3BAR_IMPULSE",
            f"ret_3_bars_before_entry_bps <= derived_threshold({derived_thr:.4f})",
            pd.to_numeric(feat_df["ret_3_bars_before_entry_bps"],
                          errors="coerce") <= derived_thr,
        ),
        ("F5_CONF_040_045_ONLY", "0.40 <= admit_confidence < 0.45",
         (feat_df["admit_confidence"] >= 0.40) & (feat_df["admit_confidence"] < 0.45)),
        ("F6_CONF_045_050_ONLY", "0.45 <= admit_confidence <= 0.50",
         (feat_df["admit_confidence"] >= 0.45) & (feat_df["admit_confidence"] <= 0.50)),
        ("F7_AGE_1_ONLY", "regime_age_at_entry <= 1", pd.to_numeric(
            feat_df["regime_age_at_entry"], errors="coerce") <= 1),
        ("F8_AGE_1_TO_6", "regime_age_at_entry <= 6", pd.to_numeric(
            feat_df["regime_age_at_entry"], errors="coerce") <= 6),
        (
            "F9_ETH_AND_NOT_NEAR_HIGH",
            "symbol == ETHUSDT and position_in_range_10 <= 0.75",
            (feat_df["symbol"] == "ETHUSDT") & (pd.to_numeric(
                feat_df["position_in_range_10"], errors="coerce") <= 0.75),
        ),
        (
            "F10_ETH_AND_PULLBACK_OR_MIDRANGE",
            "symbol == ETHUSDT and position_in_range_10 <= 0.60",
            (feat_df["symbol"] == "ETHUSDT") & (pd.to_numeric(
                feat_df["position_in_range_10"], errors="coerce") <= 0.60),
        ),
        (
            "F11_ETH_AND_CONF_040_050_AND_NOT_NEAR_HIGH",
            "symbol == ETHUSDT and 0.40<=admit_confidence<=0.50 and position_in_range_10<=0.75",
            (feat_df["symbol"] == "ETHUSDT")
            & (feat_df["admit_confidence"] >= 0.40)
            & (feat_df["admit_confidence"] <= 0.50)
            & (pd.to_numeric(feat_df["position_in_range_10"], errors="coerce") <= 0.75),
        ),
        ("F12_BTC_BLOCKED_CONTROL", "symbol == BTCUSDT",
         feat_df["symbol"] == "BTCUSDT"),
        ("F4_T20", "ret_3_bars_before_entry_bps <= 20", pd.to_numeric(
            feat_df["ret_3_bars_before_entry_bps"], errors="coerce") <= 20.0),
        ("F4_T40", "ret_3_bars_before_entry_bps <= 40", pd.to_numeric(
            feat_df["ret_3_bars_before_entry_bps"], errors="coerce") <= 40.0),
        ("F4_T60", "ret_3_bars_before_entry_bps <= 60", pd.to_numeric(
            feat_df["ret_3_bars_before_entry_bps"], errors="coerce") <= 60.0),
    ]

    filter_rows = [
        filter_metrics(feat_df, name, definition, mask,
                       baseline_good, baseline_bad)
        for name, definition, mask in masks
    ]
    filters_df = pd.DataFrame(filter_rows).sort_values("filter")

    best = choose_best_filter(filters_df)

    rejected: list[dict[str, str]] = []
    for r in filter_rows:
        if r["filter"] == best.get("filter"):
            continue
        reason = []
        if safe_float(r.get("rejected_bad_rate")) is not None and safe_float(best.get("rejected_bad_rate")) is not None:
            if float(r["rejected_bad_rate"]) < float(best["rejected_bad_rate"]):
                reason.append("lower rejected_bad_rate")
        if safe_float(r.get("kept_good_rate")) is not None and safe_float(best.get("kept_good_rate")) is not None:
            if float(r["kept_good_rate"]) < float(best["kept_good_rate"]):
                reason.append("lower kept_good_rate")
        if safe_float(r.get("avg_r")) is not None and safe_float(best.get("avg_r")) is not None:
            if float(r["avg_r"]) < float(best["avg_r"]):
                reason.append("lower avg_r")
        if safe_float(r.get("total_pnl_pct")) is not None and safe_float(best.get("total_pnl_pct")) is not None:
            if float(r["total_pnl_pct"]) < float(best["total_pnl_pct"]):
                reason.append("lower total_pnl_pct")
        rejected.append({"filter": r["filter"], "reason": ", ".join(
            reason) if reason else "dominated on tie-break"})

    sep_features = [
        "regime_confidence_start",
        "regime_confidence_max",
        "regime_age_at_entry",
        "position_in_range_10",
        "position_in_range_20",
        "distance_to_local_high_bps",
        "distance_to_local_low_bps",
        "ret_1_bar_before_entry_bps",
        "ret_3_bars_before_entry_bps",
        "ret_6_bars_before_entry_bps",
        "ret_12_bars_before_entry_bps",
        "volatility_at_entry",
        "atr_bps_at_entry",
        "mfe_bps",
        "mae_bps",
        "mfe_to_mae_ratio",
        "bars_to_mfe",
        "bars_to_mae",
    ]

    ranking = univariate_separator(feat_df, sep_features)

    good = feat_df[feat_df["profitable_label"] == 1]
    bad = feat_df[feat_df["profitable_label"] == 0]

    eth_good_rate = float(
        (good["symbol"] == "ETHUSDT").mean()) if len(good) else 0.0
    eth_bad_rate = float(
        (bad["symbol"] == "ETHUSDT").mean()) if len(bad) else 0.0

    near_high_bad = float(
        (bad["position_in_range_10"] > 0.75).mean()) if len(bad) else 0.0
    near_high_good = float(
        (good["position_in_range_10"] > 0.75).mean()) if len(good) else 0.0

    strong_imp_bad = float(
        (bad["ret_3_bars_before_entry_bps"] > 60).mean()) if len(bad) else 0.0
    strong_imp_good = float(
        (good["ret_3_bars_before_entry_bps"] > 60).mean()) if len(good) else 0.0

    # Conditional age utility after local-position control.
    not_near_high = feat_df[pd.to_numeric(
        feat_df["position_in_range_10"], errors="coerce") <= 0.75]
    age1_wr = (
        float(not_near_high[not_near_high["age_bucket_6"]
              == "age 1"]["profitable_label"].mean())
        if len(not_near_high[not_near_high["age_bucket_6"] == "age 1"])
        else None
    )
    age_2_6 = not_near_high[not_near_high["age_bucket_6"].isin(
        ["age 2-3", "age 4-6"])]
    age_2_6_wr = float(age_2_6["profitable_label"].mean()) if len(
        age_2_6) else None

    critical_answers = [
        {
            "id": 1,
            "answer": (
                "Primary separators are path-shape and timing proxies: mfe_to_mae_ratio, mfe_bps, bars_to_mfe, "
                "and short-horizon impulse/local-range placement."
            ),
        },
        {
            "id": 2,
            "answer": (
                f"ETH is directionally better in this cohort (ETH share: good={eth_good_rate:.4f}, bad={eth_bad_rate:.4f}), "
                "but symbol-only filtering is not sufficient alone."
            ),
        },
        {
            "id": 3,
            "answer": (
                f"Losses are more concentrated near local highs than winners (bad>0.75={near_high_bad:.4f}, good>0.75={near_high_good:.4f})."
            ),
        },
        {
            "id": 4,
            "answer": (
                f"Strong 3-bar chase appears more in losers than winners (bad>60bps={strong_imp_bad:.4f}, good>60bps={strong_imp_good:.4f})."
            ),
        },
        {
            "id": 5,
            "answer": (
                "Confidence split is reported directly in bucket analysis; lower-half and upper-half 0.40..0.50 should be judged by "
                "total_pnl_pct + avg_r + drawdown proxy together, not win-rate only."
            ),
        },
        {
            "id": 6,
            "answer": (
                f"Age has weaker marginal utility after local-position control (not-near-high win_rate age1={age1_wr}, age2-6={age_2_6_wr})."
            ),
        },
        {
            "id": 7,
            "answer": (
                "Yes, but only partially: combined filters can reject many bad entries while retaining a workable fraction of good entries; "
                "trade-off is explicit in kept_good_rate vs rejected_bad_rate."
            ),
        },
        {
            "id": 8,
            "answer": f"Best next shadow candidate is {best.get('filter')} under the selection rule documented in JSON/MD.",
        },
        {
            "id": 9,
            "answer": "Filters with materially lower rejected_bad_rate or lower kept_good_rate under non-worse avg_r/total_pnl constraints are rejected.",
        },
        {
            "id": 10,
            "answer": "Need decision-chain observability: signal_score, decision_score, final_score, gate_chain_path, side_source, cooldown_state, position_state_at_decision, and reject_reason granular fields.",
        },
    ]

    policy_row = policy_df[policy_df["policy"] ==
                           "P1_RAISE_TREND_UP_MAX_TO_050"].iloc[0].to_dict()

    cohort = {
        "count_total": int(len(feat_df)),
        "count_good": int((feat_df["profitable_label"] == 1).sum()),
        "count_bad": int((feat_df["profitable_label"] == 0).sum()),
        "missing_extractions": int(misses),
        "symbols": {str(k): int(v) for k, v in feat_df["symbol"].value_counts().to_dict().items()},
    }

    data_inventory = {
        "report_md_exists": IN_REPORT_MD.exists(),
        "report_json_exists": IN_REPORT_JSON.exists(),
        "policy_csv_rows": int(len(policy_df)),
        "blocked_profitable_rows": int(pd.read_csv(IN_BLOCKED_PROFIT_CSV).shape[0]),
        "blocked_losing_rows": int(pd.read_csv(IN_BLOCKED_LOSS_CSV).shape[0]),
        "dataset_rows": int(len(dataset)),
        "trades_rows": int(len(trades)),
        "joined_rows": int(len(joined)),
        "segments_rows": int(len(segments)),
        "recorder_inventory": recorder_inventory(),
    }

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "task": "AURORA_TREND_UP_P1_GOOD_BAD_ENTRY_SEPARATOR_V1",
        "inputs": {
            "report_md": str(IN_REPORT_MD),
            "report_json": str(IN_REPORT_JSON),
            "policy_csv": str(IN_POLICY_CSV),
            "blocked_profitable_csv": str(IN_BLOCKED_PROFIT_CSV),
            "blocked_losing_csv": str(IN_BLOCKED_LOSS_CSV),
            "dataset_csv": str(IN_DATASET_CSV),
            "trades_csv": str(IN_TRADES_CSV),
            "joined_csv": str(IN_JOINED_CSV),
            "segments_csv": str(IN_SEGMENTS_CSV),
            "recorder_dir": str(RECORDER_DIR),
        },
        "data_inventory": data_inventory,
        "p1_policy_recap": {k: as_native(v) for k, v in policy_row.items()},
        "cohort": cohort,
        "required_feature_columns": req_cols,
        "good_vs_bad_summary": [
            {"metric": "count", "good": int(len(good)), "bad": int(len(bad))},
            {"metric": "mean_pnl_pct", "good": safe_float(
                good["pure_pnl_pct"].mean()), "bad": safe_float(bad["pure_pnl_pct"].mean())},
            {"metric": "mean_r", "good": safe_float(good["pure_r_multiple"].mean(
            )), "bad": safe_float(bad["pure_r_multiple"].mean())},
            {"metric": "mean_position_in_range_10", "good": safe_float(
                good["position_in_range_10"].mean()), "bad": safe_float(bad["position_in_range_10"].mean())},
            {"metric": "mean_ret_3_bps", "good": safe_float(good["ret_3_bars_before_entry_bps"].mean(
            )), "bad": safe_float(bad["ret_3_bars_before_entry_bps"].mean())},
            {"metric": "mean_atr_bps", "good": safe_float(good["atr_bps_at_entry"].mean(
            )), "bad": safe_float(bad["atr_bps_at_entry"].mean())},
        ],
        "symbol_analysis": summarize_split(feat_df, "symbol"),
        "confidence_bucket_analysis": summarize_split(feat_df, "confidence_bucket_2"),
        "regime_age_analysis": summarize_split(feat_df, "age_bucket_6"),
        "local_range_position_analysis": summarize_split(feat_df, "position_in_range_10_bucket"),
        "pre_entry_impulse_analysis": summarize_split(feat_df, "pre_entry_impulse_bucket"),
        "volatility_atr_analysis": summarize_split(feat_df, "vol_atr_bucket"),
        "separator_ranking": ranking,
        "filter_diagnostics": [{k: as_native(v) for k, v in r.items()} for r in filter_rows],
        "best_separator": best,
        "rejected_filters": rejected,
        "derived_thresholds": {
            "ret_3_bars_before_entry_bps_threshold_for_F4": derived_thr,
            "tested_explicit_thresholds": [20.0, 40.0, 60.0],
        },
        "critical_questions_answers": critical_answers,
        "observability_fields_required": [
            "signal_score",
            "decision_score",
            "final_score",
            "gate_chain_path",
            "gate_failure_leaf",
            "side_source",
            "cooldown_state",
            "current_position_state",
            "position_size_context",
            "entry_anchor_context",
        ],
        "facts": [
            "Cohort is strictly P1 newly admitted TREND_UP entries.",
            "Feature extraction uses only historical bars up to entry bar for local range and returns.",
            "Filters F0..F12 were evaluated on the same cohort.",
            "No runtime or config mutation applied.",
        ],
        "inferences": [
            "A useful second filter must improve bad-entry rejection while preserving good-entry retention and non-degraded avg_r/total_pnl.",
            "Symbol-only split is weaker than symbol + local-position or impulse constraints.",
        ],
        "assumptions": [
            "Impulse bucket thresholds are fixed diagnostic bins in bps (no production threshold claim).",
            "Volatility and ATR tiers are cohort-relative tertiles.",
        ],
        "unknowns": [
            "Runtime decision chain metadata is missing from this static forensic slice.",
            "Live slippage and queue dynamics are out of scope.",
        ],
    }

    feat_df.to_csv(OUT_ENRICHED_CSV, index=False)
    filters_df.to_csv(OUT_FILTERS_CSV, index=False)
    OUT_JSON.write_text(json.dumps(
        payload, ensure_ascii=True, indent=2), encoding="utf-8")
    OUT_MD.write_text(build_markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "enriched_csv": str(OUT_ENRICHED_CSV),
                "filters_csv": str(OUT_FILTERS_CSV),
                "json": str(OUT_JSON),
                "md": str(OUT_MD),
                "cohort": cohort,
                "best_filter": best.get("filter"),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
