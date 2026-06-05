"""PKG-6A: Judge review baselines on the current 4-day window.

DIAGNOSTIC-ONLY tool that compares Judge against simple baselines:

* random_same_frequency  — random assignment preserving Judge's action counts within
                           (symbol, day, tf_sec) buckets.
* inverted_judge         — flip OPEN_LONG <-> OPEN_SHORT.
* confidence_shuffle     — shuffle confidence values within (symbol, regime, day)
                           strata, preserving actions/outcomes.
* time_shifted_judge     — DEFERRED (would require re-simulation at shifted ts).

The tool reads OFFICIAL artifacts only:
  - artifacts/phase5_calibration.jsonl
  - artifacts/judge_review/review_bundle.json (informational)
  - data/simulator/judge_path_diagnostics.jsonl (path geometry)

The tool writes DIAGNOSTIC sidecars only — it does NOT modify official artifacts.

This is a CURRENT-WINDOW sanity check. It cannot make a final OOS claim because the
observation window is only 4 days.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTIONABLE = {"OPEN_LONG", "OPEN_SHORT", "NO_ENTRY"}
ACTIONABLE_ENTRIES = {"OPEN_LONG", "OPEN_SHORT"}

CONFIDENCE_BUCKETS: Sequence[tuple[float, float, str]] = (
    (0.00, 0.25, "[0.00,0.25]"),
    (0.25, 0.50, "[0.25,0.50]"),
    (0.50, 0.75, "[0.50,0.75]"),
    (0.75, 1.01, "[0.75,1.00]"),
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_calibration(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_path_diagnostics(path: Path) -> dict[str, dict]:
    by_vid: dict[str, dict] = {}
    if not path.exists():
        return by_vid
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            vid = row.get("verdict_id")
            if vid:
                by_vid[vid] = row
    return by_vid


def derive_day_str(bar_close_ts_ms: int) -> str:
    return datetime.fromtimestamp(bar_close_ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def derive_confidence_bucket(conf: float) -> str:
    if conf is None or math.isnan(conf):
        return "unknown"
    for lo, hi, label in CONFIDENCE_BUCKETS:
        if lo <= conf < hi:
            return label
    return "unknown"


# ---------------------------------------------------------------------------
# Action-space evaluation primitives
# ---------------------------------------------------------------------------

def opposite_side(action: str) -> str:
    if action == "OPEN_LONG":
        return "OPEN_SHORT"
    if action == "OPEN_SHORT":
        return "OPEN_LONG"
    return action


def return_for_action(judge_action: str, candidate_action: str, raw_return: float,
                      matched_trade: bool) -> tuple[float, str]:
    """Return the raw return that would have been realized for ``candidate_action``
    given that Judge took ``judge_action`` and observed ``raw_return``.

    Returns (raw_return_value, quality_flag).

    quality_flag:
      * "same_side_realized"     — candidate matches Judge: realised return is exact.
      * "flipped_side_inferred"  — candidate is opposite side: -raw_return (assumes
                                   symmetric fill at same limit; documented limitation).
      * "no_entry_zero"          — candidate is NO_ENTRY: return = 0.
      * "unfilled_assumed_zero"  — Judge did not fill; assume opposite also unfilled
                                   (documented limitation).
    """
    if candidate_action == "NO_ENTRY":
        return 0.0, "no_entry_zero"
    if not matched_trade:
        return 0.0, "unfilled_assumed_zero"
    if candidate_action == judge_action:
        return raw_return, "same_side_realized"
    if candidate_action == opposite_side(judge_action):
        return -raw_return, "flipped_side_inferred"
    return 0.0, "no_entry_zero"


# ---------------------------------------------------------------------------
# Baseline generators
# ---------------------------------------------------------------------------

def build_inverted_judge(rows: list[dict]) -> list[dict]:
    """Per-row inversion: OPEN_LONG <-> OPEN_SHORT; NO_ENTRY/SUPPRESS unchanged."""
    out = []
    for row in rows:
        ja = row["entry_verdict"]
        if ja in ACTIONABLE_ENTRIES:
            new_action = opposite_side(ja)
        else:
            new_action = ja
        out.append({**row, "_baseline_action": new_action})
    return out


def build_random_same_frequency(rows: list[dict], seed: int) -> list[dict]:
    """Within (symbol, day, tf_sec) buckets, randomly reassign actions while preserving
    Judge's per-bucket action counts.

    Deterministic given ``seed`` and the sort order of rows by verdict_id.
    """
    rng = random.Random(seed)
    # Group rows by bucket, preserving global order.
    buckets: dict[tuple[str, str, int], list[int]] = defaultdict(list)
    rows_sorted = sorted(range(len(rows)),
                         key=lambda i: rows[i].get("verdict_id", str(i)))
    for i in rows_sorted:
        r = rows[i]
        day = derive_day_str(int(r["bar_close_ts"]))
        key = (r["symbol"], day, int(r["tf_sec"]))
        buckets[key].append(i)

    new_actions: dict[int, str] = {}
    for key, idxs in buckets.items():
        bucket_actions = [rows[i]["entry_verdict"] for i in idxs]
        shuffled = list(bucket_actions)
        rng.shuffle(shuffled)
        for i, a in zip(idxs, shuffled):
            new_actions[i] = a

    out = []
    for i, row in enumerate(rows):
        out.append({**row, "_baseline_action": new_actions[i]})
    return out


def build_confidence_shuffle(rows: list[dict], path_by_vid: dict[str, dict],
                             seed: int) -> list[dict]:
    """Within (symbol, regime, day) strata, shuffle confidence values; preserve
    actions and outcomes. Then re-bucket by shuffled confidence.
    """
    rng = random.Random(seed)
    buckets: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    rows_sorted = sorted(range(len(rows)),
                         key=lambda i: rows[i].get("verdict_id", str(i)))
    for i in rows_sorted:
        r = rows[i]
        vid = r.get("verdict_id")
        path = path_by_vid.get(vid, {}) if vid else {}
        regime = path.get("regime", "UNKNOWN") or "UNKNOWN"
        day = derive_day_str(int(r["bar_close_ts"]))
        buckets[(r["symbol"], regime, day)].append(i)

    new_conf: dict[int, float] = {}
    for key, idxs in buckets.items():
        confs = [float(rows[i]["confidence"]) for i in idxs]
        shuffled = list(confs)
        rng.shuffle(shuffled)
        for i, c in zip(idxs, shuffled):
            new_conf[i] = c

    out = []
    for i, row in enumerate(rows):
        c = new_conf[i]
        out.append({**row, "_baseline_action": row["entry_verdict"],
                    "_baseline_confidence": c})
    return out


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(baseline_rows: list[dict], judge_rows: list[dict],
                    path_by_vid: dict[str, dict],
                    avg_costs_per_trade: float,
                    use_baseline_confidence: bool = False) -> dict:
    """Compute aggregate + segmented metrics for one baseline."""
    n = len(baseline_rows)
    correct = 0
    actionable_count = 0
    raw_returns: list[float] = []
    net_returns: list[float] = []
    quality_flags = Counter()

    # Segment storage
    by_symbol: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})
    by_tf: dict[int, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})
    by_regime: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})
    by_bucket: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})

    for b_row, j_row in zip(baseline_rows, judge_rows):
        baseline_action = b_row["_baseline_action"]
        judge_action = j_row["entry_verdict"]
        optimal = j_row["optimal_action"]
        raw_v = j_row.get("raw_return")
        raw_j = float(raw_v) if raw_v is not None else 0.0
        matched = bool(j_row.get("matched_trade", False))

        baseline_raw, flag = return_for_action(judge_action, baseline_action,
                                               raw_j, matched)
        quality_flags[flag] += 1

        # Net return: if action is actionable and matched, subtract trade costs;
        # else 0.
        if baseline_action in ACTIONABLE_ENTRIES and flag in {"same_side_realized", "flipped_side_inferred"}:
            baseline_net = baseline_raw - avg_costs_per_trade
            actionable_count += 1
        else:
            baseline_net = 0.0

        # Correctness: baseline_action vs optimal_action
        is_correct = (baseline_action == optimal)
        if is_correct:
            correct += 1

        raw_returns.append(baseline_raw)
        net_returns.append(baseline_net)

        # Segments
        symbol = j_row["symbol"]
        tf = int(j_row["tf_sec"])
        path = path_by_vid.get(j_row.get("verdict_id", ""), {})
        regime = path.get("regime", "UNKNOWN") or "UNKNOWN"
        conf = b_row.get("_baseline_confidence", j_row["confidence"]) \
            if use_baseline_confidence else float(j_row["confidence"])
        bucket = derive_confidence_bucket(conf)

        for seg_map, key in [(by_symbol, symbol), (by_tf, tf),
                             (by_regime, regime), (by_bucket, bucket)]:
            s = seg_map[key]
            s["count"] += 1
            s["correct"] += int(is_correct)
            s["raw_sum"] += baseline_raw
            s["net_sum"] += baseline_net

    def finalize(seg_map):
        out = {}
        for k, s in seg_map.items():
            c = s["count"]
            out[str(k)] = {
                "count": c,
                "correct": s["correct"],
                "accuracy": s["correct"] / c if c else 0.0,
                "avg_raw_return": s["raw_sum"] / c if c else 0.0,
                "avg_net_return": s["net_sum"] / c if c else 0.0,
            }
        return out

    return {
        "count": n,
        "actionable_count": actionable_count,
        "correct": correct,
        "incorrect": n - correct,
        "accuracy": correct / n if n else 0.0,
        "avg_raw_return": sum(raw_returns) / n if n else 0.0,
        "avg_net_return": sum(net_returns) / n if n else 0.0,
        "positive_net_count": sum(1 for x in net_returns if x > 0),
        "negative_net_count": sum(1 for x in net_returns if x < 0),
        "quality_flags": dict(quality_flags),
        "by_symbol": finalize(by_symbol),
        "by_tf_sec": finalize(by_tf),
        "by_regime": finalize(by_regime),
        "by_confidence_bucket": finalize(by_bucket),
    }


def compute_judge_metrics(rows: list[dict], path_by_vid: dict[str, dict]) -> dict:
    """Headline metrics for Judge itself, computed from the same rows.

    Uses Judge's reported ``net_return`` directly (not recomputed)."""
    n = len(rows)
    correct = 0
    raw_returns: list[float] = []
    net_returns: list[float] = []

    by_symbol: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})
    by_tf: dict[int, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})
    by_regime: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})
    by_bucket: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "correct": 0, "raw_sum": 0.0, "net_sum": 0.0})

    for r in rows:
        is_correct = (r["entry_verdict"] == r["optimal_action"])
        if is_correct:
            correct += 1
        raw_v = r.get("raw_return")
        net_v = r.get("net_return")
        raw = float(raw_v) if raw_v is not None else 0.0
        net = float(net_v) if net_v is not None else 0.0
        raw_returns.append(raw)
        net_returns.append(net)

        path = path_by_vid.get(r.get("verdict_id", ""), {})
        regime = path.get("regime", "UNKNOWN") or "UNKNOWN"
        bucket = derive_confidence_bucket(float(r["confidence"]))

        for seg_map, key in [(by_symbol, r["symbol"]), (by_tf, int(r["tf_sec"])),
                             (by_regime, regime), (by_bucket, bucket)]:
            s = seg_map[key]
            s["count"] += 1
            s["correct"] += int(is_correct)
            s["raw_sum"] += raw
            s["net_sum"] += net

    def finalize(seg_map):
        out = {}
        for k, s in seg_map.items():
            c = s["count"]
            out[str(k)] = {
                "count": c,
                "correct": s["correct"],
                "accuracy": s["correct"] / c if c else 0.0,
                "avg_raw_return": s["raw_sum"] / c if c else 0.0,
                "avg_net_return": s["net_sum"] / c if c else 0.0,
            }
        return out

    return {
        "count": n,
        "correct": correct,
        "incorrect": n - correct,
        "accuracy": correct / n if n else 0.0,
        "avg_raw_return": sum(raw_returns) / n if n else 0.0,
        "avg_net_return": sum(net_returns) / n if n else 0.0,
        "positive_net_count": sum(1 for x in net_returns if x > 0),
        "negative_net_count": sum(1 for x in net_returns if x < 0),
        "by_symbol": finalize(by_symbol),
        "by_tf_sec": finalize(by_tf),
        "by_regime": finalize(by_regime),
        "by_confidence_bucket": finalize(by_bucket),
    }


# ---------------------------------------------------------------------------
# Confidence shuffle permutation test
# ---------------------------------------------------------------------------

def compute_confidence_monotonicity_score(metrics_by_bucket: dict[str, dict]) -> float:
    """Sum of bucket-to-bucket avg_net_return improvements ordered by confidence.

    Positive = higher confidence -> better; negative = inverse."""
    order = ["[0.00,0.25]", "[0.25,0.50]", "[0.50,0.75]", "[0.75,1.00]"]
    nets = [metrics_by_bucket.get(b, {}).get("avg_net_return", 0.0) for b in order
            if b in metrics_by_bucket]
    if len(nets) < 2:
        return 0.0
    return nets[-1] - nets[0]


def run_confidence_shuffle_permutations(rows: list[dict], path_by_vid: dict,
                                        avg_costs: float, base_seed: int,
                                        n_perms: int) -> dict:
    """Run ``n_perms`` confidence shuffles; return distribution of monotonicity score."""
    scores: list[float] = []
    for k in range(n_perms):
        shuffled = build_confidence_shuffle(
            rows, path_by_vid, seed=base_seed + k)
        m = compute_metrics(shuffled, rows, path_by_vid, avg_costs,
                            use_baseline_confidence=True)
        scores.append(compute_confidence_monotonicity_score(
            m["by_confidence_bucket"]))
    if not scores:
        return {"n_perms": 0}
    scores_sorted = sorted(scores)
    return {
        "n_perms": n_perms,
        "score_mean": sum(scores) / len(scores),
        "score_min": scores_sorted[0],
        "score_max": scores_sorted[-1],
        "score_p05": scores_sorted[int(0.05 * len(scores_sorted))],
        "score_p50": scores_sorted[len(scores_sorted) // 2],
        "score_p95": scores_sorted[int(0.95 * (len(scores_sorted) - 1))],
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_json_summary(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True),
                    encoding="utf-8")


def write_segment_csv(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_out = []
    for baseline_name, metrics in summary["baselines"].items():
        for seg_type, seg_map in [("symbol", metrics.get("by_symbol", {})),
                                  ("tf_sec", metrics.get("by_tf_sec", {})),
                                  ("regime", metrics.get("by_regime", {})),
                                  ("confidence_bucket", metrics.get("by_confidence_bucket", {}))]:
            for seg_value, s in seg_map.items():
                rows_out.append({
                    "baseline": baseline_name,
                    "segment_type": seg_type,
                    "segment_value": seg_value,
                    "count": s["count"],
                    "correct": s.get("correct", 0),
                    "accuracy": s["accuracy"],
                    "avg_raw_return": s["avg_raw_return"],
                    "avg_net_return": s["avg_net_return"],
                })
    if not rows_out:
        return
    fields = list(rows_out[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)


def write_report(path: Path, summary: dict, cmd: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    judge = summary["baselines"]["judge"]
    inverted = summary["baselines"]["inverted_judge"]
    rsf = summary["baselines"]["random_same_frequency"]
    cs = summary["baselines"]["confidence_shuffle"]
    perms = summary.get("confidence_shuffle_permutations", {})

    def fmt_pct(x): return f"{x * 100:.2f}%"
    def fmt_ret(x): return f"{x:+.6f}"

    verdict = summary["verdict"]

    lines = [
        "# PKG-6A JUDGE REVIEW BASELINES — CURRENT WINDOW — COMPLETION REPORT",
        "",
        f"**Date:** {summary['generated_at']}",
        f"**Window:** {summary['window_label']}  (4-day current dataset, NOT OOS)",
        "**Scope:** DIAGNOSTIC-ONLY — baseline sanity check on current window",
        "",
        "> **WARNING**: This report is a CURRENT-WINDOW baseline sanity check. The",
        "> dataset spans only 4 days. **No OOS claim is made here.** PKG-6B requires",
        "> ≥2 weeks of Judge logs before any final claim of edge or no-edge.",
        "",
        "---",
        "",
        "## 1. Verdict",
        "",
        f"**`{verdict}`**",
        "",
        summary.get("verdict_rationale", ""),
        "",
        "---",
        "",
        "## 2. Problem framing",
        "",
        "- **Symptom**: PKG-4 reports `avg_net_return = -0.003679`, `disagreement = 88.4%`,"
        " inverse confidence calibration. Need to know whether Judge underperforms simple"
        " baselines on this same window.",
        "- **Root cause (to test)**: unknown — could be insufficient signal, anti-signal,"
        " or random noise on a short window.",
        "- **Contributing factors**: 4-day window, only 7 symbols, no OOS partition,"
        " optimistic_touch fill model, pct_only mode (no USD ROI).",
        "- **Masking layer**: short window can produce both false positive and false"
        " negative claims of edge.",
        "- **Broader bottleneck**: counterfactual ledger (`supports_counterfactual_join=false`)"
        " prevents direct Judge-vs-runtime comparison.",
        "",
        "---",
        "",
        "## 3. FACTS",
        "",
        f"**Command run:**",
        f"```bash",
        f"{cmd}",
        f"```",
        "",
        f"- Calibration records loaded: {judge['count']:,}",
        f"- Path diagnostics rows used for regime/confidence segments: {summary['path_rows_used']:,}",
        f"- Cost model (per trade, raw_return → net_return delta): {summary['avg_costs_per_trade']:.6f}",
        f"- Random seed: {summary['seed']}",
        f"- Confidence shuffle permutations: {perms.get('n_perms', 0)}",
        "",
        "---",
        "",
        "## 4. INFERENCES",
        "",
        f"- Judge accuracy ({fmt_pct(judge['accuracy'])}) "
        f"{'<' if judge['accuracy'] < rsf['accuracy'] else '≥'} "
        f"random_same_frequency ({fmt_pct(rsf['accuracy'])}).",
        f"- Inverted Judge accuracy ({fmt_pct(inverted['accuracy'])}) "
        f"{'>' if inverted['accuracy'] > judge['accuracy'] else '≤'} "
        f"Judge accuracy ({fmt_pct(judge['accuracy'])}).",
        f"- Judge avg_net_return ({fmt_ret(judge['avg_net_return'])}) vs inverted "
        f"({fmt_ret(inverted['avg_net_return'])}).",
        f"- Confidence shuffle monotonicity distribution: mean="
        f"{perms.get('score_mean', 0):.6f}, "
        f"observed Judge score={summary.get('judge_confidence_monotonicity_score', 0):.6f}.",
        "",
        "---",
        "",
        "## 5. ASSUMPTIONS",
        "",
        "- A1: `raw_return` in calibration records is exactly side-adjusted; flipping side"
        " ⇒ negating raw_return is valid for filled rows.",
        "- A2: Unfilled rows (matched_trade=false) treated as zero return for any baseline"
        " — the opposite side might have filled at a different limit; this is a known"
        " optimism in baselines that recommend NO_ENTRY for unfilled bars.",
        "- A3: Cost model uses the constant fee+slippage from `judge_simulator.yaml`"
        " (25 bps + 0.1%) applied identically across Judge and baselines.",
        "- A4: Regime tag is sourced from `judge_path_diagnostics.jsonl`; rows without a"
        " path diagnostic carry `regime=UNKNOWN`.",
        "",
        "---",
        "",
        "## 6. UNKNOWNS",
        "",
        "- U1: time_shifted_judge is NOT implemented in this package because shifting"
        " verdict ts would require re-simulating outcomes at the shifted timestamp; the"
        " current outcomes are keyed by bar_close_ts. Deferred to PKG-6B.",
        "- U2: Whether the observed inverted_judge advantage (if any) persists on a"
        " longer window. Cannot answer without ≥2 weeks of data.",
        "- U3: Whether the symbol-level negative cohort (BTCUSDT 0 TP hits per PKG-5)"
        " reflects a systematic anti-signal or a window-specific drift.",
        "",
        "---",
        "",
        "## 7. Baseline methods",
        "",
        "### random_same_frequency",
        "Within each (symbol, day, tf_sec) bucket, the bag of Judge's actions is shuffled"
        " and reassigned. This preserves per-bucket action counts (exact LONG/SHORT mix)"
        " but breaks the per-row correlation between Judge confidence and outcome.",
        " Limitation: rows assigned NO_ENTRY by Judge (none in current dataset) remain"
        " NO_ENTRY; rows where Judge did not fill carry zero return for any baseline.",
        "",
        "### inverted_judge",
        "Per-row flip: OPEN_LONG ↔ OPEN_SHORT; NO_ENTRY/SUPPRESS/UNKNOWN unchanged."
        " Computed return: `-raw_return - costs` for filled rows; 0 for unfilled.",
        " Limitation: assumes symmetric fill at same limit price — the opposite side"
        " might not have filled in reality.",
        "",
        "### confidence_shuffle",
        "Within each (symbol, regime, day) stratum, the bag of confidence values is"
        " shuffled. Actions and returns are unchanged. Records are then re-bucketed by"
        " shuffled confidence. Tests whether the rank of confidence carries information"
        " about realized return.",
        "",
        "### time_shifted_judge",
        "**DEFERRED to PKG-6B.** Shifting verdict ts to bar_close ± Nm would require"
        " re-running the outcomes materializer at the shifted timestamp, which is outside"
        " the scope of this diagnostic.",
        "",
        "---",
        "",
        "## 8. Aggregate comparison",
        "",
        "| metric | judge | random_same_frequency | inverted_judge | confidence_shuffle |",
        "|---|---|---|---|---|",
        f"| count                | {judge['count']:,} | {rsf['count']:,} | {inverted['count']:,} | {cs['count']:,} |",
        f"| correct              | {judge['correct']:,} | {rsf['correct']:,} | {inverted['correct']:,} | {cs['correct']:,} |",
        f"| accuracy             | {fmt_pct(judge['accuracy'])} | {fmt_pct(rsf['accuracy'])} | {fmt_pct(inverted['accuracy'])} | {fmt_pct(cs['accuracy'])} |",
        f"| avg_raw_return       | {fmt_ret(judge['avg_raw_return'])} | {fmt_ret(rsf['avg_raw_return'])} | {fmt_ret(inverted['avg_raw_return'])} | {fmt_ret(cs['avg_raw_return'])} |",
        f"| avg_net_return       | {fmt_ret(judge['avg_net_return'])} | {fmt_ret(rsf['avg_net_return'])} | {fmt_ret(inverted['avg_net_return'])} | {fmt_ret(cs['avg_net_return'])} |",
        f"| positive_net_count   | {judge['positive_net_count']:,} | {rsf['positive_net_count']:,} | {inverted['positive_net_count']:,} | {cs['positive_net_count']:,} |",
        f"| negative_net_count   | {judge['negative_net_count']:,} | {rsf['negative_net_count']:,} | {inverted['negative_net_count']:,} | {cs['negative_net_count']:,} |",
        "",
        "---",
        "",
        "## 9. Segment comparison",
        "",
        "### By symbol — accuracy",
        "",
        "| symbol | judge | random_same_frequency | inverted_judge |",
        "|---|---|---|---|",
    ]
    for sym in sorted(judge.get("by_symbol", {})):
        j = judge["by_symbol"][sym]
        r = rsf["by_symbol"].get(sym, {})
        inv = inverted["by_symbol"].get(sym, {})
        lines.append(
            f"| {sym} | {fmt_pct(j['accuracy'])} | {fmt_pct(r.get('accuracy', 0))} | {fmt_pct(inv.get('accuracy', 0))} |")

    lines += [
        "",
        "### By symbol — avg_net_return",
        "",
        "| symbol | judge | random_same_frequency | inverted_judge |",
        "|---|---|---|---|",
    ]
    for sym in sorted(judge.get("by_symbol", {})):
        j = judge["by_symbol"][sym]
        r = rsf["by_symbol"].get(sym, {})
        inv = inverted["by_symbol"].get(sym, {})
        lines.append(
            f"| {sym} | {fmt_ret(j['avg_net_return'])} | {fmt_ret(r.get('avg_net_return', 0))} | {fmt_ret(inv.get('avg_net_return', 0))} |")

    lines += [
        "",
        "### By regime — accuracy",
        "",
        "| regime | judge | random_same_frequency | inverted_judge |",
        "|---|---|---|---|",
    ]
    for reg in sorted(judge.get("by_regime", {})):
        j = judge["by_regime"][reg]
        r = rsf["by_regime"].get(reg, {})
        inv = inverted["by_regime"].get(reg, {})
        lines.append(
            f"| {reg} | {fmt_pct(j['accuracy'])} | {fmt_pct(r.get('accuracy', 0))} | {fmt_pct(inv.get('accuracy', 0))} |")

    lines += [
        "",
        "### By confidence bucket — accuracy",
        "",
        "| bucket | judge | random_same_frequency | confidence_shuffle |",
        "|---|---|---|---|",
    ]
    for b in ["[0.00,0.25]", "[0.25,0.50]", "[0.50,0.75]", "[0.75,1.00]"]:
        j = judge.get("by_confidence_bucket", {}).get(b, {})
        r = rsf.get("by_confidence_bucket", {}).get(b, {})
        cs_b = cs.get("by_confidence_bucket", {}).get(b, {})
        lines.append(
            f"| {b} | {fmt_pct(j.get('accuracy', 0))} | {fmt_pct(r.get('accuracy', 0))} | {fmt_pct(cs_b.get('accuracy', 0))} |")

    lines += [
        "",
        "---",
        "",
        "## 10. Confidence shuffle results",
        "",
        "**Monotonicity score** = avg_net_return(highest bucket) − avg_net_return(lowest bucket).",
        " Positive ⇒ higher confidence is better. Negative ⇒ inverse.",
        "",
        f"- Judge observed score: **{summary.get('judge_confidence_monotonicity_score', 0):.6f}**",
        f"- Shuffle permutations: {perms.get('n_perms', 0)}",
        f"- Shuffle score mean: {perms.get('score_mean', 0):.6f}",
        f"- Shuffle score 5th percentile: {perms.get('score_p05', 0):.6f}",
        f"- Shuffle score 50th percentile: {perms.get('score_p50', 0):.6f}",
        f"- Shuffle score 95th percentile: {perms.get('score_p95', 0):.6f}",
        "",
        summary.get("confidence_shuffle_interpretation", ""),
        "",
        "---",
        "",
        "## 11. Inverted Judge result",
        "",
        summary.get("inverted_judge_interpretation", ""),
        "",
        "---",
        "",
        "## 12. Current-window limitations",
        "",
        "- Window: 2026-05-17 → 2026-05-20 (≈4 days).",
        "- No train/OOS partition — every claim here is in-sample.",
        "- BTCUSDT has 0 TP hits in the dataset (PKG-5); inverted_judge's apparent edge there"
        " may be path-asymmetry not signal.",
        "- 1000PEPEUSDT, DOGEUSDT have fewest matched rows ⇒ widest CI.",
        "- Cost model is constant 35 bps; no calibrated per-symbol spread.",
        "- **No final claim of Judge edge or no-edge is made.**",
        "",
        "---",
        "",
        "## 13. Required PKG-6B collection plan",
        "",
        "Before any OOS claim can be made:",
        "",
        "- **Window**: ≥14 calendar days of `logs/judge_experts/` (currently 4).",
        "- **Candle backfill**: cover the same 14+ days for all 7 symbols (PKG-7 logic).",
        "- **Materialized outcomes**: re-run PKG-1 materializer on the extended window.",
        "- **Min N per cohort**: 200 verdicts per (symbol × confidence_bucket) cell on the"
        " OOS half — current dataset has 4 cells below 200 already.",
        "- **OOS partition**: chronological 70/30 split with a buffer day between train/OOS.",
        "- **Baselines**: re-run this exact tool on the OOS half only.",
        "- **time_shifted_judge**: implement once outcomes can be rematerialized at"
        " shifted ts.",
        "- **expert_agreement segment**: requires chamber_aggregate consensus_strength"
        " join (deferred to PKG-6B).",
        "",
        "---",
        "",
        "## 14. Next package gate",
        "",
        summary.get("next_recommendation", ""),
        "",
        "---",
        "",
        "## Appendix A — files produced",
        "",
        "```",
        "A  tools/judge/build_review_baselines_current_window.py",
        "A  tests/alpha_search/judge/test_review_baselines_current_window.py",
        "A  data/simulator/judge_current_window_baselines.json       (DIAGNOSTIC-ONLY)",
        "A  data/simulator/judge_current_window_baselines_by_segment.csv  (DIAGNOSTIC-ONLY)",
        "A  reports/PKG_6A_JUDGE_REVIEW_BASELINES_CURRENT_WINDOW_REPORT.md",
        "```",
        "",
        "No official artifacts modified.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Verdict + interpretation logic
# ---------------------------------------------------------------------------

def derive_verdict_and_text(judge: dict, inverted: dict, rsf: dict, cs: dict,
                            perms: dict, judge_score: float) -> dict:
    """Decide final verdict + write human-readable interpretation strings."""
    judge_worse_than_random = judge["accuracy"] < rsf["accuracy"]
    inverted_better = inverted["avg_net_return"] > judge["avg_net_return"] \
        and inverted["accuracy"] > judge["accuracy"]
    shuffle_mean = perms.get("score_mean", 0.0)
    shuffle_p95 = perms.get("score_p95", 0.0)
    shuffle_p05 = perms.get("score_p05", 0.0)
    confidence_signal = judge_score > shuffle_p95

    # Verdict logic
    if judge_worse_than_random and inverted_better:
        verdict = "BASELINES_CURRENT_WINDOW_COMPLETE_NEGATIVE"
        rationale = ("Judge underperforms random_same_frequency on accuracy and"
                     " inverted_judge produces a higher avg_net_return than Judge."
                     " On this 4-day window, Judge behaves as anti-signal. THIS IS"
                     " NOT AN OOS CLAIM — PKG-6B is required to confirm.")
    else:
        verdict = "BASELINES_CURRENT_WINDOW_COMPLETE"
        rationale = ("Judge does not unambiguously underperform all baselines on this"
                     " 4-day window. PKG-6B is still required before any final claim.")

    if inverted_better:
        inv_interp = (f"On this 4-day window inverted_judge has avg_net_return"
                      f" {inverted['avg_net_return']:+.6f} vs Judge"
                      f" {judge['avg_net_return']:+.6f} and accuracy"
                      f" {inverted['accuracy']*100:.2f}% vs Judge {judge['accuracy']*100:.2f}%."
                      " Inverted Judge appears to beat Judge on this window. This is"
                      " consistent with PKG-4's inverse confidence finding. **CAVEAT**:"
                      " inversion assumes symmetric fill at the same limit price; the"
                      " opposite side might not have filled in reality.")
    else:
        inv_interp = (f"Inverted Judge avg_net_return {inverted['avg_net_return']:+.6f}"
                      f" vs Judge {judge['avg_net_return']:+.6f}. Inverted Judge does"
                      " NOT clearly beat Judge on this window.")

    if confidence_signal:
        cs_interp = (f"Judge confidence monotonicity score ({judge_score:+.6f}) exceeds"
                     f" the 95th percentile of {perms.get('n_perms', 0)} random shuffles"
                     f" ({shuffle_p95:+.6f}). Confidence appears to carry weak"
                     " ordering signal on this window.")
    else:
        cs_interp = (f"Judge confidence monotonicity score ({judge_score:+.6f}) is NOT"
                     f" above the 95th percentile of {perms.get('n_perms', 0)} random"
                     f" shuffles ({shuffle_p95:+.6f}). Confidence shows no useful"
                     " ordering signal on this window — consistent with PKG-4's inverse"
                     " calibration finding.")

    if verdict == "BASELINES_CURRENT_WINDOW_COMPLETE_NEGATIVE":
        next_rec = ("**STOP-and-COLLECT.** Do NOT promote Judge. Do NOT tune thresholds"
                    " on this window. Begin PKG-6B data collection (≥14 days) before any"
                    " further decision. If inverted_judge advantage persists on OOS, the"
                    " Judge ladder direction itself must be re-examined.")
    else:
        next_rec = ("**PKG-6B: REVIEW_BASELINES_AND_OOS.** Collect ≥14 days of Judge logs"
                    " + candles; re-run materializer; run this exact baseline tool on a"
                    " chronologically-split OOS half. Implement time_shifted_judge.")

    return {
        "verdict": verdict,
        "verdict_rationale": rationale,
        "inverted_judge_interpretation": inv_interp,
        "confidence_shuffle_interpretation": cs_interp,
        "next_recommendation": next_rec,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration-path", type=Path,
                        default=Path("artifacts/phase5_calibration.jsonl"))
    parser.add_argument("--review-dir", type=Path,
                        default=Path("artifacts/judge_review"))
    parser.add_argument("--path-diagnostics", type=Path,
                        default=Path("data/simulator/judge_path_diagnostics.jsonl"))
    parser.add_argument("--out-json", type=Path,
                        default=Path("data/simulator/judge_current_window_baselines.json"))
    parser.add_argument("--out-csv", type=Path,
                        default=Path("data/simulator/judge_current_window_baselines_by_segment.csv"))
    parser.add_argument("--report-path", type=Path,
                        default=Path("reports/PKG_6A_JUDGE_REVIEW_BASELINES_CURRENT_WINDOW_REPORT.md"))
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--n-permutations", type=int, default=200)
    parser.add_argument("--window-label", type=str,
                        default="2026-05-17 → 2026-05-20")
    args = parser.parse_args(argv)

    print(
        f"[baselines] loading calibration: {args.calibration_path}", file=sys.stderr)
    rows = load_calibration(args.calibration_path)
    print(f"[baselines] loaded {len(rows)} calibration rows", file=sys.stderr)

    print(
        f"[baselines] loading path diagnostics: {args.path_diagnostics}", file=sys.stderr)
    path_by_vid = load_path_diagnostics(args.path_diagnostics)
    print(f"[baselines] path rows: {len(path_by_vid)}", file=sys.stderr)

    # Derive avg cost per trade from first row (fee_cost + slippage_cost are constants)
    if rows:
        avg_costs = float(rows[0].get("fee_cost", 0.0)) + \
            float(rows[0].get("slippage_cost", 0.0))
    else:
        avg_costs = 0.0035
    print(
        f"[baselines] cost-per-trade (fee+slip): {avg_costs:.6f}", file=sys.stderr)

    # Build baselines
    print(f"[baselines] computing Judge metrics...", file=sys.stderr)
    judge_metrics = compute_judge_metrics(rows, path_by_vid)

    print(f"[baselines] computing inverted_judge...", file=sys.stderr)
    inv_rows = build_inverted_judge(rows)
    inv_metrics = compute_metrics(inv_rows, rows, path_by_vid, avg_costs)

    print(
        f"[baselines] computing random_same_frequency (seed={args.seed})...", file=sys.stderr)
    rsf_rows = build_random_same_frequency(rows, seed=args.seed)
    rsf_metrics = compute_metrics(rsf_rows, rows, path_by_vid, avg_costs)

    print(
        f"[baselines] computing confidence_shuffle (seed={args.seed})...", file=sys.stderr)
    cs_rows = build_confidence_shuffle(rows, path_by_vid, seed=args.seed)
    cs_metrics = compute_metrics(cs_rows, rows, path_by_vid, avg_costs,
                                 use_baseline_confidence=True)

    print(f"[baselines] running {args.n_permutations} confidence-shuffle permutations...",
          file=sys.stderr)
    perms = run_confidence_shuffle_permutations(rows, path_by_vid, avg_costs,
                                                base_seed=args.seed + 1,
                                                n_perms=args.n_permutations)

    judge_score = compute_confidence_monotonicity_score(
        judge_metrics["by_confidence_bucket"])

    summary = {
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "window_label": args.window_label,
        "seed": args.seed,
        "n_permutations": args.n_permutations,
        "avg_costs_per_trade": avg_costs,
        "path_rows_used": len(path_by_vid),
        "diagnostic_scope": "current_window_baselines_NOT_OOS",
        "baselines": {
            "judge": judge_metrics,
            "inverted_judge": inv_metrics,
            "random_same_frequency": rsf_metrics,
            "confidence_shuffle": cs_metrics,
        },
        "confidence_shuffle_permutations": perms,
        "judge_confidence_monotonicity_score": judge_score,
        "deferred_baselines": {
            "time_shifted_judge": "Deferred to PKG-6B; requires outcome re-simulation at shifted ts.",
        },
    }

    # Verdict + text
    interp = derive_verdict_and_text(judge_metrics, inv_metrics, rsf_metrics,
                                     cs_metrics, perms, judge_score)
    summary.update(interp)

    print(f"[baselines] writing JSON: {args.out_json}", file=sys.stderr)
    write_json_summary(args.out_json, summary)

    print(f"[baselines] writing CSV: {args.out_csv}", file=sys.stderr)
    write_segment_csv(args.out_csv, summary)

    cmd = (
        "PYTHONPATH=. py -3 -m tools.judge.build_review_baselines_current_window \\\n"
        f"  --calibration-path {args.calibration_path} \\\n"
        f"  --review-dir {args.review_dir} \\\n"
        f"  --path-diagnostics {args.path_diagnostics} \\\n"
        f"  --out-json {args.out_json} \\\n"
        f"  --out-csv {args.out_csv} \\\n"
        f"  --report-path {args.report_path} \\\n"
        f"  --seed {args.seed}"
    )
    print(f"[baselines] writing report: {args.report_path}", file=sys.stderr)
    write_report(args.report_path, summary, cmd)

    print(f"[baselines] verdict: {summary['verdict']}", file=sys.stderr)
    print(f"[baselines] judge accuracy={judge_metrics['accuracy']:.4f} "
          f"net={judge_metrics['avg_net_return']:+.6f}", file=sys.stderr)
    print(f"[baselines] random   accuracy={rsf_metrics['accuracy']:.4f} "
          f"net={rsf_metrics['avg_net_return']:+.6f}", file=sys.stderr)
    print(f"[baselines] inverted accuracy={inv_metrics['accuracy']:.4f} "
          f"net={inv_metrics['avg_net_return']:+.6f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
