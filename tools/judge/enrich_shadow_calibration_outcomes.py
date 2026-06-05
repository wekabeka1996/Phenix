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
)


IDENTITY_KEYS = ("decision_id", "lifecycle_id", "rid", "order_id", "client_order_id")


def load_jsonl(
    paths: Iterable[Path],
    *,
    skip_invalid_json: bool = False,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
                    if not skip_invalid_json:
                        raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
                    if diagnostics is not None:
                        diagnostics.append(
                            {
                                "reason": "invalid_json_line_skipped",
                                "path": path.as_posix(),
                                "line_number": line_number,
                                "error": str(exc),
                            }
                        )
                    continue
                if not isinstance(payload, dict):
                    raise ValueError(f"{path}:{line_number}: row must be an object")
                if isinstance(payload.get("payload"), dict):
                    payload = dict(payload["payload"])
                payload.setdefault("_input_path", path.as_posix())
                rows.append(payload)
    return rows


def load_shadow_rows(path: Path) -> list[JudgeShadowCalibrationRowV1]:
    rows: list[JudgeShadowCalibrationRowV1] = []
    for row in load_jsonl([path]):
        payload = dict(row)
        payload.pop("_input_path", None)
        rows.append(JudgeShadowCalibrationRowV1.model_validate(payload))
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
        metadata = row.get("metadata")
        if isinstance(metadata, Mapping):
            value = metadata.get(key)
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


def _normalize_side(value: Any) -> str | None:
    if value in (None, ""):
        return None
    upper = str(value).strip().upper()
    if upper in {"BUY", "SELL"}:
        return upper
    if upper == "LONG":
        return "BUY"
    if upper == "SHORT":
        return "SELL"
    if upper in {"NONE", "UNKNOWN"}:
        return None
    return None


def _side_from_row(row: Mapping[str, Any]) -> str | None:
    for key in ("candidate_side", "signal_side", "side", "order_side", "trade_side", "intent_side", "direction"):
        side = _normalize_side(row.get(key))
        if side is not None:
            return side
    for nested_key in ("payload_fragment", "metadata", "source_refs"):
        nested = row.get(nested_key)
        if not isinstance(nested, Mapping):
            continue
        for key in ("candidate_side", "signal_side", "side", "order_side", "trade_side", "intent_side", "direction"):
            side = _normalize_side(nested.get(key))
            if side is not None:
                return side
    return None


def _side_source(row: Mapping[str, Any], fallback: str) -> str:
    event = row.get("event_name") or row.get("event_type") or row.get("status")
    if event == "EVT:STRATEGY_SIGNAL_PRODUCED":
        return "critical_journal_strategy_signal"
    if event in {"TRADE_LIFECYCLE_ORDERED", "TRADE_LIFECYCLE_FILLED"} or row.get("status") in {"ORDERED", "FILLED"}:
        return "trade_lifecycle"
    if event in {"ORDER_INTENT", "ORDER_PLACED", "ORDER_FILLED", "DECISION_INTENT_REJECTED"}:
        return "order_log"
    return fallback


def _recover_side(
    row: JudgeShadowCalibrationRowV1,
    *,
    critical_rows: Sequence[Mapping[str, Any]],
    lifecycle_rows: Sequence[Mapping[str, Any]],
    order_rows: Sequence[Mapping[str, Any]],
) -> tuple[str | None, str | None, list[str]]:
    if row.side in {"BUY", "SELL"}:
        return row.side, "shadow_row", ["side_source:shadow_row"]
    identities = _row_identity(row)
    candidates: list[tuple[int, str, str]] = []
    for priority, source_name, rows in (
        (1, "critical_journal", critical_rows),
        (2, "trade_lifecycle", lifecycle_rows),
        (3, "order_log", order_rows),
    ):
        for source_row in rows:
            matched = False
            for key, value in identities.items():
                if _first(source_row, key) == value:
                    matched = True
                    break
            if not matched:
                continue
            side = _side_from_row(source_row)
            if side is not None:
                source = _side_source(source_row, source_name)
                candidates.append((priority, side, source))
    if not candidates:
        return None, None, ["side_unresolved"]
    unique = {side for _, side, _ in candidates}
    if len(unique) > 1:
        conflict_sources = ",".join(
            f"{source}={side}" for _, side, source in sorted(candidates, key=lambda item: (item[0], item[2]))
        )
        return None, None, ["side_conflict", f"side_conflict_sources:{conflict_sources}"]
    best_priority = min(priority for priority, _, _ in candidates)
    best = [(side, source) for priority, side, source in candidates if priority == best_priority]
    side, source = best[0]
    return side, source, [f"side_source:{source}"]


def _terminal_label(row: Mapping[str, Any]) -> str | None:
    value = _first(
        row,
        "event_type",
        "event_name",
        "terminal_status",
        "status",
        "reject_reason_code",
        "close_reason",
    )
    if value not in (None, ""):
        return str(value)
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        value = _first(
            metadata,
            "canonical_event_family",
            "terminal_status",
            "status",
            "reject_reason",
            "deny_reason",
            "close_reason",
        )
        if value not in (None, ""):
            return str(value)
    fragment = row.get("payload_fragment")
    if isinstance(fragment, Mapping):
        value = _first(
            fragment,
            "terminal_state_kind",
            "event_type",
            "event_name",
            "reject_reason",
            "reason_code",
            "close_reason",
        )
        if value not in (None, ""):
            return str(value)
    return None


def _terminal_text(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "event_type",
        "event_name",
        "terminal_status",
        "status",
        "reject_reason_code",
        "close_reason",
        "pnl_status",
    ):
        value = row.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    for nested_key in ("metadata", "payload_fragment"):
        nested = row.get(nested_key)
        if not isinstance(nested, Mapping):
            continue
        for key in (
            "canonical_event_family",
            "terminal_state_kind",
            "reject_reason",
            "deny_reason",
            "reason_code",
            "close_reason",
            "pnl_status",
        ):
            value = nested.get(key)
            if value not in (None, ""):
                parts.append(str(value))
    return " ".join(parts).upper()


def _net_pnl(row: Mapping[str, Any]) -> float | None:
    return _to_float(
        _first(row, "net_pnl_usd", "net_pnl", "net_return_usd", "realized_pnl_net", "realized_net_pnl", "realized_pnl_usd")
    )


def _gross_pnl(row: Mapping[str, Any]) -> float | None:
    metadata = row.get("metadata")
    nested_realized = metadata.get("realized_pnl") if isinstance(metadata, Mapping) else None
    direct = _to_float(_first(row, "gross_pnl_usd", "gross_pnl", "raw_pnl_usd", "realized_pnl_gross"))
    if direct is not None:
        return direct
    return _to_float(nested_realized)


def _is_closed_outcome(row: Mapping[str, Any]) -> bool:
    text = _terminal_text(row)
    if _net_pnl(row) is not None:
        return True
    return any(token in text for token in ("POSITION_CLOSED", "EXECUTED_AND_CLOSED", "CLOSED"))


def _is_no_trade_outcome(row: Mapping[str, Any]) -> bool:
    text = _terminal_text(row)
    if any(token in text for token in ("REJECT", "DENY", "BLOCK", "NO_TRADE", "NOT_APPLICABLE")):
        return True
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("alias_of") == "TRADE_INTENT_REJECTED":
        return True
    return False


def _is_open_or_ordered_outcome(row: Mapping[str, Any]) -> bool:
    text = _terminal_text(row)
    return any(
        token in text
        for token in (
            "ORDER_INTENT",
            "ORDER_PLACED",
            "TRADE_LIFECYCLE_ORDERED",
            "TRADE_LIFECYCLE_FILLED",
            "ORDER_FILLED",
            "ORDER_TIMEOUT",
            "ORDER_CANCELLED",
            "ORDERED",
            "FILLED",
        )
    )


def _outcome_priority(row: Mapping[str, Any]) -> tuple[int, int]:
    ts = _to_int(_first(row, "outcome_ts_ms", "close_ts_ms", "updated_ts_ms", "timestamp", "ts_ms")) or 0
    if _net_pnl(row) is not None:
        return (500, ts)
    if _is_closed_outcome(row):
        return (400, ts)
    if _is_no_trade_outcome(row):
        return (300, ts)
    if _is_open_or_ordered_outcome(row):
        return (200, ts)
    return (100, ts)


def _select_best_outcome(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return dict(sorted(candidates, key=_outcome_priority, reverse=True)[0])


def _index_many(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for key in IDENTITY_KEYS:
            value = _first(row, key)
            if value not in (None, ""):
                index[f"{key}:{value}"].append(dict(row))
    return index


def _row_identity(row: JudgeShadowCalibrationRowV1) -> dict[str, str]:
    refs = row.source_refs
    values = {
        "decision_id": refs.decision_id,
        "lifecycle_id": refs.lifecycle_id,
        "rid": refs.rid,
        "order_id": refs.order_id,
    }
    return {key: str(value) for key, value in values.items() if value not in (None, "")}


def _find_exact(
    row: JudgeShadowCalibrationRowV1,
    outcome_index: Mapping[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str | None]:
    identities = _row_identity(row)
    for key in ("decision_id", "lifecycle_id", "rid", "order_id"):
        value = identities.get(key)
        if value and f"{key}:{value}" in outcome_index:
            return _select_best_outcome(outcome_index[f"{key}:{value}"]), key
    return None, None


def _recover_identity_value(
    row: JudgeShadowCalibrationRowV1,
    outcome_index: Mapping[str, list[dict[str, Any]]],
    key: str,
) -> Any:
    for identity_key, identity_value in _row_identity(row).items():
        for candidate in outcome_index.get(f"{identity_key}:{identity_value}", []):
            value = _first(candidate, key)
            if value not in (None, ""):
                return value
    return None


def _find_fuzzy(
    row: JudgeShadowCalibrationRowV1,
    outcomes: Sequence[Mapping[str, Any]],
    *,
    horizon_sec: int,
) -> dict[str, Any] | None:
    window_ms = horizon_sec * 1000
    candidates: list[tuple[int, dict[str, Any]]] = []
    for outcome in outcomes:
        if _first(outcome, "symbol") != row.symbol:
            continue
        outcome_ts = _to_int(_first(outcome, "outcome_ts_ms", "close_ts_ms", "updated_ts_ms", "ts_ms"))
        if outcome_ts is None or outcome_ts < row.decision_ts_ms:
            continue
        if outcome_ts - row.decision_ts_ms <= window_ms:
            candidates.append((outcome_ts, dict(outcome)))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _outcome_payload(
    row: JudgeShadowCalibrationRowV1,
    outcome: Mapping[str, Any] | None,
    *,
    gross_pnl_fallback: bool,
) -> tuple[dict[str, Any], list[str]]:
    if outcome is None:
        return row.outcome.model_dump(mode="json"), ["no_join"]
    outcome_ts = _to_int(_first(outcome, "outcome_ts_ms", "close_ts_ms", "updated_ts_ms", "timestamp", "ts_ms"))
    if outcome_ts is not None and outcome_ts < row.decision_ts_ms:
        return row.outcome.model_dump(mode="json"), ["outcome_before_decision_rejected"]
    gross = _gross_pnl(outcome)
    net = _net_pnl(outcome)
    terminal_status = _terminal_label(outcome)
    reason_codes: list[str] = []
    if net is None and gross_pnl_fallback and gross is not None:
        net = gross
        reason_codes.append("gross_pnl_fallback_used")
    fees = _to_float(_first(outcome, "fees_usd", "fee_usd", "fee_cost", "fees"))
    if net is None:
        if _is_no_trade_outcome(outcome):
            payload = row.outcome.model_dump(mode="json")
            payload.update(
                {
                    "outcome_status": "NOT_APPLICABLE",
                    "outcome_ts_ms": outcome_ts,
                    "gross_pnl_usd": gross,
                    "net_pnl_usd": None,
                    "fees_usd": fees,
                    "terminal_status": terminal_status,
                }
            )
            reason_codes.append(
                "joined_to_no_entry_no_trade"
                if row.verdict.verdict == "NO_ENTRY"
                else "joined_to_rejected_no_trade"
            )
            return payload, reason_codes
        payload = row.outcome.model_dump(mode="json")
        payload.update(
            {
                "outcome_status": "UNRESOLVED",
                "outcome_ts_ms": outcome_ts,
                "gross_pnl_usd": gross,
                "net_pnl_usd": None,
                "fees_usd": fees,
                "terminal_status": terminal_status,
            }
        )
        if _is_closed_outcome(outcome):
            reason_codes.append("joined_to_closed_missing_net_pnl")
        elif _is_open_or_ordered_outcome(outcome):
            reason_codes.append("joined_to_ordered_missing_close_economics")
        else:
            reason_codes.append("joined_but_no_economics")
        return payload, reason_codes
    reason_codes.append("joined_to_closed_with_net_pnl")
    return (
        {
            "outcome_status": "RESOLVED",
            "outcome_ts_ms": outcome_ts,
            "horizon_sec": _to_int(_first(outcome, "horizon_sec")) or row.outcome.horizon_sec or 1,
            "gross_pnl_usd": gross,
            "net_pnl_usd": net,
            "fees_usd": fees,
            "slippage_usd": _to_float(_first(outcome, "slippage_usd", "slippage_cost")),
            "max_favorable_usd": _to_float(_first(outcome, "max_favorable_usd", "mfe_usd")),
            "max_adverse_usd": _to_float(_first(outcome, "max_adverse_usd", "mae_usd")),
            "terminal_status": terminal_status,
        },
        reason_codes,
    )


def enrich_shadow_rows(
    rows: Sequence[JudgeShadowCalibrationRowV1],
    *,
    lifecycle_rows: Sequence[Mapping[str, Any]] = (),
    order_rows: Sequence[Mapping[str, Any]] = (),
    critical_rows: Sequence[Mapping[str, Any]] = (),
    allow_fuzzy: bool = False,
    horizon_sec: int = 300,
    gross_pnl_fallback: bool = False,
) -> tuple[list[JudgeShadowCalibrationRowV1], list[dict[str, Any]]]:
    outcome_sources = [*lifecycle_rows, *order_rows, *critical_rows]
    index = _index_many(outcome_sources)
    enriched: list[JudgeShadowCalibrationRowV1] = []
    diagnostics: list[dict[str, Any]] = []
    input_paths = sorted(
        {
            str(row.get("_input_path"))
            for row in outcome_sources
            if row.get("_input_path")
        }
    )

    for row in rows:
        outcome, join_key = _find_exact(row, index)
        join_quality = "UNJOINED"
        reason_codes = list(row.diagnostics.reason_codes)
        if outcome is not None:
            join_quality = "RID_EXACT" if join_key == "rid" else "EXACT"
            reason_codes.append(f"joined_by_{join_key}")
        elif allow_fuzzy:
            outcome = _find_fuzzy(row, outcome_sources, horizon_sec=horizon_sec)
            if outcome is not None:
                join_quality = "FUZZY"
                reason_codes.append("joined_by_fuzzy_window")
        else:
            reason_codes.append("outcome_unjoined")

        outcome_block, outcome_reasons = _outcome_payload(
            row,
            outcome,
            gross_pnl_fallback=gross_pnl_fallback,
        )
        reason_codes.extend(outcome_reasons)
        if "outcome_before_decision_rejected" in outcome_reasons:
            join_quality = "UNJOINED"
            diagnostics.append(
                {
                    "row_id": row.row_id,
                    "reason": "future_leakage_outcome_before_decision",
                    "rid": row.source_refs.rid,
                }
            )

        recovered_side, side_source, side_reasons = _recover_side(
            row,
            critical_rows=critical_rows,
            lifecycle_rows=lifecycle_rows,
            order_rows=order_rows,
        )
        reason_codes.extend(side_reasons)

        source_refs = row.source_refs.model_dump(mode="json")
        if outcome is not None and "outcome_before_decision_rejected" not in outcome_reasons:
            for key in ("decision_id", "rid", "lifecycle_id", "order_id"):
                if source_refs.get(key) in (None, ""):
                    source_refs[key] = _first(outcome, key, "client_order_id")
        for key in ("decision_id", "lifecycle_id", "order_id"):
            if source_refs.get(key) in (None, ""):
                source_refs[key] = _recover_identity_value(row, index, key)
        source_refs["input_paths"] = sorted(set([*source_refs.get("input_paths", []), *input_paths]))

        missing_fields = [field for field in row.diagnostics.missing_fields if field != "outcome.net_pnl_usd"]
        if (
            outcome_block.get("net_pnl_usd") is None
            and outcome_block.get("outcome_status") != "NOT_APPLICABLE"
            and "outcome.net_pnl_usd" not in missing_fields
        ):
            missing_fields.append("outcome.net_pnl_usd")
        for field in ("decision_id", "lifecycle_id"):
            name = f"source_refs.{field}"
            if source_refs.get(field) in (None, "") and name not in missing_fields:
                missing_fields.append(name)
            if source_refs.get(field) not in (None, "") and name in missing_fields:
                missing_fields.remove(name)

        payload = row.model_dump(mode="json")
        if recovered_side is not None:
            payload["side"] = recovered_side
        elif "side_conflict" in side_reasons:
            payload["side"] = "UNKNOWN"
        payload["outcome"] = outcome_block
        payload["source_refs"] = source_refs
        payload["diagnostics"] = {
            "missing_fields": missing_fields,
            "join_quality": join_quality,
            "reason_codes": sorted(set(reason_codes)),
        }
        enriched.append(JudgeShadowCalibrationRowV1.model_validate(payload))
    return enriched, diagnostics


def write_rows(rows: Sequence[JudgeShadowCalibrationRowV1], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row.model_dump(mode="json"), sort_keys=True) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich Judge shadow calibration rows with read-only outcome joins.")
    parser.add_argument("--input-shadow-jsonl", required=True)
    parser.add_argument("--trade-lifecycle-jsonl", action="append", default=[])
    parser.add_argument("--order-log-jsonl", action="append", default=[])
    parser.add_argument("--critical-journal-jsonl", action="append", default=[])
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--diagnostics-json")
    parser.add_argument("--allow-fuzzy", action="store_true")
    parser.add_argument("--horizon-sec", type=int, default=300)
    parser.add_argument("--gross-pnl-fallback", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        rows = load_shadow_rows(Path(args.input_shadow_jsonl))
        loader_diagnostics: list[dict[str, Any]] = []
        enriched, diagnostics = enrich_shadow_rows(
            rows,
            lifecycle_rows=load_jsonl(
                (Path(path) for path in args.trade_lifecycle_jsonl),
                skip_invalid_json=True,
                diagnostics=loader_diagnostics,
            ),
            order_rows=load_jsonl(
                (Path(path) for path in args.order_log_jsonl),
                skip_invalid_json=True,
                diagnostics=loader_diagnostics,
            ),
            critical_rows=load_jsonl(
                (Path(path) for path in args.critical_journal_jsonl),
                skip_invalid_json=True,
                diagnostics=loader_diagnostics,
            ),
            allow_fuzzy=args.allow_fuzzy,
            horizon_sec=args.horizon_sec,
            gross_pnl_fallback=args.gross_pnl_fallback,
        )
        diagnostics = [*loader_diagnostics, *diagnostics]
        write_rows(enriched, Path(args.output_jsonl))
        if args.diagnostics_json:
            Path(args.diagnostics_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.diagnostics_json).write_text(
                json.dumps({"diagnostics": diagnostics}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return 0
    except Exception as exc:
        print(f"shadow calibration enrichment failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
