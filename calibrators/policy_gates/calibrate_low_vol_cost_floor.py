#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]

COHORT_CLOSED_REAL_TRADE = "closed_real_trade"
COHORT_REJECTED_ATTEMPT = "rejected_attempt"
COHORT_ORDER_ATTEMPT_UNFILLED = "order_attempt_unfilled"
COHORT_STRATEGY_SIGNAL_ONLY = "strategy_signal_only"
COHORT_COUNTERFACTUAL_FORWARD_BAR = "counterfactual_forward_bar"

TRUTH_REAL = "realized_execution"
TRUTH_MASTER_CSV = "master_csv"
TRUTH_ORDER_LOG = "order_log_v1_jsonl"
TRUTH_RECORDER = "recorder_forward_bar"
TRUTH_UNAVAILABLE = "unavailable"

FEE_SOURCE_CLI = "cli_override"
FEE_SOURCE_STRATEGY = "strategy_local_config"
FEE_SOURCE_GLOBAL = "objective_cost_base_fee_bps"
FEE_SOURCE_UNAVAILABLE = "unavailable"

SLIPPAGE_SOURCE_REALIZED = "realized"
SLIPPAGE_SOURCE_CONFIGURED_CAP = "configured_cap"
SLIPPAGE_SOURCE_CLI = "cli_override"
SLIPPAGE_SOURCE_UNAVAILABLE = "unavailable"

DEFAULT_CONFIDENCE_BUCKETS = [
    (0.50, 0.55),
    (0.55, 0.60),
    (0.60, 0.65),
    (0.65, 0.70),
    (0.70, 0.75),
    (0.75, 0.80),
    (0.80, None),
]

REQUIRED_OUTPUT_FILES = (
    "low_vol_trade_dataset.csv",
    "low_vol_threshold_candidates.json",
    "low_vol_candidate_yaml_patch.yaml",
)


@dataclass(frozen=True, slots=True)
class FeeResolution:
    open_fee_bps: float | None
    close_fee_bps: float | None
    fee_source: str
    acceptance_blocked: bool


@dataclass(frozen=True, slots=True)
class SlippageResolution:
    slippage_bps: float | None
    slippage_source: str


@dataclass(frozen=True, slots=True)
class DirectionConfidenceResolution:
    direction_confidence: float | None
    direction_confidence_source: str


@dataclass(frozen=True, slots=True)
class FeeEconomics:
    round_trip_fee_usd: float
    required_net_usd: float
    required_gross_tp_usd: float
    required_gross_tp_bps: float
    slippage_buffer_usd: float


@dataclass(frozen=True, slots=True)
class SameBarOutcome:
    ambiguous_same_bar: bool
    pessimistic_outcome: str | None
    optimistic_outcome: str | None


@dataclass(frozen=True, slots=True)
class SufficiencyVerdict:
    accepted: bool
    exploratory_only: bool
    reasons: tuple[str, ...]


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_symbol(value: Any) -> str | None:
    text = _normalize_text(value)
    return text.upper() if text else None


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _normalize_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    return None


def _iso_to_ts_ms(value: Any) -> int | None:
    text = _normalize_text(value)
    if text is None:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _as_quality_flags(*flags: str) -> str:
    cleaned = [flag for flag in flags if flag]
    return "|".join(cleaned)


def _required_cli_pair(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if (args.open_fee_bps is None) != (args.close_fee_bps is None):
        parser.error(
            "--open-fee-bps and --close-fee-bps must be supplied together")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only LOW_VOLATILITY cost-floor calibrator. "
            "Writes low_vol_trade_dataset.csv, low_vol_threshold_candidates.json, "
            "low_vol_candidate_yaml_patch.yaml, and markdown reports."
        )
    )
    parser.add_argument("--data-dir", default="data",
                        help="Root data directory")
    parser.add_argument("--logs-dir", default="logs",
                        help="Root logs directory")
    parser.add_argument("--reports-dir", default="reports",
                        help="Reports directory")
    parser.add_argument(
        "--out-dir", default="artifacts/calibration", help="Artifact output directory")
    parser.add_argument("--regime", default="LOW_VOLATILITY",
                        help="Target regime key")
    parser.add_argument("--open-fee-bps", type=float,
                        default=None, help="Explicit open fee override in bps")
    parser.add_argument("--close-fee-bps", type=float,
                        default=None, help="Explicit close fee override in bps")
    parser.add_argument("--target-net-fee-multiple", type=float, default=2.0,
                        help="Required net profit multiple of round-trip fees")
    parser.add_argument("--slippage-buffer-bps", type=float,
                        default=None, help="Explicit slippage scenario buffer in bps")
    parser.add_argument("--timeout-bars", type=int,
                        default=12, help="Forward-bar timeout horizon")
    parser.add_argument("--min-closed-samples", type=int, default=30,
                        help="Minimum closed trades required for accepted thresholds")
    parser.add_argument("--min-bucket-samples", type=int, default=10,
                        help="Minimum bucket count required for non-warning bucket stats")
    parser.add_argument("--min-samples-per-symbol", type=int, default=5,
                        help="Minimum closed trades per symbol for accepted per-symbol thresholds")
    parser.add_argument("--min-samples-per-strategy", type=int, default=5,
                        help="Minimum closed trades per strategy for accepted per-strategy thresholds")
    parser.add_argument("--min-counterfactual-samples", type=int, default=10,
                        help="Minimum counterfactual rows for counterfactual claims")
    parser.add_argument("--strict", action="store_true",
                        help="Fail on malformed inputs instead of recording caveats")
    parser.add_argument("--skip-bad-rows", action="store_true",
                        help="Skip malformed rows and record caveats")
    args = parser.parse_args(argv)
    _required_cli_pair(args, parser)
    return args


def resolve_fee_contract(
    *,
    cli_open_fee_bps: float | None,
    cli_close_fee_bps: float | None,
    strategy_fee_bps: float | None,
    global_fee_bps: float | None,
    strategy_specific: bool,
    acceptance_required: bool,
) -> FeeResolution:
    if cli_open_fee_bps is not None and cli_close_fee_bps is not None:
        return FeeResolution(
            open_fee_bps=float(cli_open_fee_bps),
            close_fee_bps=float(cli_close_fee_bps),
            fee_source=FEE_SOURCE_CLI,
            acceptance_blocked=False,
        )
    if strategy_specific and strategy_fee_bps is not None:
        fee_bps = float(strategy_fee_bps)
        return FeeResolution(
            open_fee_bps=fee_bps,
            close_fee_bps=fee_bps,
            fee_source=FEE_SOURCE_STRATEGY,
            acceptance_blocked=False,
        )
    if global_fee_bps is not None:
        fee_bps = float(global_fee_bps)
        return FeeResolution(
            open_fee_bps=fee_bps,
            close_fee_bps=fee_bps,
            fee_source=FEE_SOURCE_GLOBAL,
            acceptance_blocked=False,
        )
    return FeeResolution(
        open_fee_bps=None,
        close_fee_bps=None,
        fee_source=FEE_SOURCE_UNAVAILABLE,
        acceptance_blocked=bool(acceptance_required),
    )


def resolve_slippage_contract(
    *,
    cli_override_bps: float | None,
    realized_slippage_bps: float | None,
    configured_cap_bps: float | None,
) -> SlippageResolution:
    if cli_override_bps is not None:
        return SlippageResolution(float(cli_override_bps), SLIPPAGE_SOURCE_CLI)
    if realized_slippage_bps is not None:
        return SlippageResolution(float(realized_slippage_bps), SLIPPAGE_SOURCE_REALIZED)
    if configured_cap_bps is not None:
        return SlippageResolution(float(configured_cap_bps), SLIPPAGE_SOURCE_CONFIGURED_CAP)
    return SlippageResolution(None, SLIPPAGE_SOURCE_UNAVAILABLE)


def resolve_direction_confidence(
    *,
    explicit_direction_confidence: float | None = None,
    signal_score: float | None = None,
    final_score: float | None = None,
    judge_confidence: float | None = None,
) -> DirectionConfidenceResolution:
    for source_name, value in (
        ("explicit_direction_confidence", explicit_direction_confidence),
        ("strategy_signal_score", signal_score),
        ("final_score", final_score),
        ("judge_confidence", judge_confidence),
    ):
        if value is None:
            continue
        return DirectionConfidenceResolution(float(value), source_name)
    return DirectionConfidenceResolution(None, "unavailable")


def calculate_fee_economics(
    *,
    notional: float,
    open_fee_bps: float,
    close_fee_bps: float,
    target_net_fee_multiple: float,
    slippage_buffer_bps: float,
) -> FeeEconomics:
    round_trip_fee_usd = notional * (open_fee_bps + close_fee_bps) / 10_000.0
    required_net_usd = target_net_fee_multiple * round_trip_fee_usd
    required_gross_tp_usd = round_trip_fee_usd + required_net_usd
    required_gross_tp_bps = (
        (open_fee_bps + close_fee_bps) * (1.0 + target_net_fee_multiple)
        + slippage_buffer_bps
    )
    slippage_buffer_usd = notional * slippage_buffer_bps / 10_000.0
    return FeeEconomics(
        round_trip_fee_usd=round_trip_fee_usd,
        required_net_usd=required_net_usd,
        required_gross_tp_usd=required_gross_tp_usd,
        required_gross_tp_bps=required_gross_tp_bps,
        slippage_buffer_usd=slippage_buffer_usd,
    )


def detect_same_bar_collision(
    *,
    side: str,
    high_price: float,
    low_price: float,
    tp_price: float | None,
    sl_price: float | None,
) -> SameBarOutcome:
    normalized_side = (side or "").strip().upper()
    if tp_price is None or sl_price is None:
        return SameBarOutcome(False, None, None)
    if normalized_side in {"BUY", "LONG"}:
        tp_hit = high_price >= tp_price
        sl_hit = low_price <= sl_price
    else:
        tp_hit = low_price <= tp_price
        sl_hit = high_price >= sl_price
    if tp_hit and sl_hit:
        return SameBarOutcome(True, "stop_loss_first", "take_profit_first")
    return SameBarOutcome(False, None, None)


def evaluate_sufficiency(
    *,
    closed_samples: int,
    symbol_counts: Mapping[str, int],
    strategy_counts: Mapping[str, int],
    bucket_counts: Mapping[str, int],
    counterfactual_samples: int,
    min_closed_samples: int,
    min_samples_per_symbol: int,
    min_samples_per_strategy: int,
    min_bucket_samples: int,
    min_counterfactual_samples: int,
) -> SufficiencyVerdict:
    reasons: list[str] = []
    if closed_samples < min_closed_samples:
        reasons.append(f"closed_samples<{min_closed_samples}")
    if symbol_counts and any(count < min_samples_per_symbol for count in symbol_counts.values()):
        reasons.append(f"symbol_samples<{min_samples_per_symbol}")
    if strategy_counts and any(count < min_samples_per_strategy for count in strategy_counts.values()):
        reasons.append(f"strategy_samples<{min_samples_per_strategy}")
    if bucket_counts and any(count < min_bucket_samples for count in bucket_counts.values()):
        reasons.append(f"bucket_samples<{min_bucket_samples}")
    if counterfactual_samples < min_counterfactual_samples:
        reasons.append(f"counterfactual_samples<{min_counterfactual_samples}")
    accepted = not reasons
    return SufficiencyVerdict(
        accepted=accepted,
        exploratory_only=not accepted,
        reasons=tuple(reasons),
    )


def _canonical_bucket_label(value: float) -> str | None:
    if not math.isfinite(value):
        return None
    for lower, upper in DEFAULT_CONFIDENCE_BUCKETS:
        if upper is None and value >= lower:
            return f"{lower:.2f}+"
        if upper is not None and lower <= value < upper:
            return f"{lower:.2f}-{upper:.2f}"
    return None


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _read_jsonl_rows(path: Path, *, strict: bool, skip_bad_rows: bool) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                bad_rows += 1
                if strict and not skip_bad_rows:
                    raise
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                bad_rows += 1
                if strict and not skip_bad_rows:
                    raise ValueError(f"Non-object JSONL row in {path}")
    return rows, bad_rows


def _inventory_markdown_table(rows: Iterable[Mapping[str, Any]]) -> str:
    materialized = list(rows)
    if not materialized:
        return "| path | exists | rows | parse_status | notes |\n| --- | --- | ---: | --- | --- |\n"
    lines = [
        "| path | exists | rows | parse_status | notes |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in materialized:
        lines.append(
            "| {path} | {exists} | {rows} | {parse_status} | {notes} |".format(
                path=row.get("path", ""),
                exists="yes" if row.get("exists") else "no",
                rows=row.get("rows", 0),
                parse_status=row.get("parse_status", "n/a"),
                notes=(row.get("notes", "") or "").replace("|", "/"),
            )
        )
    return "\n".join(lines)


def _yaml_lines(value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, nested in value.items():
            if isinstance(nested, dict):
                lines.append(f"{prefix}{key}:")
                lines.extend(_yaml_lines(nested, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {json.dumps(nested)}")
        return lines
    return [f"{prefix}{json.dumps(value)}"]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    sort_keys=True), encoding="utf-8")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ARTIFACT ONLY - DO NOT APPLY WITHOUT REPLAY VALIDATION"]
    lines.extend(_yaml_lines(payload))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_config_fee_and_slippage() -> dict[str, float | None]:
    global_fee_bps = None
    configured_cap_bps = None
    strategy_fee_bps = None
    domains_path = REPO_ROOT / "config" / "aurora" / "domains.yaml"
    trading_path = REPO_ROOT / "config" / "aurora" / "trading.yaml"
    md_amr_path = REPO_ROOT / "config" / "aurora" / "strategies" / "md_amr.yaml"
    for path, key in (
        (domains_path, "base_fee_bps"),
        (trading_path, "max_slippage_bps"),
        (md_amr_path, "fee_bps"),
    ):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(f"{key}:"):
                continue
            _, _, raw_value = stripped.partition(":")
            numeric = _safe_float(raw_value.strip())
            if numeric is None:
                continue
            if key == "base_fee_bps":
                global_fee_bps = numeric
            elif key == "max_slippage_bps":
                configured_cap_bps = numeric
            elif key == "fee_bps":
                strategy_fee_bps = numeric
    return {
        "global_fee_bps": global_fee_bps,
        "configured_cap_bps": configured_cap_bps,
        "strategy_fee_bps": strategy_fee_bps,
    }


def _build_inventory(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    logs_dir = Path(args.logs_dir)
    reports_dir = Path(args.reports_dir)
    data_dir = Path(args.data_dir)
    inventory_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "bad_jsonl_rows": {},
        "source_paths": {},
    }
    required_sources = [
        logs_dir / "order_log_v1.jsonl",
        logs_dir / "trade_lifecycle.jsonl",
        logs_dir / "regime_confidence_audit_v1.jsonl",
        reports_dir / "executed_trades_master.csv",
        reports_dir / "rejected_attempts_master.csv",
        reports_dir / "order_attempts_master.csv",
    ]
    for path in required_sources:
        exists = path.exists()
        row_count = 0
        parse_status = "missing"
        notes = ""
        if exists and path.suffix.lower() == ".csv":
            try:
                row_count = len(_read_csv_rows(path))
                parse_status = "ok"
            except Exception as exc:
                parse_status = "error"
                notes = type(exc).__name__
                if args.strict and not args.skip_bad_rows:
                    raise
        elif exists and path.suffix.lower() == ".jsonl":
            try:
                rows, bad_rows = _read_jsonl_rows(
                    path, strict=args.strict, skip_bad_rows=args.skip_bad_rows)
                row_count = len(rows)
                parse_status = "ok" if bad_rows == 0 else "partial"
                notes = f"bad_rows={bad_rows}" if bad_rows else ""
                summary["bad_jsonl_rows"][str(path)] = bad_rows
            except Exception as exc:
                parse_status = "error"
                notes = type(exc).__name__
                if args.strict and not args.skip_bad_rows:
                    raise
        inventory_rows.append(
            {
                "path": _display_path(path),
                "exists": exists,
                "rows": row_count,
                "parse_status": parse_status,
                "notes": notes,
            }
        )
        summary["source_paths"][_display_path(path)] = exists
    recorder_root = data_dir / "recorder"
    recorder_dates = []
    if recorder_root.exists():
        for child in sorted(recorder_root.iterdir()):
            if child.is_dir():
                recorder_dates.append(child.name)
    inventory_rows.append(
        {
            "path": _display_path(data_dir / "recorder"),
            "exists": recorder_root.exists(),
            "rows": len(recorder_dates),
            "parse_status": "ok" if recorder_root.exists() else "missing",
            "notes": f"date_dirs={len(recorder_dates)}",
        }
    )
    summary["recorder_dates"] = recorder_dates
    return inventory_rows, summary


def _dedupe_master_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("attempt_id"),
            row.get("symbol"),
            row.get("side"),
            row.get("intent_ts"),
            row.get("outcome"),
            row.get("exit_ts"),
        )
        deduped[key] = dict(row)
    return list(deduped.values())


def _regime_matches_target(value: Any, target_regime: str) -> bool:
    row_regime = _normalize_text(value)
    target = _normalize_text(target_regime)
    if row_regime is None or target is None:
        return False
    return row_regime.upper() == target.upper()


def _metadata_value(payload: Mapping[str, Any], key: str) -> Any:
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _order_log_is_rejected_intent(payload: Mapping[str, Any]) -> bool:
    event_type = _normalize_text(payload.get("event_type")) or ""
    if event_type in {"DECISION_INTENT_REJECTED", "TRADE_INTENT_REJECTED"}:
        return True
    alias_of = _normalize_text(_metadata_value(payload, "alias_of")) or ""
    canonical_family = _normalize_text(
        _metadata_value(payload, "canonical_event_family")) or ""
    return alias_of == "TRADE_INTENT_REJECTED" or canonical_family == "TRADE_INTENT_REJECTED"


def _build_order_log_dataset_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    logs_dir = Path(args.logs_dir)
    path = logs_dir / "order_log_v1.jsonl"
    if not path.exists():
        return []
    config_values = _load_config_fee_and_slippage()
    global_fee_bps = config_values["global_fee_bps"]
    strategy_fee_bps = config_values["strategy_fee_bps"]
    configured_cap_bps = config_values["configured_cap_bps"]
    payloads, _ = _read_jsonl_rows(
        path, strict=args.strict, skip_bad_rows=args.skip_bad_rows)
    rows: list[dict[str, Any]] = []
    seen_rids: set[str] = set()
    for payload in payloads:
        if not _order_log_is_rejected_intent(payload):
            continue
        rid = _normalize_text(payload.get("rid"))
        if rid is None or rid in seen_rids:
            continue
        seen_rids.add(rid)
        symbol = _normalize_symbol(payload.get("symbol")) or "UNKNOWN"
        side = _normalize_text(payload.get("side")) or "UNKNOWN"
        regime = _normalize_text(payload.get("regime"))
        if not _regime_matches_target(regime, args.regime):
            continue
        strategy_id = _normalize_text(payload.get("strategy_id")) or _normalize_text(
            _metadata_value(payload, "strategy_id"))
        direction = resolve_direction_confidence(
            explicit_direction_confidence=_safe_float(
                payload.get("direction_confidence")),
            signal_score=_safe_float(payload.get("signal_score")),
            final_score=_safe_float(payload.get("final_score")),
            judge_confidence=_safe_float(payload.get("judge_confidence")),
        )
        fee = resolve_fee_contract(
            cli_open_fee_bps=args.open_fee_bps,
            cli_close_fee_bps=args.close_fee_bps,
            strategy_fee_bps=strategy_fee_bps,
            global_fee_bps=global_fee_bps,
            strategy_specific=strategy_id is not None,
            acceptance_required=False,
        )
        slippage = resolve_slippage_contract(
            cli_override_bps=args.slippage_buffer_bps,
            realized_slippage_bps=None,
            configured_cap_bps=configured_cap_bps,
        )
        quality_flags = ["raw_order_log_event"]
        if _normalize_text(_metadata_value(payload, "alias_of")) == "TRADE_INTENT_REJECTED":
            quality_flags.append("alias_of_trade_intent_rejected")
        if fee.acceptance_blocked:
            quality_flags.append("fee_unavailable_for_acceptance")
        rows.append(
            {
                "dataset_id": rid,
                "symbol": symbol,
                "strategy_id": strategy_id,
                "side": side,
                "timestamp_ms": _safe_int(payload.get("timestamp")),
                "regime": regime,
                "regime_confidence": _safe_float(payload.get("regime_confidence")),
                "direction_confidence": direction.direction_confidence,
                "direction_confidence_source": direction.direction_confidence_source,
                "entry_price": _safe_float(payload.get("entry_price")),
                "target_price": _safe_float(payload.get("target_price")),
                "stop_price": _safe_float(payload.get("stop_price")),
                "notional": _safe_float(payload.get("notional")),
                "margin": _safe_float(payload.get("margin")),
                "leverage": _safe_float(payload.get("leverage")),
                "open_fee_bps": fee.open_fee_bps,
                "close_fee_bps": fee.close_fee_bps,
                "fee_source": fee.fee_source,
                "slippage_bps": slippage.slippage_bps,
                "slippage_source": slippage.slippage_source,
                "fill_price": None,
                "close_price": None,
                "gross_pnl": None,
                "fee_paid": None,
                "net_pnl": None,
                "round_trip_fee_usd": None,
                "required_net_usd": None,
                "required_gross_tp_usd": None,
                "required_gross_tp_bps": None,
                "tp_fee_coverage_ratio": None,
                "rr_ratio": None,
                "mfe_bps": None,
                "mae_bps": None,
                "bars_to_tp": None,
                "bars_to_sl": None,
                "bars_to_timeout": None,
                "same_bar_collision_flag": False,
                "ambiguous_same_bar": False,
                "cohort": COHORT_REJECTED_ATTEMPT,
                "truth_source": TRUTH_ORDER_LOG,
                "quality_flags": _as_quality_flags(*quality_flags),
                "outcome": "rejected",
            }
        )
    return rows


def _build_master_dataset_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    reports_dir = Path(args.reports_dir)
    config_values = _load_config_fee_and_slippage()
    global_fee_bps = config_values["global_fee_bps"]
    strategy_fee_bps = config_values["strategy_fee_bps"]
    configured_cap_bps = config_values["configured_cap_bps"]
    output_rows: list[dict[str, Any]] = []
    specs = (
        (reports_dir / "executed_trades_master.csv",
         COHORT_CLOSED_REAL_TRADE, TRUTH_REAL),
        (reports_dir / "rejected_attempts_master.csv",
         COHORT_REJECTED_ATTEMPT, TRUTH_MASTER_CSV),
        (reports_dir / "order_attempts_master.csv",
         COHORT_ORDER_ATTEMPT_UNFILLED, TRUTH_MASTER_CSV),
    )
    for path, cohort, truth_source in specs:
        if not path.exists():
            continue
        for row in _dedupe_master_rows(_read_csv_rows(path)):
            symbol = _normalize_symbol(row.get("symbol")) or "UNKNOWN"
            side = _normalize_text(row.get("side")) or "UNKNOWN"
            regime = _normalize_text(row.get("regime"))
            if not _regime_matches_target(regime, args.regime):
                continue
            entry_price = _safe_float(row.get("intent_price"))
            notional = None
            if entry_price is not None:
                notional = entry_price
            fee = resolve_fee_contract(
                cli_open_fee_bps=args.open_fee_bps,
                cli_close_fee_bps=args.close_fee_bps,
                strategy_fee_bps=strategy_fee_bps,
                global_fee_bps=global_fee_bps,
                strategy_specific=False,
                acceptance_required=(cohort == COHORT_CLOSED_REAL_TRADE),
            )
            slippage = resolve_slippage_contract(
                cli_override_bps=args.slippage_buffer_bps,
                realized_slippage_bps=None,
                configured_cap_bps=configured_cap_bps,
            )
            direction = resolve_direction_confidence()
            realized_pnl = _safe_float(row.get("realized_pnl"))
            commission = _safe_float(row.get("commission")) or 0.0
            gross_pnl = None if realized_pnl is None else realized_pnl + commission
            economics = None
            if (
                notional is not None
                and fee.open_fee_bps is not None
                and fee.close_fee_bps is not None
                and slippage.slippage_bps is not None
            ):
                economics = calculate_fee_economics(
                    notional=notional,
                    open_fee_bps=fee.open_fee_bps,
                    close_fee_bps=fee.close_fee_bps,
                    target_net_fee_multiple=args.target_net_fee_multiple,
                    slippage_buffer_bps=slippage.slippage_bps,
                )
            quality_flags = []
            if _parse_bool(row.get("synthetic_id")):
                quality_flags.append("synthetic_master_row")
            if fee.acceptance_blocked:
                quality_flags.append("fee_unavailable_for_acceptance")
            output_rows.append(
                {
                    "dataset_id": row.get("attempt_id") or row.get("synthetic_id") or "",
                    "symbol": symbol,
                    "strategy_id": None,
                    "side": side,
                    "timestamp_ms": _iso_to_ts_ms(row.get("intent_ts")),
                    "regime": regime,
                    "regime_confidence": None,
                    "direction_confidence": direction.direction_confidence,
                    "direction_confidence_source": direction.direction_confidence_source,
                    "entry_price": entry_price,
                    "target_price": None,
                    "stop_price": None,
                    "notional": notional,
                    "margin": None,
                    "leverage": None,
                    "open_fee_bps": fee.open_fee_bps,
                    "close_fee_bps": fee.close_fee_bps,
                    "fee_source": fee.fee_source,
                    "slippage_bps": slippage.slippage_bps,
                    "slippage_source": slippage.slippage_source,
                    "fill_price": entry_price if cohort == COHORT_CLOSED_REAL_TRADE else None,
                    "close_price": _safe_float(row.get("exit_price")),
                    "gross_pnl": gross_pnl,
                    "fee_paid": commission,
                    "net_pnl": realized_pnl,
                    "round_trip_fee_usd": None if economics is None else economics.round_trip_fee_usd,
                    "required_net_usd": None if economics is None else economics.required_net_usd,
                    "required_gross_tp_usd": None if economics is None else economics.required_gross_tp_usd,
                    "required_gross_tp_bps": None if economics is None else economics.required_gross_tp_bps,
                    "tp_fee_coverage_ratio": None,
                    "rr_ratio": None,
                    "mfe_bps": None,
                    "mae_bps": None,
                    "bars_to_tp": None,
                    "bars_to_sl": None,
                    "bars_to_timeout": None,
                    "same_bar_collision_flag": False,
                    "ambiguous_same_bar": False,
                    "cohort": cohort,
                    "truth_source": truth_source,
                    "quality_flags": _as_quality_flags(*quality_flags),
                    "outcome": _normalize_text(row.get("outcome")),
                }
            )
    return output_rows


def _bucket_metrics(rows: Sequence[Mapping[str, Any]], *, field: str, min_bucket_samples: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        value = _safe_float(row.get(field))
        if value is None:
            continue
        label = _canonical_bucket_label(value)
        if label is None:
            continue
        grouped[label].append(row)
    metrics: list[dict[str, Any]] = []
    for label in sorted(grouped.keys()):
        bucket_rows = grouped[label]
        net_values = [float(row["net_pnl"]) for row in bucket_rows if _safe_float(
            row.get("net_pnl")) is not None]
        timeout_count = sum(1 for row in bucket_rows if str(
            row.get("outcome") or "").startswith("timeout"))
        win_count = sum(1 for row in bucket_rows if (
            _safe_float(row.get("net_pnl")) or 0.0) > 0.0)
        metrics.append(
            {
                "bucket": label,
                "field": field,
                "sample_count": len(bucket_rows),
                "winrate": None if not bucket_rows else win_count / len(bucket_rows),
                "median_net_pnl": None if not net_values else sorted(net_values)[len(net_values) // 2],
                "mean_net_pnl": None if not net_values else sum(net_values) / len(net_values),
                "timeout_rate": timeout_count / len(bucket_rows),
                "ambiguous_same_bar_count": sum(1 for row in bucket_rows if row.get("ambiguous_same_bar")),
                "quality_warning": len(bucket_rows) < min_bucket_samples,
            }
        )
    return metrics


def _candidate_thresholds(rows: Sequence[Mapping[str, Any]], verdict: SufficiencyVerdict, args: argparse.Namespace) -> dict[str, Any]:
    closed_rows = [row for row in rows if row.get(
        "cohort") == COHORT_CLOSED_REAL_TRADE]
    regime_rows = [row for row in closed_rows if _safe_float(
        row.get("regime_confidence")) is not None]
    direction_rows = [
        row for row in closed_rows
        if row.get("direction_confidence_source") != "unavailable"
        and _safe_float(row.get("direction_confidence")) is not None
    ]
    candidate = {
        "regime": args.regime,
        "verdict": "accepted" if verdict.accepted else "exploratory_only",
        "reasons": list(verdict.reasons),
        "thresholds": {
            "min_regime_confidence_by_regime": {args.regime: None},
            "min_direction_confidence_by_regime": {args.regime: None},
            "min_tp_fee_coverage_by_regime": {args.regime: None},
            "min_rr_by_regime": {args.regime: None},
        },
        "support": {
            "closed_real_trade": len(closed_rows),
            "regime_confidence_rows": len(regime_rows),
            "direction_confidence_rows": len(direction_rows),
        },
    }
    if regime_rows:
        candidate["thresholds"]["min_regime_confidence_by_regime"][args.regime] = round(
            min(float(row["regime_confidence"]) for row in regime_rows),
            4,
        )
    if direction_rows:
        candidate["thresholds"]["min_direction_confidence_by_regime"][args.regime] = round(
            min(float(row["direction_confidence"]) for row in direction_rows),
            4,
        )
    required_tp_values = [
        float(row["required_gross_tp_bps"])
        for row in closed_rows
        if _safe_float(row.get("required_gross_tp_bps")) is not None
    ]
    if required_tp_values:
        candidate["thresholds"]["min_tp_fee_coverage_by_regime"][args.regime] = 3.0
        candidate["required_gross_tp_bps_floor"] = round(
            sum(required_tp_values) / len(required_tp_values), 4)
    rr_values = [float(row["rr_ratio"]) for row in closed_rows if _safe_float(
        row.get("rr_ratio")) is not None]
    if rr_values:
        candidate["thresholds"]["min_rr_by_regime"][args.regime] = round(
            sum(rr_values) / len(rr_values), 4)
    return candidate


def _field_matrix(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    required_fields = [
        "symbol",
        "strategy_id",
        "side",
        "timestamp_ms",
        "regime",
        "regime_confidence",
        "direction_confidence",
        "direction_confidence_source",
        "entry_price",
        "target_price",
        "stop_price",
        "notional",
        "margin",
        "leverage",
        "open_fee_bps",
        "close_fee_bps",
        "fee_source",
        "slippage_bps",
        "slippage_source",
        "fill_price",
        "close_price",
        "gross_pnl",
        "fee_paid",
        "net_pnl",
        "mfe_bps",
        "mae_bps",
        "bars_to_tp",
        "bars_to_sl",
        "bars_to_timeout",
        "same_bar_collision_flag",
        "cohort",
        "truth_source",
        "quality_flags",
    ]
    matrix: list[dict[str, Any]] = []
    for field_name in required_fields:
        non_null_count = sum(1 for row in rows if row.get(
            field_name) not in (None, ""))
        if non_null_count == 0:
            status = "missing"
        elif non_null_count == len(rows):
            status = "available"
        else:
            status = "derived_or_partial"
        matrix.append(
            {
                "field": field_name,
                "status": status,
                "non_null_rows": non_null_count,
                "total_rows": len(rows),
            }
        )
    return matrix


def _sample_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_symbol = Counter(row.get("symbol") or "UNKNOWN" for row in rows)
    by_strategy = Counter(row.get("strategy_id") or "UNKNOWN" for row in rows)
    by_regime = Counter(row.get("regime") or "UNKNOWN" for row in rows)
    by_cohort = Counter(row.get("cohort") or "UNKNOWN" for row in rows)
    by_truth_source = Counter(row.get("truth_source")
                              or "UNKNOWN" for row in rows)
    return {
        "by_symbol": dict(sorted(by_symbol.items())),
        "by_strategy": dict(sorted(by_strategy.items())),
        "by_regime": dict(sorted(by_regime.items())),
        "by_cohort": dict(sorted(by_cohort.items())),
        "by_truth_source": dict(sorted(by_truth_source.items())),
    }


def _render_inventory_report(
    *,
    inventory_rows: Sequence[Mapping[str, Any]],
    field_matrix: Sequence[Mapping[str, Any]],
    sample_counts: Mapping[str, Any],
    verdict: SufficiencyVerdict,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# LOW_VOL Data Inventory Report",
        "",
        "## Executive Summary",
        f"- Target regime: {args.regime}",
        f"- Sufficiency verdict: {'ACCEPTED' if verdict.accepted else 'EXPLORATORY_ONLY'}",
        f"- Reasons: {', '.join(verdict.reasons) if verdict.reasons else 'none'}",
        "",
        "## FACTS",
        f"- Inventory scanned {len(inventory_rows)} primary sources.",
        f"- Closed real trade samples: {sample_counts['by_cohort'].get(COHORT_CLOSED_REAL_TRADE, 0)}",
        f"- Counterfactual forward-bar samples: {sample_counts['by_cohort'].get(COHORT_COUNTERFACTUAL_FORWARD_BAR, 0)}",
        "",
        "## INFERENCES",
        "- Current implementation prioritizes master CSV evidence and records missing geometry/confidence fields explicitly instead of fabricating them.",
        "- Recorder support is inventoried, but counterfactual cohort remains unavailable until explicit forward-bar reconstruction is added for a source row family.",
        "",
        "## ASSUMPTIONS",
        "- executed_trades_master.csv net/commission columns are treated as net PnL plus explicit fee column when present.",
        "- max_slippage_bps from config is treated only as configured_cap scenario input.",
        "",
        "## UNKNOWNS",
        "- Strategy-specific target/stop geometry is not yet recoverable from the current master CSV pipeline.",
        "- Direction confidence remains unavailable unless a future join to decision traces is added.",
        "",
        "## File Inventory",
        _inventory_markdown_table(inventory_rows),
        "",
        "## Field Reconstruction Matrix",
        "| field | status | non_null_rows | total_rows |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in field_matrix:
        lines.append(
            f"| {row['field']} | {row['status']} | {row['non_null_rows']} | {row['total_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Sample Counts",
            f"- By symbol: {json.dumps(sample_counts['by_symbol'], sort_keys=True)}",
            f"- By strategy: {json.dumps(sample_counts['by_strategy'], sort_keys=True)}",
            f"- By regime: {json.dumps(sample_counts['by_regime'], sort_keys=True)}",
            f"- By cohort: {json.dumps(sample_counts['by_cohort'], sort_keys=True)}",
            f"- By truth source: {json.dumps(sample_counts['by_truth_source'], sort_keys=True)}",
            "",
            "## LOW_VOLATILITY Sufficiency Verdict",
            f"- Verdict: {'accepted' if verdict.accepted else 'exploratory_only'}",
            f"- Reasons: {', '.join(verdict.reasons) if verdict.reasons else 'none'}",
            "",
            "## Limitations",
            "- Realized slippage is unavailable in the current master CSV pipeline and is therefore tagged as configured_cap or unavailable.",
            "- direction_confidence is nullable and intentionally not substituted from regime_confidence.",
            "- Cohorts are separated in the dataset and must not be mixed into a global winrate without an explicit cohort filter.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_calibration_report(
    *,
    rows: Sequence[Mapping[str, Any]],
    candidate_payload: Mapping[str, Any],
    verdict: SufficiencyVerdict,
    args: argparse.Namespace,
) -> str:
    sample_counts = _sample_counts(rows)
    regime_bucket_metrics = _bucket_metrics(
        [row for row in rows if row.get("cohort") == COHORT_CLOSED_REAL_TRADE],
        field="regime_confidence",
        min_bucket_samples=args.min_bucket_samples,
    )
    direction_bucket_metrics = _bucket_metrics(
        [
            row for row in rows
            if row.get("cohort") == COHORT_CLOSED_REAL_TRADE
            and row.get("direction_confidence_source") != "unavailable"
        ],
        field="direction_confidence",
        min_bucket_samples=args.min_bucket_samples,
    )
    lines = [
        "# LOW_VOL Cost-Floor Calibration",
        "",
        "## Executive Summary",
        f"- Verdict: {'accepted' if verdict.accepted else 'exploratory_only'}",
        f"- Closed real trades: {sample_counts['by_cohort'].get(COHORT_CLOSED_REAL_TRADE, 0)}",
        f"- Rejected attempts: {sample_counts['by_cohort'].get(COHORT_REJECTED_ATTEMPT, 0)}",
        f"- Order attempts unfilled: {sample_counts['by_cohort'].get(COHORT_ORDER_ATTEMPT_UNFILLED, 0)}",
        f"- Counterfactual forward bars: {sample_counts['by_cohort'].get(COHORT_COUNTERFACTUAL_FORWARD_BAR, 0)}",
        "",
        "## Verdict",
        f"- {'ACCEPTED' if verdict.accepted else 'EXPLORATORY_ONLY'}",
        f"- Reasons: {', '.join(verdict.reasons) if verdict.reasons else 'none'}",
        "",
        "## FACTS",
        f"- Economic contract used target_net_fee_multiple={args.target_net_fee_multiple}.",
        f"- Required output files: {', '.join(REQUIRED_OUTPUT_FILES)}.",
        "- max_slippage_bps is treated as configured_cap rather than realized slippage.",
        "",
        "## INFERENCES",
        "- Thresholds are exploratory when geometry/confidence support is sparse or fee sources are not recoverable for accepted evidence.",
        "",
        "## ASSUMPTIONS",
        "- Notional defaults to entry_price for master CSV rows until explicit quantity joins are added.",
        "",
        "## UNKNOWNS",
        "- Per-strategy and per-symbol accepted thresholds remain blocked by sparse strategy_id coverage in the current dataset slice.",
        "",
        "## Calibration Formulas",
        "- round_trip_fee_usd = notional * (open_fee_bps + close_fee_bps) / 10000",
        "- required_net_usd = target_net_fee_multiple * round_trip_fee_usd",
        "- required_gross_tp_usd = round_trip_fee_usd + required_net_usd",
        "- required_gross_tp_bps = (open_fee_bps + close_fee_bps) * (1 + target_net_fee_multiple) + slippage_buffer_bps",
        "",
        "## LOW_VOLATILITY Sample Counts",
        f"- By symbol: {json.dumps(sample_counts['by_symbol'], sort_keys=True)}",
        f"- By strategy: {json.dumps(sample_counts['by_strategy'], sort_keys=True)}",
        f"- By cohort: {json.dumps(sample_counts['by_cohort'], sort_keys=True)}",
        f"- By truth source: {json.dumps(sample_counts['by_truth_source'], sort_keys=True)}",
        "",
        "## Candidate Threshold Table",
        f"- {json.dumps(candidate_payload['thresholds'], sort_keys=True)}",
        "",
        "## Regime Confidence Buckets",
        f"- {json.dumps(regime_bucket_metrics, sort_keys=True)}",
        "",
        "## Direction Confidence Buckets",
        f"- {json.dumps(direction_bucket_metrics, sort_keys=True)}",
        "",
        "## Validation Commands and Outputs",
        "- python calibrators/policy_gates/calibrate_low_vol_cost_floor.py --help",
        "- pytest tests/test_calibrate_low_vol_cost_floor.py -q",
        "",
        "## Risks",
        "- Missing target/stop geometry limits fee-coverage and RR conclusions for realized trades.",
        "- Strategy-level overrides remain exploratory until strategy_id joins are added.",
        "",
        "## Follow-up Implementation Recommendation",
        "- Next bounded package should add raw log joins for regime_confidence, decision trace confidence, and recorder-based counterfactual outcomes without changing runtime behavior.",
    ]
    return "\n".join(lines) + "\n"


def run_calibration(args: argparse.Namespace) -> dict[str, Any]:
    inventory_rows, inventory_summary = _build_inventory(args)
    dataset_rows = _build_master_dataset_rows(args)
    dataset_rows.extend(_build_order_log_dataset_rows(args))
    field_matrix = _field_matrix(dataset_rows)
    sample_counts = _sample_counts(dataset_rows)
    closed_rows = [row for row in dataset_rows if row.get(
        "cohort") == COHORT_CLOSED_REAL_TRADE]
    bucket_counts = Counter()
    for row in closed_rows:
        confidence = _safe_float(row.get("regime_confidence"))
        if confidence is None:
            continue
        label = _canonical_bucket_label(confidence)
        if label:
            bucket_counts[label] += 1
    verdict = evaluate_sufficiency(
        closed_samples=len(closed_rows),
        symbol_counts=sample_counts["by_symbol"],
        strategy_counts=sample_counts["by_strategy"],
        bucket_counts=bucket_counts,
        counterfactual_samples=sample_counts["by_cohort"].get(
            COHORT_COUNTERFACTUAL_FORWARD_BAR, 0),
        min_closed_samples=args.min_closed_samples,
        min_samples_per_symbol=args.min_samples_per_symbol,
        min_samples_per_strategy=args.min_samples_per_strategy,
        min_bucket_samples=args.min_bucket_samples,
        min_counterfactual_samples=args.min_counterfactual_samples,
    )
    candidate_payload = _candidate_thresholds(dataset_rows, verdict, args)

    out_dir = Path(args.out_dir)
    reports_dir = Path(args.reports_dir)
    dataset_path = out_dir / "low_vol_trade_dataset.csv"
    candidate_json_path = out_dir / "low_vol_threshold_candidates.json"
    candidate_yaml_path = out_dir / "low_vol_candidate_yaml_patch.yaml"
    inventory_report_path = reports_dir / "LOW_VOL_DATA_INVENTORY_REPORT.md"
    calibration_report_path = reports_dir / "LOW_VOL_COST_FLOOR_CALIBRATION.md"

    _write_csv(dataset_path, dataset_rows)
    _write_json(candidate_json_path, candidate_payload)
    _write_yaml(candidate_yaml_path, {
                "candidates": candidate_payload["thresholds"]})
    inventory_report_path.write_text(
        _render_inventory_report(
            inventory_rows=inventory_rows,
            field_matrix=field_matrix,
            sample_counts=sample_counts,
            verdict=verdict,
            args=args,
        ),
        encoding="utf-8",
    )
    calibration_report_path.write_text(
        _render_calibration_report(
            rows=dataset_rows,
            candidate_payload=candidate_payload,
            verdict=verdict,
            args=args,
        ),
        encoding="utf-8",
    )
    return {
        "inventory_summary": inventory_summary,
        "field_matrix": field_matrix,
        "sample_counts": sample_counts,
        "verdict": {
            "accepted": verdict.accepted,
            "exploratory_only": verdict.exploratory_only,
            "reasons": list(verdict.reasons),
        },
        "outputs": {
            "dataset": str(dataset_path),
            "candidate_json": str(candidate_json_path),
            "candidate_yaml": str(candidate_yaml_path),
            "inventory_report": str(inventory_report_path),
            "calibration_report": str(calibration_report_path),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    run_calibration(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
