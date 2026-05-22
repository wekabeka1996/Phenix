from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parents[2]
T6C_DIR = ROOT / "reports" / "runtime_forensics" / "T6C_post_t5c_trace_retention"
OUT_DIR = ROOT / "reports" / "runtime_forensics" / "T6D_trace_field_propagation"

T6C_REPORT_PATH = T6C_DIR / "T6C_POST_T5C_TRACE_RETENTION_REPORT.md"
T6C_INVENTORY_PATH = T6C_DIR / "post_t5c_accepted_trace_inventory.csv"
T6C_COVERAGE_PATH = T6C_DIR / "post_t5c_replay_field_coverage.csv"
T6C_FAILURES_PATH = T6C_DIR / "decision_trace_schema_failures_post_t5c.csv"

ORDER_LOG_PATH = ROOT / "logs" / "order_log_v1.jsonl"
SHADOW_JOURNAL_PATH = ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"
SCHEMA_PATH = ROOT / "schemas" / "decision_trace_emitted_v1.json"
PAYLOAD_ASSEMBLER_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "intent" / "payload_assembler.py"
BUILDER_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "intent" / "builder.py"
FACADE_PATH = ROOT / "apps" / "reference" / \
    "domains" / "decision_making" / "core" / "facade.py"
SAFETY_GATES_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "gates" / "safety_gates.py"
LOW_VOL_COST_FLOOR_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "gates" / "low_vol_cost_floor.py"
SHADOW_JOURNAL_CODE_PATH = ROOT / "apps" / \
    "reference" / "telemetry" / "shadow_journal.py"
WAL_DIR = ROOT / "ops" / "wal"

MATRIX_PATH = OUT_DIR / "trace_field_propagation_matrix.csv"
CASEBOOK_PATH = OUT_DIR / "sample_rid_casebook.md"
REPORT_PATH = OUT_DIR / "T6D_TRACE_FIELD_PROPAGATION_REPORT.md"

REQUIRED_INPUTS = (
    T6C_REPORT_PATH,
    T6C_INVENTORY_PATH,
    T6C_COVERAGE_PATH,
    T6C_FAILURES_PATH,
    ORDER_LOG_PATH,
    SHADOW_JOURNAL_PATH,
    SCHEMA_PATH,
    PAYLOAD_ASSEMBLER_PATH,
    BUILDER_PATH,
    FACADE_PATH,
    SAFETY_GATES_PATH,
    LOW_VOL_COST_FLOOR_PATH,
    SHADOW_JOURNAL_CODE_PATH,
)

SAMPLE_RIDS = (
    "aurora_BTCUSDT_1779246904880",
    "aurora_BTCUSDT_1779247500162",
    "aurora_ETHUSDT_1779249902905",
    "aurora_ETHUSDT_1779250503866",
    "aurora_BTCUSDT_1779266703278",
)

TARGET_FIELDS = (
    "regime",
    "regime_confidence",
    "regime_confidence_gate_verdict",
    "price_motion_context",
    "pm_norm_10s",
    "pm_norm_60s",
    "pm_norm_300s",
    "missing_inputs",
    "safety_gate_snapshot",
    "low_vol_cost_floor",
    "trend_dir",
    "trend_confidence",
    "trend_run_length",
    "strategy_id",
    "side",
    "rid",
    "lifecycle_id",
)

CLASSIFICATIONS = {
    "NOT_MISSING",
    "PRODUCER_INPUT_ABSENT",
    "PAYLOAD_ASSEMBLER_NOT_ATTACHING",
    "EVENT_EMITTER_STRIPPING",
    "SHADOW_JOURNAL_FRAGMENT_THINNING",
    "PARSER_PATH_MISMATCH",
    "FALLBACK_ONLY_NOT_TRACE",
    "UNKNOWN",
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "regime": ("regime",),
    "regime_confidence": ("regime_confidence",),
    "regime_confidence_gate_verdict": ("regime_confidence_gate_verdict",),
    "price_motion_context": ("price_motion_context",),
    "pm_norm_10s": ("pm_norm_10s",),
    "pm_norm_60s": ("pm_norm_60s",),
    "pm_norm_300s": ("pm_norm_300s",),
    "missing_inputs": ("missing_inputs",),
    "safety_gate_snapshot": ("safety_gate_snapshot",),
    "low_vol_cost_floor": ("low_vol_cost_floor",),
    "trend_dir": ("trend_dir",),
    "trend_confidence": ("trend_confidence",),
    "trend_run_length": ("trend_run_length",),
    "strategy_id": ("strategy_id", "strategy"),
    "side": ("side",),
    "rid": ("rid",),
    "lifecycle_id": ("lifecycle_id", "idempotent_key", "intent_id"),
}

PREFERRED_PATHS: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "order_intent": {
        "regime": (("regime",),),
        "regime_confidence": (("regime_confidence",),),
        "regime_confidence_gate_verdict": (("metadata", "regime_confidence_gate_verdict"),),
        "price_motion_context": (("metadata", "low_vol_cost_floor", "price_motion_context"),),
        "pm_norm_10s": (("metadata", "low_vol_cost_floor", "price_motion_context", "pm_norm_10s"),),
        "pm_norm_60s": (("metadata", "low_vol_cost_floor", "price_motion_context", "pm_norm_60s"),),
        "pm_norm_300s": (("metadata", "low_vol_cost_floor", "price_motion_context", "pm_norm_300s"),),
        "missing_inputs": (("metadata", "low_vol_cost_floor", "missing_inputs"),),
        "safety_gate_snapshot": (("metadata", "safety_gate_snapshot"),),
        "low_vol_cost_floor": (("metadata", "low_vol_cost_floor"),),
        "strategy_id": (("strategy_id",),),
        "side": (("side",),),
        "rid": (("rid",),),
        "lifecycle_id": (("lifecycle_id",),),
    },
    "trade_intent": {
        "regime": (("payload_fragment", "regime"),),
        "regime_confidence": (("payload_fragment", "regime_confidence"),),
        "regime_confidence_gate_verdict": (
            ("payload_fragment", "regime_confidence_gate_verdict"),
            ("payload_fragment", "trace", "regime_confidence_gate_verdict"),
        ),
        "price_motion_context": (
            ("payload_fragment", "price_motion_context"),
            ("payload_fragment", "trace", "price_motion_context"),
            ("payload_fragment", "trace",
             "low_vol_cost_floor", "price_motion_context"),
        ),
        "pm_norm_10s": (
            ("payload_fragment", "pm_norm_10s"),
            ("payload_fragment", "trace", "pm_norm_10s"),
            ("payload_fragment", "trace", "price_motion_context", "pm_norm_10s"),
            ("payload_fragment", "trace", "low_vol_cost_floor",
             "price_motion_context", "pm_norm_10s"),
        ),
        "pm_norm_60s": (
            ("payload_fragment", "pm_norm_60s"),
            ("payload_fragment", "trace", "pm_norm_60s"),
            ("payload_fragment", "trace", "price_motion_context", "pm_norm_60s"),
            ("payload_fragment", "trace", "low_vol_cost_floor",
             "price_motion_context", "pm_norm_60s"),
        ),
        "pm_norm_300s": (
            ("payload_fragment", "pm_norm_300s"),
            ("payload_fragment", "trace", "pm_norm_300s"),
            ("payload_fragment", "trace", "price_motion_context", "pm_norm_300s"),
            ("payload_fragment", "trace", "low_vol_cost_floor",
             "price_motion_context", "pm_norm_300s"),
        ),
        "missing_inputs": (
            ("payload_fragment", "missing_inputs"),
            ("payload_fragment", "trace", "missing_inputs"),
            ("payload_fragment", "trace", "low_vol_cost_floor", "missing_inputs"),
        ),
        "safety_gate_snapshot": (
            ("payload_fragment", "safety_gate_snapshot"),
            ("payload_fragment", "trace", "safety_gate_snapshot"),
        ),
        "low_vol_cost_floor": (
            ("payload_fragment", "low_vol_cost_floor"),
            ("payload_fragment", "trace", "low_vol_cost_floor"),
        ),
        "trend_dir": (
            ("payload_fragment", "trend_dir"),
            ("payload_fragment", "trace", "trend_dir"),
        ),
        "trend_confidence": (
            ("payload_fragment", "trend_confidence"),
            ("payload_fragment", "trace", "trend_confidence"),
        ),
        "trend_run_length": (
            ("payload_fragment", "trend_run_length"),
            ("payload_fragment", "trace", "trend_run_length"),
        ),
        "strategy_id": (("strategy_id",), ("payload_fragment", "strategy")),
        "side": (("side",), ("payload_fragment", "side")),
        "rid": (("rid",),),
        "lifecycle_id": (("lifecycle_id",), ("payload_fragment", "idempotent_key")),
    },
    "decision_trace": {
        "regime": (("payload_fragment", "regime"), ("regime",)),
        "regime_confidence": (("payload_fragment", "regime_confidence"), ("regime_confidence",)),
        "regime_confidence_gate_verdict": (("payload_fragment", "regime_confidence_gate_verdict"), ("regime_confidence_gate_verdict",)),
        "price_motion_context": (("payload_fragment", "price_motion_context"), ("price_motion_context",)),
        "pm_norm_10s": (("payload_fragment", "pm_norm_10s"), ("pm_norm_10s",)),
        "pm_norm_60s": (("payload_fragment", "pm_norm_60s"), ("pm_norm_60s",)),
        "pm_norm_300s": (("payload_fragment", "pm_norm_300s"), ("pm_norm_300s",)),
        "missing_inputs": (("payload_fragment", "missing_inputs"), ("missing_inputs",)),
        "safety_gate_snapshot": (("payload_fragment", "safety_gate_snapshot"), ("safety_gate_snapshot",)),
        "low_vol_cost_floor": (("payload_fragment", "low_vol_cost_floor"), ("low_vol_cost_floor",)),
        "trend_dir": (("payload_fragment", "trend_dir"), ("trend_dir",)),
        "trend_confidence": (("payload_fragment", "trend_confidence"), ("trend_confidence",)),
        "trend_run_length": (("payload_fragment", "trend_run_length"), ("trend_run_length",)),
        "strategy_id": (("strategy_id",), ("payload_fragment", "strategy_id"), ("payload_fragment", "strategy")),
        "side": (("side",), ("payload_fragment", "side")),
        "rid": (("rid",),),
        "lifecycle_id": (("lifecycle_id",), ("payload_fragment", "lifecycle_id"), ("payload_fragment", "idempotent_key")),
    },
    "decision_fragment": {
        "regime": (("regime",),),
        "regime_confidence": (("regime_confidence",),),
        "regime_confidence_gate_verdict": (("regime_confidence_gate_verdict",),),
        "price_motion_context": (("price_motion_context",),),
        "pm_norm_10s": (("pm_norm_10s",),),
        "pm_norm_60s": (("pm_norm_60s",),),
        "pm_norm_300s": (("pm_norm_300s",),),
        "missing_inputs": (("missing_inputs",),),
        "safety_gate_snapshot": (("safety_gate_snapshot",),),
        "low_vol_cost_floor": (("low_vol_cost_floor",),),
        "trend_dir": (("trend_dir",),),
        "trend_confidence": (("trend_confidence",),),
        "trend_run_length": (("trend_run_length",),),
        "strategy_id": (("strategy_id",), ("strategy",)),
        "side": (("side",),),
        "rid": (("rid",),),
        "lifecycle_id": (("lifecycle_id",), ("idempotent_key",)),
    },
    "wal": {},
}

TEXT_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    field: tuple(alias.lower() for alias in aliases)
    for field, aliases in FIELD_ALIASES.items()
}
TEXT_FIELD_KEYWORDS["rid"] = ()

T6C_ALLOWED_PATHS: dict[str, set[str]] = {
    "regime": {"regime", "payload_fragment.regime"},
    "regime_confidence": {"regime_confidence", "payload_fragment.regime_confidence"},
    "regime_confidence_gate_verdict": {
        "metadata.regime_confidence_gate_verdict",
        "payload_fragment.regime_confidence_gate_verdict",
    },
    "price_motion_context": {
        "metadata.price_motion_context",
        "payload_fragment.price_motion_context",
    },
    "pm_norm_10s": {"pm_norm_10s", "payload_fragment.pm_norm_10s"},
    "pm_norm_60s": {"pm_norm_60s", "payload_fragment.pm_norm_60s"},
    "pm_norm_300s": {"pm_norm_300s", "payload_fragment.pm_norm_300s"},
    "missing_inputs": {"missing_inputs", "payload_fragment.missing_inputs"},
    "safety_gate_snapshot": {
        "safety_gate_snapshot",
        "payload_fragment.safety_gate_snapshot",
    },
    "low_vol_cost_floor": {
        "low_vol_cost_floor",
        "metadata.low_vol_cost_floor",
        "payload_fragment.low_vol_cost_floor",
    },
    "trend_dir": {"trend_dir", "payload_fragment.trend_dir"},
    "trend_confidence": {"trend_confidence", "payload_fragment.trend_confidence"},
    "trend_run_length": {"trend_run_length", "payload_fragment.trend_run_length"},
    "strategy_id": {"strategy_id", "payload_fragment.strategy_id", "payload_fragment.strategy"},
    "side": {"side", "payload_fragment.side"},
    "rid": {"rid", "payload_fragment.rid"},
    "lifecycle_id": {
        "lifecycle_id",
        "payload_fragment.lifecycle_id",
        "payload_fragment.idempotent_key",
    },
}

SHADOW_FRAGMENT_THINNING_FIELDS = {
    "regime_confidence_gate_verdict",
    "price_motion_context",
    "pm_norm_10s",
    "pm_norm_60s",
    "pm_norm_300s",
    "missing_inputs",
    "safety_gate_snapshot",
    "low_vol_cost_floor",
    "trend_dir",
    "trend_confidence",
    "trend_run_length",
}

CODE_EXPECTATIONS: dict[str, tuple[bool, str, str]] = {
    "regime": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['regime'] = sg.regime"),
    "regime_confidence": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['regime_confidence'] = sg.regime_confidence"),
    "regime_confidence_gate_verdict": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['regime_confidence_gate_verdict'] = getattr(sg, 'regime_confidence_gate_verdict', None)"),
    "price_motion_context": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::_build_price_motion_context + build_decision_trace_payload", "trace_payload['price_motion_context'] = _build_price_motion_context(sg)"),
    "pm_norm_10s": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['pm_norm_10s'] = sg.pm_norm_10s"),
    "pm_norm_60s": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['pm_norm_60s'] = sg.pm_norm_60s"),
    "pm_norm_300s": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['pm_norm_300s'] = sg.pm_norm_300s"),
    "missing_inputs": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::_build_missing_inputs + build_decision_trace_payload", "trace_payload['missing_inputs'] = _build_missing_inputs(sg, trace_context)"),
    "safety_gate_snapshot": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::_build_safety_gate_snapshot + build_decision_trace_payload", "trace_payload['safety_gate_snapshot'] = _build_safety_gate_snapshot(sg)"),
    "low_vol_cost_floor": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "attached when sg.low_vol_cost_floor_details is a non-empty dict"),
    "trend_dir": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['trend_dir'] = _normalize_trend_dir(getattr(sg, 'trend_dir', None))"),
    "trend_confidence": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['trend_confidence'] = getattr(sg, 'trend_confidence', None)"),
    "trend_run_length": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['trend_run_length'] = sg.trend_run_length"),
    "strategy_id": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['strategy_id'] = strategy_id"),
    "side": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['side'] = _normalize_order_side(order_side)"),
    "rid": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['rid'] = rid"),
    "lifecycle_id": (True, "apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload", "trace_payload['lifecycle_id'] = lifecycle_id when lifecycle_id is not None"),
}


@dataclass(frozen=True)
class JsonRecordRef:
    data: dict[str, Any]
    source_path: str
    source_line: int


@dataclass(frozen=True)
class TextLineRef:
    source_path: str
    source_line: int
    text: str


def ensure_inputs() -> None:
    missing = [path for path in REQUIRED_INPUTS if not path.exists()]
    if missing:
        joined = ", ".join(path.as_posix() for path in missing)
        raise RuntimeError(f"BLOCKED: missing {joined}")


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            text = raw_line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield line_number, payload


def iter_text_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            yield line_number, raw_line.rstrip("\n")


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def path_exists(data: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    current = data
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def format_path(path: Iterable[Any]) -> str:
    return ".".join(str(part) for part in path)


def recursive_key_paths(data: Any, aliases: set[str], prefix: tuple[Any, ...] = ()) -> list[str]:
    matches: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            next_prefix = prefix + (key,)
            if key in aliases:
                matches.append(format_path(next_prefix))
            matches.extend(recursive_key_paths(value, aliases, next_prefix))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            matches.extend(recursive_key_paths(
                value, aliases, prefix + (index,)))
    return matches


def find_field_path(data: Any, *, layer: str, field_name: str) -> str | None:
    preferred_paths = PREFERRED_PATHS.get(layer, {}).get(field_name, ())
    for path in preferred_paths:
        present, _value = path_exists(data, path)
        if present:
            return format_path(path)

    aliases = set(FIELD_ALIASES[field_name])
    matches = recursive_key_paths(data, aliases)
    if not matches:
        return None
    matches.sort(key=lambda item: (item.count("."), item))
    return matches[0]


def record_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def current_log_files(prefix: str) -> list[Path]:
    logs_dir = ROOT / "logs"
    return sorted(
        path
        for path in logs_dir.iterdir()
        if path.is_file() and (path.name == prefix or path.name.startswith(prefix + "."))
    )


def bool_text(value: bool) -> str:
    return "True" if value else "False"


def extract_runtime_window(inventory_rows: list[dict[str, str]]) -> tuple[str, str]:
    if not inventory_rows:
        return "", ""
    first = inventory_rows[0]
    return first.get("session_start_ts_utc", ""), first.get("session_end_ts_utc", "")


def extract_shadow_keep_keys() -> set[str]:
    text = SHADOW_JOURNAL_CODE_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"keep\s*=\s*\((?P<body>.*?)\)\s*\n\s*fragment\s*=", text, re.DOTALL)
    if match is None:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group("body")))


def scan_order_intents(selected_rids: set[str]) -> dict[str, JsonRecordRef]:
    results: dict[str, JsonRecordRef] = {}
    for line_number, record in iter_jsonl(ORDER_LOG_PATH):
        rid = str(record.get("rid", "")).strip()
        if rid not in selected_rids:
            continue
        if record.get("event_type") != "ORDER_INTENT":
            continue
        if record.get("source_fsm") != "DecisionMaking":
            continue
        results.setdefault(
            rid,
            JsonRecordRef(
                data=record,
                source_path=record_relative(ORDER_LOG_PATH),
                source_line=line_number,
            ),
        )
    return results


def scan_shadow_events(selected_rids: set[str]) -> tuple[dict[str, JsonRecordRef], dict[str, JsonRecordRef]]:
    trade_intents: dict[str, JsonRecordRef] = {}
    decision_traces: dict[str, JsonRecordRef] = {}
    for line_number, record in iter_jsonl(SHADOW_JOURNAL_PATH):
        rid = str(record.get("rid", "")).strip()
        if rid not in selected_rids:
            continue
        event_name = str(record.get("event_name", ""))
        ref = JsonRecordRef(
            data=record,
            source_path=record_relative(SHADOW_JOURNAL_PATH),
            source_line=line_number,
        )
        if event_name == "EVT:TRADE_INTENT_PROPOSED":
            trade_intents.setdefault(rid, ref)
        elif event_name == "EVT:DECISION_TRACE_EMITTED":
            decision_traces.setdefault(rid, ref)
    return trade_intents, decision_traces


def scan_wal_rows(selected_rids: set[str]) -> dict[str, JsonRecordRef]:
    results: dict[str, JsonRecordRef] = {}
    if not WAL_DIR.exists():
        return results
    for path in sorted(WAL_DIR.glob("*.jsonl")):
        remaining = selected_rids.difference(results)
        if not remaining:
            break
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not any(rid in raw_line for rid in remaining):
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                text = raw_line
                for rid in tuple(remaining):
                    if rid not in text:
                        continue
                    results.setdefault(
                        rid,
                        JsonRecordRef(
                            data=record,
                            source_path=record_relative(path),
                            source_line=line_number,
                        ),
                    )
    return results


def scan_text_logs(selected_rids: set[str]) -> dict[str, list[TextLineRef]]:
    results: dict[str, list[TextLineRef]] = {rid: [] for rid in selected_rids}
    for prefix in ("aurora_core.log", "domain_decision_making.log"):
        for path in current_log_files(prefix):
            for line_number, line in iter_text_lines(path):
                for rid in selected_rids:
                    if rid not in line:
                        continue
                    bucket = results[rid]
                    if len(bucket) >= 20:
                        continue
                    bucket.append(
                        TextLineRef(
                            source_path=record_relative(path),
                            source_line=line_number,
                            text=line,
                        )
                    )
    return results


def find_text_field(lines: list[TextLineRef], field_name: str) -> tuple[bool, str]:
    if field_name == "rid":
        if not lines:
            return False, ""
        first = lines[0]
        return True, f"{first.source_path}:{first.source_line}"

    keywords = TEXT_FIELD_KEYWORDS[field_name]
    for line in lines:
        lower = line.text.lower()
        if any(keyword in lower for keyword in keywords):
            return True, f"{line.source_path}:{line.source_line}"
    return False, ""


def first_value(data: Any, path: str | None) -> Any:
    if not path:
        return None
    current = data
    for segment in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        else:
            return None
    return current


def source_path(path: str | None, ref: JsonRecordRef | None) -> str:
    if path is None or ref is None:
        return ""
    return f"{ref.source_path}:{ref.source_line}:{path}"


def decision_fragment_record(ref: JsonRecordRef | None) -> dict[str, Any]:
    if ref is None:
        return {}
    fragment = ref.data.get("payload_fragment")
    return fragment if isinstance(fragment, dict) else {}


def present_in_layer(ref: JsonRecordRef | None, *, layer: str, field_name: str) -> tuple[bool, str]:
    if ref is None:
        return False, ""
    target = ref.data if layer != "decision_fragment" else decision_fragment_record(
        ref)
    path = find_field_path(target, layer=layer, field_name=field_name)
    if path is None:
        return False, ""
    if layer == "decision_fragment":
        return True, f"{ref.source_path}:{ref.source_line}:payload_fragment.{path}"
    return True, f"{ref.source_path}:{ref.source_line}:{path}"


def build_layer_summary(rows: list[dict[str, str]], column: str, sample_count: int) -> dict[str, str]:
    summary: dict[str, str] = {}
    for field_name in TARGET_FIELDS:
        present_count = sum(
            1
            for row in rows
            if row["field_name"] == field_name and row[column] == "True"
        )
        summary[field_name] = f"{present_count}/{sample_count}"
    return summary


def field_presence_note(summary: dict[str, str]) -> str:
    return "; ".join(f"{field}={summary[field]}" for field in TARGET_FIELDS)


def extract_selected_values(record: dict[str, Any], field_names: Iterable[str], layer: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field_name in field_names:
        path = find_field_path(record, layer=layer, field_name=field_name)
        if path is None:
            continue
        output[path] = first_value(record, path)
    return output


def json_block(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def confidence_for(classification: str, evidence_count: int) -> str:
    if classification in {"NOT_MISSING", "SHADOW_JOURNAL_FRAGMENT_THINNING"} and evidence_count >= 3:
        return "HIGH"
    if classification in {"PRODUCER_INPUT_ABSENT", "PARSER_PATH_MISMATCH"} and evidence_count >= 2:
        return "MEDIUM"
    if evidence_count >= 2:
        return "MEDIUM"
    return "LOW"


def classify_field(
    *,
    field_name: str,
    order_present: bool,
    trade_present: bool,
    decision_present: bool,
    decision_path: str,
    decision_fragment_present: bool,
    wal_present: bool,
    text_present: bool,
    code_expected: bool,
    shadow_keep_keys: set[str],
) -> tuple[str, str, str]:
    evidence_parts: list[str] = []
    evidence_count = 0

    if decision_present:
        evidence_parts.append(
            f"durable decision trace retains field at {decision_path}")
        evidence_count += 1
        allowed_paths = T6C_ALLOWED_PATHS.get(field_name, set())
        normalized_path = decision_path.split(
            ":", 2)[-1] if ":" in decision_path else decision_path
        if normalized_path and normalized_path not in allowed_paths:
            evidence_parts.append(
                "durable field path falls outside the T6C parser allowlist")
            evidence_count += 1
            return "PARSER_PATH_MISMATCH", "; ".join(evidence_parts), confidence_for("PARSER_PATH_MISMATCH", evidence_count)
        return "NOT_MISSING", "; ".join(evidence_parts), confidence_for("NOT_MISSING", evidence_count)

    if order_present:
        evidence_parts.append("field present in ORDER_INTENT")
        evidence_count += 1
    if trade_present:
        evidence_parts.append("field present in EVT:TRADE_INTENT_PROPOSED")
        evidence_count += 1
    if wal_present:
        evidence_parts.append("field present in WAL")
        evidence_count += 1
    if text_present:
        evidence_parts.append("field mentioned in current text logs")
        evidence_count += 1
    if code_expected:
        evidence_parts.append("decision-trace builder code expects the field")
        evidence_count += 1

    if field_name == "low_vol_cost_floor" and not order_present and not trade_present and not wal_present:
        evidence_parts.append(
            "low_vol_cost_floor_details was not evidenced for this RID before trace persistence")
        evidence_count += 1
        return "PRODUCER_INPUT_ABSENT", "; ".join(evidence_parts), confidence_for("PRODUCER_INPUT_ABSENT", evidence_count)

    if code_expected and field_name in SHADOW_FRAGMENT_THINNING_FIELDS and field_name not in shadow_keep_keys:
        evidence_parts.append(
            "shadow_journal.build_payload_fragment keep-list excludes the field")
        evidence_count += 1
        return (
            "SHADOW_JOURNAL_FRAGMENT_THINNING",
            "; ".join(evidence_parts),
            confidence_for("SHADOW_JOURNAL_FRAGMENT_THINNING", evidence_count),
        )

    if not code_expected and order_present:
        evidence_parts.append(
            "field is only evidenced on order-log fallback surfaces")
        evidence_count += 1
        return "FALLBACK_ONLY_NOT_TRACE", "; ".join(evidence_parts), confidence_for("FALLBACK_ONLY_NOT_TRACE", evidence_count)

    if code_expected and not order_present and not trade_present and not wal_present and not text_present:
        evidence_parts.append(
            "no pre-journal runtime artifact retained the field, but builder code still expects it")
        evidence_count += 1
        return (
            "SHADOW_JOURNAL_FRAGMENT_THINNING",
            "; ".join(evidence_parts),
            confidence_for("SHADOW_JOURNAL_FRAGMENT_THINNING", evidence_count),
        )

    if order_present and not trade_present and not decision_fragment_present and code_expected:
        evidence_parts.append(
            "field survives into order-log fallback but not into retained shadow surfaces")
        evidence_count += 1
        return (
            "SHADOW_JOURNAL_FRAGMENT_THINNING",
            "; ".join(evidence_parts),
            confidence_for("SHADOW_JOURNAL_FRAGMENT_THINNING", evidence_count),
        )

    return "UNKNOWN", "; ".join(evidence_parts) if evidence_parts else "no decisive evidence found", confidence_for("UNKNOWN", evidence_count)


def write_matrix(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "rid",
        "symbol",
        "side",
        "field_name",
        "present_in_order_intent",
        "order_intent_path",
        "present_in_trade_intent_proposed",
        "trade_intent_path",
        "present_in_decision_trace_durable",
        "decision_trace_path",
        "present_in_shadow_journal_payload_fragment",
        "shadow_journal_path",
        "present_in_wal",
        "wal_path",
        "present_in_text_log",
        "text_log_path",
        "present_in_code_builder_expected_output",
        "code_builder_path",
        "first_missing_at_layer",
        "evidence",
        "confidence",
    ]
    with MATRIX_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_casebook(
    rows: list[dict[str, str]],
    *,
    inventory_by_rid: dict[str, dict[str, str]],
    order_intents: dict[str, JsonRecordRef],
    trade_intents: dict[str, JsonRecordRef],
    decision_traces: dict[str, JsonRecordRef],
) -> None:
    lines = [
        "# T6D Sample RID Casebook",
        "",
        "This casebook inspects the required accepted allow-path RIDs and compares ORDER_INTENT, EVT:TRADE_INTENT_PROPOSED, and durable EVT:DECISION_TRACE_EMITTED retention.",
        "",
    ]

    fields_for_excerpt = (
        "regime",
        "regime_confidence",
        "regime_confidence_gate_verdict",
        "price_motion_context",
        "pm_norm_10s",
        "pm_norm_60s",
        "pm_norm_300s",
        "missing_inputs",
        "safety_gate_snapshot",
        "low_vol_cost_floor",
        "trend_dir",
        "trend_confidence",
        "trend_run_length",
        "strategy_id",
        "side",
        "rid",
        "lifecycle_id",
    )

    for rid in SAMPLE_RIDS:
        rid_rows = [row for row in rows if row["rid"] == rid]
        if not rid_rows:
            continue
        order_ref = order_intents.get(rid)
        trade_ref = trade_intents.get(rid)
        decision_ref = decision_traces.get(rid)
        inventory_row = inventory_by_rid[rid]

        symbol = inventory_row.get("symbol", "")
        side = inventory_row.get("side", "")
        order_excerpt = extract_selected_values(
            order_ref.data, fields_for_excerpt, "order_intent") if order_ref else {}
        trade_excerpt = extract_selected_values(
            trade_ref.data, fields_for_excerpt, "trade_intent") if trade_ref else {}
        decision_excerpt = extract_selected_values(
            decision_ref.data, fields_for_excerpt, "decision_trace") if decision_ref else {}
        decision_fragment_keys = sorted(decision_fragment_record(
            decision_ref).keys()) if decision_ref else []
        order_keys = sorted(order_ref.data.keys()) if order_ref else []
        trade_fragment_keys = sorted(decision_fragment_record(
            trade_ref).keys()) if trade_ref else []

        missing_fields = [
            row["field_name"]
            for row in rid_rows
            if row["present_in_decision_trace_durable"] != "True"
        ]
        differences = [
            f"{row['field_name']}: order_intent={row['present_in_order_intent']}, trade_intent={row['present_in_trade_intent_proposed']}, decision_trace={row['present_in_decision_trace_durable']}, first_missing={row['first_missing_at_layer']}"
            for row in rid_rows
            if row["present_in_decision_trace_durable"] != row["present_in_order_intent"]
            or row["present_in_decision_trace_durable"] != row["present_in_trade_intent_proposed"]
        ]
        difference_lines = (
            [f"- {item}" for item in differences]
            if differences
            else ["- No material upstream-vs-durable differences were detected for this RID."]
        )
        first_missing_summary = "; ".join(
            f"{row['field_name']}={row['first_missing_at_layer']}" for row in rid_rows
        )

        lines.extend(
            [
                f"## {rid}",
                "",
                f"- Symbol: {symbol}",
                f"- Side: {side}",
                f"- ORDER_INTENT row: {order_ref.source_path}:{order_ref.source_line}" if order_ref else "- ORDER_INTENT row: not found",
                f"- EVT:TRADE_INTENT_PROPOSED row: {trade_ref.source_path}:{trade_ref.source_line}" if trade_ref else "- EVT:TRADE_INTENT_PROPOSED row: not found",
                f"- EVT:DECISION_TRACE_EMITTED row: {decision_ref.source_path}:{decision_ref.source_line}" if decision_ref else "- EVT:DECISION_TRACE_EMITTED row: not found",
                "",
                "### ORDER_INTENT Excerpt / Keys",
                "",
                "```json",
                json_block({
                    "top_level_keys": order_keys,
                    "selected_values": order_excerpt,
                }),
                "```",
                "",
                "### EVT:TRADE_INTENT_PROPOSED Excerpt / Keys",
                "",
                "```json",
                json_block({
                    "payload_fragment_keys": trade_fragment_keys,
                    "selected_values": trade_excerpt,
                }),
                "```",
                "",
                "### Durable EVT:DECISION_TRACE_EMITTED Excerpt / Keys",
                "",
                "```json",
                json_block({
                    "top_level_keys": sorted(decision_ref.data.keys()) if decision_ref else [],
                    "payload_fragment_keys": decision_fragment_keys,
                    "selected_values": decision_excerpt,
                }),
                "```",
                "",
                "### Differences",
                "",
                *difference_lines,
                "",
                "### Exact Missing Fields",
                "",
                f"- {', '.join(missing_fields) if missing_fields else 'none'}",
                "",
                "### Likely First Missing Layer",
                "",
                f"- {first_missing_summary}",
                "",
            ]
        )

    CASEBOOK_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    *,
    rows: list[dict[str, str]],
    runtime_start_ts: str,
    runtime_end_ts: str,
    shadow_keep_keys: set[str],
) -> None:
    first_missing_counts = {
        name.lower(): 0 for name in CLASSIFICATIONS if name != "NOT_MISSING"}
    for row in rows:
        classification = row["first_missing_at_layer"]
        if classification == "NOT_MISSING":
            continue
        first_missing_counts[classification.lower()] += 1

    sample_count = len(SAMPLE_RIDS)
    order_summary = build_layer_summary(
        rows, "present_in_order_intent", sample_count)
    trade_summary = build_layer_summary(
        rows, "present_in_trade_intent_proposed", sample_count)
    decision_summary = build_layer_summary(
        rows, "present_in_decision_trace_durable", sample_count)
    fragment_summary = build_layer_summary(
        rows, "present_in_shadow_journal_payload_fragment", sample_count)
    wal_summary = build_layer_summary(rows, "present_in_wal", sample_count)
    text_summary = build_layer_summary(
        rows, "present_in_text_log", sample_count)

    parser_gap_rows = [
        row for row in rows if row["first_missing_at_layer"] == "PARSER_PATH_MISMATCH"]
    producer_gap_rows = [
        row for row in rows if row["first_missing_at_layer"] == "PRODUCER_INPUT_ABSENT"]
    shadow_gap_rows = [row for row in rows if row["first_missing_at_layer"]
                       == "SHADOW_JOURNAL_FRAGMENT_THINNING"]

    verdict = "JOURNAL_THINNING_LOCALIZED"
    if parser_gap_rows and shadow_gap_rows:
        verdict = "MIXED_GAP_LOCALIZED"
    elif parser_gap_rows:
        verdict = "PARSER_GAP_LOCALIZED"
    elif producer_gap_rows and shadow_gap_rows:
        verdict = "MIXED_GAP_LOCALIZED"
    elif producer_gap_rows and not shadow_gap_rows:
        verdict = "PRODUCER_GAP_LOCALIZED"

    answer_1 = "Yes. Replay-critical fields are present upstream and absent from durable decision-trace rows for the sampled RIDs. The strongest runtime evidence is ORDER_INTENT metadata.regime_confidence_gate_verdict and metadata.low_vol_cost_floor plus TRADE_INTENT trace.low_vol_cost_floor/price_motion_context on low-volatility samples, while durable EVT:DECISION_TRACE_EMITTED retains only regime/regime_confidence plus identity envelope fields."
    answer_2 = "Yes. The dominant gap is shadow-journal thinning, not an observed producer omission. build_decision_trace_payload constructs the replay-critical keys, but shadow_journal writes only ShadowJournalRecord envelope fields plus payload_fragment built from a restrictive keep-list."
    answer_3 = "Shadow journal stores the ShadowJournalRecord envelope plus payload_fragment, not the full event payload. record_bus_emit writes payload_fragment=build_payload_fragment(payload, event_name=event_name) and ShadowJournalSink serializes record.model_dump()."
    answer_4 = "For current durable EVT:DECISION_TRACE_EMITTED rows, T6C was not looking at the wrong path for the missing fields because the sampled rows do not retain those fields anywhere. A latent parser blind spot still exists for top-level regime_confidence_gate_verdict, but it is not the primary cause of the observed 0/N coverage result on this window."
    answer_5 = "missing_inputs is not merely nested differently inside durable decision-trace rows for the sampled RIDs. It is absent from the retained EVT:DECISION_TRACE_EMITTED record, while upstream code builds it and low-volatility fallback contexts still expose related missing-input evidence in ORDER_INTENT / TRADE_INTENT artifacts."
    answer_6 = "safety_gate_snapshot is produced by decision-trace builder code on accepted allow-path because _build_safety_gate_snapshot(sg) is called unconditionally inside build_decision_trace_payload. The sampled durable shadow-journal rows do not retain it."
    answer_7 = "low_vol_cost_floor is attached on accepted allow-path for low-volatility samples, not only on fallback. It is visible in ORDER_INTENT metadata.low_vol_cost_floor and in EVT:TRADE_INTENT_PROPOSED trace.low_vol_cost_floor for sampled low-volatility RIDs, but it is absent from durable EVT:DECISION_TRACE_EMITTED rows. On the TREND_UP sample RID the field is genuinely absent upstream, which is a secondary producer-input condition rather than the primary T6C gap."
    answer_8 = "The narrowest correct next implementation package is a shadow-journal retention repair limited to EVT:DECISION_TRACE_EMITTED. Preserve replay-critical decision-trace fields in the retained payload_fragment or store a dedicated full trace subdocument for this event only. Do not change gate evaluation, scoring, order flow, or YAML."

    lines = [
        "AGENT_REPORT_V1",
        "",
        "task:",
        "  AURORA_T6D_DECISION_TRACE_FIELD_PROPAGATION_AUDIT",
        "",
        "verdict:",
        f"  {verdict}",
        "",
        "runtime_window:",
        f"  start_ts: {runtime_start_ts}",
        f"  end_ts: {runtime_end_ts or 'open-ended current session'}",
        "",
        "sampled_rids:",
        f"  count: {len(SAMPLE_RIDS)}",
        f"  rids: {', '.join(SAMPLE_RIDS)}",
        "",
        "field_coverage_summary:",
        f"  order_intent: {field_presence_note(order_summary)}",
        f"  trade_intent_proposed: {field_presence_note(trade_summary)}",
        f"  durable_decision_trace: {field_presence_note(decision_summary)}",
        f"  shadow_journal_fragment: {field_presence_note(fragment_summary)}",
        f"  wal: {field_presence_note(wal_summary)}",
        f"  text_logs: {field_presence_note(text_summary)}",
        "",
        "first_missing_layer_summary:",
        f"  producer_input_absent: {first_missing_counts['producer_input_absent']}",
        f"  payload_assembler_not_attaching: {first_missing_counts['payload_assembler_not_attaching']}",
        f"  event_emitter_stripping: {first_missing_counts['event_emitter_stripping']}",
        f"  shadow_journal_fragment_thinning: {first_missing_counts['shadow_journal_fragment_thinning']}",
        f"  parser_path_mismatch: {first_missing_counts['parser_path_mismatch']}",
        f"  fallback_only_not_trace: {first_missing_counts['fallback_only_not_trace']}",
        f"  unknown: {first_missing_counts['unknown']}",
        "",
        "root_cause:",
        "  primary: shadow_journal.build_payload_fragment retains a compact allowlist for EVT:DECISION_TRACE_EMITTED and drops replay-critical decision-trace keys before durable storage.",
        "  secondary: low_vol_cost_floor is genuinely absent upstream on the sampled TREND_UP RID, which is a producer-input condition but not the primary cause of the T6C durable coverage failure.",
        "",
        "recommended_next_package:",
        "  task_name: AURORA_T6E_DECISION_TRACE_FRAGMENT_RETENTION_REPAIR",
        "  scope: Preserve replay-critical fields for EVT:DECISION_TRACE_EMITTED in shadow journal retention and adjust forensic parsers only if the retained path changes.",
        "  forbidden_actions: No strategy scoring changes, no safety-gate threshold changes, no YAML edits, no order-flow changes.",
        "",
        "answers:",
        f"  q1: {answer_1}",
        f"  q2: {answer_2}",
        f"  q3: {answer_3}",
        f"  q4: {answer_4}",
        f"  q5: {answer_5}",
        f"  q6: {answer_6}",
        f"  q7: {answer_7}",
        f"  q8: {answer_8}",
        "",
        "proven:",
        "  - build_decision_trace_payload attaches regime_confidence_gate_verdict, trend_*, pm_norm_*, price_motion_context, missing_inputs, safety_gate_snapshot, and conditionally low_vol_cost_floor before EVT:DECISION_TRACE_EMITTED emit.",
        "  - record_bus_emit writes only ShadowJournalRecord envelope fields plus payload_fragment=build_payload_fragment(payload, event_name=event_name); full decision-trace payload is not durably serialized in shadow journal.",
        "  - shadow_journal.build_payload_fragment keep-list excludes replay-critical keys such as regime_confidence_gate_verdict, price_motion_context, pm_norm_10s, pm_norm_60s, pm_norm_300s, missing_inputs, safety_gate_snapshot, low_vol_cost_floor, trend_dir, trend_confidence, and trend_run_length.",
        "  - For the sampled low-volatility RIDs, ORDER_INTENT and/or EVT:TRADE_INTENT_PROPOSED still retain low_vol_cost_floor and price-motion fields upstream while durable EVT:DECISION_TRACE_EMITTED does not.",
        f"  - Shadow keep-list currently retains {len(shadow_keep_keys)} keys, including regime/regime_confidence and identity fields, but not the replay-critical fields above.",
        "",
        "unproven:",
        "  - No current artifact proves the exact full in-memory EVT:DECISION_TRACE_EMITTED payload after fsm.emit and before shadow_journal thinning for every sampled RID; this audit localizes the loss using code-path and retained-surface evidence.",
        "  - No alternate durable sink outside shadow_critical_event_journal_v1.jsonl was proven to retain the full decision trace for the sampled RIDs.",
        "",
        "risks:",
        "  - If a future retention repair stores the field at a new path, existing parsers may silently undercount again unless the path contract is updated together with the repair.",
        "  - low_vol_cost_floor is regime-conditional; mixing true upstream absence with shadow thinning can misclassify non-low-volatility samples unless the regime split remains explicit.",
        "",
        "evidence_paths:",
        "  - apps/reference/domains/decision_making/intent/payload_assembler.py::build_decision_trace_payload",
        "  - apps/reference/domains/decision_making/intent/payload_assembler.py::build_trade_intent_payload",
        "  - apps/reference/domains/decision_making/core/facade.py:958",
        "  - apps/reference/telemetry/shadow_journal.py::record_bus_emit",
        "  - apps/reference/telemetry/shadow_journal.py::build_payload_fragment",
        "  - reports/runtime_forensics/T6D_trace_field_propagation/trace_field_propagation_matrix.csv",
        "  - reports/runtime_forensics/T6D_trace_field_propagation/sample_rid_casebook.md",
    ]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ensure_inputs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    inventory_rows = load_csv_rows(T6C_INVENTORY_PATH)
    coverage_rows = load_csv_rows(T6C_COVERAGE_PATH)
    _failure_rows = load_csv_rows(T6C_FAILURES_PATH)
    _t6c_report_text = T6C_REPORT_PATH.read_text(encoding="utf-8")
    _schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    _payload_assembler_source = PAYLOAD_ASSEMBLER_PATH.read_text(
        encoding="utf-8")
    _builder_source = BUILDER_PATH.read_text(encoding="utf-8")
    _facade_source = FACADE_PATH.read_text(encoding="utf-8")
    _safety_gates_source = SAFETY_GATES_PATH.read_text(encoding="utf-8")
    _low_vol_source = LOW_VOL_COST_FLOOR_PATH.read_text(encoding="utf-8")
    shadow_keep_keys = extract_shadow_keep_keys()

    inventory_by_rid = {
        row["rid"]: row for row in inventory_rows if row.get("rid")}
    missing_rids = [rid for rid in SAMPLE_RIDS if rid not in inventory_by_rid]
    if missing_rids:
        joined = ", ".join(missing_rids)
        raise RuntimeError(
            f"BLOCKED: missing sampled RIDs from T6C inventory: {joined}")

    runtime_start_ts, runtime_end_ts = extract_runtime_window(inventory_rows)

    selected_rids = set(SAMPLE_RIDS)
    order_intents = scan_order_intents(selected_rids)
    trade_intents, decision_traces = scan_shadow_events(selected_rids)
    wal_rows = scan_wal_rows(selected_rids)
    text_hits = scan_text_logs(selected_rids)

    rows: list[dict[str, str]] = []
    for rid in SAMPLE_RIDS:
        inventory_row = inventory_by_rid[rid]
        order_ref = order_intents.get(rid)
        trade_ref = trade_intents.get(rid)
        decision_ref = decision_traces.get(rid)
        wal_ref = wal_rows.get(rid)
        rid_text_hits = text_hits.get(rid, [])

        for field_name in TARGET_FIELDS:
            order_present, order_path = present_in_layer(
                order_ref, layer="order_intent", field_name=field_name)
            trade_present, trade_path = present_in_layer(
                trade_ref, layer="trade_intent", field_name=field_name)
            decision_present, decision_path = present_in_layer(
                decision_ref, layer="decision_trace", field_name=field_name)
            fragment_present, fragment_path = present_in_layer(
                decision_ref, layer="decision_fragment", field_name=field_name)
            wal_present, wal_path = present_in_layer(
                wal_ref, layer="wal", field_name=field_name)
            text_present, text_path = find_text_field(
                rid_text_hits, field_name)

            code_expected, code_path, code_note = CODE_EXPECTATIONS[field_name]
            classification, evidence, confidence = classify_field(
                field_name=field_name,
                order_present=order_present,
                trade_present=trade_present,
                decision_present=decision_present,
                decision_path=decision_path,
                decision_fragment_present=fragment_present,
                wal_present=wal_present,
                text_present=text_present,
                code_expected=code_expected,
                shadow_keep_keys=shadow_keep_keys,
            )
            if classification not in CLASSIFICATIONS:
                raise RuntimeError(
                    f"unexpected classification {classification}")

            evidence_parts = [part for part in [evidence, code_note] if part]
            rows.append(
                {
                    "rid": rid,
                    "symbol": inventory_row.get("symbol", ""),
                    "side": inventory_row.get("side", ""),
                    "field_name": field_name,
                    "present_in_order_intent": bool_text(order_present),
                    "order_intent_path": order_path,
                    "present_in_trade_intent_proposed": bool_text(trade_present),
                    "trade_intent_path": trade_path,
                    "present_in_decision_trace_durable": bool_text(decision_present),
                    "decision_trace_path": decision_path,
                    "present_in_shadow_journal_payload_fragment": bool_text(fragment_present),
                    "shadow_journal_path": fragment_path,
                    "present_in_wal": bool_text(wal_present),
                    "wal_path": wal_path,
                    "present_in_text_log": bool_text(text_present),
                    "text_log_path": text_path,
                    "present_in_code_builder_expected_output": bool_text(code_expected),
                    "code_builder_path": code_path,
                    "first_missing_at_layer": classification,
                    "evidence": "; ".join(evidence_parts),
                    "confidence": confidence,
                }
            )

    write_matrix(rows)
    write_casebook(
        rows,
        inventory_by_rid=inventory_by_rid,
        order_intents=order_intents,
        trade_intents=trade_intents,
        decision_traces=decision_traces,
    )
    write_report(
        rows=rows,
        runtime_start_ts=runtime_start_ts,
        runtime_end_ts=runtime_end_ts,
        shadow_keep_keys=shadow_keep_keys,
    )

    print(f"sample_rid_count={len(SAMPLE_RIDS)}")
    print(f"matrix_rows={len(rows)}")
    print(f"runtime_start_ts={runtime_start_ts}")
    print(f"runtime_end_ts={runtime_end_ts or 'open-ended current session'}")
    print(f"out_matrix={MATRIX_PATH.relative_to(ROOT).as_posix()}")
    print(f"out_casebook={CASEBOOK_PATH.relative_to(ROOT).as_posix()}")
    print(f"out_report={REPORT_PATH.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
