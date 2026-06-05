from __future__ import annotations

import argparse
import inspect
import json
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from apps.reference.config_loader import ConfigLoader
from apps.reference.core.time import get_clock

from .models import CanonicalEntry
from .reconstruct import reconstruct_canonical_entries


LIMITATIONS = [
    "Parity harness v1 proves one-day safety-gate family-level behavior only.",
    "It is not full runtime FSM, adapter, websocket-ordering, or async race proof.",
    "Blocked-family parity currently relies on retained regime_confidence_audit/order_log surfaces; families absent from retained logs remain out of scope.",
]


DENY_REASON_TO_FAMILY = {
    "NRR-026": "INSUFFICIENT_TREND_CONFIRMATION",
    "NRR026": "INSUFFICIENT_TREND_CONFIRMATION",
    "INSUFFICIENT_TREND_CONFIRMATION": "INSUFFICIENT_TREND_CONFIRMATION",
    "NRR-027": "DIRECTIONAL_SANITY_BLOCKED",
    "NRR027": "DIRECTIONAL_SANITY_BLOCKED",
    "DIRECTIONAL_SANITY_BLOCKED": "DIRECTIONAL_SANITY_BLOCKED",
    "NRR-028": "PRICE_MOTION_INSUFFICIENT",
    "NRR028": "PRICE_MOTION_INSUFFICIENT",
    "PRICE_MOTION_INSUFFICIENT": "PRICE_MOTION_INSUFFICIENT",
    "NRR-029": "PRICE_MOTION_FLASH_BLOCKED",
    "NRR029": "PRICE_MOTION_FLASH_BLOCKED",
    "PRICE_MOTION_FLASH_BLOCKED": "PRICE_MOTION_FLASH_BLOCKED",
    "NRR-030": "PRICE_MOTION_BLEED_BLOCKED",
    "NRR030": "PRICE_MOTION_BLEED_BLOCKED",
    "PRICE_MOTION_BLEED_BLOCKED": "PRICE_MOTION_BLEED_BLOCKED",
    "NRR-063": "REGIME_CONFIDENCE_ABOVE_MAX",
    "NRR063": "REGIME_CONFIDENCE_ABOVE_MAX",
    "REGIME_CONFIDENCE_ABOVE_MAX": "REGIME_CONFIDENCE_ABOVE_MAX",
}


@dataclass(frozen=True)
class ReplayCandidate:
    candidate_id: str
    source_surface: str
    symbol: str
    side: str
    strategy_id: str
    ts_ms: int
    expected_family: str
    regime: str | None = None
    regime_confidence: float | None = None
    trend_dir: str | None = None
    trend_confidence: float | None = None
    trend_run_length: int | None = None
    pm_norm_10s: float | None = None
    pm_norm_60s: float | None = None
    pm_norm_300s: float | None = None
    resolved_min_regime_confidence: float | None = None
    resolved_min_regime_confidence_source: str | None = None
    resolved_max_regime_confidence: float | None = None
    resolved_max_regime_confidence_source: str | None = None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def load_runtime_config(workspace_root: Path) -> Any:
    return ConfigLoader(config_dir=workspace_root / "config" / "aurora").load_config()


def _load_safety_gate_callables():
    # Mirror the import order already exercised in decision-making tests.
    from apps.reference.domains.decision_making.core.facade import DecisionMaking  # noqa: F401
    from apps.reference.domains.decision_making.gates.safety_gates import (
        _check_directional_gate,
        _check_price_motion_gate,
        apply_safety_gates,
    )

    return apply_safety_gates, _check_directional_gate, _check_price_motion_gate


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _utc_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _normalize_family(reason: Any, *, default: str) -> str:
    token = str(reason or "").strip().upper()
    return DENY_REASON_TO_FAMILY.get(token, default)


def _canonical_entry_to_candidate(entry: CanonicalEntry) -> ReplayCandidate:
    return ReplayCandidate(
        candidate_id=str(entry.entry_id or entry.rid),
        source_surface="order_log_opened_entry",
        symbol=str(entry.symbol),
        side=str(entry.side),
        strategy_id=str(entry.strategy_id or "aurora"),
        ts_ms=int(entry.entry_ts_ms),
        expected_family="ALLOW",
        regime=entry.regime_at_entry,
        regime_confidence=entry.regime_confidence_at_entry,
        trend_dir=entry.trend_dir,
        trend_confidence=entry.trend_confidence,
        trend_run_length=entry.trend_run_length,
        pm_norm_10s=entry.pm_norm_10s,
        pm_norm_60s=entry.pm_norm_60s,
        pm_norm_300s=entry.pm_norm_300s,
        resolved_min_regime_confidence=entry.resolved_min_regime_confidence,
        resolved_min_regime_confidence_source=entry.resolved_min_regime_confidence_source,
        resolved_max_regime_confidence=entry.resolved_max_regime_confidence,
        resolved_max_regime_confidence_source=entry.resolved_max_regime_confidence_source,
    )


def _audit_row_to_candidate(row: dict[str, Any]) -> ReplayCandidate:
    intent_side = str(row.get("intent_side") or "").strip().upper()
    side = "BUY" if intent_side == "LONG" else "SELL"
    return ReplayCandidate(
        candidate_id=str(row.get("rid") or row.get("lifecycle_id") or row.get("ts_ms")),
        source_surface="regime_confidence_audit",
        symbol=str(row.get("symbol") or ""),
        side=side,
        strategy_id=str(row.get("strategy_id") or "aurora"),
        ts_ms=int(row.get("ts_ms") or row.get("bar_close_ts_ms") or 0),
        expected_family=_normalize_family(
            row.get("deny_reason"),
            default=_normalize_family(row.get("regime_confidence_gate_verdict"), default="UNKNOWN"),
        ),
        regime=row.get("regime_used"),
        regime_confidence=_coerce_float(row.get("regime_confidence_used")),
        resolved_min_regime_confidence=_coerce_float(row.get("resolved_min_regime_confidence")),
        resolved_min_regime_confidence_source=_coerce_text(row.get("resolved_min_regime_confidence_source")),
        resolved_max_regime_confidence=_coerce_float(row.get("resolved_max_regime_confidence")),
        resolved_max_regime_confidence_source=_coerce_text(row.get("resolved_max_regime_confidence_source")),
    )


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _select_day(
    opened_candidates: list[ReplayCandidate],
    blocked_candidates: list[ReplayCandidate],
    *,
    forced_day: str | None,
) -> tuple[str | None, str]:
    if forced_day:
        return forced_day, "explicit"
    opened_days = {_utc_day(item.ts_ms) for item in opened_candidates if item.ts_ms}
    blocked_days = {_utc_day(item.ts_ms) for item in blocked_candidates if item.ts_ms}
    common_days = sorted(opened_days & blocked_days)
    if common_days:
        return common_days[-1], "intersection_latest"
    union_days = sorted(opened_days | blocked_days)
    if union_days:
        return union_days[-1], "union_latest"
    return None, "missing"


def _build_symbol_state(candidate: ReplayCandidate, *, min_abs_delta: float) -> dict[str, Any]:
    hist = deque(maxlen=max(int(candidate.trend_run_length or 0), 4))
    if candidate.trend_run_length and candidate.trend_dir in {"UP", "DOWN"}:
        magnitude = max(abs(float(min_abs_delta)), 0.0001)
        signed_value = magnitude if candidate.trend_dir == "UP" else -magnitude
        hist.extend([signed_value] * int(candidate.trend_run_length))
    price_motion = {
        "pm_norm_10s": candidate.pm_norm_10s,
        "pm_norm_60s": candidate.pm_norm_60s,
        "pm_norm_300s": candidate.pm_norm_300s,
    }
    return {
        "_delta_price_hist": hist,
        "features": {
            "price_motion": price_motion,
        },
    }


def _build_regime_cache(candidate: ReplayCandidate) -> dict[str, Any]:
    return {
        candidate.symbol: {
            "regime": candidate.regime,
            "confidence": candidate.regime_confidence,
            "ts_ms": candidate.ts_ms,
        }
    }


def _gate_import_provenance() -> list[dict[str, Any]]:
    apply_safety_gates, _check_directional_gate, _check_price_motion_gate = _load_safety_gate_callables()
    directional_module = inspect.getmodule(_check_directional_gate)
    price_motion_module = inspect.getmodule(_check_price_motion_gate)
    apply_module = inspect.getmodule(apply_safety_gates)
    return [
        {
            "gate_id": "FIX_CONF_GATE_01",
            "module_path": apply_module.__name__ if apply_module is not None else "",
            "callable_qualname": apply_safety_gates.__qualname__,
            "config_surface_used": "domains.decision_making.directional_sanity",
        },
        {
            "gate_id": "NRR026",
            "module_path": directional_module.__name__ if directional_module is not None else "",
            "callable_qualname": _check_directional_gate.__qualname__,
            "config_surface_used": "domains.decision_making.directional_sanity",
        },
        {
            "gate_id": "NRR027",
            "module_path": directional_module.__name__ if directional_module is not None else "",
            "callable_qualname": _check_directional_gate.__qualname__,
            "config_surface_used": "domains.decision_making.directional_sanity",
        },
        {
            "gate_id": "NRR028",
            "module_path": price_motion_module.__name__ if price_motion_module is not None else "",
            "callable_qualname": _check_price_motion_gate.__qualname__,
            "config_surface_used": "domains.decision_making.price_motion_sanity",
        },
        {
            "gate_id": "NRR029",
            "module_path": price_motion_module.__name__ if price_motion_module is not None else "",
            "callable_qualname": _check_price_motion_gate.__qualname__,
            "config_surface_used": "domains.decision_making.price_motion_sanity",
        },
        {
            "gate_id": "NRR030",
            "module_path": price_motion_module.__name__ if price_motion_module is not None else "",
            "callable_qualname": _check_price_motion_gate.__qualname__,
            "config_surface_used": "domains.decision_making.price_motion_sanity",
        },
        {
            "gate_id": "NRR063",
            "module_path": apply_module.__name__ if apply_module is not None else "",
            "callable_qualname": apply_safety_gates.__qualname__,
            "config_surface_used": "domains.decision_making.directional_sanity",
        },
    ]


def _evaluate_candidate(candidate: ReplayCandidate, config: Any) -> dict[str, Any]:
    apply_safety_gates, _, _ = _load_safety_gate_callables()
    ds_cfg = config.domains.decision_making.directional_sanity
    min_abs_delta = float(getattr(ds_cfg, "min_abs_delta_price", 0.0) or 0.0)
    symbol_states = {candidate.symbol: _build_symbol_state(candidate, min_abs_delta=min_abs_delta)}
    result = apply_safety_gates(
        symbol=candidate.symbol,
        side=candidate.side,
        reduce_only=False,
        strategy_id=candidate.strategy_id,
        decision_ts_ms=candidate.ts_ms,
        why_chain=[],
        config=config,
        clock=get_clock(),
        symbol_states=symbol_states,
        per_symbol_regimes=_build_regime_cache(candidate),
        system_stress_states=None,
    )
    observed_family = "ALLOW" if result.outcome == "ALLOW" else _normalize_family(
        result.deny_reason,
        default=str(result.deny_reason or result.outcome or "UNKNOWN"),
    )
    return {
        "candidate_id": candidate.candidate_id,
        "source_surface": candidate.source_surface,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "strategy_id": candidate.strategy_id,
        "ts_ms": candidate.ts_ms,
        "expected_family": candidate.expected_family,
        "observed_outcome": result.outcome,
        "observed_family": observed_family,
        "match": observed_family == candidate.expected_family,
        "resolved_min_regime_confidence": result.resolved_min_regime_confidence,
        "resolved_min_regime_confidence_source": result.resolved_min_regime_confidence_source,
        "resolved_max_regime_confidence": result.resolved_max_regime_confidence,
        "resolved_max_regime_confidence_source": result.resolved_max_regime_confidence_source,
        "threshold_reason": result.threshold_reason,
        "why_short": result.why_short,
    }


def _within_tolerance(actual: int, predicted: int, tolerance_pct: float) -> bool:
    if actual == predicted:
        return True
    tolerance_abs = max(1, int(round(abs(actual) * float(tolerance_pct))))
    return abs(predicted - actual) <= tolerance_abs


def _reject_family_matrix(actual_rows: list[dict[str, Any]], predicted_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual_counts = Counter(
        row["expected_family"]
        for row in actual_rows
        if row["expected_family"] != "ALLOW"
    )
    predicted_counts = Counter(
        row["observed_family"]
        for row in predicted_rows
        if row["observed_family"] != "ALLOW"
    )
    families = sorted(set(actual_counts) | set(predicted_counts))
    rows: list[dict[str, Any]] = []
    for family in families:
        actual = int(actual_counts.get(family, 0))
        predicted = int(predicted_counts.get(family, 0))
        rows.append(
            {
                "family": family,
                "actual_count": actual,
                "predicted_count": predicted,
                "delta": predicted - actual,
                "match": actual == predicted,
            }
        )
    return rows


def _threshold_provenance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    min_sources = Counter()
    max_sources = Counter()
    for row in rows:
        min_sources[str(row.get("resolved_min_regime_confidence_source") or "missing")] += 1
        max_sources[str(row.get("resolved_max_regime_confidence_source") or "missing")] += 1
    return {
        "resolved_min_regime_confidence_source_counts": dict(sorted(min_sources.items())),
        "resolved_max_regime_confidence_source_counts": dict(sorted(max_sources.items())),
        "rows_with_min_threshold": sum(1 for row in rows if row.get("resolved_min_regime_confidence") is not None),
        "rows_with_max_threshold": sum(1 for row in rows if row.get("resolved_max_regime_confidence") is not None),
    }


def _top_family(counts: Counter[str]) -> str | None:
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def run_parity_harness(
    *,
    workspace_root: Path,
    runtime_root: Path,
    report_root: Path,
    recorder_root: Path,
    extra_recorder_roots: Iterable[Path | str] | None = None,
    scenarios: str = "real_gate_parity",
    strict: bool = True,
    mode: str = "actual_trace_replay",
    tolerance_pct: float = 0.10,
    parity_day: str | None = None,
) -> dict[str, Any]:
    del recorder_root, extra_recorder_roots, scenarios, strict, mode

    config = load_runtime_config(workspace_root)
    gate_provenance = _gate_import_provenance()
    _write_json(report_root / "gate_import_provenance.json", {"rows": gate_provenance})
    order_log_path = runtime_root / "order_log_v1.jsonl"
    if not order_log_path.exists():
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "missing_runtime_surface",
            "missing_surface": str(order_log_path),
        }
        parity_summary = {
            "status": "missing_runtime_surface",
            "behavioral_family_level_parity_passed": False,
            "threshold_provenance_retained": False,
            "limitations": LIMITATIONS + ["Retained order_log_v1.jsonl is missing in this workspace slice."],
        }
        _write_json(report_root / "run_manifest.json", manifest)
        _write_json(report_root / "one_day_parity_summary.json", parity_summary)
        _write_markdown(
            report_root / "parity_limitations.md",
            ["# Parity Limitations", "", *[f"- {item}" for item in parity_summary["limitations"]]],
        )
        return {
            "manifest": manifest,
            "parity_summary": parity_summary,
            "reject_family_matrix": [],
            "threshold_provenance": {},
            "gate_import_provenance": gate_provenance,
            "mismatch_rows": [],
        }

    canonical_entries, unresolved_rows, reconstruction_manifest = reconstruct_canonical_entries(
        workspace_root,
        runtime_root,
        report_root,
    )
    opened_candidates = [_canonical_entry_to_candidate(entry) for entry in canonical_entries]
    confidence_rows = [
        row for row in _load_jsonl_rows(runtime_root / "regime_confidence_audit_v1.jsonl")
        if str(row.get("record_type") or "decision") == "decision"
        and str(row.get("outcome") or "").upper() == "DENY"
    ]
    blocked_candidates = [_audit_row_to_candidate(row) for row in confidence_rows]

    selected_day, day_selection_method = _select_day(
        opened_candidates,
        blocked_candidates,
        forced_day=parity_day,
    )
    if selected_day is None:
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "missing_day_selection",
            "reconstruction": reconstruction_manifest,
            "unresolved_order_rows": len(unresolved_rows),
        }
        _write_json(report_root / "run_manifest.json", manifest)
        _write_markdown(report_root / "parity_limitations.md", ["# Parity Limitations", "", *[f"- {item}" for item in LIMITATIONS]])
        return {
            "manifest": manifest,
            "parity_summary": {
                "status": "missing_day_selection",
                "threshold_provenance_retained": False,
                "behavioral_family_level_parity_passed": False,
            },
        }

    opened_day = [item for item in opened_candidates if _utc_day(item.ts_ms) == selected_day]
    blocked_day = [item for item in blocked_candidates if _utc_day(item.ts_ms) == selected_day]
    opened_results = [_evaluate_candidate(item, config) for item in opened_day]
    blocked_results = [_evaluate_candidate(item, config) for item in blocked_day]

    actual_opened_count = len(opened_day)
    predicted_opened_count = sum(1 for row in opened_results if row["observed_family"] == "ALLOW")
    actual_blocked_counts = Counter(item.expected_family for item in blocked_day if item.expected_family != "ALLOW")
    predicted_blocked_counts = Counter(row["observed_family"] for row in blocked_results if row["observed_family"] != "ALLOW")
    reject_family_rows = _reject_family_matrix(
        [{"expected_family": item.expected_family} for item in blocked_day],
        blocked_results,
    )
    opened_match = _within_tolerance(actual_opened_count, predicted_opened_count, tolerance_pct)
    reject_match = all(row["match"] for row in reject_family_rows)
    dominant_reject_match = _top_family(actual_blocked_counts) == _top_family(predicted_blocked_counts)
    threshold_rows = opened_results + blocked_results
    threshold_provenance = _threshold_provenance(threshold_rows)
    mismatches = [
        row for row in (opened_results + blocked_results)
        if row["expected_family"] != row["observed_family"]
    ]

    parity_summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_day_utc": selected_day,
        "day_selection_method": day_selection_method,
        "actual_opened_count": actual_opened_count,
        "predicted_opened_count": predicted_opened_count,
        "opened_count_match": opened_match,
        "actual_blocked_family_counts": dict(sorted(actual_blocked_counts.items())),
        "predicted_blocked_family_counts": dict(sorted(predicted_blocked_counts.items())),
        "dominant_reject_families_match": dominant_reject_match,
        "reject_family_matrix_match": reject_match,
        "threshold_provenance_retained": True,
        "behavioral_family_level_parity_passed": bool(opened_match and reject_match and dominant_reject_match),
        "mismatch_count": len(mismatches),
        "tolerance_pct": float(tolerance_pct),
        "limitations": LIMITATIONS,
    }
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "selected_day_utc": selected_day,
        "reconstruction": reconstruction_manifest,
        "canonical_entries": len(canonical_entries),
        "opened_candidates_for_day": len(opened_day),
        "blocked_candidates_for_day": len(blocked_day),
        "unresolved_order_rows": len(unresolved_rows),
    }

    _write_json(report_root / "one_day_parity_summary.json", parity_summary)
    _write_json(report_root / "one_day_reject_family_matrix.json", {"rows": reject_family_rows})
    _write_json(report_root / "threshold_provenance.json", threshold_provenance)
    _write_json(report_root / "mismatch_rows.json", {"rows": mismatches})
    _write_json(report_root / "run_manifest.json", manifest)
    _write_markdown(
        report_root / "parity_limitations.md",
        ["# Parity Limitations", "", *[f"- {item}" for item in LIMITATIONS]],
    )
    return {
        "manifest": manifest,
        "parity_summary": parity_summary,
        "reject_family_matrix": reject_family_rows,
        "threshold_provenance": threshold_provenance,
        "gate_import_provenance": gate_provenance,
        "mismatch_rows": mismatches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="logs")
    parser.add_argument("--report-root", default="reports/order_log_parity_harness")
    parser.add_argument("--recorder-root", default="data/recorder")
    parser.add_argument("--extra-recorder-root", action="append", default=["data/recorder_backfill_1m"])
    parser.add_argument("--scenarios", default="real_gate_parity")
    parser.add_argument("--strict", default="true")
    parser.add_argument("--mode", default="actual_trace_replay")
    parser.add_argument("--tolerance-pct", type=float, default=0.10)
    parser.add_argument("--day", default=None)
    args = parser.parse_args(argv)

    workspace_root = Path.cwd()
    result = run_parity_harness(
        workspace_root=workspace_root,
        runtime_root=(workspace_root / args.runtime_root).resolve(),
        report_root=(workspace_root / args.report_root).resolve(),
        recorder_root=(workspace_root / args.recorder_root).resolve(),
        extra_recorder_roots=[
            (workspace_root / item).resolve() if not Path(item).is_absolute() else Path(item)
            for item in args.extra_recorder_root
        ],
        scenarios=args.scenarios,
        strict=str(args.strict).strip().lower() not in {"0", "false", "no", "off"},
        mode=args.mode,
        tolerance_pct=float(args.tolerance_pct),
        parity_day=args.day,
    )
    print(json.dumps(result["parity_summary"], ensure_ascii=False, indent=2))
    summary = result["parity_summary"]
    return 0 if result["manifest"].get("status") == "complete" and summary.get("behavioral_family_level_parity_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
