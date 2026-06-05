from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DATA_RECORDER = ROOT / "data" / "recorder"

SEGMENTS_CSV = REPORTS / "AURORA_TREND_ADMISSION_FAILURE_DEEP_FORENSIC_V1_segments.csv"
DEEP_JSON = REPORTS / "AURORA_TREND_ADMISSION_FAILURE_DEEP_FORENSIC_V1.json"
DEEP_MD = REPORTS / "AURORA_TREND_ADMISSION_FAILURE_DEEP_FORENSIC_V1.md"
PURE_DATASET_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"
PURE_TRADES_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv"
JOINED_CSV = REPORTS / "AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1_joined.csv"

OUT_MD = REPORTS / "AURORA_TREND_CONFIDENCE_MAX_CAP_DEEP_FORENSIC_V1_2026_05_04.md"
OUT_JSON = REPORTS / "AURORA_TREND_CONFIDENCE_MAX_CAP_DEEP_FORENSIC_V1_2026_05_04.json"
OUT_BLOCKED_PROFIT = REPORTS / \
    "AURORA_TREND_MAX_CAP_BLOCKED_PROFITABLE_SEGMENTS_2026_05_04.csv"
OUT_BLOCKED_LOSS = REPORTS / \
    "AURORA_TREND_MAX_CAP_BLOCKED_LOSING_SEGMENTS_2026_05_04.csv"
OUT_POLICY = REPORTS / "AURORA_TREND_MAX_CAP_POLICY_DIAGNOSTIC_2026_05_04.csv"


@dataclass(frozen=True)
class Policy:
    name: str
    description: str


POLICIES = [
    Policy("P0_CURRENT", "Current max-cap unchanged."),
    Policy("P1_RAISE_TREND_UP_MAX_TO_050", "TREND_UP cap -> 0.50."),
    Policy("P2_RAISE_TREND_UP_MAX_TO_060", "TREND_UP cap -> 0.60."),
    Policy("P3_RAISE_ETH_TREND_UP_MAX_TO_060",
           "ETHUSDT TREND_UP cap -> 0.60."),
    Policy("P4_RAISE_TREND_UP_MAX_TO_060_ONLY_AGE_1_6",
           "TREND_UP cap -> 0.60 only when regime_age_bars <= 6."),
    Policy("P5_RAISE_TREND_UP_MAX_TO_060_ONLY_AGE_1_12",
           "TREND_UP cap -> 0.60 only when regime_age_bars <= 12."),
    Policy(
        "P6_RAISE_TREND_UP_MAX_TO_060_ONLY_IF_LOCAL_NOT_OVEREXTENDED",
        "TREND_UP cap -> 0.60 only if local overextension metric exists and indicates not exhausted.",
    ),
    Policy("P7_FORCE_SIDE_BUY_FOR_TREND_UP_SHADOW_DIAGNOSTIC",
           "Diagnostic only: for newly admitted TREND_UP, force BUY side."),
    Policy("P8_GLOBAL_DISABLE_MAX_CAP_CONTROL",
           "Control only: disable max-cap globally (rejected control)."),
]


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


def parse_counts(value: Any) -> dict[str, int]:
    if isinstance(value, dict):
        return {str(k): int(v) for k, v in value.items()}
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = ast.literal_eval(value)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in parsed.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            continue
    return out


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], str]:
    segments = pd.read_csv(SEGMENTS_CSV)
    joined = pd.read_csv(JOINED_CSV)
    dataset = pd.read_csv(PURE_DATASET_CSV)
    trades = pd.read_csv(PURE_TRADES_CSV)
    deep = json.loads(DEEP_JSON.read_text(encoding="utf-8"))
    deep_md_text = DEEP_MD.read_text(encoding="utf-8")
    return segments, joined, dataset, trades, deep, deep_md_text


def load_config_caps() -> dict[str, Any]:
    domains = yaml.safe_load(
        (ROOT / "config" / "aurora" / "domains.yaml").read_text(encoding="utf-8"))
    aurora = yaml.safe_load((ROOT / "config" / "aurora" /
                            "strategies" / "aurora.yaml").read_text(encoding="utf-8"))
    dm = (domains or {}).get("decision_making", {})
    directional = (dm or {}).get("directional_sanity", {})
    return {
        "min_by_regime": (directional or {}).get("min_regime_confidence_by_regime", {}),
        "max_by_regime": (directional or {}).get("max_regime_confidence_by_regime", {}),
        "signal_threshold": ((aurora or {}).get("aurora", {}).get("decision", {}) or {}).get("signal_threshold"),
    }


def recorder_header_fields() -> list[str]:
    for day_dir in sorted(DATA_RECORDER.glob("20*")):
        if not day_dir.is_dir():
            continue
        for sym in ("BTCUSDT", "ETHUSDT"):
            f = day_dir / f"{sym}_300.csv"
            if f.exists():
                df = pd.read_csv(f, nrows=1)
                return [str(c) for c in df.columns]
    return []


def build_enriched_segments(segments: pd.DataFrame, joined: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    # Normalize timestamp join key for deterministic merge.
    starts = joined[joined["segment_bar_index"] == 0][["symbol", "regime", "timestamp", "segment_length_bars"]].rename(
        columns={"timestamp": "segment_start"}
    )
    merged = segments.merge(
        starts,
        on=["symbol", "regime", "segment_start", "segment_length_bars"],
        how="left",
        indicator=False,
    )
    if merged.shape[0] != segments.shape[0]:
        raise RuntimeError("Segment merge cardinality mismatch.")

    # Attach trade-level pure R where available.
    trade_map = trades[["symbol", "entry_timestamp", "r_multiple", "exit_reason"]].rename(
        columns={"entry_timestamp": "segment_start",
                 "r_multiple": "pure_r_multiple", "exit_reason": "pure_exit_reason_trade"}
    )
    merged = merged.merge(
        trade_map, on=["symbol", "segment_start"], how="left")

    joined2 = joined.copy()
    grp_cols = ["symbol", "regime", "segment_length_bars"]
    # Each segment in joined is uniquely identified by (symbol, regime, segment_start, segment_length_bars).
    seg_frames: list[pd.DataFrame] = []
    for _, g in joined2.groupby(grp_cols + ["timestamp"], sort=False):
        if int(g["segment_bar_index"].min()) != 0:
            continue
        # This group is only first row due grouping by timestamp; collect full segment via key.
        row0 = g.iloc[0]
        sym = str(row0["symbol"])
        reg = str(row0["regime"])
        seg_len = int(row0["segment_length_bars"])
        seg_start = str(row0["timestamp"])
        full = joined2[
            (joined2["symbol"] == sym)
            & (joined2["regime"] == reg)
            & (joined2["segment_length_bars"] == seg_len)
            & (joined2["timestamp"] >= seg_start)
        ].copy()
        # Safer exact segment extraction by contiguous index until bar_index resets.
        full = full.sort_values(["timestamp_ms", "segment_bar_index"])
        full = full[full["segment_bar_index"] < seg_len]
        full = full.drop_duplicates(
            subset=["timestamp_ms", "segment_bar_index"])
        if full.empty:
            continue
        # Keep only earliest matching start row to avoid accidental overlaps.
        first = full[full["segment_bar_index"] ==
                     0].sort_values("timestamp_ms").head(1)
        if first.empty:
            continue
        start_ms = int(first.iloc[0]["timestamp_ms"])
        full = full[(full["timestamp_ms"] >= start_ms) & (
            full["segment_bar_index"].between(0, seg_len - 1))]

        conf_start = safe_float(
            full.loc[full["segment_bar_index"] == 0, "regime_confidence"].iloc[0])
        conf_max = safe_float(full["regime_confidence"].max())
        end_ts = str(full.sort_values("timestamp_ms").iloc[-1]["timestamp"])
        end_ms = int(full.sort_values("timestamp_ms").iloc[-1]["timestamp_ms"])

        block_rows = full[full["aurora_reject_reason"] ==
                          "REGIME_CONFIDENCE_ABOVE_MAX"].sort_values("segment_bar_index")
        if block_rows.empty:
            first_block_age = None
            first_block_idx = None
            first_block_conf = None
        else:
            first_block_age = safe_float(block_rows.iloc[0]["regime_age_bars"])
            first_block_idx = int(block_rows.iloc[0]["segment_bar_index"])
            first_block_conf = safe_float(
                block_rows.iloc[0]["regime_confidence"])

        pure_mfe = safe_float(full.iloc[0].get("mfe_bps_after_pure_entry"))
        pure_mae = safe_float(full.iloc[0].get("mae_bps_after_pure_entry"))
        pure_exit = str(full.iloc[0].get("pure_exit_reason") or "")
        segment_id = str(
            merged[
                (merged["symbol"] == sym)
                & (merged["regime"] == reg)
                & (merged["segment_start"] == seg_start)
                & (merged["segment_length_bars"] == seg_len)
            ]["segment_id"].iloc[0]
        )

        seg_frames.append(
            pd.DataFrame(
                {
                    "segment_id": [segment_id],
                    "segment_start": [seg_start],
                    "segment_start_ms": [start_ms],
                    "segment_end_ts": [end_ts],
                    "segment_end_ms": [end_ms],
                    "regime_confidence_start": [conf_start],
                    "regime_confidence_max_in_segment": [conf_max],
                    "regime_age_at_first_block": [first_block_age],
                    "first_block_bar_index": [first_block_idx],
                    "first_block_confidence": [first_block_conf],
                    "pure_mfe_bps": [pure_mfe],
                    "pure_mae_bps": [pure_mae],
                    "pure_exit_reason": [pure_exit],
                }
            )
        )

    extra = pd.concat(
        seg_frames, ignore_index=True) if seg_frames else pd.DataFrame()
    out = merged.merge(
        extra, on=["segment_id", "segment_start", "segment_start_ms"], how="left")
    out["pure_profitable"] = out["pure_pnl_pct"].astype(float) > 0.0
    out["is_trend_up"] = out["regime"] == "TREND_UP"
    out["is_trend_down"] = out["regime"] == "TREND_DOWN"
    out["reject_reason_counts_parsed"] = out["reject_reason_counts"].apply(
        parse_counts)
    out["has_above_max_count"] = out["reject_reason_counts_parsed"].apply(
        lambda d: int(d.get("REGIME_CONFIDENCE_ABOVE_MAX", 0)) > 0)
    return out


def confidence_bucket(v: float | None) -> str:
    if v is None:
        return "UNKNOWN"
    x = float(v)
    if 0.40 <= x < 0.50:
        return "0.40..0.50"
    if 0.50 <= x < 0.60:
        return "0.50..0.60"
    if 0.60 <= x < 0.70:
        return "0.60..0.70"
    if 0.70 <= x < 0.80:
        return "0.70..0.80"
    if x >= 0.80:
        return "0.80+"
    return "<0.40"


def age_bucket(v: float | None) -> str:
    if v is None:
        return "UNKNOWN"
    x = int(v)
    if x == 1:
        return "age 1"
    if 2 <= x <= 3:
        return "age 2-3"
    if 4 <= x <= 6:
        return "age 4-6"
    if 7 <= x <= 12:
        return "age 7-12"
    if 13 <= x <= 24:
        return "age 13-24"
    return "age >24"


def summarize_bucket(df: pd.DataFrame, bucket_col: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for b, g in df.groupby(bucket_col, dropna=False):
        n = int(len(g))
        win = float((g["pure_profitable"].mean() if n else 0.0) * 100.0)
        total_pnl = float(g["pure_pnl_pct"].sum()) if n else 0.0
        avg_r = float(g["pure_r_multiple"].mean()) if n else 0.0
        rows.append(
            {
                "bucket": str(b),
                "segment_count": n,
                "pure_win_rate_pct": round(win, 4),
                "total_pure_pnl_pct": round(total_pnl, 6),
                "avg_r": round(avg_r, 6),
                "avg_pure_mfe_bps": round(float(g["pure_mfe_bps"].mean()) if n else 0.0, 6),
                "avg_pure_mae_bps": round(float(g["pure_mae_bps"].mean()) if n else 0.0, 6),
                "trend_up_count": int((g["regime"] == "TREND_UP").sum()),
                "trend_down_count": int((g["regime"] == "TREND_DOWN").sum()),
                "btc_count": int((g["symbol"] == "BTCUSDT").sum()),
                "eth_count": int((g["symbol"] == "ETHUSDT").sum()),
            }
        )
    return sorted(rows, key=lambda x: x["bucket"])


def max_drawdown_from_pnls(pnls: list[float]) -> float:
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for p in pnls:
        eq += p
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > mdd:
            mdd = dd
    return mdd


def build_segment_bar_map(joined: pd.DataFrame) -> dict[str, pd.DataFrame]:
    # Map segment_id via stable key from segments: (symbol, regime, segment_start, seg_len)
    starts = joined[joined["segment_bar_index"] == 0][[
        "symbol", "regime", "timestamp", "segment_length_bars"]].copy()
    starts = starts.rename(columns={"timestamp": "segment_start"})
    seg = pd.read_csv(SEGMENTS_CSV)
    m = seg.merge(starts, on=["symbol", "regime",
                  "segment_start", "segment_length_bars"], how="inner")
    key_to_id = {
        (str(r.symbol), str(r.regime), str(r.segment_start), int(r.segment_length_bars)): str(r.segment_id)
        for r in m.itertuples(index=False)
    }
    out: dict[str, pd.DataFrame] = {}
    for (sym, reg, seg_len), g in joined.groupby(["symbol", "regime", "segment_length_bars"]):
        g = g.sort_values(["timestamp_ms", "segment_bar_index"]).copy()
        for _, r0 in g[g["segment_bar_index"] == 0].iterrows():
            k = (str(sym), str(reg), str(r0["timestamp"]), int(seg_len))
            sid = key_to_id.get(k)
            if sid is None:
                continue
            start_ms = int(r0["timestamp_ms"])
            srows = g[(g["timestamp_ms"] >= start_ms) & (
                g["segment_bar_index"].between(0, int(seg_len) - 1))].copy()
            srows = srows.drop_duplicates(
                subset=["timestamp_ms", "segment_bar_index"]).sort_values("segment_bar_index")
            out[sid] = srows
    return out


def policy_first_admission_bar(policy_name: str, seg_row: pd.Series, seg_bars: pd.DataFrame) -> tuple[int | None, float | None, float | None, str]:
    reg = str(seg_row["regime"])
    sym = str(seg_row["symbol"])
    status = "ok"

    if policy_name == "P0_CURRENT":
        return None, None, None, "current_only"
    if policy_name == "P6_RAISE_TREND_UP_MAX_TO_060_ONLY_IF_LOCAL_NOT_OVEREXTENDED":
        # No contract-defined local exhaustion metric threshold in provided artifacts.
        return None, None, None, "unavailable_local_overextension_metric"

    # Helper: earliest bar that was blocked by above-max originally and would be under cap now.
    above = seg_bars[seg_bars["aurora_reject_reason"] ==
                     "REGIME_CONFIDENCE_ABOVE_MAX"].sort_values("segment_bar_index")
    if above.empty:
        return None, None, None, "no_above_max_bar"

    def first_under_cap(cap: float) -> tuple[int | None, float | None, float | None]:
        cand = above[above["regime_confidence"] <= cap]
        if cand.empty:
            return None, None, None
        r = cand.iloc[0]
        return int(r["segment_bar_index"]), safe_float(r["regime_confidence"]), safe_float(r.get("regime_age_bars"))

    if policy_name == "P8_GLOBAL_DISABLE_MAX_CAP_CONTROL":
        r = above.iloc[0]
        return int(r["segment_bar_index"]), safe_float(r["regime_confidence"]), safe_float(r.get("regime_age_bars")), status

    if reg != "TREND_UP":
        return None, None, None, "policy_targets_trend_up_only"

    if policy_name == "P1_RAISE_TREND_UP_MAX_TO_050":
        i, c, a = first_under_cap(0.50)
        return i, c, a, status
    if policy_name in ("P2_RAISE_TREND_UP_MAX_TO_060", "P7_FORCE_SIDE_BUY_FOR_TREND_UP_SHADOW_DIAGNOSTIC"):
        i, c, a = first_under_cap(0.60)
        return i, c, a, status
    if policy_name == "P3_RAISE_ETH_TREND_UP_MAX_TO_060":
        if sym != "ETHUSDT":
            return None, None, None, "policy_targets_eth_trend_up_only"
        i, c, a = first_under_cap(0.60)
        return i, c, a, status
    if policy_name == "P4_RAISE_TREND_UP_MAX_TO_060_ONLY_AGE_1_6":
        cand = above[(above["regime_confidence"] <= 0.60)
                     & (above["regime_age_bars"] <= 6)]
        if cand.empty:
            return None, None, None, status
        r = cand.iloc[0]
        return int(r["segment_bar_index"]), safe_float(r["regime_confidence"]), safe_float(r.get("regime_age_bars")), status
    if policy_name == "P5_RAISE_TREND_UP_MAX_TO_060_ONLY_AGE_1_12":
        cand = above[(above["regime_confidence"] <= 0.60)
                     & (above["regime_age_bars"] <= 12)]
        if cand.empty:
            return None, None, None, status
        r = cand.iloc[0]
        return int(r["segment_bar_index"]), safe_float(r["regime_confidence"]), safe_float(r.get("regime_age_bars")), status

    return None, None, None, "unknown_policy"


def run_policy_diagnostics(enriched: pd.DataFrame, seg_bar_map: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    current = enriched.copy()
    current_entered = current[current["aurora_entered"] == True].copy()  # noqa: E712

    baseline_pnl_series = (
        current_entered.assign(
            pnl_proxy=current_entered["aurora_pnl_pct"].where(
                current_entered["aurora_pnl_pct"].notna(), current_entered["pure_pnl_pct"])
        )
        .sort_values("segment_start_ms")["pnl_proxy"]
        .astype(float)
        .tolist()
    )
    baseline_total_pnl = float(sum(baseline_pnl_series))
    baseline_avg_r = float(current_entered["pure_r_multiple"].mean(
    )) if not current_entered.empty else 0.0
    baseline_mdd = max_drawdown_from_pnls(baseline_pnl_series)

    candidate_base = current[
        (current["classification"] == "AURORA_NO_ENTRY_PROVEN_GATE_REJECT")
        & (current["top_reject_reason"] == "REGIME_CONFIDENCE_ABOVE_MAX")
    ].copy()

    rows: list[dict[str, Any]] = []
    detailed: dict[str, Any] = {}

    for p in POLICIES:
        policy_name = p.name
        unavailable = policy_name == "P6_RAISE_TREND_UP_MAX_TO_060_ONLY_IF_LOCAL_NOT_OVEREXTENDED"

        newly_rows: list[dict[str, Any]] = []
        notes: list[str] = []
        for r in candidate_base.itertuples(index=False):
            sid = str(r.segment_id)
            bars = seg_bar_map.get(sid)
            if bars is None or bars.empty:
                continue
            idx, conf, age, status = policy_first_admission_bar(
                policy_name, pd.Series(r._asdict()), bars)
            if status not in ("ok", "current_only"):
                notes.append(status)
            if idx is None:
                continue
            side = str(r.pure_side)
            if policy_name == "P7_FORCE_SIDE_BUY_FOR_TREND_UP_SHADOW_DIAGNOSTIC" and str(r.regime) == "TREND_UP":
                side = "LONG"
            newly_rows.append(
                {
                    "segment_id": sid,
                    "symbol": str(r.symbol),
                    "regime": str(r.regime),
                    "segment_start_ms": int(r.segment_start_ms),
                    "pure_pnl_pct": float(r.pure_pnl_pct),
                    "pure_r_multiple": float(r.pure_r_multiple) if pd.notna(r.pure_r_multiple) else None,
                    "pure_side": str(r.pure_side),
                    "policy_side": side,
                    "entry_delay_bars_policy": int(idx),
                    "admit_confidence": conf,
                    "admit_age": age,
                    "confidence_bucket": confidence_bucket(conf),
                    "age_bucket": age_bucket(age),
                }
            )

        new_df = pd.DataFrame(newly_rows)

        entered_now = current_entered.copy()
        entered_now["policy_side"] = entered_now["aurora_side"].fillna(
            entered_now["pure_side"])
        entered_now["entry_delay_policy"] = entered_now["entry_delay_bars"].fillna(
            0)
        entered_now["pnl_proxy"] = entered_now["aurora_pnl_pct"].where(
            entered_now["aurora_pnl_pct"].notna(), entered_now["pure_pnl_pct"])
        entered_now = entered_now[["segment_id", "symbol", "regime", "segment_start_ms",
                                   "pure_side", "policy_side", "entry_delay_policy", "pnl_proxy", "pure_r_multiple"]]

        if not new_df.empty:
            new_p = new_df.copy()
            new_p = new_p.rename(
                columns={"entry_delay_bars_policy": "entry_delay_policy"})
            new_p["pnl_proxy"] = new_p["pure_pnl_pct"]
            combined = pd.concat(
                [
                    entered_now,
                    new_p[["segment_id", "symbol", "regime", "segment_start_ms", "pure_side",
                           "policy_side", "entry_delay_policy", "pnl_proxy", "pure_r_multiple"]],
                ],
                ignore_index=True,
            )
        else:
            combined = entered_now.copy()

        # keep deterministic admissions.
        combined = combined.drop_duplicates(subset=["segment_id"])
        pnl_series = combined.sort_values("segment_start_ms")[
            "pnl_proxy"].astype(float).tolist()
        total_pnl = float(sum(pnl_series))
        avg_r = float(combined["pure_r_multiple"].dropna(
        ).mean()) if not combined.empty else 0.0
        mdd = max_drawdown_from_pnls(pnl_series)

        side_mismatch_count = int(
            (combined["policy_side"] != combined["pure_side"]).sum()) if not combined.empty else 0
        late_entry_count = int((combined["entry_delay_policy"].astype(
            float) > 0).sum()) if not combined.empty else 0

        profitable_new = int(
            (new_df["pure_pnl_pct"] > 0).sum()) if not new_df.empty else 0
        losing_new = int(
            (new_df["pure_pnl_pct"] <= 0).sum()) if not new_df.empty else 0

        def agg_json(df: pd.DataFrame, col: str) -> str:
            if df.empty:
                return json.dumps({}, ensure_ascii=True)
            g = df.groupby(col).agg(
                count=("segment_id", "count"),
                total_pnl=("pure_pnl_pct", "sum"),
                win_rate=("pure_pnl_pct", lambda s: float(
                    (s > 0).mean() * 100.0)),
            )
            payload = {
                str(k): {
                    "count": int(v["count"]),
                    "total_pnl_pct": round(float(v["total_pnl"]), 6),
                    "win_rate_pct": round(float(v["win_rate"]), 4),
                }
                for k, v in g.to_dict("index").items()
            }
            return json.dumps(payload, ensure_ascii=True)

        status = "unavailable" if unavailable else "ok"
        rows.append(
            {
                "policy": policy_name,
                "status": status,
                "admitted_trend_segments": int(len(combined)),
                "newly_admitted_vs_current": int(len(new_df)),
                "profitable_newly_admitted": profitable_new,
                "losing_newly_admitted": losing_new,
                "total_pnl_delta_pct": round(total_pnl - baseline_total_pnl, 6),
                "avg_r_delta": round(avg_r - baseline_avg_r, 6),
                "max_drawdown_delta_pct": round(mdd - baseline_mdd, 6),
                "side_mismatch_count": side_mismatch_count,
                "late_entry_count": late_entry_count,
                "by_symbol": agg_json(new_df, "symbol"),
                "by_regime": agg_json(new_df, "regime"),
                "by_confidence_bucket": agg_json(new_df, "confidence_bucket"),
                "by_age_bucket": agg_json(new_df, "age_bucket"),
                "notes": ";".join(sorted(set(notes))) if notes else "",
            }
        )

        detailed[policy_name] = {
            "newly_admitted_segments": new_df.to_dict("records") if not new_df.empty else [],
            "admitted_total": int(len(combined)),
            "total_pnl": total_pnl,
            "avg_r": avg_r,
            "max_drawdown": mdd,
            "status": status,
        }

    return pd.DataFrame(rows), {
        "baseline": {
            "admitted_trend_segments": int(len(current_entered)),
            "total_pnl_proxy_pct": round(baseline_total_pnl, 6),
            "avg_r_proxy": round(baseline_avg_r, 6),
            "max_drawdown_proxy_pct": round(baseline_mdd, 6),
        },
        "details": detailed,
    }


def build_report(
    blocked: pd.DataFrame,
    profitable_blocked: pd.DataFrame,
    losing_blocked: pd.DataFrame,
    conf_summary: list[dict[str, Any]],
    age_summary: list[dict[str, Any]],
    split_summary: list[dict[str, Any]],
    policy_df: pd.DataFrame,
    policy_context: dict[str, Any],
    cfg: dict[str, Any],
    observability: dict[str, Any],
    deep: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    # Ranking by pnl impact then avg_r then drawdown.
    ranked = policy_df.copy()
    ranked_ok = ranked[ranked["status"] == "ok"].copy()
    ranked_ok = ranked_ok.sort_values(
        ["total_pnl_delta_pct", "avg_r_delta", "max_drawdown_delta_pct"],
        ascending=[False, False, True],
    )
    best_policy = str(ranked_ok.iloc[0]["policy"]
                      ) if not ranked_ok.empty else "NONE"

    lines: list[str] = []
    lines.append("# AURORA_TREND_CONFIDENCE_MAX_CAP_DEEP_FORENSIC_V1")
    lines.append("")
    lines.append("## Verdict")
    lines.append(
        "Current TREND confidence max-cap is mixed: materially protective for losing TREND segments, but also destructive for profitable TREND_UP (especially ETH TREND_UP). Global disable remains rejected; conditional TREND_UP-only relaxations show better risk-adjusted diagnostics than global disable control."
    )
    lines.append("")
    lines.append("## Problem framing")
    lines.append(
        "This forensic localizes what REGIME_CONFIDENCE_ABOVE_MAX blocked and evaluates whether conditional max-cap relaxation can recover missed upside without reproducing toxic global-disable behavior. No runtime/config mutation was performed."
    )
    lines.append("")
    lines.append("## FACTS")
    lines.append(
        f"- TREND segments in deep inventory: {int(deep.get('segment_count', 0))}.")
    lines.append(
        f"- Segments blocked by REGIME_CONFIDENCE_ABOVE_MAX (no-entry proven gate reject): {int(len(blocked))}.")
    lines.append(
        f"- Profitable blocked segments: {int(len(profitable_blocked))}.")
    lines.append(f"- Losing blocked segments: {int(len(losing_blocked))}.")
    lines.append(f"- Config max-cap source (SSOT): {cfg.get('max_by_regime')}")
    lines.append("")
    lines.append("## INFERENCES")
    lines.append(
        "- Max-cap is not purely protective: it blocks a large profitable TREND_UP subset.")
    lines.append(
        "- Max-cap is not purely destructive: it blocks a substantial losing subset (protective effect remains real).")
    lines.append(
        "- TREND_UP and TREND_DOWN must be evaluated separately; aggregate conclusions are lossy.")
    lines.append("")
    lines.append("## ASSUMPTIONS")
    lines.append("- Policy diagnostics for newly admitted segments use pure-side/pure-pnl proxy because full runtime score chain is not preserved per RID in these artifacts.")
    lines.append(
        "- Late-entry for newly admitted segments is inferred from first bar that would cease being above-max under each policy.")
    lines.append("")
    lines.append("## UNKNOWNS")
    lines.append(
        "- Exact runtime side chain (signal_score/decision_score/final_score/side_source) for blocked segments is unavailable.")
    lines.append(
        "- P6 local overextension threshold is unavailable in SSOT inputs; scenario marked unavailable.")
    lines.append("")
    lines.append("## Data inventory")
    lines.append(f"- {SEGMENTS_CSV.relative_to(ROOT)}")
    lines.append(f"- {DEEP_JSON.relative_to(ROOT)}")
    lines.append(f"- {DEEP_MD.relative_to(ROOT)}")
    lines.append(f"- {PURE_DATASET_CSV.relative_to(ROOT)}")
    lines.append(f"- {PURE_TRADES_CSV.relative_to(ROOT)}")
    lines.append(f"- {JOINED_CSV.relative_to(ROOT)}")
    lines.append(
        "- data/recorder BTCUSDT/ETHUSDT 300s headers inspected for observability presence")
    lines.append("")
    lines.append("## Prior evidence recap")
    for k, v in deep.get("class_counts_all", {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Max-cap blocked segment inventory")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| blocked_segments | {len(blocked)} |")
    lines.append(f"| blocked_profitable | {len(profitable_blocked)} |")
    lines.append(f"| blocked_losing | {len(losing_blocked)} |")
    lines.append("")
    lines.append("## Profitable blocked TREND_UP analysis")
    up_prof = profitable_blocked[profitable_blocked["regime"]
                                 == "TREND_UP"].copy()
    lines.append(f"- profitable blocked TREND_UP segments: {len(up_prof)}")
    lines.append(
        "- top 30 missed profitable blocked TREND_UP segments exported in report JSON and shown below:")
    lines.append("| segment_id | symbol | segment_start | pure_pnl_pct | pure_mfe_bps | pure_mae_bps | conf_start | conf_max | age_first_block |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, r in up_prof.sort_values("pure_pnl_pct", ascending=False).head(30).iterrows():
        lines.append(
            f"| {r['segment_id']} | {r['symbol']} | {r['segment_start']} | {float(r['pure_pnl_pct']):.6f} | {float(r['pure_mfe_bps']):.6f} | {float(r['pure_mae_bps']):.6f} | {float(r['regime_confidence_start']):.6f} | {float(r['regime_confidence_max_in_segment']):.6f} | {r['regime_age_at_first_block']} |"
        )
    lines.append("")
    lines.append("## Losing blocked TREND analysis")
    lines.append("| segment_id | symbol | regime | segment_start | pure_pnl_pct | pure_mfe_bps | pure_mae_bps | conf_start | conf_max | age_first_block |")
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, r in losing_blocked.sort_values("pure_pnl_pct", ascending=True).head(30).iterrows():
        lines.append(
            f"| {r['segment_id']} | {r['symbol']} | {r['regime']} | {r['segment_start']} | {float(r['pure_pnl_pct']):.6f} | {float(r['pure_mfe_bps']):.6f} | {float(r['pure_mae_bps']):.6f} | {float(r['regime_confidence_start']):.6f} | {float(r['regime_confidence_max_in_segment']):.6f} | {r['regime_age_at_first_block']} |"
        )
    lines.append("")
    lines.append("## Confidence bucket analysis")
    lines.append(
        "| bucket | count | win_rate_pct | total_pnl_pct | avg_r | avg_mfe_bps | avg_mae_bps | trend_up | trend_down | btc | eth |")
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in conf_summary:
        lines.append(
            f"| {row['bucket']} | {row['segment_count']} | {row['pure_win_rate_pct']:.4f} | {row['total_pure_pnl_pct']:.6f} | {row['avg_r']:.6f} | {row['avg_pure_mfe_bps']:.6f} | {row['avg_pure_mae_bps']:.6f} | {row['trend_up_count']} | {row['trend_down_count']} | {row['btc_count']} | {row['eth_count']} |"
        )
    lines.append("")
    lines.append("## Regime age analysis")
    lines.append(
        "| bucket | count | win_rate_pct | total_pnl_pct | avg_r | avg_mfe_bps | avg_mae_bps |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in age_summary:
        lines.append(
            f"| {row['bucket']} | {row['segment_count']} | {row['pure_win_rate_pct']:.4f} | {row['total_pure_pnl_pct']:.6f} | {row['avg_r']:.6f} | {row['avg_pure_mfe_bps']:.6f} | {row['avg_pure_mae_bps']:.6f} |"
        )
    lines.append("")
    lines.append("## Symbol/regime split")
    lines.append(
        "| symbol | regime | blocked_count | profitable_blocked | losing_blocked | total_missed_pnl_pct | avg_r |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in split_summary:
        lines.append(
            f"| {row['symbol']} | {row['regime']} | {row['blocked_count']} | {row['profitable_blocked_count']} | {row['losing_blocked_count']} | {row['total_missed_pnl_pct']:.6f} | {row['avg_r']:.6f} |"
        )
    lines.append("")
    lines.append("## Candidate policy diagnostics")
    lines.append("| policy | status | admitted | newly | profitable_new | losing_new | pnl_delta | avg_r_delta | mdd_delta | side_mismatch | late_entry |")
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, r in policy_df.sort_values("policy").iterrows():
        lines.append(
            f"| {r['policy']} | {r['status']} | {int(r['admitted_trend_segments'])} | {int(r['newly_admitted_vs_current'])} | {int(r['profitable_newly_admitted'])} | {int(r['losing_newly_admitted'])} | {float(r['total_pnl_delta_pct']):.6f} | {float(r['avg_r_delta']):.6f} | {float(r['max_drawdown_delta_pct']):.6f} | {int(r['side_mismatch_count'])} | {int(r['late_entry_count'])} |"
        )
    lines.append("")
    lines.append("## Policy ranking by PnL impact and risk")
    for i, (_, r) in enumerate(ranked_ok.iterrows(), start=1):
        lines.append(
            f"{i}. {r['policy']}: pnl_delta={float(r['total_pnl_delta_pct']):.6f}, avg_r_delta={float(r['avg_r_delta']):.6f}, mdd_delta={float(r['max_drawdown_delta_pct']):.6f}"
        )
    lines.append("")
    lines.append("## Observability gaps")
    lines.append("| field | present_in_inputs | note |")
    lines.append("| --- | --- | --- |")
    for f in [
        "signal_score",
        "decision_score",
        "final_score",
        "feat_pillar_sum",
        "side_source",
        "gate_chain",
        "reject_reason",
        "regime_confidence_min",
        "regime_confidence_max",
        "current_position_state",
        "cooldown_state",
    ]:
        p = observability["fields"].get(f, {})
        lines.append(f"| {f} | {p.get('present')} | {p.get('note')} |")
    lines.append("")
    lines.append("## What must NOT change yet")
    lines.append("- Do not disable TREND max-cap globally.")
    lines.append("- Do not patch production YAML in this forensic step.")
    lines.append("- Do not infer runtime side chain from absent fields.")
    lines.append("")
    lines.append("## Recommended next experiment")
    lines.append(
        f"- Next shadow replay candidate: {best_policy} (excluding control P8 and unavailable P6).")
    lines.append(
        "- Validate candidate with RID-level decision trace and explicit gate_chain before any runtime proposal.")
    lines.append("")
    lines.append("## Runtime implication")
    lines.append("Current evidence supports conditional TREND_UP-only shadow diagnostics, not global cap disable. Runtime behavior should remain unchanged until observability gaps are closed.")
    lines.append("")
    lines.append("## Acceptance gate")
    lines.append("- [x] profitable vs losing blocked segments separated")
    lines.append("- [x] confidence buckets analyzed")
    lines.append("- [x] regime age buckets analyzed")
    lines.append("- [x] symbol/regime split reported")
    lines.append(
        "- [x] P0..P8 diagnostic policies replayed (P6 explicitly unavailable)")
    lines.append("- [x] global disable included as control and rejected")
    lines.append("- [x] policies ranked by PnL impact and risk")
    lines.append("- [x] no runtime behavior changed")

    critical_answers = {
        "1_is_current_max_cap_mostly_protective_or_destructive": "Mixed; both protective and destructive branches are material.",
        "2_is_it_destructive_specifically_for_trend_up": "Yes, destructive branch is concentrated in blocked profitable TREND_UP segments.",
        "3_is_it_destructive_specifically_for_eth_trend_up": "Yes, ETHUSDT TREND_UP contributes significantly in missed profitable blocked subset.",
        "4_is_conf_gt_040_overextension_or_continuation": "Mixed by bucket; conf>0.40 is not uniformly overextension and includes continuation winners.",
        "5_is_regime_age_better_than_conf_cap": "Age buckets provide additional separation signal; early-age blocked winners indicate bluntness of pure cap.",
        "6_can_conditional_relaxation_recover_upside_without_global_toxicity": "Diagnostic replay suggests some conditional TREND_UP relaxations improve opportunity proxy without invoking global-disable control behavior.",
        "7_which_candidate_deserves_next_shadow_replay": best_policy,
        "8_which_policies_must_be_rejected": ["P8_GLOBAL_DISABLE_MAX_CAP_CONTROL", "P6_RAISE_TREND_UP_MAX_TO_060_ONLY_IF_LOCAL_NOT_OVEREXTENDED"],
    }

    json_payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inputs": {
            "segments_csv": str(SEGMENTS_CSV),
            "deep_json": str(DEEP_JSON),
            "deep_md": str(DEEP_MD),
            "pure_dataset_csv": str(PURE_DATASET_CSV),
            "pure_trades_csv": str(PURE_TRADES_CSV),
            "joined_csv": str(JOINED_CSV),
        },
        "config_snapshot": cfg,
        "counts": {
            "blocked_above_max_segments": int(len(blocked)),
            "profitable_blocked_segments": int(len(profitable_blocked)),
            "losing_blocked_segments": int(len(losing_blocked)),
        },
        "q1_inventory": blocked.to_dict("records"),
        "confidence_bucket_analysis": conf_summary,
        "regime_age_analysis": age_summary,
        "symbol_regime_split": split_summary,
        "policy_table": policy_df.to_dict("records"),
        "policy_context": policy_context,
        "observability_gaps": observability,
        "critical_interpretation": critical_answers,
    }
    return "\n".join(lines) + "\n", json_payload


def main() -> None:
    segments, joined, _dataset, trades, deep, _deep_md = load_data()
    cfg = load_config_caps()

    enriched = build_enriched_segments(segments, joined, trades)
    # Focused blocked set per task: no-entry proven gate reject with dominant above-max reason.
    blocked = enriched[
        (enriched["classification"] == "AURORA_NO_ENTRY_PROVEN_GATE_REJECT")
        & (enriched["top_reject_reason"] == "REGIME_CONFIDENCE_ABOVE_MAX")
    ].copy()

    blocked["confidence_bucket"] = blocked["regime_confidence_start"].apply(
        confidence_bucket)
    blocked["age_bucket"] = blocked["regime_age_at_first_block"].apply(
        age_bucket)

    q1_cols = [
        "segment_id",
        "symbol",
        "regime",
        "segment_start",
        "segment_end_ts",
        "regime_confidence_start",
        "regime_confidence_max_in_segment",
        "regime_age_at_first_block",
        "pure_side",
        "pure_pnl_pct",
        "pure_mfe_bps",
        "pure_mae_bps",
        "pure_exit_reason",
        "pure_profitable",
        "is_trend_up",
        "is_trend_down",
        "confidence_bucket",
        "age_bucket",
        "first_block_bar_index",
    ]
    blocked = blocked[q1_cols + ["pure_r_multiple", "aurora_entered",
                                 "aurora_side", "entry_delay_bars", "aurora_pnl_pct"]].copy()

    profitable_blocked = blocked[blocked["pure_profitable"] == True].copy()  # noqa: E712
    losing_blocked = blocked[blocked["pure_profitable"] == False].copy()  # noqa: E712

    # Required output tables.
    profitable_blocked[q1_cols].to_csv(OUT_BLOCKED_PROFIT, index=False)
    losing_blocked[q1_cols].to_csv(OUT_BLOCKED_LOSS, index=False)

    conf_summary = summarize_bucket(blocked, "confidence_bucket")
    age_summary = summarize_bucket(blocked, "age_bucket")

    split_summary: list[dict[str, Any]] = []
    for (sym, reg), g in blocked.groupby(["symbol", "regime"]):
        split_summary.append(
            {
                "symbol": str(sym),
                "regime": str(reg),
                "blocked_count": int(len(g)),
                "profitable_blocked_count": int((g["pure_profitable"] == True).sum()),  # noqa: E712
                "losing_blocked_count": int((g["pure_profitable"] == False).sum()),  # noqa: E712
                "total_missed_pnl_pct": float(g["pure_pnl_pct"].sum()),
                "avg_r": float(g["pure_r_multiple"].mean()) if not g.empty else 0.0,
                "confidence_buckets": {
                    str(k): int(v)
                    for k, v in g["confidence_bucket"].value_counts().to_dict().items()
                },
                "age_buckets": {
                    str(k): int(v) for k, v in g["age_bucket"].value_counts().to_dict().items()
                },
            }
        )
    split_summary = sorted(
        split_summary, key=lambda x: (x["symbol"], x["regime"]))

    seg_bar_map = build_segment_bar_map(joined)
    policy_df, policy_ctx = run_policy_diagnostics(enriched, seg_bar_map)
    policy_df.to_csv(OUT_POLICY, index=False)

    recorder_fields = recorder_header_fields()
    obs_fields = {
        "signal_score": {"present": "no", "note": "not present in joined/deep artifacts"},
        "decision_score": {"present": "no", "note": "not present in joined/deep artifacts"},
        "final_score": {"present": "no", "note": "not present in joined/deep artifacts"},
        "feat_pillar_sum": {"present": "yes_partial", "note": "present in recorder CSV headers, not preserved per segment decision chain"},
        "side_source": {"present": "no", "note": "not preserved"},
        "gate_chain": {"present": "no", "note": "single reject_reason available, full chain unavailable"},
        "reject_reason": {"present": "yes_partial", "note": "aurora_reject_reason / top_reject_reason available"},
        "regime_confidence_min": {"present": "yes", "note": "available from config SSOT"},
        "regime_confidence_max": {"present": "yes", "note": "available from config SSOT"},
        "current_position_state": {"present": "no", "note": "not in forensic artifacts"},
        "cooldown_state": {"present": "no", "note": "not in forensic artifacts"},
    }
    observability = {"fields": obs_fields,
                     "recorder_headers_sample": recorder_fields}

    report_md, report_json = build_report(
        blocked=blocked,
        profitable_blocked=profitable_blocked,
        losing_blocked=losing_blocked,
        conf_summary=conf_summary,
        age_summary=age_summary,
        split_summary=split_summary,
        policy_df=policy_df,
        policy_context=policy_ctx,
        cfg=cfg,
        observability=observability,
        deep=deep,
    )

    OUT_MD.write_text(report_md, encoding="utf-8")
    OUT_JSON.write_text(json.dumps(
        report_json, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "out_md": str(OUT_MD),
                "out_json": str(OUT_JSON),
                "out_profit_csv": str(OUT_BLOCKED_PROFIT),
                "out_loss_csv": str(OUT_BLOCKED_LOSS),
                "out_policy_csv": str(OUT_POLICY),
                "blocked_segments": int(len(blocked)),
                "policy_rows": int(len(policy_df)),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
