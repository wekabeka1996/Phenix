#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.config_loader import ConfigLoader  # noqa: E402
from apps.reference.domains.alpha_search.judge.config_models import ShadowSimulatorConfig  # noqa: E402
from apps.reference.domains.alpha_search.judge.shadow_simulator import ShadowPlanSimulator  # noqa: E402
from apps.reference.shared.decision_primitives.aurora_confidence import compute_aurora_strategy_confidence  # noqa: E402
from tools.judge.analyze_shadow_plan_file import (  # noqa: E402
    apply_envelope_context,
    apply_result_context,
    apply_verdict_context,
    bool_from_any,
    build_base_row,
    build_recorder_context,
    build_single_index,
    confidence_bucket,
    infer_file_context,
    load_plans,
    load_rows,
    pick_feature_row,
    write_csv,
    write_json,
    write_jsonl,
)


DEFAULT_INCLUDE_DATES = ("2026-05-23", "2026-05-24")
TARGET_BUCKETS = {"0.6-0.7", "0.7-0.8", "0.8-0.9"}


def parse_csv_set(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    parts = [item.strip() for item in str(raw).split(",")]
    return {item for item in parts if item}


def to_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def safe_pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100.0, 4) if denominator else 0.0


def safe_mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def pearson_corr(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0.0 or var_y <= 0.0:
        return None
    return round(cov / math.sqrt(var_x * var_y), 6)


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    if not rows:
        return []
    header_line = "| " + " | ".join(str(header) for header in headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    rendered_rows = [
        "| " + " | ".join(str(cell) for cell in row) + " |"
        for row in rows
    ]
    return [header_line, separator_line, *rendered_rows]


def discover_shadow_plan_files(
    judge_log_dir: Path,
    *,
    include_dates: set[str],
    include_symbols: set[str],
) -> list[Path]:
    matches: list[Path] = []
    for path in sorted(judge_log_dir.glob("shadow_entry_plan_*.jsonl")):
        try:
            context = infer_file_context(path)
        except ValueError:
            continue
        if include_dates and context.utc_date not in include_dates:
            continue
        if include_symbols and context.symbol not in include_symbols:
            continue
        matches.append(path)
    return matches


def resolve_base_threshold(global_threshold: float, symbol_cfg: Any) -> float:
    if symbol_cfg is None:
        return global_threshold
    override = getattr(symbol_cfg, "signal_threshold", None)
    if override is None:
        return global_threshold
    if isinstance(override, (int, float, Decimal, str)):
        resolved = to_float(override)
        return resolved if resolved is not None and resolved > 0.0 else global_threshold
    if getattr(override, "enabled", False):
        resolved = to_float(getattr(override, "value", None))
        return resolved if resolved is not None and resolved > 0.0 else global_threshold
    return global_threshold


def resolve_regime_thresholds(global_thresholds: Mapping[str, Any], symbol_cfg: Any) -> dict[str, float]:
    candidate = getattr(symbol_cfg, "regime_thresholds",
                        None) if symbol_cfg is not None else None
    mapping = candidate if isinstance(
        candidate, Mapping) and candidate else global_thresholds
    resolved: dict[str, float] = {}
    for key, value in dict(mapping or {}).items():
        numeric = to_float(value)
        if numeric is not None and numeric > 0.0:
            resolved[str(key)] = numeric
    return resolved


def bucket_or_unknown(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    clamped = max(0.0, min(1.0, float(value)))
    return confidence_bucket(clamped)


def classify_side_alignment(judge_side: str | None, aurora_side: str) -> str:
    if judge_side not in {"BUY", "SELL"}:
        return "JUDGE_NON_DIRECTIONAL"
    if aurora_side == "UNKNOWN":
        return "AURORA_SCORE_MISSING"
    if aurora_side == "NO_ENTRY":
        return "AURORA_NEUTRAL"
    if aurora_side == judge_side:
        return "SAME_DIRECTION"
    return "OPPOSITE_DIRECTION"


def classify_sign_alignment(judge_side: str | None, pillar_sum: float | None) -> str:
    if judge_side not in {"BUY", "SELL"}:
        return "JUDGE_NON_DIRECTIONAL"
    if pillar_sum is None:
        return "PILLAR_MISSING"
    if math.isclose(pillar_sum, 0.0, rel_tol=0.0, abs_tol=1e-12):
        return "PILLAR_ZERO"
    if judge_side == "BUY":
        return "SIGN_ALIGNED" if pillar_sum > 0.0 else "SIGN_OPPOSED"
    return "SIGN_ALIGNED" if pillar_sum < 0.0 else "SIGN_OPPOSED"


def derive_aurora_proxy_fields(
    row: dict[str, Any],
    *,
    symbol_cfg: Any,
    global_threshold: float,
    global_regime_thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    pillar_sum = to_float(row.get("recorder_feat_pillar_sum"))
    recorder_regime = str(row.get("recorder_regime") or "") or None
    envelope_regime = str(row.get("envelope_regime") or "") or None
    active_regime = recorder_regime or envelope_regime
    base_threshold = resolve_base_threshold(global_threshold, symbol_cfg)
    regime_thresholds = resolve_regime_thresholds(
        global_regime_thresholds, symbol_cfg)
    regime_factor = to_float(regime_thresholds.get(
        active_regime, 1.0)) if active_regime else 1.0
    if regime_factor is None or regime_factor <= 0.0:
        regime_factor = 1.0
    active_threshold = base_threshold * regime_factor
    if active_threshold <= 0.0:
        active_threshold = base_threshold if base_threshold > 0.0 else 1.0

    aurora_confidence_proxy = compute_aurora_strategy_confidence(
        score=pillar_sum,
        threshold_factor=active_threshold,
    )
    if pillar_sum is None:
        aurora_side_proxy = "UNKNOWN"
    elif pillar_sum >= active_threshold:
        aurora_side_proxy = "BUY"
    elif pillar_sum <= -active_threshold:
        aurora_side_proxy = "SELL"
    else:
        aurora_side_proxy = "NO_ENTRY"

    allowed_regimes = list(getattr(symbol_cfg, "allowed_regimes", None) or [
    ]) if symbol_cfg is not None else []
    symbol_enabled = bool(getattr(symbol_cfg, "enabled", True)
                          ) if symbol_cfg is not None else True
    regime_allowed = True
    if active_regime and allowed_regimes:
        regime_allowed = active_regime in allowed_regimes

    entry_side = row.get("entry_side")
    side_alignment = classify_side_alignment(entry_side, aurora_side_proxy)
    sign_alignment = classify_sign_alignment(entry_side, pillar_sum)
    return {
        "aurora_symbol_enabled": symbol_enabled,
        "aurora_allowed_regimes": allowed_regimes,
        "aurora_active_regime": active_regime,
        "aurora_regime_factor_proxy": round(regime_factor, 6),
        "aurora_active_threshold_proxy": round(active_threshold, 6),
        "aurora_pillar_sum_proxy": round(pillar_sum, 6) if pillar_sum is not None else None,
        "aurora_abs_pillar_sum_proxy": round(abs(pillar_sum), 6) if pillar_sum is not None else None,
        "aurora_confidence_proxy": round(aurora_confidence_proxy, 6) if aurora_confidence_proxy is not None else None,
        "aurora_confidence_bucket": bucket_or_unknown(aurora_confidence_proxy),
        "aurora_side_proxy": aurora_side_proxy,
        "aurora_regime_allowed": regime_allowed,
        "judge_vs_aurora_side_alignment": side_alignment,
        "judge_vs_aurora_sign_alignment": sign_alignment,
        "judge_vs_aurora_conf_gap": round(float(row.get("confidence") or 0.0) - float(aurora_confidence_proxy), 6)
        if aurora_confidence_proxy is not None and row.get("confidence") is not None
        else None,
    }


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    net_values = [to_float(row.get("net_pnl_pct")) for row in rows]
    net_values = [value for value in net_values if value is not None]
    win_rows = sum(1 for row in rows if row.get("trade_pnl_class") == "WIN")
    filled_rows = sum(1 for row in rows if bool_from_any(
        row.get("filled_trade")))
    same_side_rows = sum(1 for row in rows if row.get(
        "judge_vs_aurora_side_alignment") == "SAME_DIRECTION")
    neutral_rows = sum(1 for row in rows if row.get(
        "judge_vs_aurora_side_alignment") == "AURORA_NEUTRAL")
    opposite_rows = sum(1 for row in rows if row.get(
        "judge_vs_aurora_side_alignment") == "OPPOSITE_DIRECTION")
    regime_block_rows = sum(1 for row in rows if row.get(
        "aurora_regime_allowed") is False)
    symbol_disabled_rows = sum(1 for row in rows if row.get(
        "aurora_symbol_enabled") is False)
    return {
        "rows": len(rows),
        "proposal_win_rate_pct": safe_pct(win_rows, len(rows)),
        "fill_rate_pct": safe_pct(filled_rows, len(rows)),
        "total_net_pnl_pct": round(sum(net_values), 6),
        "avg_net_pnl_pct": safe_mean(net_values),
        "avg_judge_confidence": safe_mean([float(row.get("confidence")) for row in rows if row.get("confidence") is not None]),
        "avg_aurora_confidence_proxy": safe_mean([float(row.get("aurora_confidence_proxy")) for row in rows if row.get("aurora_confidence_proxy") is not None]),
        "avg_abs_pillar_sum_proxy": safe_mean([float(row.get("aurora_abs_pillar_sum_proxy")) for row in rows if row.get("aurora_abs_pillar_sum_proxy") is not None]),
        "same_direction_rate_pct": safe_pct(same_side_rows, len(rows)),
        "aurora_neutral_rate_pct": safe_pct(neutral_rows, len(rows)),
        "opposite_direction_rate_pct": safe_pct(opposite_rows, len(rows)),
        "regime_block_rate_pct": safe_pct(regime_block_rows, len(rows)),
        "symbol_disabled_rate_pct": safe_pct(symbol_disabled_rows, len(rows)),
    }


def build_group_summary(rows: Sequence[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "UNKNOWN")].append(row)
    output: list[dict[str, Any]] = []
    for bucket, bucket_rows in sorted(grouped.items()):
        summary = summarize_rows(bucket_rows)
        output.append({key: bucket, **summary})
    return output


def build_matrix_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("confidence_bucket") or "UNKNOWN"),
            str(row.get("aurora_confidence_bucket") or "UNKNOWN"),
        )
        grouped[key].append(row)
    output: list[dict[str, Any]] = []
    for (judge_bucket, aurora_bucket), bucket_rows in sorted(grouped.items()):
        summary = summarize_rows(bucket_rows)
        output.append(
            {
                "judge_confidence_bucket": judge_bucket,
                "aurora_confidence_bucket": aurora_bucket,
                **summary,
            }
        )
    return output


def process_shadow_plan_file(
    plans_file: Path,
    *,
    judge_log_dir: Path,
    recorder_root: Path,
    simulator: ShadowPlanSimulator,
    global_threshold: float,
    global_regime_thresholds: Mapping[str, Any],
    symbol_cfgs: Mapping[str, Any],
) -> list[dict[str, Any]]:
    context = infer_file_context(plans_file)
    verdict_rows = load_rows(context.verdict_path)
    envelope_rows = load_rows(context.envelope_path)
    verdict_by_id = build_single_index(verdict_rows, "verdict_id")
    verdict_by_cycle = build_single_index(verdict_rows, "cycle_key")
    envelope_by_id = build_single_index(envelope_rows, "envelope_id")
    envelope_by_cycle = build_single_index(envelope_rows, "cycle_key")
    plans, invalid_rows = load_plans(plans_file)

    bars_cache: dict[tuple[str, str, int], Any] = {}

    def get_bars(plan: Any) -> Any:
        date_key = context.utc_date
        cache_key = (date_key, plan.symbol, int(plan.tf_sec))
        if cache_key not in bars_cache:
            bars_cache[cache_key] = simulator._load_bars(
                recorder_root,
                date_key,
                plan.symbol,
                int(plan.tf_sec),
            )
        return bars_cache[cache_key]

    symbol_cfg = symbol_cfgs.get(context.symbol)
    rows: list[dict[str, Any]] = []
    for plan in plans:
        row = build_base_row(plan)
        verdict = verdict_by_cycle.get(
            plan.cycle_key) or verdict_by_id.get(plan.source_verdict_id)
        envelope = envelope_by_cycle.get(
            plan.cycle_key) or envelope_by_id.get(plan.source_envelope_id)
        apply_verdict_context(row, verdict)
        apply_envelope_context(row, envelope)

        feature_row = pick_feature_row(get_bars(plan), plan.ts_ms)
        row.update(build_recorder_context(feature_row))
        row.update(
            derive_aurora_proxy_fields(
                row,
                symbol_cfg=symbol_cfg,
                global_threshold=global_threshold,
                global_regime_thresholds=global_regime_thresholds,
            )
        )

        if plan.suppressed:
            row["simulation_status"] = "skipped"
            row["skipped_reason"] = "suppressed_plan"
            row["terminal_reason"] = "suppressed_plan"
            row["proposal_outcome_class"] = "SUPPRESSED"
            rows.append(row)
            continue

        if not plan.actionable:
            row["simulation_status"] = "skipped"
            row["skipped_reason"] = "non_actionable_plan"
            row["terminal_reason"] = "non_actionable_plan"
            row["proposal_outcome_class"] = "NON_ACTIONABLE"
            rows.append(row)
            continue

        if plan.entry_side not in {"BUY", "SELL"} or plan.limit_price is None or plan.tp_price is None or plan.sl_price is None:
            row["simulation_status"] = "invalid"
            row["invalid_reason"] = "incomplete_plan_geometry"
            row["terminal_reason"] = "incomplete_plan_geometry"
            row["proposal_outcome_class"] = "INVALID"
            rows.append(row)
            continue

        bars = get_bars(plan)
        if getattr(bars, "empty", True):
            row["simulation_status"] = "skipped"
            row["skipped_reason"] = "missing_ohlc_file"
            row["terminal_reason"] = "missing_ohlc_file"
            row["proposal_outcome_class"] = "MISSING_OHLC"
            rows.append(row)
            continue

        result = simulator.simulate_plan(plan, bars)
        apply_result_context(row, result)
        row["in_primary_cohort"] = row["simulation_status"] == "success"
        row["primary_is_win"] = bool(
            row["in_primary_cohort"] and row.get("trade_pnl_class") == "WIN")
        rows.append(row)

    for row in invalid_rows:
        row = dict(row)
        row.update(
            derive_aurora_proxy_fields(
                row,
                symbol_cfg=symbol_cfg,
                global_threshold=global_threshold,
                global_regime_thresholds=global_regime_thresholds,
            )
        )
        rows.append(row)
    return rows


def build_report(summary: Mapping[str, Any], output_dir: Path) -> str:
    lines = [
        "# Judge vs Aurora Joint Calibration Report",
        "",
        "## Scope",
        f"- Generated at: {summary['generated_at_utc']}",
        f"- Judge log dir: {summary['judge_log_dir']}",
        f"- Recorder root: {summary['recorder_root']}",
        f"- Dates: {', '.join(summary['include_dates'])}",
        f"- Shadow files processed: {summary['files_processed']}",
        f"- Primary rows: {summary['overall']['rows']}",
        f"- Target 0.6-0.9 rows: {summary['target_0_6_0_9']['rows']}",
        "",
        "## Headline Findings",
        f"- Judge confidence vs Aurora confidence proxy correlation: {summary['correlations']['judge_vs_aurora_confidence_proxy']}",
        f"- Judge confidence vs |pillar_sum| correlation: {summary['correlations']['judge_vs_abs_pillar_sum_proxy']}",
        f"- Same-direction rate: {summary['overall']['same_direction_rate_pct']}%",
        f"- Aurora-neutral rate: {summary['overall']['aurora_neutral_rate_pct']}%",
        f"- Opposite-direction rate: {summary['overall']['opposite_direction_rate_pct']}%",
        f"- Regime-block rate under current Aurora allowlists: {summary['overall']['regime_block_rate_pct']}%",
        f"- Symbol-disabled rate under current Aurora config: {summary['overall']['symbol_disabled_rate_pct']}%",
        "",
        "## Judge Bucket Summary",
    ]
    lines.extend(
        markdown_table(
            (
                "judge_bucket",
                "rows",
                "avg_judge_conf",
                "avg_aurora_conf_proxy",
                "avg_abs_pillar_sum",
                "same_dir_rate",
                "aurora_neutral_rate",
                "opposite_rate",
                "win_rate",
                "total_net",
            ),
            [
                (
                    row["confidence_bucket"],
                    row["rows"],
                    row["avg_judge_confidence"],
                    row["avg_aurora_confidence_proxy"],
                    row["avg_abs_pillar_sum_proxy"],
                    row["same_direction_rate_pct"],
                    row["aurora_neutral_rate_pct"],
                    row["opposite_direction_rate_pct"],
                    row["proposal_win_rate_pct"],
                    row["total_net_pnl_pct"],
                )
                for row in summary["by_judge_bucket"]
            ],
        )
    )
    lines.extend([
        "",
        "## Side Alignment Summary",
    ])
    lines.extend(
        markdown_table(
            (
                "alignment",
                "rows",
                "win_rate",
                "avg_net",
                "total_net",
                "regime_block_rate",
                "symbol_disabled_rate",
            ),
            [
                (
                    row["judge_vs_aurora_side_alignment"],
                    row["rows"],
                    row["proposal_win_rate_pct"],
                    row["avg_net_pnl_pct"],
                    row["total_net_pnl_pct"],
                    row["regime_block_rate_pct"],
                    row["symbol_disabled_rate_pct"],
                )
                for row in summary["by_side_alignment"]
            ],
        )
    )
    lines.extend([
        "",
        "## Target 0.6-0.9 Summary",
    ])
    target = summary["target_0_6_0_9"]
    lines.extend([
        f"- Rows: {target['rows']}",
        f"- Win rate: {target['proposal_win_rate_pct']}%",
        f"- Total net pnl pct: {target['total_net_pnl_pct']}",
        f"- Same-direction rate: {target['same_direction_rate_pct']}%",
        f"- Aurora-neutral rate: {target['aurora_neutral_rate_pct']}%",
        f"- Opposite-direction rate: {target['opposite_direction_rate_pct']}%",
        f"- Regime-block rate: {target['regime_block_rate_pct']}%",
        f"- Symbol-disabled rate: {target['symbol_disabled_rate_pct']}%",
        "",
        "## Output Artifacts",
        f"- Summary JSON: {(output_dir / 'summary.json').as_posix()}",
        f"- Per-plan joint rows CSV: {(output_dir / 'per_plan_joint_rows.csv').as_posix()}",
        f"- Judge bucket summary CSV: {(output_dir / 'judge_bucket_summary.csv').as_posix()}",
        f"- Confidence matrix CSV: {(output_dir / 'judge_aurora_confidence_matrix.csv').as_posix()}",
        f"- Side alignment summary CSV: {(output_dir / 'judge_aurora_side_alignment_summary.csv').as_posix()}",
    ])
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Judge-vs-Aurora joint calibration for the current shadow window.",
    )
    parser.add_argument(
        "--judge-log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "judge_experts",
    )
    parser.add_argument(
        "--recorder-root",
        type=Path,
        default=REPO_ROOT / "data" / "recorder",
    )
    parser.add_argument(
        "--include-dates",
        type=str,
        default=",".join(DEFAULT_INCLUDE_DATES),
        help="Comma-separated UTC dates to include. Use empty string to include every discovered date.",
    )
    parser.add_argument(
        "--include-symbols",
        type=str,
        default="",
        help="Optional comma-separated symbol allowlist.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "judge" /
        "judge_aurora_joint_calibration_current_window",
    )
    parser.add_argument("--max-bars-after-signal", type=int, default=12)
    parser.add_argument(
        "--intrabar-ambiguity-policy",
        choices=["mark_ambiguous", "prioritize_sl", "prioritize_tp"],
        default="mark_ambiguous",
    )
    parser.add_argument("--fees-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    include_dates = parse_csv_set(args.include_dates)
    include_symbols = parse_csv_set(args.include_symbols)

    shadow_files = discover_shadow_plan_files(
        args.judge_log_dir,
        include_dates=include_dates,
        include_symbols=include_symbols,
    )
    if not shadow_files:
        raise SystemExit(
            "No shadow plan files discovered for the requested scope.")

    cfg = ConfigLoader(REPO_ROOT / "config" / "aurora").load_config()
    aurora_cfg = cfg.strategies.aurora
    decision_cfg = aurora_cfg.decision
    global_threshold = to_float(
        getattr(decision_cfg, "signal_threshold", None)) or 1.0
    global_regime_thresholds = dict(
        getattr(decision_cfg, "regime_thresholds", {}) or {})
    symbol_cfgs = dict(getattr(aurora_cfg, "assets", {}) or {})

    simulator_cfg = ShadowSimulatorConfig(
        enabled=True,
        max_bars_after_signal=args.max_bars_after_signal,
        intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
        fees_bps=args.fees_bps,
        slippage_bps=args.slippage_bps,
    )
    simulator = ShadowPlanSimulator(simulator_cfg)

    all_rows: list[dict[str, Any]] = []
    for shadow_file in shadow_files:
        all_rows.extend(
            process_shadow_plan_file(
                shadow_file,
                judge_log_dir=args.judge_log_dir,
                recorder_root=args.recorder_root,
                simulator=simulator,
                global_threshold=global_threshold,
                global_regime_thresholds=global_regime_thresholds,
                symbol_cfgs=symbol_cfgs,
            )
        )

    primary_rows = [row for row in all_rows if row.get(
        "simulation_status") == "success"]
    target_rows = [row for row in primary_rows if row.get(
        "confidence_bucket") in TARGET_BUCKETS]

    judge_conf_values = [float(row["confidence"])
                         for row in primary_rows if row.get("confidence") is not None]
    aurora_conf_values = [
        float(row["aurora_confidence_proxy"])
        for row in primary_rows
        if row.get("aurora_confidence_proxy") is not None and row.get("confidence") is not None
    ]
    judge_conf_for_proxy = [
        float(row["confidence"])
        for row in primary_rows
        if row.get("aurora_confidence_proxy") is not None and row.get("confidence") is not None
    ]
    abs_pillar_values = [
        float(row["aurora_abs_pillar_sum_proxy"])
        for row in primary_rows
        if row.get("aurora_abs_pillar_sum_proxy") is not None and row.get("confidence") is not None
    ]
    judge_conf_for_abs = [
        float(row["confidence"])
        for row in primary_rows
        if row.get("aurora_abs_pillar_sum_proxy") is not None and row.get("confidence") is not None
    ]

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "judge_log_dir": args.judge_log_dir.as_posix(),
        "recorder_root": args.recorder_root.as_posix(),
        "output_dir": args.output_dir.as_posix(),
        "include_dates": sorted(include_dates) if include_dates else ["ALL_DISCOVERED"],
        "include_symbols": sorted(include_symbols),
        "files_processed": len(shadow_files),
        "shadow_files": [path.as_posix() for path in shadow_files],
        "simulator_config": {
            "max_bars_after_signal": args.max_bars_after_signal,
            "intrabar_ambiguity_policy": args.intrabar_ambiguity_policy,
            "fees_bps": args.fees_bps,
            "slippage_bps": args.slippage_bps,
        },
        "overall": summarize_rows(primary_rows),
        "target_0_6_0_9": summarize_rows(target_rows),
        "by_judge_bucket": build_group_summary(primary_rows, "confidence_bucket"),
        "by_aurora_bucket": build_group_summary(primary_rows, "aurora_confidence_bucket"),
        "by_side_alignment": build_group_summary(primary_rows, "judge_vs_aurora_side_alignment"),
        "by_sign_alignment": build_group_summary(primary_rows, "judge_vs_aurora_sign_alignment"),
        "confidence_matrix": build_matrix_summary(primary_rows),
        "correlations": {
            "judge_vs_aurora_confidence_proxy": pearson_corr(judge_conf_for_proxy, aurora_conf_values),
            "judge_vs_abs_pillar_sum_proxy": pearson_corr(judge_conf_for_abs, abs_pillar_values),
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "summary.json", summary)
    write_jsonl(args.output_dir / "per_plan_joint_rows.jsonl", all_rows)
    write_csv(args.output_dir / "per_plan_joint_rows.csv", all_rows)
    write_csv(args.output_dir / "judge_bucket_summary.csv",
              summary["by_judge_bucket"])
    write_csv(args.output_dir / "judge_aurora_confidence_matrix.csv",
              summary["confidence_matrix"])
    write_csv(args.output_dir / "judge_aurora_side_alignment_summary.csv",
              summary["by_side_alignment"])
    report = build_report(summary, args.output_dir)
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": args.output_dir.as_posix(),
                "files_processed": len(shadow_files),
                "primary_rows": summary["overall"]["rows"],
                "target_rows": summary["target_0_6_0_9"]["rows"],
                "same_direction_rate_pct": summary["overall"]["same_direction_rate_pct"],
                "aurora_neutral_rate_pct": summary["overall"]["aurora_neutral_rate_pct"],
                "opposite_direction_rate_pct": summary["overall"]["opposite_direction_rate_pct"],
                "judge_vs_aurora_conf_corr": summary["correlations"]["judge_vs_aurora_confidence_proxy"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
