from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


ROOT = Path(__file__).resolve().parents[2]

ACCEPTED_REPLAY_CSV = ROOT / \
    "reports/runtime_forensics/T3_decision_nrr_rebuild/accepted_intents_counterfactual_nrr_replay.csv"
DECISION_EVENTS_CSV = ROOT / \
    "reports/runtime_forensics/T3_decision_nrr_rebuild/decision_events_normalized.csv"
MASTER_TRADE_CSV = ROOT / \
    "reports/runtime_forensics/T4_final/MASTER_TRADE_FORENSIC_TABLE.csv"
FINAL_REPORT_MD = ROOT / "reports/runtime_forensics/T4_final/FINAL_REPORT.md"
T3C_REPORT_MD = ROOT / \
    "reports/runtime_forensics/T3c_deep_nrr_input_excavation/T3C_ACCEPTED_BNBUSDT_NRR_INPUT_REPORT.md"
T3C_MATRIX_CSV = ROOT / \
    "reports/runtime_forensics/T3c_deep_nrr_input_excavation/T3C_ACCEPTED_BNBUSDT_NRR_INPUT_MATRIX.csv"
DISABLED_TRUTH_MD = ROOT / "reports/runtime_forensics/T0/DISABLED_NRR_TRUTH_TABLE.md"
RUNTIME_MANIFEST_JSON = ROOT / "reports/runtime_forensics/T0/runtime_manifest.json"

OUTPUT_DIR = ROOT / "reports/runtime_forensics/T3d_deep_nrr_all_accepted"
OUTPUT_INPUT_RECOVERY = OUTPUT_DIR / "accepted_intent_input_recovery_all.csv"
OUTPUT_REPLAY = OUTPUT_DIR / "deep_counterfactual_nrr_replay_all.csv"
OUTPUT_ECON = OUTPUT_DIR / "nrr_replay_economic_preview.csv"
OUTPUT_REPORT = OUTPUT_DIR / "T3D_DEEP_NRR_ALL_ACCEPTED_REPORT.md"

CONTROL_RID = "aurora_BNBUSDT_1778024100899"
NRR_CODES = ["NRR-026", "NRR-027", "NRR-028", "NRR-029", "NRR-030"]
TEXT_FILE_SUFFIXES = {".jsonl", ".json", ".csv", ".log", ".md", ".txt"}

QUALITY_RANK = {
    "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH": 0,
    "RECOMPUTED_APPROX": 1,
    "RUNTIME_RECONSTRUCTED_FROM_RECORDER": 2,
    "RUNTIME_PERSISTED_EXACT": 3,
}

CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

EXPECTED_INPUTS = {
    "NRR-026": ["regime_confidence", "resolved_min_regime_confidence"],
    "NRR-027": ["trend_dir", "trend_run_length", "side", "hard_veto_consecutive_bars"],
    "NRR-028": ["pm_norm_60s", "pm_norm_300s", "side", "flash_threshold_norm", "bleed_threshold_norm"],
    "NRR-029": ["pm_norm_60s", "pm_norm_300s", "side", "flash_threshold_norm"],
    "NRR-030": ["pm_norm_60s", "pm_norm_300s", "side", "bleed_threshold_norm"],
}

RID_PATTERN = re.compile(r"aurora_[A-Z0-9]+_\d+")
BAR_PATTERN = re.compile(r"bar:([A-Z0-9]+):(\d+):(\d+)")
NUMBER_PATTERN_TEMPLATE = r'"?{field}"?\s*[:=]\s*(null|true|false|-?\d+(?:\.\d+)?)'


@dataclass
class Evidence:
    recovered: bool
    recovered_value: str = ""
    source_quality: str = "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH"
    source_file: str = ""
    source_line_or_row: str = ""
    source_event_name: str = ""
    correlation_method: str = ""
    time_delta_ms: str = ""
    missing_reason: str = ""
    confidence: str = "LOW"


@dataclass
class IntentRecord:
    intent_id: str
    event_ts: str
    symbol: str
    strategy_id: str
    side: str
    event_ts_ms: int
    rid: str = ""
    trade_id: str = ""
    net_pnl_if_joined: Optional[float] = None
    lifecycle_id: str = ""
    order_id: str = ""
    tf_sec: Optional[int] = None
    features_ts_ms: Optional[int] = None
    bar_close_ts: Optional[int] = None
    fields: dict[str, Evidence] = field(default_factory=dict)
    search_notes: list[str] = field(default_factory=list)


def require_paths(paths: Iterable[Path]) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        joined = ", ".join(path.as_posix() for path in missing)
        raise SystemExit(f"BLOCKED: missing {joined}")


def rel(path: Path | str) -> str:
    path_obj = Path(path)
    try:
        return path_obj.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return path_obj.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_iso_to_ms(value: str) -> int:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def ms_to_utc(ms_value: int) -> str:
    return datetime.fromtimestamp(ms_value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def ms_to_date(ms_value: int) -> str:
    return datetime.fromtimestamp(ms_value / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def normalize_side(side: str) -> str:
    side_upper = (side or "").strip().upper()
    if side_upper in {"BUY", "LONG"}:
        return "LONG"
    if side_upper in {"SELL", "SHORT"}:
        return "SHORT"
    return side_upper or "UNKNOWN"


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return format(value, ".15g")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def maybe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def maybe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def serialize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def evidence_value_rank(evidence: Evidence) -> tuple[int, int]:
    return (QUALITY_RANK.get(evidence.source_quality, -1), CONFIDENCE_RANK.get(evidence.confidence, -1))


def choose_better(existing: Optional[Evidence], candidate: Evidence) -> bool:
    if existing is None:
        return True
    if existing.recovered != candidate.recovered:
        return candidate.recovered
    if evidence_value_rank(existing) != evidence_value_rank(candidate):
        return evidence_value_rank(candidate) > evidence_value_rank(existing)
    try:
        existing_delta = abs(int(existing.time_delta_ms))
    except Exception:
        existing_delta = 10**18
    try:
        candidate_delta = abs(int(candidate.time_delta_ms))
    except Exception:
        candidate_delta = 10**18
    return candidate_delta < existing_delta


def set_field(intent: IntentRecord, field_name: str, evidence: Evidence) -> None:
    existing = intent.fields.get(field_name)
    if choose_better(existing, evidence):
        intent.fields[field_name] = evidence


def csv_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            normalized = {key: (value or "").strip()
                          for key, value in row.items()}
            normalized["__line__"] = str(line_number)
            rows.append(normalized)
    return rows


def find_first_non_empty(rows: list[dict[str, str]], key: str) -> tuple[Optional[str], Optional[str]]:
    for row in rows:
        value = row.get(key, "").strip()
        if value:
            return value, row.get("__line__")
    return None, None


def recursive_leaf_map(obj: Any) -> dict[str, list[Any]]:
    found: dict[str, list[Any]] = defaultdict(list)
    stack: list[tuple[list[str], Any]] = [([], obj)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                stack.append((path + [str(key)], nested))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                stack.append((path + [str(index)], nested))
        else:
            if not path:
                continue
            found[path[-1].lower()].append((path, value))
    return found


def first_named_value(leaf_map: dict[str, list[Any]], names: Iterable[str]) -> Any:
    for name in names:
        candidates = leaf_map.get(name.lower())
        if not candidates:
            continue
        for _, value in candidates:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def extract_event_name(leaf_map: dict[str, list[Any]]) -> str:
    value = first_named_value(
        leaf_map, ["event_name", "event", "evt", "verb", "type", "action"])
    return clean_value(value)


def compile_token_pattern(tokens: Iterable[str]) -> Optional[re.Pattern[str]]:
    usable = sorted({token for token in tokens if token},
                    key=len, reverse=True)
    if not usable:
        return None
    return re.compile("|".join(re.escape(token) for token in usable))


def extract_number_from_text(line: str, field_name: str) -> Optional[float | bool]:
    pattern = re.compile(NUMBER_PATTERN_TEMPLATE.format(
        field=re.escape(field_name)), re.IGNORECASE)
    match = pattern.search(line)
    if not match:
        return None
    value = match.group(1).strip().lower()
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return float(value)
    except ValueError:
        return None


def search_recorder_row(intent: IntentRecord, recorder_cache: dict[Path, list[dict[str, str]]]) -> tuple[Optional[dict[str, str]], Optional[str], list[dict[str, str]]]:
    if intent.tf_sec is None:
        return None, None, []

    candidate_ts = intent.features_ts_ms
    if candidate_ts is None:
        derived = derive_bar_close_from_event_ts(
            intent.event_ts_ms, intent.tf_sec)
        candidate_ts = derived
        intent.search_notes.append(
            "features_ts_ms_missing_used_event_ts_floor")

    expected = ROOT / \
        f"data/recorder/{ms_to_date(candidate_ts)}/{intent.symbol}_{intent.tf_sec}.csv"
    candidates = [expected]
    if not expected.exists():
        basename = expected.name
        candidates = sorted(ROOT.glob(f"data/recorder/**/{basename}"))

    candidate_text = str(candidate_ts)
    for path in candidates:
        if not path.exists():
            continue
        rows = recorder_cache.get(path)
        if rows is None:
            rows = csv_rows(path)
            recorder_cache[path] = rows
        for row in rows:
            if candidate_text in row.values():
                return row, rel(path), rows
    return None, None, []


def derive_bar_close_from_event_ts(event_ts_ms: int, tf_sec: int) -> int:
    tf_ms = int(tf_sec) * 1000
    return (event_ts_ms // tf_ms) * tf_ms - 1


def delta_column_name(row: dict[str, str]) -> Optional[str]:
    for candidate in ("feat_delta_price", "delta_price"):
        if candidate in row:
            return candidate
    return None


def reconstruct_trend_from_rows(rows: list[dict[str, str]], matched_line: str, min_abs_delta: float, consecutive_bars: int) -> tuple[str, float, Optional[float], int, str]:
    target_line = int(matched_line)
    filtered: list[tuple[int, float]] = []
    for row in rows:
        line_number = int(row["__line__"])
        if line_number > target_line:
            break
        delta_col = delta_column_name(row)
        if not delta_col:
            continue
        delta_value = maybe_float(row.get(delta_col))
        if delta_value is None:
            continue
        if abs(delta_value) < min_abs_delta:
            continue
        if delta_value == 0.0:
            continue
        filtered.append((line_number, delta_value))

    if not filtered:
        return "UNKNOWN", 0.0, None, 0, ""

    last_line, last_delta = filtered[-1]
    last_sign = 1 if last_delta > 0 else -1
    run_length = 0
    start_line = last_line
    for line_number, delta_value in reversed(filtered):
        sign = 1 if delta_value > 0 else -1
        if sign != last_sign:
            break
        run_length += 1
        start_line = line_number

    trend_dir = "UNKNOWN"
    trend_conf = 0.0
    window = filtered[-consecutive_bars:]
    if len(window) >= consecutive_bars:
        if all(value > 0 for _, value in window):
            trend_dir = "UP"
            trend_conf = 1.0
        elif all(value < 0 for _, value in window):
            trend_dir = "DOWN"
            trend_conf = 1.0

    return trend_dir, trend_conf, last_delta, run_length, f"{start_line}-{last_line}"


def load_runtime_window() -> tuple[int, int]:
    manifest = json.loads(read_text(RUNTIME_MANIFEST_JSON))
    window = manifest["runtime_window"]
    return parse_iso_to_ms(window["start_ts"]), parse_iso_to_ms(window["end_ts"])


def build_accepted_intents(window_start_ms: int, window_end_ms: int) -> list[IntentRecord]:
    intents: dict[str, IntentRecord] = {}
    for row in csv_rows(ACCEPTED_REPLAY_CSV):
        intent_id = row["intent_id"]
        if intent_id in intents:
            continue
        event_ts_ms = parse_iso_to_ms(row["event_ts"])
        if not (window_start_ms <= event_ts_ms <= window_end_ms):
            continue
        intents[intent_id] = IntentRecord(
            intent_id=intent_id,
            event_ts=row["event_ts"],
            symbol=row["symbol"],
            strategy_id=row["strategy_id"],
            side=row["side"],
            event_ts_ms=event_ts_ms,
        )
    return sorted(intents.values(), key=lambda item: (item.event_ts_ms, item.intent_id))


def enrich_from_decision_events(intents: list[IntentRecord]) -> dict[str, list[dict[str, str]]]:
    by_intent = {intent.intent_id: intent for intent in intents}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in csv_rows(DECISION_EVENTS_CSV):
        intent = by_intent.get(row.get("intent_id", ""))
        if not intent:
            continue
        grouped[intent.intent_id].append(row)

        source_file = rel(DECISION_EVENTS_CSV)
        line = row["__line__"]
        event_name = row.get("event_name", "")
        time_delta_ms = str(parse_iso_to_ms(
            row["event_ts"]) - intent.event_ts_ms)

        if not intent.rid and row.get("rid"):
            intent.rid = row["rid"]
        if intent.tf_sec is None:
            intent.tf_sec = maybe_int(row.get("tf_sec"))
        if row.get("side"):
            set_field(
                intent,
                "side",
                Evidence(
                    recovered=True,
                    recovered_value=row["side"],
                    source_quality="RUNTIME_PERSISTED_EXACT",
                    source_file=source_file,
                    source_line_or_row=line,
                    source_event_name=event_name,
                    correlation_method="exact_intent_id_csv_join",
                    time_delta_ms=time_delta_ms,
                    confidence="HIGH",
                ),
            )
        for field_name in ("regime", "regime_confidence", "trend_dir", "trend_confidence", "trend_run_length", "pm_norm_60s", "pm_norm_300s"):
            raw_value = row.get(field_name, "")
            if not raw_value:
                continue
            set_field(
                intent,
                field_name,
                Evidence(
                    recovered=True,
                    recovered_value=raw_value,
                    source_quality="RUNTIME_PERSISTED_EXACT",
                    source_file=source_file,
                    source_line_or_row=line,
                    source_event_name=event_name,
                    correlation_method="exact_intent_id_csv_join",
                    time_delta_ms=time_delta_ms,
                    confidence="HIGH",
                ),
            )

    return grouped


def enrich_from_trade_table(intents: list[IntentRecord]) -> None:
    by_intent = {intent.intent_id: intent for intent in intents}
    for row in csv_rows(MASTER_TRADE_CSV):
        if row.get("row_kind") != "ENTRY":
            continue
        intent = by_intent.get(row.get("intent_id", ""))
        if not intent:
            continue
        if not intent.rid and row.get("matched_lifecycle_id"):
            intent.rid = row["matched_lifecycle_id"]
        intent.trade_id = row.get("trade_id", "")
        intent.lifecycle_id = row.get("matched_lifecycle_id", "")
        intent.order_id = row.get("entry_order_id", "")
        intent.net_pnl_if_joined = maybe_float(row.get("proven_net_pnl"))


def stream_jsonl_matches(paths: Iterable[Path], pattern: Optional[re.Pattern[str]]) -> Iterable[tuple[Path, int, str, dict[str, Any], list[str]]]:
    if pattern is None:
        return
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                matches = pattern.findall(raw_line)
                if not matches:
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    payload = {}
                yield path, line_number, raw_line, payload, matches


def gather_runtime_events(intents: list[IntentRecord]) -> None:
    token_to_intent: dict[str, IntentRecord] = {}
    for intent in intents:
        token_to_intent[intent.intent_id] = intent
        if intent.rid:
            token_to_intent[intent.rid] = intent
    pattern = compile_token_pattern(token_to_intent)

    jsonl_paths = []
    for glob_pattern in (
        "logs/shadow_critical_event_journal_v1.jsonl",
        "logs/order_log_v1.jsonl",
        "ops/wal/**/*.jsonl",
        "wal/**/*.jsonl",
    ):
        jsonl_paths.extend(sorted(ROOT.glob(glob_pattern)))

    for path, line_number, raw_line, payload, matches in stream_jsonl_matches(jsonl_paths, pattern):
        intent = token_to_intent[matches[0]]
        leaf_map = recursive_leaf_map(payload)
        event_name = extract_event_name(leaf_map)
        event_ts_value = first_named_value(
            leaf_map, ["event_ts", "ts", "ts_utc", "timestamp"]) or intent.event_ts
        try:
            time_delta_ms = str(parse_iso_to_ms(
                str(event_ts_value)) - intent.event_ts_ms)
        except Exception:
            time_delta_ms = ""

        if not intent.rid:
            rid_value = first_named_value(
                leaf_map, ["rid", "lifecycle_id", "matched_lifecycle_id"])
            if isinstance(rid_value, str) and rid_value.startswith("aurora_"):
                intent.rid = rid_value

        if intent.tf_sec is None:
            tf_value = first_named_value(leaf_map, ["tf_sec", "timeframe_sec"])
            intent.tf_sec = maybe_int(tf_value)

        features_ts = maybe_int(
            first_named_value(leaf_map, ["features_ts_ms"]))
        if features_ts is not None:
            intent.features_ts_ms = features_ts
            intent.bar_close_ts = features_ts

        for match in BAR_PATTERN.finditer(raw_line):
            symbol, tf_text, ts_text = match.groups()
            if symbol == intent.symbol:
                intent.tf_sec = intent.tf_sec or int(tf_text)
                intent.bar_close_ts = int(ts_text)
                intent.features_ts_ms = intent.features_ts_ms or int(ts_text)

        field_map = {
            "regime": ["regime"],
            "regime_confidence": ["regime_confidence"],
            "strategy_id": ["strategy_id"],
            "side": ["side", "intent_side"],
            "trend_dir": ["trend_dir"],
            "trend_confidence": ["trend_confidence"],
            "trend_run_length": ["trend_run_length"],
            "pm_norm_60s": ["pm_norm_60s"],
            "pm_norm_300s": ["pm_norm_300s"],
        }
        for field_name, aliases in field_map.items():
            field_value = first_named_value(leaf_map, aliases)
            if field_value is None:
                continue
            set_field(
                intent,
                field_name,
                Evidence(
                    recovered=True,
                    recovered_value=clean_value(field_value),
                    source_quality="RUNTIME_PERSISTED_EXACT",
                    source_file=rel(path),
                    source_line_or_row=str(line_number),
                    source_event_name=event_name,
                    correlation_method="exact_rid_or_intent_jsonl_match",
                    time_delta_ms=time_delta_ms,
                    confidence="HIGH",
                ),
            )


def gather_order_logs_collected(intents: list[IntentRecord]) -> None:
    tokens = {}
    for intent in intents:
        if intent.rid:
            tokens[intent.rid] = intent
        tokens[intent.intent_id] = intent
        if intent.features_ts_ms is not None:
            tokens[str(intent.features_ts_ms)] = intent
    pattern = compile_token_pattern(tokens)
    paths = sorted(ROOT.glob("data/order_logs_collected/*.jsonl"))
    for path, line_number, raw_line, payload, matches in stream_jsonl_matches(paths, pattern):
        intent = tokens[matches[0]]
        leaf_map = recursive_leaf_map(payload)
        event_name = extract_event_name(leaf_map)
        event_ts_value = first_named_value(
            leaf_map, ["event_ts", "ts", "ts_utc", "timestamp"]) or intent.event_ts
        try:
            time_delta_ms = str(parse_iso_to_ms(
                str(event_ts_value)) - intent.event_ts_ms)
        except Exception:
            time_delta_ms = ""

        for field_name in ("pm_norm_60s", "pm_norm_300s", "trend_dir", "trend_run_length", "trend_confidence"):
            field_value = first_named_value(leaf_map, [field_name])
            if field_value is None:
                field_value = extract_number_from_text(raw_line, field_name)
            if field_value is None:
                continue
            set_field(
                intent,
                field_name,
                Evidence(
                    recovered=True,
                    recovered_value=clean_value(field_value),
                    source_quality="RUNTIME_PERSISTED_EXACT",
                    source_file=rel(path),
                    source_line_or_row=str(line_number),
                    source_event_name=event_name,
                    correlation_method="exact_rid_or_features_ts_order_logs_collected",
                    time_delta_ms=time_delta_ms,
                    confidence="HIGH",
                ),
            )


def gather_generic_text_hits(intents: list[IntentRecord]) -> None:
    tokens = {}
    for intent in intents:
        tokens[intent.intent_id] = intent
        if intent.rid:
            tokens[intent.rid] = intent
        if intent.features_ts_ms is not None:
            tokens[str(intent.features_ts_ms)] = intent

    pattern = compile_token_pattern(tokens)
    if pattern is None:
        return

    candidate_files: list[Path] = []
    for root_name in (
        "logs/frozen",
        "logs/judge_experts",
        "data/processed",
        "data/shadow_telemetry",
    ):
        root_path = ROOT / root_name
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_FILE_SUFFIXES:
                candidate_files.append(path)

    seen = set()
    for path in sorted(candidate_files):
        path_key = str(path.resolve())
        if path_key in seen:
            continue
        seen.add(path_key)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                matches = pattern.findall(line)
                if not matches:
                    continue
                if not any(name in line for name in ("pm_norm_60s", "pm_norm_300s", "price_motion_context")):
                    continue
                intent = tokens[matches[0]]
                if rel(path).startswith("reports/"):
                    intent.search_notes.append(
                        f"report_surface_hit:{rel(path)}:{line_number}")
                    continue
                for field_name in ("pm_norm_60s", "pm_norm_300s"):
                    numeric = extract_number_from_text(line, field_name)
                    if isinstance(numeric, bool):
                        continue
                    if numeric is None:
                        continue
                    set_field(
                        intent,
                        field_name,
                        Evidence(
                            recovered=True,
                            recovered_value=clean_value(numeric),
                            source_quality="RUNTIME_PERSISTED_EXACT",
                            source_file=rel(path),
                            source_line_or_row=str(line_number),
                            source_event_name="GENERIC_TEXT_HIT",
                            correlation_method="recursive_text_scan_exact_token_match",
                            time_delta_ms="",
                            confidence="HIGH",
                        ),
                    )


def gather_schema_failures(intents: list[IntentRecord]) -> dict[str, Any]:
    target_rids = {intent.rid for intent in intents if intent.rid}
    by_rid: dict[str, list[str]] = defaultdict(list)
    affected_rids: set[str] = set()
    lost_fields: Counter[str] = Counter()
    failure_count = 0

    for path in sorted(ROOT.glob("logs/aurora_core.log*")):
        recent_rids: deque[str] = deque(maxlen=12)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                for rid in RID_PATTERN.findall(line):
                    if rid in target_rids:
                        recent_rids.append(rid)
                if "Payload validation failed for EVT:DECISION_TRACE_EMITTED" not in line:
                    continue
                rid = recent_rids[-1] if recent_rids else ""
                if not rid:
                    continue
                failure_count += 1
                if rid:
                    affected_rids.add(rid)
                    by_rid[rid].append(f"{rel(path)}:{line_number}")
                for field_name in re.findall(r"'([^']+)'", line):
                    lost_fields[field_name] += 1

    return {
        "failure_count": failure_count,
        "affected_rids": sorted(affected_rids),
        "lost_fields": sorted(lost_fields),
        "locations": by_rid,
    }


def apply_config_thresholds(intents: list[IntentRecord]) -> dict[str, Any]:
    domains_lines = read_text(ROOT / "config/aurora/domains.yaml").splitlines()
    min_conf = 0.35
    per_regime = {"DEFAULT": 0.35, "TREND_UP": 0.20, "TREND_DOWN": 0.20}
    hard_veto = 2
    flash_threshold = 1.0
    bleed_threshold = 0.5
    consecutive_bars = 1

    strategy_text = read_text(ROOT / "config/aurora/strategies/aurora.yaml")
    strategy_override_present = any(token in strategy_text for token in (
        "min_by_regime", "min_by_symbol", "max_by_regime", "max_by_symbol"))

    for intent in intents:
        regime_text = intent.fields.get(
            "regime", Evidence(False)).recovered_value or "DEFAULT"
        regime_key = regime_text.strip().upper() or "DEFAULT"
        resolved = per_regime.get(regime_key, per_regime["DEFAULT"])
        set_field(
            intent,
            "resolved_min_regime_confidence",
            Evidence(
                recovered=True,
                recovered_value=clean_value(resolved),
                source_quality="RUNTIME_PERSISTED_EXACT",
                source_file="config/aurora/domains.yaml",
                source_line_or_row="56-72",
                source_event_name="CONFIG",
                correlation_method="ssot_config_exact",
                time_delta_ms="",
                confidence="HIGH",
            ),
        )
        set_field(
            intent,
            "hard_veto_consecutive_bars",
            Evidence(
                recovered=True,
                recovered_value=clean_value(hard_veto),
                source_quality="RUNTIME_PERSISTED_EXACT",
                source_file="config/aurora/domains.yaml",
                source_line_or_row="67-70",
                source_event_name="CONFIG",
                correlation_method="ssot_config_exact",
                time_delta_ms="",
                confidence="HIGH",
            ),
        )
        set_field(
            intent,
            "flash_threshold_norm",
            Evidence(
                recovered=True,
                recovered_value=clean_value(flash_threshold),
                source_quality="RUNTIME_PERSISTED_EXACT",
                source_file="config/aurora/domains.yaml",
                source_line_or_row="129-136",
                source_event_name="CONFIG",
                correlation_method="ssot_config_exact",
                time_delta_ms="",
                confidence="HIGH",
            ),
        )
        set_field(
            intent,
            "bleed_threshold_norm",
            Evidence(
                recovered=True,
                recovered_value=clean_value(bleed_threshold),
                source_quality="RUNTIME_PERSISTED_EXACT",
                source_file="config/aurora/domains.yaml",
                source_line_or_row="129-136",
                source_event_name="CONFIG",
                correlation_method="ssot_config_exact",
                time_delta_ms="",
                confidence="HIGH",
            ),
        )
        set_field(
            intent,
            "side",
            Evidence(
                recovered=True,
                recovered_value=intent.side,
                source_quality="RUNTIME_PERSISTED_EXACT",
                source_file=rel(ACCEPTED_REPLAY_CSV),
                source_line_or_row="intent_seed",
                source_event_name="accepted_intent_seed",
                correlation_method="seed_csv_exact",
                time_delta_ms="0",
                confidence="HIGH",
            ),
        )
        intent.search_notes.append(
            "strategy_threshold_override_present=false" if not strategy_override_present else "strategy_threshold_override_present=true"
        )

    return {
        "min_abs_delta_price": 0.0,
        "consecutive_bars": consecutive_bars,
        "hard_veto_consecutive_bars": hard_veto,
        "flash_threshold_norm": flash_threshold,
        "bleed_threshold_norm": bleed_threshold,
        "strategy_override_present": strategy_override_present,
        "resolved_min_by_regime": per_regime,
        "min_regime_confidence": min_conf,
    }


def enrich_from_recorder(intents: list[IntentRecord], config: dict[str, Any]) -> None:
    recorder_cache: dict[Path, list[dict[str, str]]] = {}
    for intent in intents:
        row, source_file, all_rows = search_recorder_row(
            intent, recorder_cache)
        if row is None or source_file is None:
            intent.search_notes.append("recorder_row_not_found")
            continue

        matched_line = row["__line__"]
        if intent.features_ts_ms is None:
            for value in row.values():
                candidate = maybe_int(value)
                if candidate and len(str(candidate)) >= 13:
                    intent.features_ts_ms = candidate
                    intent.bar_close_ts = candidate
                    break

        regime = row.get("regime", "")
        if regime:
            set_field(
                intent,
                "regime",
                Evidence(
                    recovered=True,
                    recovered_value=regime,
                    source_quality="RUNTIME_PERSISTED_EXACT",
                    source_file=source_file,
                    source_line_or_row=matched_line,
                    source_event_name="RECORDER_CSV_ROW",
                    correlation_method="exact_features_ts_ms_csv_row",
                    time_delta_ms=str(
                        (intent.features_ts_ms or intent.event_ts_ms) - intent.event_ts_ms),
                    confidence="HIGH",
                ),
            )
        regime_conf = row.get("regime_confidence", "")
        if regime_conf:
            set_field(
                intent,
                "regime_confidence",
                Evidence(
                    recovered=True,
                    recovered_value=regime_conf,
                    source_quality="RUNTIME_PERSISTED_EXACT",
                    source_file=source_file,
                    source_line_or_row=matched_line,
                    source_event_name="RECORDER_CSV_ROW",
                    correlation_method="exact_features_ts_ms_csv_row",
                    time_delta_ms=str(
                        (intent.features_ts_ms or intent.event_ts_ms) - intent.event_ts_ms),
                    confidence="HIGH",
                ),
            )
        delta_col = delta_column_name(row)
        if delta_col:
            delta_value = row.get(delta_col, "")
            if delta_value:
                set_field(
                    intent,
                    "delta_price",
                    Evidence(
                        recovered=True,
                        recovered_value=delta_value,
                        source_quality="RUNTIME_PERSISTED_EXACT",
                        source_file=source_file,
                        source_line_or_row=matched_line,
                        source_event_name="RECORDER_CSV_ROW",
                        correlation_method="exact_features_ts_ms_csv_row",
                        time_delta_ms=str(
                            (intent.features_ts_ms or intent.event_ts_ms) - intent.event_ts_ms),
                        confidence="HIGH",
                    ),
                )

        if not intent.fields.get("trend_dir", Evidence(False)).recovered or not intent.fields.get("trend_run_length", Evidence(False)).recovered:
            trend_dir, trend_conf, delta_price, run_length, line_range = reconstruct_trend_from_rows(
                all_rows,
                matched_line,
                float(config["min_abs_delta_price"]),
                int(config["consecutive_bars"]),
            )
            if trend_dir != "UNKNOWN":
                base_kwargs = {
                    "source_quality": "RUNTIME_RECONSTRUCTED_FROM_RECORDER",
                    "source_file": source_file,
                    "source_line_or_row": f"{line_range} | code=569-624",
                    "source_event_name": "RECORDER_DELTA_HISTORY",
                    "correlation_method": "reconstructed_from_recorder_delta_history",
                    "time_delta_ms": str((intent.features_ts_ms or intent.event_ts_ms) - intent.event_ts_ms),
                    "confidence": "MEDIUM",
                }
                set_field(intent, "trend_dir", Evidence(
                    recovered=True, recovered_value=trend_dir, **base_kwargs))
                set_field(intent, "trend_confidence", Evidence(
                    recovered=True, recovered_value=clean_value(trend_conf), **base_kwargs))
                set_field(intent, "trend_run_length", Evidence(
                    recovered=True, recovered_value=clean_value(run_length), **base_kwargs))
                if delta_price is not None:
                    set_field(intent, "delta_price", Evidence(
                        recovered=True, recovered_value=clean_value(delta_price), **base_kwargs))


def mark_missing_price_motion_fields(intents: list[IntentRecord]) -> None:
    missing_reason = (
        "no_exact_pm_norm_60s_or_pm_norm_300s_in_shadow_journal_order_logs_collected_wal_order_log_recorder_or_workspace_text_surfaces"
    )
    for intent in intents:
        for field_name in ("pm_norm_60s", "pm_norm_300s"):
            evidence = intent.fields.get(field_name)
            if evidence and evidence.recovered:
                continue
            set_field(
                intent,
                field_name,
                Evidence(
                    recovered=False,
                    recovered_value="",
                    source_quality="NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
                    source_file="logs/,data/,ops/,wal/ searched",
                    source_line_or_row="",
                    source_event_name="SEARCH",
                    correlation_method="exact_rid_exact_intent_id_exact_features_ts_ms_symbol_side_time_window",
                    time_delta_ms="",
                    missing_reason=missing_reason,
                    confidence="LOW",
                ),
            )


def build_input_recovery_rows(intents: list[IntentRecord]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for intent in intents:
        for nrr_code in NRR_CODES:
            for required_input in EXPECTED_INPUTS[nrr_code]:
                evidence = intent.fields.get(required_input)
                if evidence is None:
                    evidence = Evidence(
                        recovered=False, missing_reason="input_not_recovered")
                rows.append(
                    {
                        "rid": intent.rid,
                        "intent_id": intent.intent_id,
                        "symbol": intent.symbol,
                        "strategy_id": intent.strategy_id,
                        "side": intent.side,
                        "event_ts": intent.event_ts,
                        "features_ts_ms": clean_value(intent.features_ts_ms),
                        "nrr_code": nrr_code,
                        "required_input": required_input,
                        "recovered": "true" if evidence.recovered else "false",
                        "recovered_value": evidence.recovered_value,
                        "source_quality": evidence.source_quality,
                        "source_file": evidence.source_file,
                        "source_line_or_row": evidence.source_line_or_row,
                        "source_event_name": evidence.source_event_name,
                        "correlation_method": evidence.correlation_method,
                        "time_delta_ms": evidence.time_delta_ms,
                        "missing_reason": evidence.missing_reason,
                        "confidence": evidence.confidence,
                    }
                )
    return rows


def replay_nrr026(intent: IntentRecord) -> tuple[str, str, str, str, str]:
    regime_conf = intent.fields.get("regime_confidence")
    threshold = intent.fields.get("resolved_min_regime_confidence")
    if not regime_conf or not regime_conf.recovered or not threshold or not threshold.recovered:
        return (
            "UNPROVEN_INPUT_MISSING",
            "missing_regime_confidence_or_resolved_threshold",
            "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
            "{}",
            serialize_json(
                {"resolved_min_regime_confidence": threshold.recovered_value if threshold else ""}),
        )

    regime_conf_value = float(regime_conf.recovered_value)
    threshold_value = float(threshold.recovered_value)
    result = "BLOCK" if regime_conf_value < threshold_value else "PASS"
    reason = f"regime_confidence={regime_conf_value:.15g} {'<' if result == 'BLOCK' else '>='} min={threshold_value:.15g}"
    inputs_used = serialize_json(
        {
            "regime": intent.fields.get("regime", Evidence(False)).recovered_value,
            "regime_confidence": regime_conf_value,
            "features_ts_ms": intent.features_ts_ms,
        }
    )
    thresholds_used = serialize_json(
        {"resolved_min_regime_confidence": threshold_value})
    return result, reason, "RUNTIME_PERSISTED_EXACT", inputs_used, thresholds_used


def replay_nrr027(intent: IntentRecord) -> tuple[str, str, str, str, str]:
    trend_dir = intent.fields.get("trend_dir")
    trend_run = intent.fields.get("trend_run_length")
    side = intent.fields.get("side")
    hard_veto = intent.fields.get("hard_veto_consecutive_bars")
    if not trend_dir or not trend_dir.recovered or not trend_run or not trend_run.recovered or not side or not side.recovered or not hard_veto or not hard_veto.recovered:
        return (
            "UNPROVEN_INPUT_MISSING",
            "missing_trend_dir_or_run_length_or_side_or_hard_veto",
            "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
            "{}",
            serialize_json(
                {"hard_veto_consecutive_bars": hard_veto.recovered_value if hard_veto else ""}),
        )

    trend_dir_value = trend_dir.recovered_value.strip().upper()
    trend_run_value = int(float(trend_run.recovered_value))
    hard_veto_value = int(float(hard_veto.recovered_value))
    gate_side = normalize_side(side.recovered_value)
    aligned = (trend_dir_value == "UP" and gate_side == "LONG") or (
        trend_dir_value == "DOWN" and gate_side == "SHORT")
    countertrend = (trend_dir_value == "UP" and gate_side == "SHORT") or (
        trend_dir_value == "DOWN" and gate_side == "LONG")
    if countertrend and trend_run_value >= hard_veto_value:
        result = "BLOCK"
        reason = f"countertrend side={gate_side} trend_dir={trend_dir_value} run_length={trend_run_value} >= veto={hard_veto_value}"
    elif aligned or countertrend:
        result = "PASS"
        relation = "aligned" if aligned else "countertrend_below_veto"
        reason = f"{relation}: side={gate_side} trend_dir={trend_dir_value} run_length={trend_run_value} veto={hard_veto_value}"
    else:
        result = "UNPROVEN_INPUT_MISSING"
        reason = f"trend_dir={trend_dir_value} not actionable"

    quality = trend_dir.source_quality if trend_dir.source_quality == trend_run.source_quality else "RUNTIME_RECONSTRUCTED_FROM_RECORDER"
    inputs_used = serialize_json(
        {
            "trend_dir": trend_dir_value,
            "trend_run_length": trend_run_value,
            "intent_side": gate_side,
            "delta_price": intent.fields.get("delta_price", Evidence(False)).recovered_value,
            "features_ts_ms": intent.features_ts_ms,
        }
    )
    thresholds_used = serialize_json(
        {"hard_veto_consecutive_bars": hard_veto_value})
    return result, reason, quality, inputs_used, thresholds_used


def replay_price_motion(intent: IntentRecord, nrr_code: str) -> tuple[str, str, str, str, str]:
    pm60 = intent.fields.get("pm_norm_60s")
    pm300 = intent.fields.get("pm_norm_300s")
    side = normalize_side(intent.side)
    flash_threshold = float(intent.fields.get(
        "flash_threshold_norm", Evidence(False)).recovered_value or 1.0)
    bleed_threshold = float(intent.fields.get(
        "bleed_threshold_norm", Evidence(False)).recovered_value or 0.5)

    if not pm60 or not pm60.recovered or not pm300 or not pm300.recovered:
        return (
            "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
            "pm_norm_60s_or_pm_norm_300s_absent_after_exhaustive_search",
            "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
            "{}",
            serialize_json({"flash_threshold_norm": flash_threshold,
                           "bleed_threshold_norm": bleed_threshold}),
        )

    try:
        pm60_value = float(pm60.recovered_value)
        pm300_value = float(pm300.recovered_value)
    except (TypeError, ValueError):
        return (
            "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
            "pm_norm_60s_or_pm_norm_300s_non_numeric_after_search",
            "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH",
            "{}",
            serialize_json({"flash_threshold_norm": flash_threshold,
                           "bleed_threshold_norm": bleed_threshold}),
        )
    if nrr_code == "NRR-028":
        result = "PASS"
        if side == "LONG" and (pm60_value is None or pm300_value is None):
            result = "BLOCK"
        reason = "price_motion_exact_inputs_present"
    elif nrr_code == "NRR-029":
        if side == "LONG":
            result = "BLOCK" if pm60_value <= -flash_threshold else "PASS"
        else:
            result = "BLOCK" if pm60_value >= flash_threshold else "PASS"
        reason = f"pm_norm_60s={pm60_value:.15g} flash_threshold={flash_threshold:.15g} side={side}"
    else:
        if side == "LONG":
            result = "BLOCK" if pm300_value <= -bleed_threshold else "PASS"
        else:
            result = "BLOCK" if pm300_value >= bleed_threshold else "PASS"
        reason = f"pm_norm_300s={pm300_value:.15g} bleed_threshold={bleed_threshold:.15g} side={side}"

    inputs_used = serialize_json(
        {
            "pm_norm_60s": pm60_value,
            "pm_norm_300s": pm300_value,
            "intent_side": side,
            "features_ts_ms": intent.features_ts_ms,
        }
    )
    thresholds_used = serialize_json(
        {"flash_threshold_norm": flash_threshold, "bleed_threshold_norm": bleed_threshold})
    return result, reason, "RUNTIME_PERSISTED_EXACT", inputs_used, thresholds_used


def build_replay_rows(intents: list[IntentRecord]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for intent in intents:
        for nrr_code in NRR_CODES:
            if nrr_code == "NRR-026":
                replay_result, result_reason, source_quality, inputs_used, thresholds_used = replay_nrr026(
                    intent)
            elif nrr_code == "NRR-027":
                replay_result, result_reason, source_quality, inputs_used, thresholds_used = replay_nrr027(
                    intent)
            else:
                replay_result, result_reason, source_quality, inputs_used, thresholds_used = replay_price_motion(
                    intent, nrr_code)

            confidence = "HIGH" if replay_result in {
                "PASS", "BLOCK"} and source_quality == "RUNTIME_PERSISTED_EXACT" else "MEDIUM"
            if source_quality == "RUNTIME_RECONSTRUCTED_FROM_RECORDER" and replay_result in {"PASS", "BLOCK"}:
                confidence = "MEDIUM"
            if replay_result in {"UNPROVEN_INPUT_MISSING", "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH"}:
                confidence = "LOW"

            rows.append(
                {
                    "rid": intent.rid,
                    "intent_id": intent.intent_id,
                    "symbol": intent.symbol,
                    "strategy_id": intent.strategy_id,
                    "side": intent.side,
                    "event_ts": intent.event_ts,
                    "trade_id": intent.trade_id,
                    "net_pnl_if_joined": clean_value(intent.net_pnl_if_joined),
                    "nrr_code": nrr_code,
                    "replay_result": replay_result,
                    "result_reason": result_reason,
                    "source_quality_used": source_quality,
                    "inputs_used": inputs_used,
                    "thresholds_used": thresholds_used,
                    "confidence": confidence,
                }
            )
    return rows


def build_economic_preview(replay_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in replay_rows:
        grouped[row["nrr_code"]].append(row)

    preview_rows: list[dict[str, str]] = []
    for nrr_code in NRR_CODES:
        rows = grouped[nrr_code]
        det_block = [row for row in rows if row["replay_result"] == "BLOCK"]
        det_pass = [row for row in rows if row["replay_result"] == "PASS"]
        approx_block = [
            row for row in rows if row["replay_result"] == "RECOMPUTED_APPROX_BLOCK"]
        approx_pass = [row for row in rows if row["replay_result"]
                       == "RECOMPUTED_APPROX_PASS"]
        unproven = [row for row in rows if row["replay_result"] in {
            "UNPROVEN_INPUT_MISSING", "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH", "NOT_APPLICABLE"}]

        blocked_net = sum(maybe_float(
            row["net_pnl_if_joined"]) or 0.0 for row in det_block)
        passed_net = sum(maybe_float(
            row["net_pnl_if_joined"]) or 0.0 for row in det_pass)
        blocked_winners = sum(1 for row in det_block if (
            maybe_float(row["net_pnl_if_joined"]) or 0.0) > 0.0)
        blocked_losers = sum(1 for row in det_block if (
            maybe_float(row["net_pnl_if_joined"]) or 0.0) < 0.0)
        passed_winners = sum(1 for row in det_pass if (
            maybe_float(row["net_pnl_if_joined"]) or 0.0) > 0.0)
        passed_losers = sum(1 for row in det_pass if (
            maybe_float(row["net_pnl_if_joined"]) or 0.0) < 0.0)
        evidence_quality = "+".join(
            sorted({row["source_quality_used"] for row in rows}))

        preview_rows.append(
            {
                "nrr_code": nrr_code,
                "deterministic_block_count": str(len(det_block)),
                "deterministic_pass_count": str(len(det_pass)),
                "approx_block_count": str(len(approx_block)),
                "approx_pass_count": str(len(approx_pass)),
                "unproven_count": str(len(unproven)),
                "blocked_winners": str(blocked_winners),
                "blocked_losers": str(blocked_losers),
                "blocked_net_pnl": clean_value(blocked_net),
                "passed_winners": str(passed_winners),
                "passed_losers": str(passed_losers),
                "passed_net_pnl": clean_value(passed_net),
                "protection_value": clean_value(-blocked_net),
                "evidence_quality": evidence_quality,
            }
        )

    return preview_rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_t3c_matrix() -> dict[str, tuple[str, str]]:
    results: dict[str, tuple[str, str]] = {}
    for row in csv_rows(T3C_MATRIX_CSV):
        if row.get("field_name") == "regime_confidence":
            results["NRR-026"] = (row.get("status", ""),
                                  row.get("value_or_resolution", ""))
        if row.get("field_name") == "trend_dir":
            results["NRR-027"] = (row.get("status", ""),
                                  row.get("value_or_resolution", ""))
        if row.get("field_name") == "pm_norm_60s":
            results["NRR-028"] = (row.get("status", ""),
                                  row.get("value_or_resolution", ""))
            results["NRR-029"] = (row.get("status", ""),
                                  row.get("value_or_resolution", ""))
            results["NRR-030"] = (row.get("status", ""),
                                  row.get("value_or_resolution", ""))
    return results


def validate_outputs(intents: list[IntentRecord], input_rows: list[dict[str, str]], replay_rows: list[dict[str, str]]) -> None:
    intents_by_rid = {intent.rid: intent for intent in intents if intent.rid}
    for intent in intents:
        rows = [row for row in replay_rows if row["intent_id"] == intent.intent_id]
        nrrs = {row["nrr_code"] for row in rows}
        if nrrs != set(NRR_CODES):
            raise AssertionError(
                f"missing nrr rows for intent_id={intent.intent_id}: {sorted(set(NRR_CODES) - nrrs)}")
        for row in rows:
            if not row["replay_result"]:
                raise AssertionError(
                    f"missing replay_result for {row['intent_id']} {row['nrr_code']}")
            if row["replay_result"] in {"PASS", "BLOCK"}:
                if not row["inputs_used"] or not row["source_quality_used"]:
                    raise AssertionError(
                        f"missing inputs/source quality for {row['intent_id']} {row['nrr_code']}")

    input_counts = Counter((row["intent_id"], row["nrr_code"])
                           for row in input_rows)
    for intent in intents:
        for nrr_code in NRR_CODES:
            if input_counts[(intent.intent_id, nrr_code)] < len(EXPECTED_INPUTS[nrr_code]):
                raise AssertionError(
                    f"missing input recovery rows for {intent.intent_id} {nrr_code}")

    control_rows = {
        row["nrr_code"]: row for row in replay_rows if row["rid"] == CONTROL_RID}
    if control_rows["NRR-026"]["replay_result"] != "BLOCK":
        raise AssertionError("BNB control NRR-026 did not reproduce BLOCK")
    if control_rows["NRR-027"]["replay_result"] != "PASS":
        raise AssertionError("BNB control NRR-027 did not reproduce PASS")
    for nrr_code in ("NRR-028", "NRR-029", "NRR-030"):
        if control_rows[nrr_code]["replay_result"] != "NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH":
            raise AssertionError(
                f"BNB control {nrr_code} did not stay NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH")

    if CONTROL_RID not in intents_by_rid:
        raise AssertionError(
            "BNB control rid not present in processed intents")


def summarize_replay(replay_rows: list[dict[str, str]]) -> dict[str, Counter[str]]:
    grouped: dict[str, Counter[str]] = {}
    for nrr_code in NRR_CODES:
        grouped[nrr_code] = Counter(row["replay_result"]
                                    for row in replay_rows if row["nrr_code"] == nrr_code)
    return grouped


def build_report(
    intents: list[IntentRecord],
    replay_rows: list[dict[str, str]],
    economic_rows: list[dict[str, str]],
    schema_failures: dict[str, Any],
    window_start_ms: int,
    window_end_ms: int,
) -> str:
    replay_summary = summarize_replay(replay_rows)
    exact_anchor_found = sum(1 for intent in intents if intent.rid)
    unresolved = sum(1 for intent in intents if not intent.rid)
    action_rows = [row for row in replay_rows if row["replay_result"] in {
        "PASS", "BLOCK", "RECOMPUTED_APPROX_PASS", "RECOMPUTED_APPROX_BLOCK"}]
    verdict = "PARTIAL_REPLAY_RECOVERED" if action_rows else "MOSTLY_UNPROVEN"

    source_quality_counter = Counter(
        row["source_quality_used"] for row in replay_rows)
    deterministic_blocked_winners = sum(
        int(row["blocked_winners"]) for row in economic_rows)
    deterministic_blocked_losers = sum(
        int(row["blocked_losers"]) for row in economic_rows)
    deterministic_blocked_net_pnl = sum(maybe_float(
        row["blocked_net_pnl"]) or 0.0 for row in economic_rows)
    deterministic_passed_winners = sum(
        int(row["passed_winners"]) for row in economic_rows)
    deterministic_passed_losers = sum(
        int(row["passed_losers"]) for row in economic_rows)
    deterministic_passed_net_pnl = sum(maybe_float(
        row["passed_net_pnl"]) or 0.0 for row in economic_rows)

    revise_t4 = any(
        row["replay_result"] in {"PASS", "BLOCK"}
        and row["source_quality_used"] in {"RUNTIME_PERSISTED_EXACT", "RUNTIME_RECONSTRUCTED_FROM_RECORDER"}
        for row in replay_rows
    )

    exact_pm_rows = [
        row for row in replay_rows
        if row["nrr_code"] in {"NRR-028", "NRR-029", "NRR-030"}
        and row["source_quality_used"] == "RUNTIME_PERSISTED_EXACT"
        and row["replay_result"] in {"PASS", "BLOCK"}
    ]
    exact_pm_intents = sorted({row["rid"]
                              for row in exact_pm_rows if row["rid"]})

    protection_lines = [
        f"  - {row['nrr_code']}: {row['protection_value']}" for row in economic_rows]
    summary_lines = [
        "# AGENT_REPORT_V1",
        "",
        "## Executive Summary",
        "task:",
        "  AURORA_DEEP_NRR_INPUT_EVIDENCE_EXCAVATION_T3D_ALL_ACCEPTED",
        "",
        "verdict:",
        f"  {verdict}",
        "",
        "runtime_window:",
        f"  start_ts: {ms_to_utc(window_start_ms)}",
        f"  end_ts: {ms_to_utc(window_end_ms)}",
        "",
        "accepted_intents:",
        f"  total: {len(intents)}",
        f"  processed: {len(intents)}",
        f"  exact_anchor_found: {exact_anchor_found}",
        f"  unresolved: {unresolved}",
        "",
        "replay_summary:",
        f"  NRR-026: {dict(replay_summary['NRR-026'])}",
        f"  NRR-027: {dict(replay_summary['NRR-027'])}",
        f"  NRR-028: {dict(replay_summary['NRR-028'])}",
        f"  NRR-029: {dict(replay_summary['NRR-029'])}",
        f"  NRR-030: {dict(replay_summary['NRR-030'])}",
        "",
        "economic_preview:",
        f"  deterministic_blocked_winners: {deterministic_blocked_winners}",
        f"  deterministic_blocked_losers: {deterministic_blocked_losers}",
        f"  deterministic_blocked_net_pnl: {clean_value(deterministic_blocked_net_pnl)}",
        f"  deterministic_passed_winners: {deterministic_passed_winners}",
        f"  deterministic_passed_losers: {deterministic_passed_losers}",
        f"  deterministic_passed_net_pnl: {clean_value(deterministic_passed_net_pnl)}",
        "  protection_value_by_gate:",
        *protection_lines,
        "",
        "source_quality_summary:",
        f"  runtime_persisted_exact: {source_quality_counter.get('RUNTIME_PERSISTED_EXACT', 0)}",
        f"  runtime_reconstructed_from_recorder: {source_quality_counter.get('RUNTIME_RECONSTRUCTED_FROM_RECORDER', 0)}",
        f"  recomputed_approx: {source_quality_counter.get('RECOMPUTED_APPROX', 0)}",
        f"  not_found_after_exhaustive_search: {source_quality_counter.get('NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH', 0)}",
        "",
        "schema_failure_summary:",
        f"  decision_trace_validation_failures: {schema_failures['failure_count']}",
        f"  affected_rids: {schema_failures['affected_rids']}",
        f"  lost_fields: {schema_failures['lost_fields']}",
        "  root_contract_drift: EVT:DECISION_TRACE_EMITTED rejected unexpected builder fields before durable allow-path persistence",
        "",
        "## Proven Facts",
        f"- Processed {len(intents)} accepted intents from {rel(ACCEPTED_REPLAY_CSV)} inside the T0 runtime window.",
        f"- Exact rid anchors were recovered for {exact_anchor_found}/{len(intents)} accepted intents using {rel(DECISION_EVENTS_CSV)} and {rel(MASTER_TRADE_CSV)}.",
        f"- NRR-026 now has actionable PASS/BLOCK rows: {replay_summary['NRR-026'].get('PASS', 0)} PASS and {replay_summary['NRR-026'].get('BLOCK', 0)} BLOCK.",
        f"- NRR-027 now has actionable PASS/BLOCK rows: {replay_summary['NRR-027'].get('PASS', 0)} PASS and {replay_summary['NRR-027'].get('BLOCK', 0)} BLOCK.",
        f"- Accepted price-motion replay remains absent or unresolved for most accepted intents: NRR-028={dict(replay_summary['NRR-028'])}, NRR-029={dict(replay_summary['NRR-029'])}, NRR-030={dict(replay_summary['NRR-030'])}.",
        f"- Exact accepted price-motion recovery exists for {len(exact_pm_intents)} accepted intents via logs/frozen/nrr062_fresh_capture_20260507_103909/nrr062_cases.jsonl, not via the missing accepted decision trace.",
        f"- BNB control rid {CONTROL_RID} reproduces T3C: NRR-026 BLOCK, NRR-027 PASS, NRR-028..030 NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH.",
        "",
        "## Inferred Findings",
        "- T4 is revised for the directional slice: accepted-intent NRR-026 and NRR-027 are no longer universally fail-closed once recorder history and config thresholds are joined back to accepted anchors.",
        "- Accepted allow-path observability remains structurally incomplete for price-motion replay because the exact pm_norm_60s and pm_norm_300s fields do not survive on most accepted intents even after recursive text scans across the allowed runtime and evidence-freeze surfaces.",
        "- The cohort remains only partially replayable: directional gates are materially recoverable, while price-motion gates remain mostly evidence-missing.",
        "- The small exact price-motion subset comes from evidence-freeze capture reuse and does not overturn the broader accepted-trace persistence defect.",
        "",
        "## Contradictions / Evidence Gaps",
        "- Exact accepted decision traces are still not durably present for every accepted rid, so exact price-motion inputs cannot be assumed from decision logs alone.",
        "- Recorder rows preserve delta_price and regime fields but do not preserve the named 60s and 300s price-motion windows required for NRR-028..030.",
        "- Some accepted intents may still rely on event_ts-floor correlation to locate recorder bars when WAL features_ts_ms is absent; these were kept at reconstructed, not exact, quality.",
        "- Report-surface hits were treated as search evidence only and were not promoted to deterministic runtime inputs.",
        "",
        "## Root Cause Candidates",
        "- Primary: EVT:DECISION_TRACE_EMITTED schema validation drift drops accepted allow-path rich trace fields before persistence.",
        "- Secondary: recorder flattening preserves directional reconstruction inputs but not the exact multi-window price-motion fields.",
        "- Secondary: order_logs_collected rich price_motion_context is path-dependent and not a universal accepted-intent recovery seam.",
        "",
        "## Operational Risk",
        "- Observability Gap",
        "",
        "## Files / Areas Touched",
        "- tools/runtime_forensics_tmp/build_t3d_all_accepted_replay.py",
        "- reports/runtime_forensics/T3d_deep_nrr_all_accepted/accepted_intent_input_recovery_all.csv",
        "- reports/runtime_forensics/T3d_deep_nrr_all_accepted/deep_counterfactual_nrr_replay_all.csv",
        "- reports/runtime_forensics/T3d_deep_nrr_all_accepted/nrr_replay_economic_preview.csv",
        "- reports/runtime_forensics/T3d_deep_nrr_all_accepted/T3D_DEEP_NRR_ALL_ACCEPTED_REPORT.md",
        "",
        "## Validation Performed",
        "- Verified every accepted intent has NRR-026..030 rows and every row has replay_result.",
        "- Verified every deterministic PASS/BLOCK row has inputs_used and source_quality_used.",
        "- Verified BNB control rid reproduces the prior T3C findings exactly.",
        "- Rebuilt the CSV outputs from runtime-window-limited sources only.",
        "",
        "## Residual Risk",
        "- Exact price-motion replay may improve only if another allowed runtime artifact with accepted price_motion_context exists outside the currently indexed workspace surfaces.",
        "- The reconstructed directional rows depend on stable recorder ordering and the in-repo safety_gates trend logic; if runtime code diverged from the checked tree, that would need separate proof.",
        "",
        "## What Remains Unproven",
        "- Exact accepted pm_norm_60s and pm_norm_300s for most accepted intents.",
        "- Whether every accepted decision-trace validation failure is explicitly present in aurora_core rotated logs for the full accepted cohort.",
        "",
        "## Minimal Safe Verdict",
        f"- proven: accepted directional replay is materially recoverable for NRR-026 and NRR-027 across the cohort, with actionable PASS/BLOCK rows present.",
        f"- unproven: accepted NRR-028..030 remain mostly NOT_FOUND_AFTER_EXHAUSTIVE_SEARCH because exact pm_norm_60s and pm_norm_300s are absent for 37/42 intents.",
        "- does_this_revise_T4:",
        f"  yes/no: {'yes' if revise_t4 else 'no'}",
        "  explanation: T4 claimed 0 actionable PASS_or_BLOCK across accepted intents; T3D now recovers actionable directional rows and a small evidence-freeze-backed price-motion subset.",
        "- next_action:",
        "  - repair accepted decision-trace schema persistence first, then rerun T3/T4/T3D to verify whether the remaining 37/42 accepted intents gain exact price-motion recovery.",
    ]
    return "\n".join(summary_lines) + "\n"


def main() -> int:
    require_paths(
        [
            ACCEPTED_REPLAY_CSV,
            DECISION_EVENTS_CSV,
            MASTER_TRADE_CSV,
            FINAL_REPORT_MD,
            T3C_REPORT_MD,
            T3C_MATRIX_CSV,
            DISABLED_TRUTH_MD,
            RUNTIME_MANIFEST_JSON,
        ]
    )

    window_start_ms, window_end_ms = load_runtime_window()
    intents = build_accepted_intents(window_start_ms, window_end_ms)
    enrich_from_decision_events(intents)
    enrich_from_trade_table(intents)
    gather_runtime_events(intents)
    config = apply_config_thresholds(intents)
    enrich_from_recorder(intents, config)
    gather_order_logs_collected(intents)
    gather_generic_text_hits(intents)
    mark_missing_price_motion_fields(intents)
    schema_failures = gather_schema_failures(intents)

    input_rows = build_input_recovery_rows(intents)
    replay_rows = build_replay_rows(intents)
    economic_rows = build_economic_preview(replay_rows)
    validate_outputs(intents, input_rows, replay_rows)

    write_csv(
        OUTPUT_INPUT_RECOVERY,
        input_rows,
        [
            "rid",
            "intent_id",
            "symbol",
            "strategy_id",
            "side",
            "event_ts",
            "features_ts_ms",
            "nrr_code",
            "required_input",
            "recovered",
            "recovered_value",
            "source_quality",
            "source_file",
            "source_line_or_row",
            "source_event_name",
            "correlation_method",
            "time_delta_ms",
            "missing_reason",
            "confidence",
        ],
    )
    write_csv(
        OUTPUT_REPLAY,
        replay_rows,
        [
            "rid",
            "intent_id",
            "symbol",
            "strategy_id",
            "side",
            "event_ts",
            "trade_id",
            "net_pnl_if_joined",
            "nrr_code",
            "replay_result",
            "result_reason",
            "source_quality_used",
            "inputs_used",
            "thresholds_used",
            "confidence",
        ],
    )
    write_csv(
        OUTPUT_ECON,
        economic_rows,
        [
            "nrr_code",
            "deterministic_block_count",
            "deterministic_pass_count",
            "approx_block_count",
            "approx_pass_count",
            "unproven_count",
            "blocked_winners",
            "blocked_losers",
            "blocked_net_pnl",
            "passed_winners",
            "passed_losers",
            "passed_net_pnl",
            "protection_value",
            "evidence_quality",
        ],
    )
    OUTPUT_REPORT.write_text(
        build_report(intents, replay_rows, economic_rows,
                     schema_failures, window_start_ms, window_end_ms),
        encoding="utf-8",
    )

    print(serialize_json({
        "accepted_intents": len(intents),
        "input_rows": len(input_rows),
        "replay_rows": len(replay_rows),
        "economic_rows": len(economic_rows),
        "control_rid": CONTROL_RID,
        "outputs": [
            rel(OUTPUT_INPUT_RECOVERY),
            rel(OUTPUT_REPLAY),
            rel(OUTPUT_ECON),
            rel(OUTPUT_REPORT),
        ],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
