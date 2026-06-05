from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"

IN_ENRICHED = REPORTS / "AURORA_TREND_UP_P1_ENRICHED_ENTRIES_2026_05_04.csv"
IN_FILTERS = REPORTS / "AURORA_TREND_UP_P1_FILTER_DIAGNOSTICS_2026_05_04.csv"
IN_SEPARATOR_JSON = REPORTS / \
    "AURORA_TREND_UP_P1_GOOD_BAD_ENTRY_SEPARATOR_V1_2026_05_04.json"

OUT_MD = REPORTS / "AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_2026_05_04.md"
OUT_JSON = REPORTS / "AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_2026_05_04.json"
OUT_FILTERS = REPORTS / \
    "AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_FILTERS_2026_05_04.csv"
OUT_FOLDS = REPORTS / "AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_FOLDS_2026_05_04.csv"
OUT_ENTRIES = REPORTS / \
    "AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_ENTRIES_2026_05_04.csv"


@dataclass(frozen=True)
class CandidatePolicy:
    enabled: bool = True
    regime: str = "TREND_UP"
    min_confidence: float = 0.40
    max_confidence_exclusive: float = 0.45
    side_policy: str = "regime_aligned_buy"
    mode: str = "shadow"


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


def compute_drawdown_proxy(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    s = df.sort_values("entry_ts")["pure_pnl_pct"].astype(float).cumsum()
    dd = s.cummax() - s
    return safe_float(dd.max())


def compute_metrics(df: pd.DataFrame, baseline_good: int, baseline_bad: int) -> dict[str, Any]:
    admitted = int(len(df))
    good = int((df["profitable_label"] == 1).sum())
    bad = int((df["profitable_label"] == 0).sum())
    kept_good = good
    kept_bad = bad
    rejected_good = baseline_good - kept_good
    rejected_bad = baseline_bad - kept_bad

    return {
        "admitted_count": admitted,
        "profitable_count": good,
        "losing_count": bad,
        "win_rate": (good / admitted) if admitted else None,
        "total_pnl_pct": safe_float(df["pure_pnl_pct"].sum()) if admitted else None,
        "avg_pnl_pct": safe_float(df["pure_pnl_pct"].mean()) if admitted else None,
        "avg_r": safe_float(df["pure_r_multiple"].mean()) if admitted else None,
        "max_drawdown_proxy_pct": compute_drawdown_proxy(df),
        "avg_mfe_bps": safe_float(df["mfe_bps"].mean()) if admitted else None,
        "avg_mae_bps": safe_float(df["mae_bps"].mean()) if admitted else None,
        "median_mfe_bps": safe_float(df["mfe_bps"].median()) if admitted else None,
        "median_mae_bps": safe_float(df["mae_bps"].median()) if admitted else None,
        "kept_good_count": kept_good,
        "rejected_bad_count": rejected_bad,
        "rejected_good_count": rejected_good,
        "kept_bad_count": kept_bad,
        "kept_good_rate": (kept_good / baseline_good) if baseline_good else None,
        "rejected_bad_rate": (rejected_bad / baseline_bad) if baseline_bad else None,
    }


def fmt(v: Any, n: int = 4) -> str:
    x = safe_float(v)
    if x is None:
        return "na"
    return f"{x:.{n}f}"


def five_folds(df: pd.DataFrame) -> pd.DataFrame:
    x = df.sort_values("entry_ts").reset_index(drop=True).copy()
    if x.empty:
        return pd.DataFrame(columns=["fold", "start_ts", "end_ts", "count", "good", "bad", "win_rate", "total_pnl_pct", "avg_r", "mdd_proxy"])

    x["fold"] = pd.qcut(x.index, q=5, labels=False, duplicates="drop") + 1
    rows: list[dict[str, Any]] = []
    for fold, g in x.groupby("fold"):
        rows.append(
            {
                "fold": int(fold),
                "start_ts": str(g["entry_ts"].iloc[0]),
                "end_ts": str(g["entry_ts"].iloc[-1]),
                "count": int(len(g)),
                "good": int((g["profitable_label"] == 1).sum()),
                "bad": int((g["profitable_label"] == 0).sum()),
                "win_rate": safe_float((g["profitable_label"] == 1).mean()),
                "total_pnl_pct": safe_float(g["pure_pnl_pct"].sum()),
                "avg_r": safe_float(g["pure_r_multiple"].mean()),
                "mdd_proxy": compute_drawdown_proxy(g),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    if not IN_ENRICHED.exists():
        raise RuntimeError(f"Missing input: {IN_ENRICHED}")
    if not IN_FILTERS.exists():
        raise RuntimeError(f"Missing input: {IN_FILTERS}")

    policy = CandidatePolicy()

    enriched = pd.read_csv(IN_ENRICHED)
    filters = pd.read_csv(IN_FILTERS)
    separator_payload = json.loads(IN_SEPARATOR_JSON.read_text(
        encoding="utf-8")) if IN_SEPARATOR_JSON.exists() else {}

    # Strict scope: TREND_UP P1 cohort from previous forensic output.
    if "admit_confidence" not in enriched.columns:
        raise RuntimeError(
            "enriched table missing admit_confidence; cannot apply F5 confidence candidate exactly.")

    baseline = enriched.copy()
    if "regime" not in baseline.columns:
        baseline["regime"] = "TREND_UP"
    candidate_mask = (baseline["admit_confidence"] >= policy.min_confidence) & (
        baseline["admit_confidence"] < policy.max_confidence_exclusive)
    candidate = baseline[candidate_mask].copy()

    baseline_good = int((baseline["profitable_label"] == 1).sum())
    baseline_bad = int((baseline["profitable_label"] == 0).sum())

    baseline_metrics = compute_metrics(baseline, baseline_good, baseline_bad)
    candidate_metrics = compute_metrics(candidate, baseline_good, baseline_bad)

    # Controls to avoid overclaiming from one slice.
    f6 = baseline[(baseline["admit_confidence"] >= 0.45) &
                  (baseline["admit_confidence"] <= 0.50)].copy()
    eth = baseline[baseline["symbol"] == "ETHUSDT"].copy()
    btc = baseline[baseline["symbol"] == "BTCUSDT"].copy()

    rows = [
        {"filter": "BASELINE_F0_P1_ALL",
            "definition": "all P1 newly admitted TREND_UP", **baseline_metrics},
        {
            "filter": "CANDIDATE_F5_TREND_UP_CONF_040_045",
            "definition": "0.40 <= admit_confidence < 0.45, TREND_UP only, shadow-only",
            **candidate_metrics,
        },
        {"filter": "CONTROL_F6_CONF_045_050", "definition": "0.45 <= admit_confidence <= 0.50",
            **compute_metrics(f6, baseline_good, baseline_bad)},
        {"filter": "CONTROL_ETH_ONLY", "definition": "symbol == ETHUSDT",
            **compute_metrics(eth, baseline_good, baseline_bad)},
        {"filter": "CONTROL_BTC_ONLY", "definition": "symbol == BTCUSDT",
            **compute_metrics(btc, baseline_good, baseline_bad)},
    ]
    out_filters = pd.DataFrame(rows)

    # Stability checks for candidate.
    symbol_split = (
        candidate.groupby("symbol", dropna=False)
        .apply(lambda g: pd.Series({
            "count": int(len(g)),
            "good": int((g["profitable_label"] == 1).sum()),
            "bad": int((g["profitable_label"] == 0).sum()),
            "win_rate": safe_float((g["profitable_label"] == 1).mean()),
            "total_pnl_pct": safe_float(g["pure_pnl_pct"].sum()),
            "avg_r": safe_float(g["pure_r_multiple"].mean()),
            "mdd_proxy": compute_drawdown_proxy(g),
        }))
        .reset_index()
    )

    age_split = (
        candidate.groupby("age_bucket_6", dropna=False)
        .apply(lambda g: pd.Series({
            "count": int(len(g)),
            "good": int((g["profitable_label"] == 1).sum()),
            "bad": int((g["profitable_label"] == 0).sum()),
            "win_rate": safe_float((g["profitable_label"] == 1).mean()),
            "total_pnl_pct": safe_float(g["pure_pnl_pct"].sum()),
            "avg_r": safe_float(g["pure_r_multiple"].mean()),
        }))
        .reset_index()
        .sort_values("count", ascending=False)
    )

    pos_split = (
        candidate.groupby("position_in_range_10_bucket", dropna=False)
        .apply(lambda g: pd.Series({
            "count": int(len(g)),
            "good": int((g["profitable_label"] == 1).sum()),
            "bad": int((g["profitable_label"] == 0).sum()),
            "win_rate": safe_float((g["profitable_label"] == 1).mean()),
            "total_pnl_pct": safe_float(g["pure_pnl_pct"].sum()),
            "avg_r": safe_float(g["pure_r_multiple"].mean()),
        }))
        .reset_index()
        .sort_values("count", ascending=False)
    )

    folds = five_folds(candidate)

    # Acceptance rule for shadow candidate (diagnostic only):
    # non-degraded total_pnl/avg_r vs baseline + meaningful bad rejection + manageable good retention.
    acceptance = {
        "non_degraded_total_pnl_vs_baseline": bool((candidate_metrics["total_pnl_pct"] or -1e9) >= (baseline_metrics["total_pnl_pct"] or -1e9)),
        "non_degraded_avg_r_vs_baseline": bool((candidate_metrics["avg_r"] or -1e9) >= (baseline_metrics["avg_r"] or -1e9)),
        "rejected_bad_rate_ge_0_50": bool((candidate_metrics["rejected_bad_rate"] or 0.0) >= 0.50),
        "kept_good_rate_ge_0_55": bool((candidate_metrics["kept_good_rate"] or 0.0) >= 0.55),
    }
    acceptance["all_pass"] = all(acceptance.values())

    # Reconcile against prior separator report if available.
    prior_f5 = None
    if not filters.empty and (filters["filter"] == "F5_CONF_040_045_ONLY").any():
        prior_f5 = filters[filters["filter"] ==
                           "F5_CONF_040_045_ONLY"].iloc[0].to_dict()

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "task": "AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1",
        "hard_laws": [
            "No runtime mutation",
            "No production YAML patch",
            "No live execution",
            "No execution_position changes",
            "YAML + Pydantic remain SSOT",
            "No hidden constants",
            "No silent fallback",
            "No TREND_DOWN admission expansion",
            "No global max-cap disable",
            "No max-cap 0.50 broad deployment",
        ],
        "candidate_policy": {
            "enabled": policy.enabled,
            "regime": policy.regime,
            "min_confidence": policy.min_confidence,
            "max_confidence_exclusive": policy.max_confidence_exclusive,
            "side_policy": policy.side_policy,
            "mode": policy.mode,
        },
        "cohort": {
            "baseline_count": int(len(baseline)),
            "candidate_count": int(len(candidate)),
            "baseline_good": baseline_good,
            "baseline_bad": baseline_bad,
            "candidate_good": int((candidate["profitable_label"] == 1).sum()),
            "candidate_bad": int((candidate["profitable_label"] == 0).sum()),
        },
        "metrics": {
            "baseline": baseline_metrics,
            "candidate": candidate_metrics,
            "controls": out_filters.to_dict("records"),
        },
        "stability": {
            "by_symbol": symbol_split.to_dict("records"),
            "by_age": age_split.to_dict("records"),
            "by_position_in_range_10": pos_split.to_dict("records"),
            "five_folds": folds.to_dict("records"),
        },
        "acceptance_gate": acceptance,
        "prior_separator_f5_snapshot": prior_f5,
        "facts": [
            "Candidate computed on same P1 TREND_UP enriched cohort generated earlier.",
            "Shadow validation performed offline only; no runtime execution path touched.",
            "Candidate keeps confidence band 0.40..0.45 exclusive upper bound exactly.",
        ],
        "inferences": [
            "Candidate is viable for shadow replay when risk-aware acceptance gate passes.",
            "Controls prevent over-claiming from symbol-only or opposite-confidence effects.",
        ],
        "assumptions": [
            "pure_pnl_pct and pure_r_multiple remain authoritative replay outcomes for this offline shadow check.",
            "drawdown proxy from cumulative pure_pnl_pct is acceptable as relative risk comparator.",
        ],
        "unknowns": [
            "No live microstructure slippage/queue effects in this offline validation.",
            "Decision-chain runtime observability remains incomplete for live gating translation.",
        ],
    }

    # Emit artifacts.
    out_filters.to_csv(OUT_FILTERS, index=False)
    folds.to_csv(OUT_FOLDS, index=False)
    candidate.to_csv(OUT_ENTRIES, index=False)
    OUT_JSON.write_text(json.dumps(
        payload, ensure_ascii=True, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1")
    lines.append("")
    lines.append("## Verdict")
    verdict = "ACCEPTED_FOR_SHADOW_REPLAY" if acceptance[
        "all_pass"] else "NOT_ACCEPTED_YET_FOR_SHADOW_REPLAY"
    lines.append(f"- {verdict}")
    lines.append("")
    lines.append("## Problem framing")
    lines.append(
        "Validate F5 confidence-band candidate as shadow replay policy candidate, not merely a cohort separator.")
    lines.append("")
    lines.append("## FACT")
    for x in payload["facts"]:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## INFERENCE")
    for x in payload["inferences"]:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## ASSUMPTION")
    for x in payload["assumptions"]:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## UNKNOWN")
    for x in payload["unknowns"]:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## Candidate policy")
    lines.append("```yaml")
    lines.append("trend_up_shadow_admission_candidate:")
    lines.append("  enabled: true")
    lines.append("  regime: TREND_UP")
    lines.append("  min_confidence: 0.40")
    lines.append("  max_confidence_exclusive: 0.45")
    lines.append("  side_policy: regime_aligned_buy")
    lines.append("  mode: shadow")
    lines.append("```")
    lines.append("")

    lines.append("## Baseline vs candidate")
    lines.append("| metric | baseline_F0 | candidate_F5 |")
    lines.append("| --- | ---: | ---: |")
    lines.append(
        f"| admitted_count | {baseline_metrics['admitted_count']} | {candidate_metrics['admitted_count']} |")
    lines.append(
        f"| profitable_count | {baseline_metrics['profitable_count']} | {candidate_metrics['profitable_count']} |")
    lines.append(
        f"| losing_count | {baseline_metrics['losing_count']} | {candidate_metrics['losing_count']} |")
    lines.append(
        f"| win_rate | {fmt(baseline_metrics['win_rate'], 4)} | {fmt(candidate_metrics['win_rate'], 4)} |")
    lines.append(
        f"| total_pnl_pct | {fmt(baseline_metrics['total_pnl_pct'], 6)} | {fmt(candidate_metrics['total_pnl_pct'], 6)} |")
    lines.append(
        f"| avg_r | {fmt(baseline_metrics['avg_r'], 6)} | {fmt(candidate_metrics['avg_r'], 6)} |")
    lines.append(
        f"| mdd_proxy | {fmt(baseline_metrics['max_drawdown_proxy_pct'], 6)} | {fmt(candidate_metrics['max_drawdown_proxy_pct'], 6)} |")
    lines.append(
        f"| kept_good_rate | {fmt(baseline_metrics['kept_good_rate'], 4)} | {fmt(candidate_metrics['kept_good_rate'], 4)} |")
    lines.append(
        f"| rejected_bad_rate | {fmt(baseline_metrics['rejected_bad_rate'], 4)} | {fmt(candidate_metrics['rejected_bad_rate'], 4)} |")
    lines.append("")

    lines.append("## Controls")
    lines.append(
        "| filter | admitted | good | bad | win_rate | total_pnl_pct | avg_r |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in out_filters.to_dict("records"):
        lines.append(
            f"| {r['filter']} | {r['admitted_count']} | {r['profitable_count']} | {r['losing_count']} | {fmt(r['win_rate'], 4)} | {fmt(r['total_pnl_pct'], 6)} | {fmt(r['avg_r'], 6)} |"
        )
    lines.append("")

    lines.append("## Stability")
    lines.append("### By symbol")
    lines.append(
        "| symbol | count | good | bad | win_rate | total_pnl_pct | avg_r | mdd_proxy |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in symbol_split.to_dict("records"):
        lines.append(
            f"| {r['symbol']} | {r['count']} | {r['good']} | {r['bad']} | {fmt(r['win_rate'], 4)} | {fmt(r['total_pnl_pct'], 6)} | {fmt(r['avg_r'], 6)} | {fmt(r['mdd_proxy'], 6)} |"
        )
    lines.append("")

    lines.append("### Five chronological folds")
    lines.append(
        "| fold | count | good | bad | win_rate | total_pnl_pct | avg_r | mdd_proxy |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in folds.to_dict("records"):
        lines.append(
            f"| {r['fold']} | {r['count']} | {r['good']} | {r['bad']} | {fmt(r['win_rate'], 4)} | {fmt(r['total_pnl_pct'], 6)} | {fmt(r['avg_r'], 6)} | {fmt(r['mdd_proxy'], 6)} |"
        )
    lines.append("")

    lines.append("## Acceptance gate")
    for k, v in acceptance.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## What must NOT change yet")
    lines.append("- no production YAML change")
    lines.append("- no runtime gate mutation")
    lines.append("- no TREND_DOWN admission expansion")
    lines.append("- no global max-cap disable")
    lines.append("")

    lines.append("## Artifacts")
    lines.append(f"- {OUT_MD.relative_to(ROOT).as_posix()}")
    lines.append(f"- {OUT_JSON.relative_to(ROOT).as_posix()}")
    lines.append(f"- {OUT_FILTERS.relative_to(ROOT).as_posix()}")
    lines.append(f"- {OUT_FOLDS.relative_to(ROOT).as_posix()}")
    lines.append(f"- {OUT_ENTRIES.relative_to(ROOT).as_posix()}")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "md": str(OUT_MD),
                "json": str(OUT_JSON),
                "filters_csv": str(OUT_FILTERS),
                "folds_csv": str(OUT_FOLDS),
                "entries_csv": str(OUT_ENTRIES),
                "verdict": verdict,
                "candidate_count": int(len(candidate)),
                "candidate_good": int((candidate["profitable_label"] == 1).sum()),
                "candidate_bad": int((candidate["profitable_label"] == 0).sum()),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
