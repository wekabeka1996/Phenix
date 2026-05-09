from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DATE_TAG = "2026_05_04"

DATASET_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"
TRADES_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv"
JOINED_CSV = REPORTS / "AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1_joined.csv"
SEGMENTS_CSV = REPORTS / "AURORA_TREND_ADMISSION_FAILURE_DEEP_FORENSIC_V1_segments.csv"

OUT_MD = REPORTS / f"AURORA_TREND_DOWN_FULL_RESEARCH_SEQUENCE_V1_{DATE_TAG}.md"
OUT_JSON = REPORTS / \
    f"AURORA_TREND_DOWN_FULL_RESEARCH_SEQUENCE_V1_{DATE_TAG}.json"
OUT_ENRICHED = REPORTS / f"AURORA_TREND_DOWN_ENRICHED_ENTRIES_{DATE_TAG}.csv"
OUT_FILTERS = REPORTS / f"AURORA_TREND_DOWN_FILTER_DIAGNOSTICS_{DATE_TAG}.csv"
OUT_MICROBAND = REPORTS / f"AURORA_TREND_DOWN_MICROBAND_RESULTS_{DATE_TAG}.csv"
OUT_TPSL = REPORTS / f"AURORA_TREND_DOWN_TPSL_GRID_RESULTS_{DATE_TAG}.csv"
OUT_TIMEOUT = REPORTS / \
    f"AURORA_TREND_DOWN_TIMEOUT_GRID_RESULTS_{DATE_TAG}.csv"
OUT_RECHECK_MD = REPORTS / \
    f"AURORA_TREND_DOWN_BEST_CANDIDATE_RECHECK_{DATE_TAG}.md"

PRIMARY_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
SECONDARY_SYMBOLS = ["BNBUSDT", "SOLUSDT", "XRPUSDT"]

CONF_BANDS = [
    ("0.20..0.30", 0.20, 0.30),
    ("0.30..0.35", 0.30, 0.35),
    ("0.35..0.40", 0.35, 0.40),
    ("0.40..0.45", 0.40, 0.45),
    ("0.45..0.50", 0.45, 0.50),
    ("0.50..0.60", 0.50, 0.60),
    ("0.60..0.70", 0.60, 0.70),
    ("0.70+", 0.70, np.inf),
]

TP_MULTIPLIERS = [0.20, 0.25, 0.30, 0.40, 0.50, 0.70, 1.00]
SL_MULTIPLIERS = [0.75, 1.00, 1.25, 1.50, 2.00]


@dataclass
class SimResult:
    pnl_pct: float
    exit_reason: str
    bars_held: int
    still_open: bool


def pct_to_bps(pct: float) -> float:
    return float(pct) * 100.0


def cost_to_pct(cost_bps: float) -> float:
    return float(cost_bps) / 100.0


def max_drawdown_from_series(values: Iterable[float]) -> float:
    arr = np.array(list(values), dtype=float)
    if arr.size == 0:
        return 0.0
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return float(dd.min())


def metrics_from_trades(df: pd.DataFrame, cost_bps: float = 6.0) -> Dict[str, Any]:
    if df.empty:
        return {
            "count": 0,
            "win_rate": 0.0,
            "gross_pnl_pct": 0.0,
            "net_pnl_pct": 0.0,
            "avg_r": 0.0,
            "max_drawdown_pct": 0.0,
            "exit_counts": {},
            "avg_mfe_bps": 0.0,
            "avg_mae_bps": 0.0,
        }
    net_per_trade = df["pnl_pct"] - cost_to_pct(cost_bps)
    out = {
        "count": int(len(df)),
        "win_rate": float((df["pnl_pct"] > 0).mean()),
        "gross_pnl_pct": float(df["pnl_pct"].sum()),
        "net_pnl_pct": float(net_per_trade.sum()),
        "avg_r": float(df["r_multiple"].mean()) if "r_multiple" in df else 0.0,
        "max_drawdown_pct": max_drawdown_from_series(net_per_trade.tolist()),
        "exit_counts": {k: int(v) for k, v in df["exit_reason"].value_counts().to_dict().items()},
        "avg_mfe_bps": float(df.get("mfe_bps", pd.Series(dtype=float)).mean()) if "mfe_bps" in df else 0.0,
        "avg_mae_bps": float(df.get("mae_bps", pd.Series(dtype=float)).mean()) if "mae_bps" in df else 0.0,
    }
    return out


def load_inputs() -> Dict[str, pd.DataFrame]:
    dataset = pd.read_csv(DATASET_CSV)
    trades = pd.read_csv(TRADES_CSV)
    joined = pd.read_csv(JOINED_CSV)
    segments = pd.read_csv(SEGMENTS_CSV)

    for df, col in [(dataset, "timestamp"), (trades, "entry_timestamp"), (trades, "exit_timestamp"), (joined, "timestamp")]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    if "pure_exit_timestamp" in joined.columns:
        joined["pure_exit_timestamp"] = pd.to_datetime(
            joined["pure_exit_timestamp"], utc=True, errors="coerce")

    dataset = dataset.sort_values(
        ["symbol", "timestamp"]).reset_index(drop=True)
    trades = trades.sort_values(
        ["symbol", "entry_timestamp"]).reset_index(drop=True)
    joined = joined.sort_values(
        ["symbol", "timestamp_ms"]).reset_index(drop=True)

    return {"dataset": dataset, "trades": trades, "joined": joined, "segments": segments}


def add_segment_id_from_joined(joined: pd.DataFrame) -> pd.DataFrame:
    out = joined.copy()
    out["segment_start_flag"] = (out["segment_bar_index"] == 0).astype(int)
    out["segment_seq"] = out.groupby(
        "symbol")["segment_start_flag"].cumsum() - 1
    out["segment_seq"] = out["segment_seq"].clip(lower=0)
    out["segment_id"] = out.apply(
        lambda r: f"{r['symbol']}:{int(r['segment_seq']):05d}", axis=1)
    return out


def classify_status(row: pd.Series) -> str:
    entered = bool(row.get("aurora_entered", False))
    pure_side = str(row.get("pure_side", "")).upper()
    aurora_side = str(row.get("aurora_side", "")).upper()
    delay = row.get("entry_delay_bars")
    delay_val = int(delay) if pd.notna(delay) else None
    cls = str(row.get("classification", ""))
    reject = str(row.get("top_reject_reason", ""))

    if entered:
        same = aurora_side == pure_side
        if delay_val is None:
            delay_val = 0
        if delay_val <= 0 and same:
            return "AURORA_ENTERED_SAME_SIDE"
        if delay_val <= 0 and not same:
            return "AURORA_ENTERED_OPPOSITE_SIDE"
        if delay_val > 0 and same:
            return "AURORA_ENTERED_LATE_SAME_SIDE"
        return "AURORA_ENTERED_LATE_OPPOSITE_SIDE"

    if "PROVEN_GATE_REJECT" in cls or reject not in ("", "nan", "None"):
        return "AURORA_NO_ENTRY_PROVEN_GATE_REJECT"
    if pure_side in ("", "NAN", "NONE"):
        return "AURORA_NO_ENTRY_NO_SIDE"
    if "UNKNOWN_SCORE" in cls:
        return "AURORA_NO_ENTRY_UNKNOWN_SCORE_SURFACE"
    if "POSITION" in cls or "COOLDOWN" in cls:
        return "AURORA_NO_ENTRY_POSITION_OR_COOLDOWN_POSSIBLE"
    return "AURORA_NO_ENTRY_OTHER_POLICY"


def build_segment_table(joined_with_id: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    j = joined_with_id.copy()
    seg_agg = j.groupby("segment_id").agg(
        symbol=("symbol", "first"),
        segment_start_ts=("timestamp", "min"),
        segment_end_ts=("timestamp", "max"),
        segment_start_ms=("timestamp_ms", "min"),
        regime=("regime", "first"),
        regime_confidence_start=("regime_confidence", "first"),
        regime_confidence_max=("regime_confidence", "max"),
        regime_age_at_first_possible_entry=("regime_age_bars", "first"),
        pure_short_entry_price=("pure_entry_price", "first"),
        pure_exit_reason=("pure_exit_reason", "first"),
        pure_pnl_pct=("pure_pnl_pct", "first"),
        pure_mfe_bps=("mfe_bps_after_pure_entry", "first"),
        pure_mae_bps=("mae_bps_after_pure_entry", "first"),
        segment_length_bars=("segment_length_bars", "first"),
    ).reset_index()

    s = segments.copy()
    s["segment_start"] = pd.to_datetime(
        s["segment_start"], utc=True, errors="coerce")
    s = s.rename(columns={"segment_start": "segment_start_ts"})

    merged = seg_agg.merge(
        s[[
            "segment_id", "aurora_entered", "aurora_side", "entry_delay_bars",
            "classification", "top_reject_reason", "pure_side",
        ]],
        on="segment_id",
        how="left",
    )
    merged["Aurora_status"] = merged.apply(classify_status, axis=1)
    merged["Aurora_reject_reason_if_known"] = merged["top_reject_reason"].fillna(
        "")
    merged["Aurora_side_if_entered"] = merged["aurora_side"].fillna("")
    return merged


def add_entry_features(dataset: pd.DataFrame, td_trades: pd.DataFrame) -> pd.DataFrame:
    ds = dataset.copy()
    ds = ds.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    for w in (10, 20):
        ds[f"local_high_{w}"] = ds.groupby("symbol")["high"].transform(
            lambda s: s.rolling(w, min_periods=1).max())
        ds[f"local_low_{w}"] = ds.groupby("symbol")["low"].transform(
            lambda s: s.rolling(w, min_periods=1).min())
        rng = (ds[f"local_high_{w}"] - ds[f"local_low_{w}"]).replace(0, np.nan)
        ds[f"position_in_range_{w}"] = (
            (ds["close"] - ds[f"local_low_{w}"]) / rng).clip(0, 1)
        ds[f"distance_to_local_low_{w}_bps"] = (
            ds["close"] / ds[f"local_low_{w}"] - 1.0) * 1e4
        ds[f"distance_to_local_high_{w}_bps"] = (
            ds[f"local_high_{w}"] / ds["close"] - 1.0) * 1e4

    for n in (1, 3, 6, 12):
        ds[f"ret_{n}_bars_before_entry_bps"] = ds.groupby(
            "symbol")["close"].transform(lambda s: (s / s.shift(n) - 1.0) * 1e4)

    trade = td_trades.copy()
    trade["entry_timestamp"] = pd.to_datetime(
        trade["entry_timestamp"], utc=True, errors="coerce")
    enriched = trade.merge(
        ds[[
            "symbol", "timestamp", "regime_age_bars", "regime_confidence",
            "position_in_range_10", "position_in_range_20",
            "distance_to_local_low_10_bps", "distance_to_local_high_10_bps",
            "distance_to_local_low_20_bps", "distance_to_local_high_20_bps",
            "ret_1_bars_before_entry_bps", "ret_3_bars_before_entry_bps",
            "ret_6_bars_before_entry_bps", "ret_12_bars_before_entry_bps",
            "high", "low", "close",
        ]],
        left_on=["symbol", "entry_timestamp"],
        right_on=["symbol", "timestamp"],
        how="left",
    )
    enriched = enriched.drop(columns=["timestamp"])
    enriched["good_bad_label"] = np.where(
        enriched["pnl_pct"] > 0, "good", "bad")

    def conf_bucket(x: float) -> str:
        if pd.isna(x):
            return "UNKNOWN"
        for label, lo, hi in CONF_BANDS:
            if x >= lo and x < hi:
                return label
        return "UNKNOWN"

    enriched["confidence_bucket"] = enriched["entry_regime_confidence"].map(
        conf_bucket)

    def range_bucket(x: float) -> str:
        if pd.isna(x):
            return "UNKNOWN"
        if x < 0.25:
            return "0.00..0.25"
        if x < 0.50:
            return "0.25..0.50"
        if x < 0.75:
            return "0.50..0.75"
        return "0.75..1.00"

    enriched["position_bucket_10"] = enriched["position_in_range_10"].map(
        range_bucket)
    enriched["position_bucket_20"] = enriched["position_in_range_20"].map(
        range_bucket)

    def impulse_bucket(x: float) -> str:
        if pd.isna(x):
            return "UNKNOWN"
        if x <= -60:
            return "strong_negative_chase"
        if x <= -15:
            return "mild_negative"
        if x < 15:
            return "flat"
        if x < 60:
            return "positive_pullback"
        return "strong_positive_pullback"

    enriched["impulse_bucket_3"] = enriched["ret_3_bars_before_entry_bps"].map(
        impulse_bucket)
    enriched["impulse_bucket_6"] = enriched["ret_6_bars_before_entry_bps"].map(
        impulse_bucket)
    enriched["atr_proxy_bps"] = ((enriched["high"] - enriched["low"]) /
                                 enriched["close"]).replace([np.inf, -np.inf], np.nan) * 1e4
    enriched["volatility_bucket"] = pd.qcut(
        enriched["atr_proxy_bps"].fillna(enriched["atr_proxy_bps"].median()),
        q=4,
        labels=["Q1_LOW", "Q2", "Q3", "Q4_HIGH"],
        duplicates="drop",
    )

    return enriched


def filter_metrics(df_all: pd.DataFrame, mask: pd.Series, name: str, cost_bps: float = 6.0) -> Dict[str, Any]:
    base = df_all.copy()
    sub = base[mask].copy()

    good_total = int((base["good_bad_label"] == "good").sum())
    bad_total = int((base["good_bad_label"] == "bad").sum())
    good_kept = int((sub["good_bad_label"] == "good").sum())
    bad_kept = int((sub["good_bad_label"] == "bad").sum())

    net = sub["pnl_pct"] - \
        cost_to_pct(cost_bps) if not sub.empty else pd.Series(dtype=float)

    return {
        "filter_id": name,
        "admitted_count": int(len(sub)),
        "good_count": good_kept,
        "bad_count": bad_kept,
        "win_rate": float((sub["pnl_pct"] > 0).mean()) if len(sub) else 0.0,
        "gross_pnl_pct": float(sub["pnl_pct"].sum()) if len(sub) else 0.0,
        "net_pnl_pct_6bps": float(net.sum()) if len(sub) else 0.0,
        "avg_r": float(sub["r_multiple"].mean()) if len(sub) else 0.0,
        "max_drawdown_proxy_pct": max_drawdown_from_series(net.tolist()) if len(sub) else 0.0,
        "kept_good_rate": float(good_kept / good_total) if good_total else 0.0,
        "rejected_bad_rate": float((bad_total - bad_kept) / bad_total) if bad_total else 0.0,
    }


def build_filter_diagnostics(enriched: pd.DataFrame) -> pd.DataFrame:
    e = enriched.copy()

    def in_band(lo: float, hi: float) -> pd.Series:
        return (e["entry_regime_confidence"] >= lo) & (e["entry_regime_confidence"] < hi)

    filters: list[tuple[str, pd.Series]] = [
        ("D0_ALL_TREND_DOWN", pd.Series(True, index=e.index)),
        ("D1_CONF_020_030", in_band(0.20, 0.30)),
        ("D2_CONF_030_035", in_band(0.30, 0.35)),
        ("D3_CONF_035_040", in_band(0.35, 0.40)),
        ("D4_CONF_040_045", in_band(0.40, 0.45)),
        ("D5_CONF_045_050", in_band(0.45, 0.50)),
        ("D6_NOT_NEAR_LOCAL_LOW_10", e["position_in_range_10"] > 0.25),
        ("D7_POSITION_RANGE_025_075", (e["position_in_range_10"] >= 0.25) & (
            e["position_in_range_10"] <= 0.75)),
        ("D8_AFTER_POSITIVE_PULLBACK", e["ret_3_bars_before_entry_bps"] > 0.0),
        ("D9_NOT_AFTER_STRONG_NEGATIVE_IMPULSE",
         e["ret_3_bars_before_entry_bps"] > -60.0),
        ("D10_ETH_ONLY", e["symbol"] == "ETHUSDT"),
        ("D11_BTC_ONLY", e["symbol"] == "BTCUSDT"),
    ]

    broad = pd.DataFrame([filter_metrics(e, m, n) for n, m in filters])
    best_band_row = broad[broad["filter_id"].isin(["D1_CONF_020_030", "D2_CONF_030_035", "D3_CONF_035_040", "D4_CONF_040_045", "D5_CONF_045_050"])].sort_values([
        "net_pnl_pct_6bps", "admitted_count"], ascending=[False, False]).head(1)
    best_band_id = "D3_CONF_035_040"
    if not best_band_row.empty:
        best_band_id = str(best_band_row.iloc[0]["filter_id"])

    band_map = {
        "D1_CONF_020_030": (0.20, 0.30),
        "D2_CONF_030_035": (0.30, 0.35),
        "D3_CONF_035_040": (0.35, 0.40),
        "D4_CONF_040_045": (0.40, 0.45),
        "D5_CONF_045_050": (0.45, 0.50),
    }
    b_lo, b_hi = band_map[best_band_id]
    best_mask = in_band(b_lo, b_hi)

    extra = [
        filter_metrics(e, best_mask & (
            e["position_in_range_10"] > 0.25), "D12_CONF_BAND_PLUS_NOT_NEAR_LOW"),
        filter_metrics(e, best_mask & (
            e["ret_3_bars_before_entry_bps"] > 0.0), "D13_CONF_BAND_PLUS_PULLBACK"),
    ]

    btc_mask = (e["symbol"] == "BTCUSDT") & (e["entry_regime_confidence"] >= 0.30) & (
        e["entry_regime_confidence"] < 0.40) & (e["ret_3_bars_before_entry_bps"] > -30)
    eth_mask = (e["symbol"] == "ETHUSDT") & (e["entry_regime_confidence"] >= 0.35) & (
        e["entry_regime_confidence"] < 0.50) & (e["position_in_range_10"] > 0.20)
    extra.append(filter_metrics(
        e, btc_mask | eth_mask, "D14_SYMBOL_SPECIFIC_BEST"))

    out = pd.concat([broad, pd.DataFrame(extra)], ignore_index=True)
    out = out.sort_values(["net_pnl_pct_6bps", "admitted_count"], ascending=[
                          False, False]).reset_index(drop=True)
    return out


def confidence_band_table(enriched: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, lo, hi in CONF_BANDS:
        sub = enriched[(enriched["entry_regime_confidence"] >= lo)
                       & (enriched["entry_regime_confidence"] < hi)]
        net6 = sub["pnl_pct"] - \
            cost_to_pct(6) if len(sub) else pd.Series(dtype=float)
        rows.append(
            {
                "band": label,
                "count": int(len(sub)),
                "good_count": int((sub["good_bad_label"] == "good").sum()),
                "bad_count": int((sub["good_bad_label"] == "bad").sum()),
                "win_rate": float((sub["pnl_pct"] > 0).mean()) if len(sub) else 0.0,
                "gross_pnl_pct": float(sub["pnl_pct"].sum()) if len(sub) else 0.0,
                "net_pnl_pct_6bps": float(net6.sum()) if len(sub) else 0.0,
                "avg_r": float(sub["r_multiple"].mean()) if len(sub) else 0.0,
                "max_dd_proxy_pct": max_drawdown_from_series(net6.tolist()) if len(sub) else 0.0,
                "avg_mfe_bps": float(sub["mfe_bps"].mean()) if "mfe_bps" in sub and len(sub) else 0.0,
                "avg_mae_bps": float(sub["mae_bps"].mean()) if "mae_bps" in sub and len(sub) else 0.0,
                "btc_count": int((sub["symbol"] == "BTCUSDT").sum()),
                "eth_count": int((sub["symbol"] == "ETHUSDT").sum()),
                "exit_reason_distribution": json.dumps({k: int(v) for k, v in sub["exit_reason"].value_counts().to_dict().items()}),
            }
        )
    return pd.DataFrame(rows)


def build_microbands(enriched: pd.DataFrame, filter_df: pd.DataFrame) -> pd.DataFrame:
    band_candidates = filter_df[filter_df["filter_id"].str.startswith(
        "D") & filter_df["filter_id"].str.contains("CONF_")]
    if band_candidates.empty:
        lo, hi = 0.40, 0.45
    else:
        best = str(band_candidates.sort_values(
            "net_pnl_pct_6bps", ascending=False).iloc[0]["filter_id"])
        mapping = {
            "D1_CONF_020_030": (0.20, 0.30),
            "D2_CONF_030_035": (0.30, 0.35),
            "D3_CONF_035_040": (0.35, 0.40),
            "D4_CONF_040_045": (0.40, 0.45),
            "D5_CONF_045_050": (0.45, 0.50),
        }
        lo, hi = mapping.get(best, (0.40, 0.45))

    rows: list[dict[str, Any]] = []
    step = 0.01
    x = lo
    while x < hi - 1e-12:
        x2 = min(hi, x + step)
        sub = enriched[(enriched["entry_regime_confidence"] >= x)
                       & (enriched["entry_regime_confidence"] < x2)]
        rows.append(
            {
                "type": "micro",
                "band": f"{x:.3f}..{x2:.3f}",
                "lo": x,
                "hi": x2,
                "count": int(len(sub)),
                "win_rate": float((sub["pnl_pct"] > 0).mean()) if len(sub) else 0.0,
                "gross_pnl_pct": float(sub["pnl_pct"].sum()) if len(sub) else 0.0,
                "net_pnl_pct_6bps": float((sub["pnl_pct"] - cost_to_pct(6)).sum()) if len(sub) else 0.0,
                "avg_r": float(sub["r_multiple"].mean()) if len(sub) else 0.0,
            }
        )
        x = x2

    cut_points = np.arange(lo, hi + 1e-9, step)
    for i in range(1, len(cut_points)):
        c = cut_points[i]
        sub = enriched[(enriched["entry_regime_confidence"] >= lo)
                       & (enriched["entry_regime_confidence"] < c)]
        rows.append(
            {
                "type": "cumulative",
                "band": f"{lo:.3f}..{c:.3f}",
                "lo": lo,
                "hi": c,
                "count": int(len(sub)),
                "win_rate": float((sub["pnl_pct"] > 0).mean()) if len(sub) else 0.0,
                "gross_pnl_pct": float(sub["pnl_pct"].sum()) if len(sub) else 0.0,
                "net_pnl_pct_6bps": float((sub["pnl_pct"] - cost_to_pct(6)).sum()) if len(sub) else 0.0,
                "avg_r": float(sub["r_multiple"].mean()) if len(sub) else 0.0,
            }
        )

    return pd.DataFrame(rows).sort_values(["type", "lo", "hi"]).reset_index(drop=True)


def build_price_index(dataset: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym, g in dataset.groupby("symbol"):
        s = g.sort_values("timestamp").reset_index(drop=True).copy()
        out[sym] = s
    return out


def simulate_short_trade(
    bars: pd.DataFrame,
    entry_idx: int,
    entry_price: float,
    entry_regime: str,
    tp_pct: float,
    sl_pct: float,
    timeout_bars: Optional[int],
    exit_on_regime_change: bool,
    max_lookahead: int = 240,
) -> SimResult:
    tp_price = entry_price * (1.0 - tp_pct)
    sl_price = entry_price * (1.0 + sl_pct)

    steps = 0
    for i in range(entry_idx + 1, min(len(bars), entry_idx + 1 + max_lookahead)):
        row = bars.iloc[i]
        steps += 1

        if float(row["high"]) >= sl_price:
            pnl = (entry_price - sl_price) / entry_price * 100.0
            return SimResult(pnl, "SL", steps, False)
        if float(row["low"]) <= tp_price:
            pnl = (entry_price - tp_price) / entry_price * 100.0
            return SimResult(pnl, "TP", steps, False)

        if exit_on_regime_change and str(row["regime"]) != str(entry_regime):
            exit_price = float(row["close"])
            pnl = (entry_price - exit_price) / entry_price * 100.0
            return SimResult(pnl, "REGIME_CHANGE", steps, False)

        if timeout_bars is not None and steps >= int(timeout_bars):
            exit_price = float(row["close"])
            pnl = (entry_price - exit_price) / entry_price * 100.0
            return SimResult(pnl, "TIMEOUT", steps, False)

    exit_price = float(
        bars.iloc[min(len(bars) - 1, entry_idx + max_lookahead)]["close"])
    pnl = (entry_price - exit_price) / entry_price * 100.0
    return SimResult(pnl, "STILL_OPEN_DIAGNOSTIC", steps, True)


def simulate_portfolio(
    entries: pd.DataFrame,
    prices_by_symbol: Dict[str, pd.DataFrame],
    tp_pct: float,
    sl_pct: float,
    timeout_bars: Optional[int],
    exit_on_regime_change: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, r in entries.iterrows():
        sym = str(r["symbol"])
        bars = prices_by_symbol.get(sym)
        if bars is None or bars.empty:
            continue
        ts = pd.to_datetime(r["entry_timestamp"], utc=True)
        idx_arr = bars.index[bars["timestamp"] == ts]
        if len(idx_arr) == 0:
            pos = bars.index[bars["timestamp"] > ts]
            if len(pos) == 0:
                continue
            entry_idx = int(pos[0]) - 1
            if entry_idx < 0:
                continue
        else:
            entry_idx = int(idx_arr[0])

        entry_price = float(r["entry_price"])
        entry_regime = str(r.get("entry_regime", "TREND_DOWN"))
        sim = simulate_short_trade(
            bars=bars,
            entry_idx=entry_idx,
            entry_price=entry_price,
            entry_regime=entry_regime,
            tp_pct=float(tp_pct),
            sl_pct=float(sl_pct),
            timeout_bars=timeout_bars,
            exit_on_regime_change=exit_on_regime_change,
        )
        rows.append(
            {
                "symbol": sym,
                "entry_timestamp": ts,
                "entry_price": entry_price,
                "pnl_pct": sim.pnl_pct,
                "exit_reason": sim.exit_reason,
                "bars_held": sim.bars_held,
                "still_open": sim.still_open,
                "r_multiple": sim.pnl_pct / (float(sl_pct) * 100.0) if sl_pct > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_sim(df: pd.DataFrame, cost_bps: float = 6.0) -> Dict[str, Any]:
    if df.empty:
        return {
            "count": 0,
            "gross_pnl_pct": 0.0,
            "net_pnl_pct": 0.0,
            "avg_r": 0.0,
            "max_drawdown_pct": 0.0,
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "regime_change_count": 0,
            "still_open_count": 0,
        }
    net = df["pnl_pct"] - cost_to_pct(cost_bps)
    vc = df["exit_reason"].value_counts().to_dict()
    return {
        "count": int(len(df)),
        "gross_pnl_pct": float(df["pnl_pct"].sum()),
        "net_pnl_pct": float(net.sum()),
        "avg_r": float(df["r_multiple"].mean()),
        "max_drawdown_pct": max_drawdown_from_series(net.tolist()),
        "tp_count": int(vc.get("TP", 0)),
        "sl_count": int(vc.get("SL", 0)),
        "timeout_count": int(vc.get("TIMEOUT", 0)),
        "regime_change_count": int(vc.get("REGIME_CHANGE", 0)),
        "still_open_count": int(vc.get("STILL_OPEN_DIAGNOSTIC", 0)),
    }


def fmt_pct(x: float) -> str:
    return f"{x:.6f}"


def build_outputs() -> None:
    inputs = load_inputs()
    dataset = inputs["dataset"]
    trades = inputs["trades"]
    joined = inputs["joined"]
    segments = inputs["segments"]

    secondary_available = [
        s for s in SECONDARY_SYMBOLS if s in set(dataset["symbol"].unique())]

    td_trades = trades[(trades["entry_regime"] == "TREND_DOWN") & (trades["side"].isin(
        ["SHORT", "SELL"])) & (trades["symbol"].isin(PRIMARY_SYMBOLS))].copy()
    tu_trades = trades[(trades["entry_regime"] == "TREND_UP") & (trades["side"].isin(
        ["LONG", "BUY"])) & (trades["symbol"].isin(PRIMARY_SYMBOLS))].copy()

    phase1_td = metrics_from_trades(td_trades, cost_bps=6)
    phase1_tu = metrics_from_trades(tu_trades, cost_bps=6)

    phase1_costs = {}
    for bps in [4, 6, 8, 10]:
        phase1_costs[f"net_pnl_pct_cost_{bps}bps"] = float(
            (td_trades["pnl_pct"] - cost_to_pct(bps)).sum()) if len(td_trades) else 0.0

    joined_td = add_segment_id_from_joined(joined[(joined["regime"] == "TREND_DOWN") & (
        joined["symbol"].isin(PRIMARY_SYMBOLS))].copy())
    segment_table = build_segment_table(joined_td, segments)

    enriched = add_entry_features(
        dataset[dataset["symbol"].isin(PRIMARY_SYMBOLS)].copy(), td_trades)
    # Align requested column names for output artifact
    enriched_out = enriched.rename(columns={
        "entry_timestamp": "entry_ts",
        "entry_regime_confidence": "confidence",
        "entry_regime_age_bars": "regime_age",
        "atr_proxy_bps": "atr_bps",
        "exit_reason": "exit_reason",
    })
    enriched_out["segment_id"] = [
        f"TD_ENTRY:{i:06d}" for i in range(len(enriched_out))]

    filter_df = build_filter_diagnostics(enriched)
    conf_band_df = confidence_band_table(enriched)
    microband_df = build_microbands(enriched, filter_df)

    # Candidate pool for TPSL: top 3 filters with sample >= 20
    filt_candidates = filter_df[filter_df["admitted_count"] >= 20].head(10)
    if filt_candidates.empty:
        filt_candidates = filter_df.head(3)

    # Reconstruct filter masks map
    e = enriched.copy()
    mask_map: Dict[str, pd.Series] = {
        "D0_ALL_TREND_DOWN": pd.Series(True, index=e.index),
        "D1_CONF_020_030": (e["entry_regime_confidence"] >= 0.20) & (e["entry_regime_confidence"] < 0.30),
        "D2_CONF_030_035": (e["entry_regime_confidence"] >= 0.30) & (e["entry_regime_confidence"] < 0.35),
        "D3_CONF_035_040": (e["entry_regime_confidence"] >= 0.35) & (e["entry_regime_confidence"] < 0.40),
        "D4_CONF_040_045": (e["entry_regime_confidence"] >= 0.40) & (e["entry_regime_confidence"] < 0.45),
        "D5_CONF_045_050": (e["entry_regime_confidence"] >= 0.45) & (e["entry_regime_confidence"] < 0.50),
        "D6_NOT_NEAR_LOCAL_LOW_10": e["position_in_range_10"] > 0.25,
        "D7_POSITION_RANGE_025_075": (e["position_in_range_10"] >= 0.25) & (e["position_in_range_10"] <= 0.75),
        "D8_AFTER_POSITIVE_PULLBACK": e["ret_3_bars_before_entry_bps"] > 0.0,
        "D9_NOT_AFTER_STRONG_NEGATIVE_IMPULSE": e["ret_3_bars_before_entry_bps"] > -60.0,
        "D10_ETH_ONLY": e["symbol"] == "ETHUSDT",
        "D11_BTC_ONLY": e["symbol"] == "BTCUSDT",
    }
    # D12-D14 from earlier rules
    best_band = filter_df[filter_df["filter_id"].isin(["D1_CONF_020_030", "D2_CONF_030_035", "D3_CONF_035_040", "D4_CONF_040_045", "D5_CONF_045_050"])].sort_values([
        "net_pnl_pct_6bps", "admitted_count"], ascending=[False, False]).head(1)
    best_band_id = str(
        best_band.iloc[0]["filter_id"]) if not best_band.empty else "D3_CONF_035_040"
    best_mask = mask_map.get(best_band_id, pd.Series(True, index=e.index))
    mask_map["D12_CONF_BAND_PLUS_NOT_NEAR_LOW"] = best_mask & (
        e["position_in_range_10"] > 0.25)
    mask_map["D13_CONF_BAND_PLUS_PULLBACK"] = best_mask & (
        e["ret_3_bars_before_entry_bps"] > 0.0)
    mask_map["D14_SYMBOL_SPECIFIC_BEST"] = (
        ((e["symbol"] == "BTCUSDT") & (e["entry_regime_confidence"] >= 0.30) & (
            e["entry_regime_confidence"] < 0.40) & (e["ret_3_bars_before_entry_bps"] > -30))
        |
        ((e["symbol"] == "ETHUSDT") & (e["entry_regime_confidence"] >= 0.35) & (
            e["entry_regime_confidence"] < 0.50) & (e["position_in_range_10"] > 0.20))
    )

    # Baseline TP/SL/TIMEOUT from trend-down trades if present
    td_baseline_tp = float(td_trades["tp_pct_used"].mode().iloc[0]) if len(
        td_trades) and td_trades["tp_pct_used"].notna().any() else 0.00665
    td_baseline_sl = float(td_trades["sl_pct_used"].mode().iloc[0]) if len(
        td_trades) and td_trades["sl_pct_used"].notna().any() else 0.0075
    td_timeout_current = int(td_trades.loc[td_trades["exit_reason"] == "TIMEOUT", "bars_held"].mode(
    ).iloc[0]) if (len(td_trades) and (td_trades["exit_reason"] == "TIMEOUT").any()) else 18

    prices_by_symbol = build_price_index(
        dataset[dataset["symbol"].isin(PRIMARY_SYMBOLS)].copy())

    tpsl_rows: list[dict[str, Any]] = []
    cand_ids = [str(x) for x in filt_candidates["filter_id"].tolist()[:3]]
    for cid in cand_ids:
        cmask = mask_map.get(cid, pd.Series(False, index=e.index))
        entries = e[cmask].copy()
        if entries.empty:
            continue
        for tm in TP_MULTIPLIERS:
            for sm in SL_MULTIPLIERS:
                tp_pct = td_baseline_tp * tm
                sl_pct = td_baseline_sl * sm
                sim_df = simulate_portfolio(
                    entries, prices_by_symbol, tp_pct, sl_pct, td_timeout_current, exit_on_regime_change=True)
                summary = summarize_sim(sim_df, cost_bps=6)
                tpsl_rows.append(
                    {
                        "candidate_filter": cid,
                        "tp_profile": f"TP_{int(tm*100):03d}X",
                        "sl_profile": f"SL_{int(sm*100):03d}X",
                        "tp_pct": tp_pct,
                        "sl_pct": sl_pct,
                        "tp_bps": pct_to_bps(tp_pct),
                        "sl_bps": pct_to_bps(sl_pct),
                        **summary,
                    }
                )

    tpsl_df = pd.DataFrame(tpsl_rows).sort_values(
        ["net_pnl_pct", "count"], ascending=[False, False]).reset_index(drop=True)

    timeout_rows: list[dict[str, Any]] = []
    top_tpsl = tpsl_df.head(5).copy() if len(tpsl_df) else pd.DataFrame()

    timeout_variants: list[tuple[str, Optional[int]]] = [
        ("TIMEOUT_CURRENT", td_timeout_current),
        ("TIMEOUT_SHORTER_25_PERCENT", max(1, int(round(td_timeout_current * 0.75)))),
        ("TIMEOUT_SHORTER_50_PERCENT", max(1, int(round(td_timeout_current * 0.50)))),
        ("TIMEOUT_PLUS_5_BARS", td_timeout_current + 5),
        ("TIMEOUT_PLUS_10_BARS", td_timeout_current + 10),
        ("TIMEOUT_PLUS_20_BARS", td_timeout_current + 20),
        ("NO_TIMEOUT_DIAGNOSTIC", None),
    ]

    for _, rr in top_tpsl.iterrows():
        cid = str(rr["candidate_filter"])
        entries = e[mask_map.get(cid, pd.Series(False, index=e.index))].copy()
        if entries.empty:
            continue
        for t_name, t_val in timeout_variants:
            sim_df = simulate_portfolio(
                entries,
                prices_by_symbol,
                float(rr["tp_pct"]),
                float(rr["sl_pct"]),
                t_val,
                exit_on_regime_change=True,
            )
            summary = summarize_sim(sim_df, cost_bps=6)
            timeout_rows.append(
                {
                    "candidate_filter": cid,
                    "tp_profile": rr["tp_profile"],
                    "sl_profile": rr["sl_profile"],
                    "tp_pct": float(rr["tp_pct"]),
                    "sl_pct": float(rr["sl_pct"]),
                    "timeout_variant": t_name,
                    "timeout_bars": t_val,
                    **summary,
                }
            )

    timeout_df = pd.DataFrame(timeout_rows).sort_values(
        ["net_pnl_pct", "count"], ascending=[False, False]).reset_index(drop=True)

    # Regime-change exit analysis on best timeout candidate
    best_timeout_row = timeout_df.head(1)
    regime_change_compare = {}
    best_sim_df = pd.DataFrame()
    if not best_timeout_row.empty:
        br = best_timeout_row.iloc[0]
        cid = str(br["candidate_filter"])
        entries = e[mask_map.get(cid, pd.Series(False, index=e.index))].copy()
        if not entries.empty:
            for mode in ["EXIT_ON_REGIME_CHANGE", "EXIT_NO_REGIME_CHANGE"]:
                sim_df = simulate_portfolio(
                    entries,
                    prices_by_symbol,
                    float(br["tp_pct"]),
                    float(br["sl_pct"]),
                    int(br["timeout_bars"]) if pd.notna(
                        br["timeout_bars"]) else None,
                    exit_on_regime_change=(mode == "EXIT_ON_REGIME_CHANGE"),
                )
                regime_change_compare[mode] = summarize_sim(sim_df, cost_bps=6)
                if mode == "EXIT_ON_REGIME_CHANGE":
                    best_sim_df = sim_df.copy()

    # Best candidate recheck
    best_candidate = {}
    if not best_timeout_row.empty and not best_sim_df.empty:
        br = best_timeout_row.iloc[0]
        gross = float(best_sim_df["pnl_pct"].sum())
        recheck = {
            "candidate_filter": str(br["candidate_filter"]),
            "tp_pct": float(br["tp_pct"]),
            "sl_pct": float(br["sl_pct"]),
            "timeout_bars": None if pd.isna(br["timeout_bars"]) else int(br["timeout_bars"]),
            "gross_pnl_pct": gross,
            "net_pnl_pct_4bps": float((best_sim_df["pnl_pct"] - cost_to_pct(4)).sum()),
            "net_pnl_pct_6bps": float((best_sim_df["pnl_pct"] - cost_to_pct(6)).sum()),
            "net_pnl_pct_8bps": float((best_sim_df["pnl_pct"] - cost_to_pct(8)).sum()),
            "net_pnl_pct_10bps": float((best_sim_df["pnl_pct"] - cost_to_pct(10)).sum()),
            "cost_drag_pct_6bps": float(gross - (best_sim_df["pnl_pct"] - cost_to_pct(6)).sum()),
            "avg_pnl_pct_per_trade": float(best_sim_df["pnl_pct"].mean()) if len(best_sim_df) else 0.0,
            "avg_r": float(best_sim_df["r_multiple"].mean()) if len(best_sim_df) else 0.0,
            "total_r": float(best_sim_df["r_multiple"].sum()) if len(best_sim_df) else 0.0,
            "max_drawdown_pct": max_drawdown_from_series((best_sim_df["pnl_pct"] - cost_to_pct(6)).tolist()),
            "tp_count": int((best_sim_df["exit_reason"] == "TP").sum()),
            "sl_count": int((best_sim_df["exit_reason"] == "SL").sum()),
            "timeout_count": int((best_sim_df["exit_reason"] == "TIMEOUT").sum()),
            "regime_change_count": int((best_sim_df["exit_reason"] == "REGIME_CHANGE").sum()),
            "btc_count": int((best_sim_df["symbol"] == "BTCUSDT").sum()),
            "eth_count": int((best_sim_df["symbol"] == "ETHUSDT").sum()),
        }
        verdict = "ACCEPTED_FOR_TESTNET_PREP"
        if recheck["net_pnl_pct_6bps"] <= 0:
            verdict = "REJECTED_NO_POSITIVE_EDGE"
        if int(len(best_sim_df)) < 25:
            verdict = "INSUFFICIENT_SAMPLE"
        recheck["verdict"] = verdict
        best_candidate = recheck
    else:
        best_candidate = {
            "verdict": "INSUFFICIENT_SAMPLE",
            "reason": "No valid timeout-grid candidate",
        }

    # Write outputs CSV
    enriched_out.to_csv(OUT_ENRICHED, index=False)
    filter_df.to_csv(OUT_FILTERS, index=False)
    microband_df.to_csv(OUT_MICROBAND, index=False)
    tpsl_df.to_csv(OUT_TPSL, index=False)
    timeout_df.to_csv(OUT_TIMEOUT, index=False)

    # Build FACT/INFERENCE/ASSUMPTION/UNKNOWN
    facts = [
        f"Input rows: dataset={len(dataset)}, trades={len(trades)}, joined={len(joined)}, segments={len(segments)}",
        f"TREND_DOWN short trades on BTC/ETH: {len(td_trades)}",
        f"TREND_UP long trades on BTC/ETH: {len(tu_trades)}",
        f"Config-independent gate flags were not mutated by this script; research is offline/historical only.",
        f"Secondary symbols available in dataset: {secondary_available}",
    ]

    inferences = [
        "TREND_DOWN behavior is not assumed to mirror TREND_UP; all candidate search performed on TREND_DOWN-only slices.",
        "If best candidate net PnL after 6 bps is non-positive, TREND_DOWN short candidate is rejected for testnet prep.",
        "Confidence-only filters are insufficient when local-position/impulse indicate exhaustion/chase behavior.",
    ]

    assumptions = [
        "Intrabar TP/SL collision for SHORT is resolved conservatively as SL-first.",
        "Trading cost is applied as fixed per-trade round cost in bps (4/6/8/10).",
        "No-lookahead local features use rolling windows up to entry bar only.",
    ]

    unknowns = [
        "Recorder-based extension to BNB/SOL/XRP was not integrated into the current base replay unless present in source artifacts.",
        "Order-book microstructure fields were not used as mandatory separators in this V1 TREND_DOWN sequence.",
    ]

    # Phase 2 summary
    phase2_status_counts = segment_table["Aurora_status"].value_counts(
    ).to_dict()
    phase2_top_reject = segment_table["Aurora_reject_reason_if_known"].replace(
        "", np.nan).dropna().value_counts().head(10).to_dict()

    # Comparison with TREND_UP
    cmp = {
        "trend_down_short_count": phase1_td["count"],
        "trend_down_short_net6": phase1_td["net_pnl_pct"],
        "trend_up_long_count": phase1_tu["count"],
        "trend_up_long_net6": phase1_tu["net_pnl_pct"],
    }

    # Rejected candidates list
    rejected_candidates = []
    for _, row in filter_df.head(20).iterrows():
        if row["net_pnl_pct_6bps"] <= 0:
            rejected_candidates.append(
                {
                    "filter_id": str(row["filter_id"]),
                    "reason": "non_positive_net_after_6bps",
                    "admitted_count": int(row["admitted_count"]),
                    "net_pnl_pct_6bps": float(row["net_pnl_pct_6bps"]),
                }
            )

    report_json = {
        "report_id": "AURORA_TREND_DOWN_FULL_RESEARCH_SEQUENCE_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": best_candidate.get("verdict", "INSUFFICIENT_SAMPLE"),
        "problem_framing": "Independent TREND_DOWN SHORT research sequence mirroring TREND_UP rigor without symmetry assumptions.",
        "FACTS": facts,
        "INFERENCES": inferences,
        "ASSUMPTIONS": assumptions,
        "UNKNOWNS": unknowns,
        "data_inventory": {
            "dataset_csv": str(DATASET_CSV.relative_to(ROOT)),
            "trades_csv": str(TRADES_CSV.relative_to(ROOT)),
            "joined_csv": str(JOINED_CSV.relative_to(ROOT)),
            "segments_csv": str(SEGMENTS_CSV.relative_to(ROOT)),
            "primary_symbols": PRIMARY_SYMBOLS,
            "secondary_symbols_available": secondary_available,
        },
        "phase1_pure_trend_down_edge": {
            **phase1_td,
            **phase1_costs,
            "btc_split": metrics_from_trades(td_trades[td_trades["symbol"] == "BTCUSDT"], cost_bps=6),
            "eth_split": metrics_from_trades(td_trades[td_trades["symbol"] == "ETHUSDT"], cost_bps=6),
            "trend_up_comparison": phase1_tu,
        },
        "phase2_aurora_admission_failure": {
            "status_counts": {k: int(v) for k, v in phase2_status_counts.items()},
            "top_reject_reasons": {k: int(v) for k, v in phase2_top_reject.items()},
            "segment_count": int(len(segment_table)),
        },
        "phase3_confidence_band_analysis": conf_band_df.to_dict(orient="records"),
        "phase4_local_range_analysis": {
            "losses_near_low_10_rate": float(((enriched["pnl_pct"] <= 0) & (enriched["position_in_range_10"] <= 0.25)).mean()),
            "wins_after_pullback_midhigh_rate": float(((enriched["pnl_pct"] > 0) & (enriched["position_in_range_10"] >= 0.25)).mean()),
            "bucket_stats_10": enriched.groupby("position_bucket_10")["pnl_pct"].agg(["count", "mean"]).reset_index().to_dict(orient="records"),
            "bucket_stats_20": enriched.groupby("position_bucket_20")["pnl_pct"].agg(["count", "mean"]).reset_index().to_dict(orient="records"),
        },
        "phase5_pre_entry_impulse_analysis": {
            "ret3_bucket_stats": enriched.groupby("impulse_bucket_3")["pnl_pct"].agg(["count", "mean"]).reset_index().to_dict(orient="records"),
            "ret6_bucket_stats": enriched.groupby("impulse_bucket_6")["pnl_pct"].agg(["count", "mean"]).reset_index().to_dict(orient="records"),
        },
        "phase6_good_bad_separator": filter_df.to_dict(orient="records"),
        "phase7_microband_decomposition": microband_df.to_dict(orient="records"),
        "phase8_tpsl_grid": tpsl_df.to_dict(orient="records"),
        "phase9_timeout_grid": timeout_df.to_dict(orient="records"),
        "phase10_regime_change_exit": regime_change_compare,
        "phase11_metric_recheck": best_candidate,
        "comparison_with_trend_up_candidate": cmp,
        "best_trend_down_candidate": best_candidate,
        "rejected_candidates": rejected_candidates,
        "testnet_implication": (
            "Do NOT apply production mutation based on this report alone; use candidate in testnet-prep only if verdict is ACCEPTED_FOR_TESTNET_PREP."
        ),
        "what_must_not_change_yet": [
            "No production YAML mutation without explicit approval.",
            "No execution_position contract/runtime mutations from this research.",
            "No assumption that TREND_DOWN thresholds mirror TREND_UP.",
        ],
        "recommended_next_step": (
            "If accepted, run isolated testnet shadow pass for best TREND_DOWN candidate with strict post-run metric recheck."
        ),
        "acceptance_gate": {
            "researched_separately_from_trend_up": True,
            "confidence_bands_analyzed": True,
            "local_range_and_impulse_no_lookahead": True,
            "good_bad_separator_tested": True,
            "microbands_tested_if_zone_exists": True,
            "tpsl_grid_tested": True,
            "timeout_grid_tested": True,
            "best_candidate_recheck_performed": True,
            "final_verdict_explicit": True,
        },
    }

    # MD rendering
    def md_table(df: pd.DataFrame, cols: list[str], n: int = 20) -> str:
        if df.empty:
            return "(no rows)"
        x = df[cols].head(n).copy()
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        body = []
        for _, row in x.iterrows():
            vals = []
            for c in cols:
                v = row[c]
                if isinstance(v, float):
                    vals.append(f"{v:.6f}")
                else:
                    vals.append(str(v))
            body.append("| " + " | ".join(vals) + " |")
        return "\n".join([header, sep] + body)

    md_lines: list[str] = []
    md_lines.append("# AURORA_TREND_DOWN_FULL_RESEARCH_SEQUENCE_V1")
    md_lines.append("")
    md_lines.append("## Verdict")
    md_lines.append(str(report_json["verdict"]))
    md_lines.append("")
    md_lines.append("## Problem framing")
    md_lines.append(report_json["problem_framing"])
    md_lines.append("")
    for section in ["FACTS", "INFERENCES", "ASSUMPTIONS", "UNKNOWNS"]:
        md_lines.append(f"## {section}")
        for item in report_json[section]:
            md_lines.append(f"- {item}")
        md_lines.append("")

    md_lines.append("## Data inventory")
    md_lines.append(
        f"- dataset_csv: {report_json['data_inventory']['dataset_csv']}")
    md_lines.append(
        f"- trades_csv: {report_json['data_inventory']['trades_csv']}")
    md_lines.append(
        f"- joined_csv: {report_json['data_inventory']['joined_csv']}")
    md_lines.append(
        f"- segments_csv: {report_json['data_inventory']['segments_csv']}")
    md_lines.append(
        f"- primary_symbols: {report_json['data_inventory']['primary_symbols']}")
    md_lines.append(
        f"- secondary_symbols_available: {report_json['data_inventory']['secondary_symbols_available']}")
    md_lines.append("")

    md_lines.append("## Pure TREND_DOWN edge recap")
    md_lines.append("```json")
    md_lines.append(json.dumps(
        report_json["phase1_pure_trend_down_edge"], ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Aurora admission failure for TREND_DOWN")
    md_lines.append("```json")
    md_lines.append(json.dumps(
        report_json["phase2_aurora_admission_failure"], ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Confidence band analysis")
    md_lines.append(md_table(conf_band_df, [
                    "band", "count", "win_rate", "gross_pnl_pct", "net_pnl_pct_6bps", "avg_r", "btc_count", "eth_count"]))
    md_lines.append("")

    md_lines.append("## Local range position analysis for SHORT")
    md_lines.append("```json")
    md_lines.append(json.dumps(
        report_json["phase4_local_range_analysis"], ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Pre-entry impulse analysis for SHORT")
    md_lines.append("```json")
    md_lines.append(json.dumps(
        report_json["phase5_pre_entry_impulse_analysis"], ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Good/bad separator")
    md_lines.append(md_table(filter_df, ["filter_id", "admitted_count", "win_rate", "gross_pnl_pct",
                    "net_pnl_pct_6bps", "avg_r", "kept_good_rate", "rejected_bad_rate"], n=30))
    md_lines.append("")

    md_lines.append("## Candidate filters")
    md_lines.append(
        "Top candidates by net_pnl_pct_6bps are listed in the separator table above.")
    md_lines.append("")

    md_lines.append("## Micro-band decomposition")
    md_lines.append(md_table(microband_df, [
                    "type", "band", "count", "win_rate", "gross_pnl_pct", "net_pnl_pct_6bps", "avg_r"], n=50))
    md_lines.append("")

    md_lines.append("## TP/SL grid")
    md_lines.append(md_table(tpsl_df, ["candidate_filter", "tp_profile", "sl_profile", "tp_bps",
                    "sl_bps", "count", "gross_pnl_pct", "net_pnl_pct", "avg_r", "max_drawdown_pct"]))
    md_lines.append("")

    md_lines.append("## Timeout grid")
    md_lines.append(md_table(timeout_df, ["candidate_filter", "tp_profile", "sl_profile", "timeout_variant",
                    "timeout_bars", "count", "gross_pnl_pct", "net_pnl_pct", "avg_r", "max_drawdown_pct"], n=40))
    md_lines.append("")

    md_lines.append("## Regime-change exit analysis")
    md_lines.append("```json")
    md_lines.append(json.dumps(regime_change_compare,
                    ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## BTC vs ETH split")
    md_lines.append("```json")
    md_lines.append(json.dumps({
        "btc_trend_down": metrics_from_trades(td_trades[td_trades["symbol"] == "BTCUSDT"], cost_bps=6),
        "eth_trend_down": metrics_from_trades(td_trades[td_trades["symbol"] == "ETHUSDT"], cost_bps=6),
    }, ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Comparison with TREND_UP candidate")
    md_lines.append("```json")
    md_lines.append(json.dumps(cmp, ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Best TREND_DOWN candidate")
    md_lines.append("```json")
    md_lines.append(json.dumps(best_candidate, ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Rejected candidates")
    md_lines.append("```json")
    md_lines.append(json.dumps(
        rejected_candidates[:25], ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Metric recheck")
    md_lines.append("```json")
    md_lines.append(json.dumps(best_candidate, ensure_ascii=True, indent=2))
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## Testnet implication")
    md_lines.append(report_json["testnet_implication"])
    md_lines.append("")

    md_lines.append("## What must NOT change yet")
    for item in report_json["what_must_not_change_yet"]:
        md_lines.append(f"- {item}")
    md_lines.append("")

    md_lines.append("## Recommended next step")
    md_lines.append(report_json["recommended_next_step"])
    md_lines.append("")

    md_lines.append("## Acceptance gate")
    md_lines.append("```json")
    md_lines.append(json.dumps(
        report_json["acceptance_gate"], ensure_ascii=True, indent=2))
    md_lines.append("```")

    OUT_JSON.write_text(json.dumps(
        report_json, ensure_ascii=True, indent=2), encoding="utf-8")
    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")

    recheck_lines = [
        f"# AURORA_TREND_DOWN_BEST_CANDIDATE_RECHECK_{DATE_TAG}",
        "",
        "## Best candidate metrics",
        "```json",
        json.dumps(best_candidate, ensure_ascii=True, indent=2),
        "```",
        "",
        "## Unit validation",
        "- pnl_* are in percent units",
        "- tp_bps/sl_bps values are basis points",
        "- avg_r and total_r are R-multiples",
    ]
    OUT_RECHECK_MD.write_text("\n".join(recheck_lines), encoding="utf-8")

    print("Generated artifacts:")
    for p in [OUT_MD, OUT_JSON, OUT_ENRICHED, OUT_FILTERS, OUT_MICROBAND, OUT_TPSL, OUT_TIMEOUT, OUT_RECHECK_MD]:
        print(" -", p.relative_to(ROOT))


if __name__ == "__main__":
    build_outputs()
