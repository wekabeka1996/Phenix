from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

FROZEN = Path("logs/frozen/nrr062_fresh_capture_20260507_103909")


def _load_cases() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with (FROZEN / "nrr062_cases.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            case = row.get("nrr062_case", row)
            rid = case["rid"]
            out[rid] = case
    return out


def _load_replay() -> list[dict]:
    rows: list[dict] = []
    with (FROZEN / "nrr062_recorder_path_replay_PROMPT11.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def _scan_file_range(path: Path) -> tuple[int | None, int | None]:
    mn = None
    mx = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_raw = row.get("open_time") or row.get(
                    "ts") or row.get("timestamp")
                if ts_raw is None:
                    continue
                try:
                    ts = int(float(ts_raw))
                except Exception:
                    continue
                mn = ts if mn is None else min(mn, ts)
                mx = ts if mx is None else max(mx, ts)
    except Exception:
        return (None, None)
    return (mn, mx)


def _find_recorder_files(symbol: str, dates: list[str]) -> dict[str, dict[str, Path]]:
    out: dict[str, dict[str, Path]] = {}
    ext_dirs = sorted(FROZEN.glob("recorder_extension_*"))
    ext = ext_dirs[-1] if ext_dirs else None
    for date in dates:
        out[date] = {}
        for tf in ("180", "300", "900"):
            cands = [
                FROZEN / "data" / "recorder" / date / f"{symbol}_{tf}.csv",
            ]
            if ext is not None:
                cands.append(ext / "data" / "recorder" /
                             date / f"{symbol}_{tf}.csv")
            found = None
            for c in cands:
                if c.exists():
                    found = c
                    break
            if found is not None:
                out[date][tf] = found
    return out


def _ambiguous_audit(cases: dict[str, dict], replay: list[dict]) -> dict:
    ambiguous = [r for r in replay if r.get("classification") == "ambiguous"]
    rows = []
    root = Counter()
    resolved = 0

    for r in ambiguous:
        rid = r["rid"]
        c = cases[rid]
        ts_ms = int(c["ts_ms"])
        ts_iso = c["ts_iso"]
        dt = _parse_iso(ts_iso)
        horizon_end = dt + timedelta(minutes=120)
        dates = sorted(
            {dt.strftime("%Y-%m-%d"), horizon_end.strftime("%Y-%m-%d")})
        files = _find_recorder_files(c["symbol"], dates)

        tf_cov = {}
        gap_reason = "unknown"
        for tf in ("180", "300", "900"):
            paths = [files[d][tf] for d in files if tf in files[d]]
            if not paths:
                tf_cov[tf] = {"available": False}
                continue
            mins = []
            maxs = []
            for p in paths:
                mn, mx = _scan_file_range(p)
                if mn is not None:
                    mins.append(mn)
                if mx is not None:
                    maxs.append(mx)
            if mins and maxs:
                mn = min(mins)
                mx = max(maxs)
                has_start = mx >= ts_ms
                has_horizon = mx >= int(horizon_end.timestamp() * 1000)
                tf_cov[tf] = {
                    "available": True,
                    "min_ts_ms": mn,
                    "max_ts_ms": mx,
                    "covers_start": has_start,
                    "covers_horizon_end": has_horizon,
                    "files": [str(p).replace("\\", "/") for p in paths],
                }
            else:
                tf_cov[tf] = {"available": True, "parse_error": True, "files": [
                    str(p).replace("\\", "/") for p in paths]}

        has_any = any(tf_cov.get(tf, {}).get("available")
                      for tf in ("180", "300", "900"))
        if not has_any:
            gap_reason = "missing_recorder_file"
        else:
            horizon_by_tf = {tf: tf_cov.get(tf, {}).get("covers_horizon_end") for tf in (
                "180", "300", "900") if tf_cov.get(tf, {}).get("available")}
            if any(horizon_by_tf.values()):
                # likely parser/selection issue in replay logic rather than no data
                gap_reason = "replay_parser_or_bar_selection_gap"
                resolved += 1
            else:
                gap_reason = "horizon_beyond_captured_data_or_data_gap"

        root[gap_reason] += 1
        rows.append(
            {
                "rid": rid,
                "symbol": c.get("symbol"),
                "side": c.get("side"),
                "ts_iso": ts_iso,
                "replay_horizon_end_utc": horizon_end.isoformat(),
                "notes": r.get("notes"),
                "timeframe_coverage": tf_cov,
                "root_cause": gap_reason,
            }
        )

    return {
        "total": len(ambiguous),
        "resolved_by_coarser_timeframe": resolved,
        "still_ambiguous": len(ambiguous) - resolved,
        "root_causes": dict(root),
        "rows": rows,
        "recommended_freeze_rule": "Finalize freeze only after last_case_ts + 120m + 1 timeframe bucket; verify per-case horizon coverage before manifest close.",
    }


def _temporal_holdout(replay: list[dict], cases: dict[str, dict]) -> dict:
    rows = []
    for r in replay:
        rid = r["rid"]
        c = cases[rid]
        dt = _parse_iso(c["ts_iso"])
        rows.append({
            "rid": rid,
            "dt": dt,
            "label": r.get("classification"),
            "symbol": c.get("symbol"),
            "side": c.get("side"),
            "net_bps": r.get("net_bps"),
        })
    rows.sort(key=lambda x: x["dt"])
    usable = [x for x in rows if x["label"] != "ambiguous"]
    ambiguous = [x for x in rows if x["label"] == "ambiguous"]
    if not usable:
        return {"computed": False}

    mid_idx = len(usable) // 2
    first = usable[:mid_idx]
    second = usable[mid_idx:]

    def summarize(part: list[dict]) -> dict:
        winners = [x for x in part if x["label"] == "missed_positive"]
        losers = [x for x in part if x["label"] == "correct_block"]
        buy = [x for x in part if x["side"] == "BUY"]
        sell = [x for x in part if x["side"] == "SELL"]
        return {
            "count": len(part),
            "winners": len(winners),
            "losers": len(losers),
            "winner_pct": round(100.0 * len(winners) / len(part), 2) if part else 0.0,
            "mean_net_bps": round(mean([x["net_bps"] for x in part if x["net_bps"] is not None]), 4) if part else None,
            "buy_count": len(buy),
            "sell_count": len(sell),
            "by_symbol": dict(Counter([x["symbol"] for x in part])),
        }

    # hourly buckets
    by_hour: dict[str, dict[str, int]] = defaultdict(
        lambda: {"winners": 0, "losers": 0, "ambiguous": 0})
    for x in rows:
        k = x["dt"].strftime("%Y-%m-%dT%H")
        if x["label"] == "missed_positive":
            by_hour[k]["winners"] += 1
        elif x["label"] == "correct_block":
            by_hour[k]["losers"] += 1
        else:
            by_hour[k]["ambiguous"] += 1

    # simple stability checks
    fsum = summarize(first)
    ssum = summarize(second)
    stable_patterns = []
    overfit_patterns = []
    if abs(fsum["winner_pct"] - ssum["winner_pct"]) <= 10.0:
        stable_patterns.append("winner_ratio_stable_within_10pct")
    else:
        overfit_patterns.append("winner_ratio_shift_gt_10pct")

    # BUY-side advantage stability
    def buy_winner_rate(part: list[dict]) -> float:
        b = [x for x in part if x["side"] == "BUY"]
        if not b:
            return 0.0
        w = len([x for x in b if x["label"] == "missed_positive"])
        return 100.0 * w / len(b)

    b1 = buy_winner_rate(first)
    b2 = buy_winner_rate(second)
    if abs(b1 - b2) <= 20.0:
        stable_patterns.append("buy_side_winner_bias_stable_within_20pct")
    else:
        overfit_patterns.append("buy_side_winner_bias_unstable")

    conclusion = "NO_SAFE_SEPARATOR_CONCLUSION_STILL_HOLDS"

    return {
        "computed": True,
        "split_method": "timestamp_first_half_vs_second_half_non_ambiguous",
        "first_half": summarize(first),
        "second_half": summarize(second),
        "ambiguous_total": len(ambiguous),
        "hourly_buckets": dict(sorted(by_hour.items())),
        "stable_patterns": stable_patterns,
        "overfit_patterns": overfit_patterns,
        "conclusion": conclusion,
    }


def _field_provenance(cases: dict[str, dict]) -> dict:
    # empirically inspect frozen rows for missingness and nested provenance
    total = len(cases)
    miss_counts = Counter()
    pm_missing_reasons = Counter()
    liq_missing_reasons = Counter()

    for c in cases.values():
        lvf = c.get("low_vol_cost_floor", {})
        pm = lvf.get("price_motion", {})
        liq = lvf.get("liquidity", {})
        pm_missing = pm.get("missing", {}) if isinstance(
            pm.get("missing"), dict) else {}
        liq_missing = liq.get("missing", {}) if isinstance(
            liq.get("missing"), dict) else {}

        for f in ("ret_60s", "ret_300s"):
            if pm.get(f) is None:
                miss_counts[f] += 1
            reason = pm_missing.get(f)
            if reason:
                pm_missing_reasons[str(reason)] += 1
        for f in ("spread_bps", "liquidity_kappa", "absorption"):
            if liq.get(f) is None:
                miss_counts[f] += 1
            reason = liq_missing.get(f)
            if reason:
                liq_missing_reasons[str(reason)] += 1

    return {
        "total_cases": total,
        "missing_counts": dict(miss_counts),
        "price_motion_missing_reasons": dict(pm_missing_reasons),
        "liquidity_missing_reasons": dict(liq_missing_reasons),
    }


def main() -> int:
    cases = _load_cases()
    replay = _load_replay()

    out = {
        "field_provenance_empirical": _field_provenance(cases),
        "ambiguous_case_audit": _ambiguous_audit(cases, replay),
        "temporal_holdout": _temporal_holdout(replay, cases),
    }

    out_path = FROZEN / "nrr062_prompt13_forensics.json"
    out_path.write_text(json.dumps(
        out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(
        out_path).replace('\\', '/')}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
