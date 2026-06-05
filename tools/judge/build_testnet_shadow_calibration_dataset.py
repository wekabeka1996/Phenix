#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (  # noqa: E402
    JudgeShadowCalibrationRowV1,
    side_from_verdict,
)


def load_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"input path does not exist: {path}")
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
                if not isinstance(payload, dict):
                    raise ValueError(f"{path}:{line_number}: row must be an object")
                if isinstance(payload.get("payload"), dict):
                    payload = dict(payload["payload"])
                payload.setdefault("_input_path", path.as_posix())
                rows.append(payload)
    return rows


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
        source_refs = row.get("source_refs")
        if isinstance(source_refs, Mapping):
            value = source_refs.get(key)
            if value not in (None, ""):
                return value
    return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _index(rows: Sequence[Mapping[str, Any]], *keys: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in keys:
            value = _first(row, key)
            if value not in (None, ""):
                indexed.setdefault(str(value), dict(row))
    return indexed


def _index_many(rows: Sequence[Mapping[str, Any]], *keys: str) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for key in keys:
            value = _first(row, key)
            if value not in (None, ""):
                indexed[str(value)].append(dict(row))
    return indexed


def _find_by_identity(
    source: Mapping[str, Any],
    indexes: Sequence[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str | None]:
    for key_name, index in indexes:
        key = _first(source, key_name)
        if key not in (None, "") and str(key) in index:
            return index[str(key)], key_name
    return None, None


def _find_fuzzy_outcome(
    verdict: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
    *,
    horizon_sec: int,
) -> dict[str, Any] | None:
    symbol = verdict.get("symbol")
    decision_ts = _to_int(_first(verdict, "decision_ts_ms", "created_ts_ms", "ts_ms"))
    if not symbol or decision_ts is None:
        return None
    window_ms = horizon_sec * 1000
    candidates = []
    for outcome in outcomes:
        if outcome.get("symbol") != symbol:
            continue
        outcome_ts = _to_int(_first(outcome, "outcome_ts_ms", "exit_ts_ms", "ts_ms"))
        if outcome_ts is None or outcome_ts < decision_ts:
            continue
        if outcome_ts - decision_ts <= window_ms:
            candidates.append((outcome_ts, dict(outcome)))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _extract_regime(verdict: Mapping[str, Any], envelope: Mapping[str, Any] | None) -> tuple[str | None, float | None]:
    label = _first(verdict, "regime_label", "regime")
    confidence = _to_float(_first(verdict, "regime_confidence"))
    if envelope:
        label = label or _first(envelope, "regime_label", "regime")
        confidence = confidence if confidence is not None else _to_float(_first(envelope, "regime_confidence"))
        regime_context = envelope.get("regime_context")
        if isinstance(regime_context, dict):
            nested = regime_context.get("envelope")
            if isinstance(nested, dict):
                regime = nested.get("regime")
                if isinstance(regime, dict):
                    label = label or regime.get("label")
                    confidence = confidence if confidence is not None else _to_float(regime.get("confidence"))
    return (str(label) if label not in (None, "") else None), confidence


def _outcome_block(
    outcome: Mapping[str, Any] | None,
    *,
    horizon_sec: int,
    allow_unresolved: bool,
) -> dict[str, Any]:
    if outcome is None:
        status = "UNRESOLVED" if allow_unresolved else "MISSING"
        return {
            "outcome_status": status,
            "outcome_ts_ms": None,
            "horizon_sec": horizon_sec if allow_unresolved else None,
            "gross_pnl_usd": None,
            "net_pnl_usd": None,
            "fees_usd": None,
            "slippage_usd": None,
            "max_favorable_usd": None,
            "max_adverse_usd": None,
            "terminal_status": None,
        }
    net = _to_float(_first(outcome, "net_pnl_usd", "net_pnl", "net_return_usd"))
    return {
        "outcome_status": "RESOLVED" if net is not None else "UNRESOLVED",
        "outcome_ts_ms": _to_int(_first(outcome, "outcome_ts_ms", "exit_ts_ms", "ts_ms")),
        "horizon_sec": _to_int(_first(outcome, "horizon_sec")) or horizon_sec,
        "gross_pnl_usd": _to_float(_first(outcome, "gross_pnl_usd", "gross_pnl", "raw_pnl_usd")),
        "net_pnl_usd": net,
        "fees_usd": _to_float(_first(outcome, "fees_usd", "fee_usd", "fee_cost")),
        "slippage_usd": _to_float(_first(outcome, "slippage_usd", "slippage_cost")),
        "max_favorable_usd": _to_float(_first(outcome, "max_favorable_usd", "mfe_usd")),
        "max_adverse_usd": _to_float(_first(outcome, "max_adverse_usd", "mae_usd")),
        "terminal_status": _first(outcome, "terminal_status", "status", "exit_reason"),
    }


def build_shadow_calibration_rows(
    *,
    verdict_rows: Sequence[Mapping[str, Any]],
    envelope_rows: Sequence[Mapping[str, Any]] = (),
    bridge_rows: Sequence[Mapping[str, Any]] = (),
    lifecycle_rows: Sequence[Mapping[str, Any]] = (),
    order_rows: Sequence[Mapping[str, Any]] = (),
    source_kind: str,
    horizon_sec: int,
    join_mode: str = "exact",
    allow_unresolved: bool = False,
) -> tuple[list[JudgeShadowCalibrationRowV1], list[dict[str, Any]]]:
    if join_mode not in {"exact", "fuzzy"}:
        raise ValueError("join_mode must be exact or fuzzy")
    envelope_by_id = _index(envelope_rows, "envelope_id")
    bridge_by_verdict = _index(bridge_rows, "source_verdict_id", "verdict_id")
    bridge_by_identity = _index(bridge_rows, "decision_id", "rid")
    outcomes_by_identity = _index_many(lifecycle_rows, "decision_id", "rid", "lifecycle_id")
    orders_by_identity = _index(order_rows, "decision_id", "rid", "lifecycle_id", "order_id", "client_order_id")
    input_paths = sorted(
        {
            str(row.get("_input_path"))
            for row in [*verdict_rows, *envelope_rows, *bridge_rows, *lifecycle_rows, *order_rows]
            if row.get("_input_path")
        }
    )

    built: list[JudgeShadowCalibrationRowV1] = []
    diagnostics: list[dict[str, Any]] = []
    for index, verdict in enumerate(sorted(verdict_rows, key=lambda row: (str(_first(row, "decision_id", "rid", "verdict_id") or ""), _to_int(_first(row, "decision_ts_ms", "created_ts_ms", "ts_ms")) or 0))):
        verdict_id = _first(verdict, "verdict_id")
        envelope_id = _first(verdict, "envelope_id")
        envelope = envelope_by_id.get(str(envelope_id)) if envelope_id else None
        decision_ts = _to_int(_first(verdict, "decision_ts_ms", "created_ts_ms", "ts_ms")) or 0
        bridge = bridge_by_verdict.get(str(verdict_id)) if verdict_id else None
        if bridge is None:
            bridge, _ = _find_by_identity(verdict, (("decision_id", bridge_by_identity), ("rid", bridge_by_identity)))
        outcome = None
        join_quality = "UNJOINED"
        reason_codes: list[str] = []
        for key in ("decision_id", "lifecycle_id", "rid"):
            value = _first(verdict, key)
            if value not in (None, "") and str(value) in outcomes_by_identity:
                outcome = outcomes_by_identity[str(value)][0]
                join_quality = "RID_EXACT" if key == "rid" else "EXACT"
                reason_codes.append(f"joined_by_{key}")
                break
        if outcome is None and join_mode == "fuzzy":
            outcome = _find_fuzzy_outcome(verdict, lifecycle_rows, horizon_sec=horizon_sec)
            if outcome is not None:
                join_quality = "FUZZY"
                reason_codes.append("joined_by_fuzzy_window")
        if outcome is not None:
            outcome_ts = _to_int(_first(outcome, "outcome_ts_ms", "exit_ts_ms", "ts_ms"))
            if outcome_ts is not None and outcome_ts < decision_ts:
                diagnostics.append(
                    {
                        "verdict_id": verdict_id,
                        "reason": "future_leakage_outcome_before_decision",
                        "decision_id": verdict.get("decision_id"),
                        "rid": verdict.get("rid"),
                    }
                )
                outcome = None
                join_quality = "UNJOINED"
                reason_codes = ["outcome_before_decision_rejected"]
        if outcome is None and not allow_unresolved:
            diagnostics.append(
                {
                    "verdict_id": verdict_id,
                    "reason": "unjoined_outcome_dropped",
                    "decision_id": verdict.get("decision_id"),
                    "rid": verdict.get("rid"),
                }
            )
            continue
        if outcome is None:
            reason_codes.append("unresolved_outcome_allowed")

        order = None
        for key in ("decision_id", "lifecycle_id", "rid", "order_id", "client_order_id"):
            value = _first(verdict, key) or _first(outcome or {}, key)
            if value not in (None, "") and str(value) in orders_by_identity:
                order = orders_by_identity[str(value)][0]
                break

        verdict_value = _first(verdict, "verdict", "entry_verdict")
        regime_label, regime_confidence = _extract_regime(verdict, envelope)
        missing_fields = []
        if not envelope:
            missing_fields.append("envelope")
        if outcome is None:
            missing_fields.append("outcome")
        bridge_present = bridge is not None
        row = JudgeShadowCalibrationRowV1(
            row_id=f"shadow_cal_{source_kind}_{verdict_id or index}",
            source_kind=source_kind,
            created_ts_ms=_to_int(_first(verdict, "created_ts_ms", "ts_ms", "decision_ts_ms")) or decision_ts,
            decision_ts_ms=decision_ts,
            symbol=str(_first(verdict, "symbol") or "UNKNOWN"),
            side=str(_first(verdict, "side") or side_from_verdict(str(verdict_value) if verdict_value else None)),
            regime_label=regime_label,
            regime_confidence=regime_confidence,
            envelope={
                "envelope_id": str(envelope_id) if envelope_id else None,
                "present": envelope is not None,
                "missing_reason": None if envelope else "not_joined",
            },
            verdict={
                "verdict_id": str(verdict_id) if verdict_id else None,
                "verdict": str(verdict_value) if verdict_value else None,
                "confidence": _to_float(_first(verdict, "confidence", "judge_confidence")),
                "authority_status": _first(verdict, "authority_status") or "shadow_only",
                "applied": False,
            },
            bridge={
                "bridge_decision_id": _first(bridge or {}, "bridge_decision_id"),
                "authority_mode": _first(bridge or {}, "authority_mode"),
                "bridge_action": _first(bridge or {}, "bridge_action"),
                "applied": False if bridge_present else None,
                "no_effect": True if bridge_present else None,
            },
            outcome=_outcome_block(outcome, horizon_sec=horizon_sec, allow_unresolved=allow_unresolved),
            source_refs={
                "decision_id": _first(verdict, "decision_id") or _first(outcome or {}, "decision_id"),
                "rid": _first(verdict, "rid") or _first(outcome or {}, "rid"),
                "lifecycle_id": _first(verdict, "lifecycle_id") or _first(outcome or {}, "lifecycle_id"),
                "order_id": _first(order or {}, "order_id", "client_order_id"),
                "trace_id": _first(verdict, "trace_id") or _first(envelope or {}, "trace_id"),
                "input_paths": input_paths,
            },
            diagnostics={
                "missing_fields": missing_fields,
                "join_quality": join_quality,
                "reason_codes": reason_codes or ["no_outcome_join"],
            },
        )
        built.append(row)
    return built, diagnostics


def write_rows(rows: Sequence[JudgeShadowCalibrationRowV1], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row.model_dump(mode="json"), sort_keys=True) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Judge shadow calibration dataset rows from replay artifacts.")
    parser.add_argument("--judge-verdict-jsonl", action="append", default=[])
    parser.add_argument("--judge-envelope-jsonl", action="append", default=[])
    parser.add_argument("--bridge-decision-jsonl", action="append", default=[])
    parser.add_argument("--trade-lifecycle-jsonl", action="append", default=[])
    parser.add_argument("--order-log-jsonl", action="append", default=[])
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--horizon-sec", type=int, required=True)
    parser.add_argument("--join-mode", choices=["exact", "fuzzy"], default="exact")
    parser.add_argument("--allow-unresolved", action="store_true")
    parser.add_argument("--source-kind", choices=["replay", "testnet", "runtime_shadow", "simulator"], required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        rows, diagnostics = build_shadow_calibration_rows(
            verdict_rows=load_jsonl(Path(path) for path in args.judge_verdict_jsonl),
            envelope_rows=load_jsonl(Path(path) for path in args.judge_envelope_jsonl),
            bridge_rows=load_jsonl(Path(path) for path in args.bridge_decision_jsonl),
            lifecycle_rows=load_jsonl(Path(path) for path in args.trade_lifecycle_jsonl),
            order_rows=load_jsonl(Path(path) for path in args.order_log_jsonl),
            source_kind=args.source_kind,
            horizon_sec=args.horizon_sec,
            join_mode=args.join_mode,
            allow_unresolved=args.allow_unresolved,
        )
        write_rows(rows, Path(args.output_jsonl))
        if diagnostics:
            print(json.dumps({"diagnostics": diagnostics}, sort_keys=True), file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"shadow calibration dataset build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
