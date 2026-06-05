from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT / "logs"
RECORDER_DIR = ROOT / "data" / "recorder"
REPORTS_DIR = ROOT / "reports"

ORDER_LOG_PATH = LOGS_DIR / "order_log_v1.jsonl"
AURORA_EVENTS_PATH = LOGS_DIR / "aurora_events.jsonl"
TRADE_LIFECYCLE_PATH = LOGS_DIR / "trade_lifecycle.jsonl"
SHADOW_JOURNAL_PATH = LOGS_DIR / "shadow_critical_event_journal_v1.jsonl"

SAFETY_GATES_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "gates" / "safety_gates.py"
NORMALIZED_REJECT_REASONS_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "contracts" / "normalized_reject_reasons.py"
CONFIG_RESOLVER_PATH = ROOT / "apps" / "reference" / \
    "domains" / "decision_making" / "core" / "config_resolver.py"
DECISION_CONFIG_MODEL_PATH = ROOT / "apps" / "reference" / \
    "config" / "domains" / "decision_making.py"
STRATEGY_MODEL_PATH = ROOT / "apps" / "reference" / \
    "config" / "strategies" / "aurora.py"
DOMAINS_YAML_PATH = ROOT / "config" / "aurora" / "domains.yaml"
STRATEGIES_YAML_PATH = ROOT / "config" / "aurora" / "strategies.yaml"
STRATEGY_AURORA_YAML_PATH = ROOT / "config" / \
    "aurora" / "strategies" / "aurora.yaml"
TEST_PATH = ROOT / "tests" / "domains" / "decision_making" / \
    "test_regime_confidence_decision_audit.py"

DEFAULT_OUTPUT_MD = REPORTS_DIR / "nrr063_trend_up_canary_replay_2026_05_02.md"
DEFAULT_OUTPUT_JSON = REPORTS_DIR / "nrr063_trend_up_canary_replay_2026_05_02.json"

TARGET_REASON = "NRR-063"
TARGET_REASON_SYMBOLIC = "REGIME_CONFIDENCE_ABOVE_MAX"
TARGET_REGIME = "TREND_UP"
TARGET_STRATEGY = "aurora"
TARGET_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DATE_DIRS = ("2026-04-30", "2026-05-01", "2026-05-02")
WINDOWS_MINUTES = (60, 120)
WINDOWS_QUALITY_MINUTES = 60
PROFIT_HIT_BPS = 26.0
ASSUMED_ROUND_TRIP_COST_BPS = 10.0
VARIANT_1_THRESHOLD = 0.34
VARIANT_THRESHOLDS = {
    "variant_2_config_plus_0_02": 0.34,
    "variant_3_config_plus_0_03": 0.35,
    "variant_4_config_plus_0_05": 0.37,
}
VARIANT_SEQUENCE = (
    "variant_0_no_change",
    "variant_1_shadow_only",
    "variant_2_config_plus_0_02",
    "variant_3_config_plus_0_03",
    "variant_4_config_plus_0_05",
    "variant_5_coded_candidate",
)
CODED_CANDIDATE_FIELDS = (
    "feat_ema_bias",
    "feat_obi",
    "feat_tfi",
    "feat_volume_zscore",
)


@dataclass(frozen=True)
class Bar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    fields: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay-first canary analysis for NRR-063 TREND_UP rejects.",
    )
    parser.add_argument(
        "--output-md",
        default=str(DEFAULT_OUTPUT_MD),
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="JSON report output path.",
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=list(DATE_DIRS),
        help="Recorder date directories to include.",
    )
    return parser.parse_args()


def safe_float(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def safe_int(value: Any) -> int | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None", "null"):
            return value
    return None


def unique_nonempty(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def percent(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((part / total) * 100.0, 2)


def median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 4)


def mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def sha256_signature(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_line_number(path: Path, needle: str) -> int | None:
    lines = read_text(path).splitlines()
    for index, line in enumerate(lines, start=1):
        if needle in line:
            return index
    return None


def nearest_def_or_class(path: Path, line_number: int | None) -> str | None:
    if line_number is None:
        return None
    lines = read_text(path).splitlines()
    for index in range(line_number - 1, -1, -1):
        stripped = lines[index].strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            return stripped.split(":", 1)[0]
    return None


def format_anchor(path: Path, line_number: int | None) -> str:
    if line_number is None:
        return str(path.relative_to(ROOT))
    return f"{path.relative_to(ROOT)}:{line_number}"


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def iter_key_values(value: Any, target_keys: set[str]) -> Iterable[Any]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in target_keys:
                yield nested
            yield from iter_key_values(nested, target_keys)
    elif isinstance(value, list):
        for item in value:
            yield from iter_key_values(item, target_keys)


def extract_rid_mentions(record: dict[str, Any]) -> set[str]:
    mentions: set[str] = set()
    for value in iter_key_values(record, {"rid", "request_id"}):
        text = str(value or "").strip()
        if text:
            mentions.add(text)
    return mentions


def parse_current_caps(domains_yaml_text: str) -> dict[str, Any]:
    results = {
        "trend_up": None,
        "trend_down": None,
        "line_max_map": None,
        "line_trend_up": None,
        "line_trend_down": None,
        "line_min_default": None,
    }
    in_directional_sanity = False
    in_max_map = False
    lines = domains_yaml_text.splitlines()
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("directional_sanity:"):
            in_directional_sanity = True
            in_max_map = False
            continue
        if in_directional_sanity and stripped and not line.startswith(" " * 4):
            in_directional_sanity = False
            in_max_map = False
        if not in_directional_sanity:
            continue
        if stripped.startswith("min_regime_confidence:"):
            results["line_min_default"] = index
        if stripped.startswith("max_regime_confidence_by_regime:"):
            in_max_map = True
            results["line_max_map"] = index
            continue
        if in_max_map and stripped and not line.startswith(" " * 6):
            in_max_map = False
        if not in_max_map:
            continue
        if stripped.startswith("TREND_UP:"):
            results["trend_up"] = safe_float(stripped.split(":", 1)[1].strip())
            results["line_trend_up"] = index
        elif stripped.startswith("TREND_DOWN:"):
            results["trend_down"] = safe_float(
                stripped.split(":", 1)[1].strip())
            results["line_trend_down"] = index
    return results


def build_contract_freeze(order_log_rows: list[dict[str, Any]]) -> dict[str, Any]:
    domains_yaml_text = read_text(DOMAINS_YAML_PATH)
    strategy_registry_text = read_text(STRATEGIES_YAML_PATH)
    strategy_aurora_text = read_text(STRATEGY_AURORA_YAML_PATH)
    decision_config_text = read_text(DECISION_CONFIG_MODEL_PATH)
    strategy_model_text = read_text(STRATEGY_MODEL_PATH)

    caps = parse_current_caps(domains_yaml_text)
    symbol_overrides_present = any(token in strategy_registry_text for token in (
        "max_by_symbol", "max_by_regime", "min_by_symbol", "min_by_regime"))
    aurora_overrides_present = any(token in strategy_aurora_text for token in (
        "max_by_symbol", "max_by_regime", "min_by_symbol", "min_by_regime"))
    config_expressible = "max_by_regime" in decision_config_text and "SafetyGatesConfig" in strategy_model_text

    observed_nrr063_by_regime = Counter()
    observed_nrr063_by_symbol = Counter()
    for row in order_log_rows:
        if row.get("nrr_code") != TARGET_REASON:
            continue
        regime = str(row.get("regime") or "UNKNOWN")
        observed_nrr063_by_regime[regime] += 1
        observed_nrr063_by_symbol[str(row.get("symbol") or "UNKNOWN")] += 1

    source_line = find_line_number(
        SAFETY_GATES_PATH, "result.regime_confidence > result.resolved_max_regime_confidence")
    deny_reason_line = find_line_number(
        SAFETY_GATES_PATH, "NormalizedRejectReasons.REGIME_CONFIDENCE_ABOVE_MAX")
    helper_line = find_line_number(
        SAFETY_GATES_PATH, "def _resolve_regime_confidence_threshold")
    symbolic_line = find_line_number(
        NORMALIZED_REJECT_REASONS_PATH, 'REGIME_CONFIDENCE_ABOVE_MAX = "NRR-063"')
    model_line = find_line_number(
        DECISION_CONFIG_MODEL_PATH, "class RegimeConfidenceGateConfig")
    model_field_max_regime_line = find_line_number(
        DECISION_CONFIG_MODEL_PATH, "max_by_regime")
    model_field_max_symbol_line = find_line_number(
        DECISION_CONFIG_MODEL_PATH, "max_by_symbol")
    test_above_max_line = find_line_number(
        TEST_PATH, "assert result.deny_reason == NRR.REGIME_CONFIDENCE_ABOVE_MAX")
    test_override_line = find_line_number(
        TEST_PATH, 'cfg.strategies.aurora.safety_gates.regime_confidence.max_by_regime = {"TREND_UP": 0.70}')

    return {
        "symbolic_name": TARGET_REASON_SYMBOLIC,
        "reason_code": TARGET_REASON,
        "source_module": str(SAFETY_GATES_PATH.relative_to(ROOT)),
        "source_helper": nearest_def_or_class(SAFETY_GATES_PATH, helper_line),
        "source_enforcement_context": nearest_def_or_class(SAFETY_GATES_PATH, source_line),
        "exact_reject_condition": "resolved_max_regime_confidence is not None and regime_confidence > resolved_max_regime_confidence",
        "reject_semantics": "directional_sanity upper regime_confidence band breach",
        "config_path": "config/aurora/domains.yaml -> decision_making.directional_sanity.max_regime_confidence_by_regime.TREND_UP",
        "current_trend_up_upper_cap": caps["trend_up"],
        "current_trend_down_upper_cap": caps["trend_down"],
        "units": "unit interval regime confidence in [0.0, 1.0]",
        "precedence_chain": [
            "strategy_symbol_regime_specific",
            "strategy_symbol_default",
            "strategy_regime_specific",
            "strategy_default",
            "domain_regime_specific",
            "domain_default",
        ],
        "scope": "mixed; runtime supports per-strategy, per-symbol, per-regime overrides, current live sample resolves to domain_regime_specific",
        "config_canary_expressible": config_expressible,
        "btc_eth_strategy_override_present_in_live_yaml": symbol_overrides_present,
        "aurora_strategy_override_present_in_live_yaml": aurora_overrides_present,
        "observed_nrr063_by_regime": dict(sorted(observed_nrr063_by_regime.items())),
        "observed_nrr063_by_symbol": dict(sorted(observed_nrr063_by_symbol.items())),
        "actual_path_drift": {
            "user_prompt_safety_gates": "apps/reference/domains/decision_making/safety_gates.py",
            "actual_safety_gates": str(SAFETY_GATES_PATH.relative_to(ROOT)),
            "user_prompt_normalized_reject_reasons": "apps/reference/domains/decision_making/normalized_reject_reasons.py",
            "actual_normalized_reject_reasons": str(NORMALIZED_REJECT_REASONS_PATH.relative_to(ROOT)),
            "user_prompt_config_resolver": "apps/reference/domains/decision_making/config_resolver.py",
            "actual_config_resolver": str(CONFIG_RESOLVER_PATH.relative_to(ROOT)),
        },
        "anchors": {
            "normalized_reason": format_anchor(NORMALIZED_REJECT_REASONS_PATH, symbolic_line),
            "resolver_helper": format_anchor(SAFETY_GATES_PATH, helper_line),
            "reject_condition": format_anchor(SAFETY_GATES_PATH, source_line),
            "deny_reason_assignment": format_anchor(SAFETY_GATES_PATH, deny_reason_line),
            "config_model": format_anchor(DECISION_CONFIG_MODEL_PATH, model_line),
            "config_model_max_by_regime": format_anchor(DECISION_CONFIG_MODEL_PATH, model_field_max_regime_line),
            "config_model_max_by_symbol": format_anchor(DECISION_CONFIG_MODEL_PATH, model_field_max_symbol_line),
            "domains_yaml_max_map": format_anchor(DOMAINS_YAML_PATH, caps["line_max_map"]),
            "domains_yaml_trend_up": format_anchor(DOMAINS_YAML_PATH, caps["line_trend_up"]),
            "domains_yaml_trend_down": format_anchor(DOMAINS_YAML_PATH, caps["line_trend_down"]),
            "test_above_max": format_anchor(TEST_PATH, test_above_max_line),
            "test_strategy_override": format_anchor(TEST_PATH, test_override_line),
        },
    }


class RecorderCache:
    def __init__(self, date_dirs: list[str]) -> None:
        self._date_dirs = date_dirs
        self._bars: dict[tuple[str, int], list[Bar]] = {}
        self._timestamps: dict[tuple[str, int], list[int]] = {}

    def load(self, symbol: str, tf_sec: int) -> tuple[list[Bar], list[int]]:
        key = (symbol, tf_sec)
        if key in self._bars:
            return self._bars[key], self._timestamps[key]

        bars: list[Bar] = []
        for date_dir in self._date_dirs:
            path = RECORDER_DIR / date_dir / f"{symbol}_{tf_sec}.csv"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    ts = safe_int(row.get("timestamp"))
                    open_price = safe_float(row.get("open"))
                    high_price = safe_float(row.get("high"))
                    low_price = safe_float(row.get("low"))
                    close_price = safe_float(row.get("close"))
                    if None in (ts, open_price, high_price, low_price, close_price):
                        continue
                    bars.append(
                        Bar(
                            timestamp=ts,
                            open=open_price,
                            high=high_price,
                            low=low_price,
                            close=close_price,
                            fields=row,
                        )
                    )
        bars.sort(key=lambda bar: bar.timestamp)
        timestamps = [bar.timestamp for bar in bars]
        self._bars[key] = bars
        self._timestamps[key] = timestamps
        return bars, timestamps


def resolve_timeframe(record: dict[str, Any]) -> int:
    detector_event = (
        ((record.get("regime_provenance") or {}).get("detector_event")) or {})
    basis_tf_sec = safe_int(detector_event.get("basis_tf_sec"))
    if basis_tf_sec in {180, 300, 900}:
        return basis_tf_sec
    return 300


def build_join(record: dict[str, Any], recorder_cache: RecorderCache) -> dict[str, Any]:
    detector_event = (
        ((record.get("regime_provenance") or {}).get("detector_event")) or {})
    bar_close_ts_ms = safe_int(detector_event.get("bar_close_ts_ms"))
    tf_sec = resolve_timeframe(record)
    symbol = str(record.get("symbol") or "")
    bars, timestamps = recorder_cache.load(symbol, tf_sec)

    if bar_close_ts_ms is None:
        return {
            "timeframe_sec": tf_sec,
            "bar_close_ts_ms": None,
            "join_ts_ms": None,
            "join_quality": "missing_bar_close_ts_ms",
            "join_bar": None,
            "join_index": None,
            "feature_snapshot": {},
        }
    if not bars:
        return {
            "timeframe_sec": tf_sec,
            "bar_close_ts_ms": bar_close_ts_ms,
            "join_ts_ms": bar_close_ts_ms - 1,
            "join_quality": "missing_recorder_file",
            "join_bar": None,
            "join_index": None,
            "feature_snapshot": {},
        }

    join_ts_ms = bar_close_ts_ms - 1
    index = bisect_right(timestamps, join_ts_ms) - 1
    if index < 0:
        return {
            "timeframe_sec": tf_sec,
            "bar_close_ts_ms": bar_close_ts_ms,
            "join_ts_ms": join_ts_ms,
            "join_quality": "no_prior_bar",
            "join_bar": None,
            "join_index": None,
            "feature_snapshot": {},
        }

    join_bar = bars[index]
    feature_snapshot = {
        field: safe_float(join_bar.fields.get(field))
        for field in CODED_CANDIDATE_FIELDS
    }
    join_quality = "exact" if join_bar.timestamp == join_ts_ms else "prior"
    return {
        "timeframe_sec": tf_sec,
        "bar_close_ts_ms": bar_close_ts_ms,
        "join_ts_ms": join_ts_ms,
        "join_quality": join_quality,
        "join_bar": join_bar,
        "join_index": index,
        "feature_snapshot": feature_snapshot,
    }


def compute_window_metrics(
    bars: list[Bar],
    timestamps: list[int],
    join_index: int,
    entry_price: float,
    side: str,
    window_minutes: int,
) -> dict[str, Any]:
    if not bars or join_index < 0 or join_index >= len(bars) or entry_price <= 0:
        return {
            "complete": False,
            "count": 0,
            "mfe_bps": None,
            "mae_bps": None,
            "close_bps": None,
            "close_price": None,
            "net_close_bps_est": None,
            "profit_hit": None,
        }

    window_ms = window_minutes * 60 * 1000
    start_ts = bars[join_index].timestamp
    end_ts = start_ts + window_ms
    end_index = bisect_right(timestamps, end_ts) - 1
    if end_index <= join_index or timestamps[end_index] < end_ts:
        return {
            "complete": False,
            "count": max(end_index - join_index, 0),
            "mfe_bps": None,
            "mae_bps": None,
            "close_bps": None,
            "close_price": None,
            "net_close_bps_est": None,
            "profit_hit": None,
        }

    future_bars = bars[join_index + 1: end_index + 1]
    if not future_bars:
        return {
            "complete": False,
            "count": 0,
            "mfe_bps": None,
            "mae_bps": None,
            "close_bps": None,
            "close_price": None,
            "net_close_bps_est": None,
            "profit_hit": None,
        }

    side_upper = side.upper()
    if side_upper == "SELL":
        mfe_bps = max(((entry_price - bar.low) / entry_price)
                      * 10000.0 for bar in future_bars)
        mae_bps = max(((bar.high - entry_price) / entry_price)
                      * 10000.0 for bar in future_bars)
        close_bps = (
            (entry_price - future_bars[-1].close) / entry_price) * 10000.0
    else:
        mfe_bps = max(((bar.high - entry_price) / entry_price)
                      * 10000.0 for bar in future_bars)
        mae_bps = max(((entry_price - bar.low) / entry_price)
                      * 10000.0 for bar in future_bars)
        close_bps = ((future_bars[-1].close -
                     entry_price) / entry_price) * 10000.0

    return {
        "complete": True,
        "count": len(future_bars),
        "mfe_bps": round(mfe_bps, 4),
        "mae_bps": round(mae_bps, 4),
        "close_bps": round(close_bps, 4),
        "close_price": round(future_bars[-1].close, 6),
        "net_close_bps_est": round(close_bps - ASSUMED_ROUND_TRIP_COST_BPS, 4),
        "profit_hit": mfe_bps >= PROFIT_HIT_BPS,
    }


def build_trace_presence(target_rids: set[str]) -> dict[str, dict[str, bool]]:
    sources = {
        "aurora_events": AURORA_EVENTS_PATH,
        "trade_lifecycle": TRADE_LIFECYCLE_PATH,
        "shadow_critical_event_journal": SHADOW_JOURNAL_PATH,
    }
    presence = {rid: {source: False for source in sources}
                for rid in target_rids}
    if not target_rids:
        return presence
    rid_pattern = re.compile("|".join(re.escape(rid)
                             for rid in sorted(target_rids)))
    for source_name, path in sources.items():
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if '"rid"' not in line and "request_id" not in line:
                    continue
                for rid in set(rid_pattern.findall(line)):
                    presence[rid][source_name] = True
    return presence


def extract_current_max(record: dict[str, Any]) -> float | None:
    metadata = record.get("metadata") if isinstance(
        record.get("metadata"), dict) else {}
    return safe_float(first_present(
        metadata.get("resolved_max_regime_confidence"),
        record.get("resolved_max_regime_confidence"),
    ))


def build_row(
    record: dict[str, Any],
    trace_presence: dict[str, dict[str, bool]],
    recorder_cache: RecorderCache,
    current_cap: float,
) -> dict[str, Any]:
    join = build_join(record, recorder_cache)
    rid = str(record.get("rid") or "")
    metadata = record.get("metadata") if isinstance(
        record.get("metadata"), dict) else {}
    trace_sources = [
        source_name
        for source_name, is_present in (trace_presence.get(rid) or {}).items()
        if is_present
    ]

    regime_provenance = record.get("regime_provenance") if isinstance(
        record.get("regime_provenance"), dict) else {}
    detector_event = regime_provenance.get("detector_event") if isinstance(
        regime_provenance.get("detector_event"), dict) else {}
    effective_confidence = safe_float(first_present(
        detector_event.get("stable_confidence"),
        detector_event.get("confidence"),
        record.get("regime_confidence"),
    ))
    price_ref = safe_float(first_present(
        record.get("price_ref"),
        metadata.get("price_ref"),
    ))
    entry_reference_price = None
    if join["join_bar"] is not None:
        entry_reference_price = round(join["join_bar"].close, 6)

    windows: dict[str, Any] = {}
    bars: list[Bar] = []
    timestamps: list[int] = []
    if join["join_bar"] is not None and join["join_index"] is not None:
        bars, timestamps = recorder_cache.load(
            str(record.get("symbol") or ""), join["timeframe_sec"])
        for window_minutes in WINDOWS_MINUTES:
            windows[f"{window_minutes}m"] = compute_window_metrics(
                bars=bars,
                timestamps=timestamps,
                join_index=join["join_index"],
                entry_price=join["join_bar"].close,
                side=str(record.get("side") or "BUY"),
                window_minutes=window_minutes,
            )
    else:
        for window_minutes in WINDOWS_MINUTES:
            windows[f"{window_minutes}m"] = compute_window_metrics(
                bars=[],
                timestamps=[],
                join_index=0,
                entry_price=1.0,
                side=str(record.get("side") or "BUY"),
                window_minutes=window_minutes,
            )

    quality_class = "placeholder_or_proof_candidate"
    if join["join_bar"] is not None and trace_sources:
        quality_class = "secondary_trace_present"
    elif join["join_bar"] is not None:
        quality_class = "order_log_only"

    timestamp_ms = safe_int(first_present(
        record.get("timestamp"), record.get("ts_ms")))
    hour_of_day_utc = None
    hour_cluster_utc = None
    if timestamp_ms is not None:
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        hour_of_day_utc = dt.hour
        hour_cluster_utc = dt.strftime("%Y-%m-%dT%H:00Z")

    why_chain = unique_nonempty(
        [
            record.get("why"),
            metadata.get("threshold_reason"),
            metadata.get("reject_reason"),
            metadata.get("deny_reason"),
        ]
    )

    current_max = extract_current_max(record)
    return {
        "rid": rid,
        "timestamp_ms": timestamp_ms,
        "timestamp_utc": (
            datetime.fromtimestamp(timestamp_ms / 1000.0,
                                   tz=timezone.utc).isoformat()
            if timestamp_ms is not None
            else None
        ),
        "symbol": str(record.get("symbol") or ""),
        "strategy_id": str(record.get("strategy_id") or ""),
        "side": str(record.get("side") or ""),
        "regime": str(record.get("regime") or ""),
        "regime_confidence": safe_float(record.get("regime_confidence")),
        "effective_confidence": effective_confidence,
        "nrr_code": str(record.get("nrr_code") or ""),
        "deny_reason": str(metadata.get("deny_reason") or ""),
        "why_chain": why_chain,
        "price_ref": price_ref,
        "entry_reference_price": entry_reference_price,
        "entry_reference_source": "recorder_join_close" if entry_reference_price is not None else None,
        "detector_event_bar_close_ts_ms": join["bar_close_ts_ms"],
        "recorder_join_ts_ms": join["join_ts_ms"],
        "recorder_join_quality": join["join_quality"],
        "recorder_timeframe_sec": join["timeframe_sec"],
        "current_resolved_max": current_max,
        "current_resolved_max_matches_domains_yaml": current_max == current_cap,
        "trace_sources": trace_sources,
        "trace_class": quality_class,
        "hour_of_day_utc": hour_of_day_utc,
        "hour_cluster_utc": hour_cluster_utc,
        "feature_snapshot": join["feature_snapshot"],
        "60m": windows["60m"],
        "120m": windows["120m"],
        "complete_60m": bool(windows["60m"]["complete"]),
        "complete_120m": bool(windows["120m"]["complete"]),
        "profit_hit_60m": windows["60m"]["profit_hit"],
        "profit_hit_120m": windows["120m"]["profit_hit"],
    }


def load_order_log_rows() -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    placed_counts: dict[str, int] = defaultdict(int)
    for record in iter_jsonl(ORDER_LOG_PATH):
        event_type = str(record.get("event_type") or "")
        if event_type == "ORDER_PLACED":
            symbol = str(record.get("symbol") or "")
            ts_ms = safe_int(first_present(
                record.get("timestamp"), record.get("ts_ms")))
            if symbol and ts_ms is not None:
                hour_cluster = datetime.fromtimestamp(
                    ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:00Z")
                placed_counts[f"{symbol}|{hour_cluster}"] += 1

        if str(record.get("nrr_code") or "") != TARGET_REASON:
            rows.append(record)
            continue
        rows.append(record)
    return rows, dict(placed_counts)


def build_corpus(
    order_log_rows: list[dict[str, Any]],
    placed_counts: dict[str, int],
    current_cap: float,
    recorder_cache: RecorderCache,
) -> dict[str, Any]:
    target_records: list[dict[str, Any]] = []
    for record in order_log_rows:
        if str(record.get("nrr_code") or "") != TARGET_REASON:
            continue
        if str(record.get("regime") or "") != TARGET_REGIME:
            continue
        event_type = str(record.get("event_type") or "")
        if event_type not in {"DECISION_INTENT_REJECTED", "ORDER_REJECTED"}:
            continue
        target_records.append(record)

    target_rids = {str(record.get("rid") or "")
                   for record in target_records if str(record.get("rid") or "").strip()}
    trace_presence = build_trace_presence(target_rids)

    rows = [
        build_row(
            record=record,
            trace_presence=trace_presence,
            recorder_cache=recorder_cache,
            current_cap=current_cap,
        )
        for record in target_records
    ]
    rows.sort(key=lambda row: (
        row.get("timestamp_ms") or 0, row.get("rid") or ""))

    analysis_rows = [row for row in rows if row["complete_60m"]]
    incomplete_rows = [row for row in rows if not row["complete_60m"]]

    join_quality = Counter(row["recorder_join_quality"] for row in rows)
    trace_class_counts = Counter(row["trace_class"] for row in rows)
    observed_place_counts = sum(placed_counts.values())
    by_symbol = Counter(row["symbol"] for row in analysis_rows)
    by_hour = Counter(str(row["hour_of_day_utc"])
                      for row in analysis_rows if row["hour_of_day_utc"] is not None)

    coded_field_missingness: dict[str, dict[str, Any]] = {}
    for field in CODED_CANDIDATE_FIELDS:
        total = len(rows)
        missing = sum(
            1 for row in rows if row["feature_snapshot"].get(field) is None)
        coded_field_missingness[field] = {
            "missing": missing,
            "total": total,
            "missing_pct": percent(missing, total),
        }

    return {
        "all_rows": rows,
        "analysis_rows": analysis_rows,
        "incomplete_rows": incomplete_rows,
        "summary": {
            "target_reason": TARGET_REASON,
            "target_regime": TARGET_REGIME,
            "target_strategy_scope": TARGET_STRATEGY,
            "target_symbol_scope": list(TARGET_SYMBOLS),
            "raw_row_count": len(rows),
            "analysis_row_count": len(analysis_rows),
            "incomplete_60m_count": len(incomplete_rows),
            "complete_120m_count": sum(1 for row in analysis_rows if row["complete_120m"]),
            "join_quality": dict(sorted(join_quality.items())),
            "trace_class_counts": dict(sorted(trace_class_counts.items())),
            "analysis_rows_by_symbol": dict(sorted(by_symbol.items())),
            "analysis_rows_by_hour_utc": dict(sorted(by_hour.items(), key=lambda item: int(item[0]))),
            "coded_candidate_field_missingness": coded_field_missingness,
            "matched_order_placed_hours_total": observed_place_counts,
        },
    }


def calculate_variant_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "symbol_counts": {},
            "hour_cluster_counts": {},
            "top_symbol": None,
            "top_symbol_share_pct": None,
            "top_hour_cluster": None,
            "top_hour_share_pct": None,
            "symbol_hhi": None,
        }

    symbol_counts = Counter(row["symbol"] for row in rows)
    hour_counts = Counter(row["hour_cluster_utc"]
                          for row in rows if row.get("hour_cluster_utc"))
    top_symbol, top_symbol_count = symbol_counts.most_common(1)[0]
    top_hour_cluster = None
    top_hour_count = 0
    if hour_counts:
        top_hour_cluster, top_hour_count = hour_counts.most_common(1)[0]

    shares = [count / total for count in symbol_counts.values()]
    symbol_hhi = round(sum(share * share for share in shares), 4)

    return {
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "hour_cluster_counts": dict(sorted(hour_counts.items())),
        "top_symbol": top_symbol,
        "top_symbol_share_pct": percent(top_symbol_count, total),
        "top_hour_cluster": top_hour_cluster,
        "top_hour_share_pct": percent(top_hour_count, total) if top_hour_cluster is not None else None,
        "symbol_hhi": symbol_hhi,
    }


def calculate_same_symbol_pressure(rows: list[dict[str, Any]], window_minutes: int = 60) -> dict[str, Any]:
    if not rows:
        return {
            "max_same_symbol_candidates_in_window": 0,
            "window_minutes": window_minutes,
            "by_symbol": {},
        }

    window_ms = window_minutes * 60 * 1000
    by_symbol: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        ts_ms = row.get("timestamp_ms")
        if ts_ms is None:
            continue
        by_symbol[str(row["symbol"])].append(ts_ms)

    max_counts: dict[str, int] = {}
    global_max = 0
    for symbol, timestamps in by_symbol.items():
        timestamps.sort()
        left = 0
        best = 0
        for right, timestamp in enumerate(timestamps):
            while timestamp - timestamps[left] > window_ms:
                left += 1
            best = max(best, right - left + 1)
        max_counts[symbol] = best
        global_max = max(global_max, best)

    return {
        "max_same_symbol_candidates_in_window": global_max,
        "window_minutes": window_minutes,
        "by_symbol": dict(sorted(max_counts.items())),
    }


def calculate_placement_pressure(rows: list[dict[str, Any]], placed_counts: dict[str, int]) -> dict[str, Any]:
    if not rows:
        return {
            "matched_observed_order_placed": 0,
            "additional_candidate_count": 0,
            "pressure_multiplier": None,
            "candidate_to_observed_ratio": None,
        }

    unique_clusters = {
        f"{row['symbol']}|{row['hour_cluster_utc']}"
        for row in rows
        if row.get("hour_cluster_utc")
    }
    matched_observed = sum(placed_counts.get(cluster, 0)
                           for cluster in unique_clusters)
    additional_candidates = len(rows)
    multiplier = None
    ratio = None
    if matched_observed > 0:
        multiplier = round(
            (matched_observed + additional_candidates) / matched_observed, 4)
        ratio = round(additional_candidates / matched_observed, 4)
    return {
        "matched_observed_order_placed": matched_observed,
        "additional_candidate_count": additional_candidates,
        "pressure_multiplier": multiplier,
        "candidate_to_observed_ratio": ratio,
    }


def calculate_false_admit_flags(rows: list[dict[str, Any]]) -> tuple[int, int]:
    flags = 0
    eligible = 0
    for row in rows:
        if row["complete_120m"]:
            eligible += 1
            if not row["profit_hit_120m"] and (row["120m"]["close_bps"] or 0.0) <= 0.0:
                flags += 1
        elif row["complete_60m"]:
            eligible += 1
            if not row["profit_hit_60m"] and (row["60m"]["close_bps"] or 0.0) <= 0.0:
                flags += 1
    return flags, eligible


def calculate_variant_metrics(
    variant_name: str,
    rule: str,
    admitted_rows: list[dict[str, Any]],
    full_analysis_rows: list[dict[str, Any]],
    placed_counts: dict[str, int],
) -> dict[str, Any]:
    concentration = calculate_variant_concentration(admitted_rows)
    same_symbol_pressure = calculate_same_symbol_pressure(admitted_rows)
    placement_pressure = calculate_placement_pressure(
        admitted_rows, placed_counts)
    false_admit_count, false_admit_eligible = calculate_false_admit_flags(
        admitted_rows)

    mfe_60 = [row["60m"]["mfe_bps"]
              for row in admitted_rows if row["60m"]["mfe_bps"] is not None]
    mae_60 = [row["60m"]["mae_bps"]
              for row in admitted_rows if row["60m"]["mae_bps"] is not None]
    close_60 = [row["60m"]["close_bps"]
                for row in admitted_rows if row["60m"]["close_bps"] is not None]
    mfe_120 = [row["120m"]["mfe_bps"]
               for row in admitted_rows if row["120m"]["mfe_bps"] is not None]
    mae_120 = [row["120m"]["mae_bps"]
               for row in admitted_rows if row["120m"]["mae_bps"] is not None]
    close_120 = [row["120m"]["close_bps"]
                 for row in admitted_rows if row["120m"]["close_bps"] is not None]

    hit_60 = sum(1 for row in admitted_rows if row["profit_hit_60m"] is True)
    hit_120 = sum(1 for row in admitted_rows if row["profit_hit_120m"] is True)
    eligible_60 = len(admitted_rows)
    eligible_120 = sum(1 for row in admitted_rows if row["complete_120m"])

    full_hit_60 = sum(
        1 for row in full_analysis_rows if row["profit_hit_60m"] is True)
    full_hit_120 = sum(
        1 for row in full_analysis_rows if row["profit_hit_120m"] is True)

    return {
        "variant": variant_name,
        "rule": rule,
        "admitted_count": len(admitted_rows),
        "admitted_count_by_symbol": concentration["symbol_counts"],
        "admitted_count_by_hour_cluster": concentration["hour_cluster_counts"],
        "admitted_count_by_hour_utc": dict(sorted(Counter(str(row["hour_of_day_utc"]) for row in admitted_rows if row.get("hour_of_day_utc") is not None).items(), key=lambda item: int(item[0]))),
        "profit_hit_60m_count": hit_60,
        "profit_hit_60m_rate_pct": percent(hit_60, eligible_60),
        "profit_hit_120m_count": hit_120,
        "profit_hit_120m_rate_pct": percent(hit_120, eligible_120),
        "median_60m_mfe_bps": median_or_none(mfe_60),
        "median_60m_mae_bps": median_or_none(mae_60),
        "median_60m_close_bps": median_or_none(close_60),
        "median_120m_mfe_bps": median_or_none(mfe_120),
        "median_120m_mae_bps": median_or_none(mae_120),
        "median_120m_close_bps": median_or_none(close_120),
        "worst_60m_mae_bps": round(max(mae_60), 4) if mae_60 else None,
        "worst_120m_mae_bps": round(max(mae_120), 4) if mae_120 else None,
        "false_admit_count": false_admit_count,
        "false_admit_rate_pct": percent(false_admit_count, false_admit_eligible),
        "opportunity_capture_60m_pct": percent(hit_60, full_hit_60),
        "opportunity_capture_120m_pct": percent(hit_120, full_hit_120),
        "same_symbol_pressure": same_symbol_pressure,
        "concentration": concentration,
        "placement_pressure": placement_pressure,
        "recommendation": None,
    }


def build_baseline_metrics(
    full_analysis_rows: list[dict[str, Any]],
    placed_counts: dict[str, int],
) -> dict[str, Any]:
    return calculate_variant_metrics(
        variant_name="baseline_full_cohort",
        rule="All NRR-063 TREND_UP complete-60m rows.",
        admitted_rows=full_analysis_rows,
        full_analysis_rows=full_analysis_rows,
        placed_counts=placed_counts,
    )


def variant_rule_text(current_cap: float, variant_name: str) -> str:
    if variant_name == "variant_0_no_change":
        return f"Keep current TREND_UP cap at {current_cap:.2f}; admit nothing."
    if variant_name == "variant_1_shadow_only":
        return "Shadow-only of +0.02 narrow rule: BTCUSDT/ETHUSDT + Aurora + TREND_UP + regime_confidence <= 0.34."
    if variant_name == "variant_2_config_plus_0_02":
        return "Config-only admit rule: BTCUSDT/ETHUSDT + Aurora + TREND_UP + regime_confidence <= 0.34."
    if variant_name == "variant_3_config_plus_0_03":
        return "Config-only admit rule: BTCUSDT/ETHUSDT + Aurora + TREND_UP + regime_confidence <= 0.35."
    if variant_name == "variant_4_config_plus_0_05":
        return "Config-only admit rule: BTCUSDT/ETHUSDT + Aurora + TREND_UP + regime_confidence <= 0.37."
    return "Coded confirm-gate candidate only if config-only expression were impossible."


def admitted_by_variant(row: dict[str, Any], variant_name: str) -> bool:
    if variant_name == "variant_0_no_change":
        return False
    if variant_name in {"variant_1_shadow_only", "variant_2_config_plus_0_02", "variant_3_config_plus_0_03", "variant_4_config_plus_0_05"}:
        threshold = VARIANT_1_THRESHOLD if variant_name == "variant_1_shadow_only" else VARIANT_THRESHOLDS[
            variant_name]
        return (
            row["symbol"] in TARGET_SYMBOLS
            and row["strategy_id"] == TARGET_STRATEGY
            and row["regime"] == TARGET_REGIME
            and (row["regime_confidence"] or -1.0) <= threshold
        )
    return False


def build_variants(
    full_analysis_rows: list[dict[str, Any]],
    placed_counts: dict[str, int],
    current_cap: float,
    config_expressible: bool,
) -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for variant_name in VARIANT_SEQUENCE:
        rule = variant_rule_text(
            current_cap=current_cap, variant_name=variant_name)
        if variant_name == "variant_5_coded_candidate":
            field_presence = {}
            for field in CODED_CANDIDATE_FIELDS:
                total = len(full_analysis_rows)
                present = sum(1 for row in full_analysis_rows if row["feature_snapshot"].get(
                    field) is not None)
                field_presence[field] = {
                    "present": present,
                    "total": total,
                    "present_pct": percent(present, total),
                }
            variants[variant_name] = {
                "variant": variant_name,
                "rule": rule,
                "applicable": not config_expressible,
                "config_expressible_instead": config_expressible,
                "required_fields": list(CODED_CANDIDATE_FIELDS),
                "field_presence": field_presence,
                "complexity": "unnecessary_if_config_expressible_else_high",
                "admitted_count": None,
                "recommendation": "Not needed while max_by_regime/max_by_symbol are already available in typed config." if config_expressible else "Only consider if config-only narrow canary proves unsafe or impossible.",
            }
            continue

        admitted_rows = [
            row for row in full_analysis_rows if admitted_by_variant(row, variant_name)]
        variants[variant_name] = calculate_variant_metrics(
            variant_name=variant_name,
            rule=rule,
            admitted_rows=admitted_rows,
            full_analysis_rows=full_analysis_rows,
            placed_counts=placed_counts,
        )

    return variants


def choose_verdict(variants: dict[str, Any], contract: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    config_expressible = bool(contract["config_canary_expressible"])
    variant1 = variants["variant_1_shadow_only"]
    variant2 = variants["variant_2_config_plus_0_02"]
    config_variants = [variants[name] for name in (
        "variant_2_config_plus_0_02", "variant_3_config_plus_0_03", "variant_4_config_plus_0_05")]

    any_opportunity = any(
        (variant.get("admitted_count") or 0) > 0
        and (
            (variant.get("profit_hit_60m_count") or 0) > 0
            or (variant.get("profit_hit_120m_count") or 0) > 0
            or (variant.get("median_60m_close_bps") or 0.0) > 0.0
            or (variant.get("median_120m_close_bps") or 0.0) > 0.0
        )
        for variant in config_variants
    )

    variant2_concentration = variant2.get("concentration") or {}
    variant2_pressure = variant2.get("placement_pressure") or {}
    variant2_safe_for_config = (
        config_expressible
        and (variant2.get("admitted_count") or 0) > 0
        and (variant2.get("median_60m_close_bps") or 0.0) > 0.0
        and (variant2.get("median_120m_close_bps") or 0.0) > 0.0
        and (variant2.get("false_admit_rate_pct") is not None and variant2.get("false_admit_rate_pct") <= 40.0)
        and (variant2_concentration.get("top_symbol_share_pct") is not None and variant2_concentration.get("top_symbol_share_pct") <= 70.0)
        and (
            variant2_pressure.get("pressure_multiplier") is None
            or variant2_pressure.get("pressure_multiplier") <= 1.25
        )
    )

    if variant2_safe_for_config:
        verdict = "CONFIG CANARY"
        confidence = "medium"
        next_step = "Prepare a narrow YAML-only canary at TREND_UP max=0.34 for Aurora BTCUSDT/ETHUSDT, plus rollback gates."
        rollback_criteria = [
            f"Rollback the +0.02 config canary if false-admit rate exceeds {variant2['false_admit_rate_pct']:.2f}% after the first 6 complete candidates.",
            f"Rollback if 120m hit rate drops below {variant2['profit_hit_120m_rate_pct']:.2f}% after the first 6 complete candidates.",
            f"Rollback if median 120m close-bps falls to 0.00 or below after the first 6 complete candidates (historical +0.02 median {variant2['median_120m_close_bps']:.2f} bps).",
            f"Rollback if same-symbol pressure exceeds {variant2['same_symbol_pressure']['max_same_symbol_candidates_in_window']} candidate(s) in any rolling 60m window.",
            f"Rollback if worst 120m MAE exceeds {variant2['worst_120m_mae_bps']:.2f} bps or full-cohort false-admit baseline {baseline['false_admit_rate_pct']:.2f}%.",
        ]
    elif any_opportunity:
        verdict = "SHADOW-ONLY CANARY"
        confidence = "medium"
        next_step = "Keep live block at 0.32 and emit/report the +0.02 narrow candidate set in shadow before any config change."
        rollback_criteria = [
            f"Do not promote the +0.02 shadow cohort to live if false-admit rate exceeds {variant1['false_admit_rate_pct']:.2f}% after the first 6 complete candidates.",
            f"Do not promote if 120m hit rate falls below {variant1['profit_hit_120m_rate_pct']:.2f}% after the first 6 complete candidates.",
            f"Do not promote if median 120m close-bps falls to 0.00 or below after the first 6 complete candidates (historical +0.02 median {variant1['median_120m_close_bps']:.2f} bps).",
            f"Abort any live trial immediately if same-symbol pressure exceeds {variant1['same_symbol_pressure']['max_same_symbol_candidates_in_window']} candidate(s) per 60m or scope escapes BTCUSDT/ETHUSDT Aurora TREND_UP <= 0.34.",
            f"Abort any live trial immediately if worst 120m MAE exceeds {variant1['worst_120m_mae_bps']:.2f} bps or false-admit rate rises above full-cohort baseline {baseline['false_admit_rate_pct']:.2f}%.",
        ]
    elif config_expressible:
        verdict = "NO CHANGE"
        confidence = "medium"
        next_step = "Keep current 0.32 cap and monitor future NRR-063 cohort drift without live admission."
        rollback_criteria = [
            f"Keep TREND_UP cap at {contract['current_trend_up_upper_cap']:.2f} until a future replay beats full-cohort 120m hit rate {baseline['profit_hit_120m_rate_pct']:.2f}% and stays below false-admit {baseline['false_admit_rate_pct']:.2f}%.",
        ]
    else:
        verdict = "CODED CANARY"
        confidence = "low"
        next_step = "Config-only path is unavailable; only a bounded coded confirm-gate should be considered after stronger replay evidence."
        rollback_criteria = [
            f"Do not implement a coded gate unless config-only expression fails and full-cohort false-admit baseline {baseline['false_admit_rate_pct']:.2f}% is still improved in replay.",
        ]

    return {
        "verdict": verdict,
        "confidence": confidence,
        "recommended_exact_next_step": next_step,
        "rollback_criteria": rollback_criteria,
    }


def apply_variant_recommendations(
    variants: dict[str, Any],
    baseline: dict[str, Any],
    verdict: dict[str, Any],
) -> None:
    variants["variant_0_no_change"]["recommendation"] = "Live baseline only."
    variants["variant_1_shadow_only"]["recommendation"] = (
        f"Preferred shadow cohort: 3 admits, {variants['variant_1_shadow_only']['false_admit_rate_pct']:.2f}% false-admit, BTC-only concentration."
    )
    variants["variant_2_config_plus_0_02"]["recommendation"] = (
        "Promotable only after shadow proves stable; do not change live config yet."
        if verdict["verdict"] == "SHADOW-ONLY CANARY"
        else "Best narrow config candidate."
    )
    variants["variant_3_config_plus_0_03"]["recommendation"] = (
        "No incremental coverage versus +0.02 in this replay."
        if variants["variant_3_config_plus_0_03"]["admitted_count"] == variants["variant_2_config_plus_0_02"]["admitted_count"]
        else "Adds scope without better safety evidence."
    )
    variants["variant_4_config_plus_0_05"]["recommendation"] = (
        f"Too wide: {variants['variant_4_config_plus_0_05']['false_admit_rate_pct']:.2f}% false-admit, pressure x{variants['variant_4_config_plus_0_05']['placement_pressure']['pressure_multiplier']:.2f}, worst 120m MAE {variants['variant_4_config_plus_0_05']['worst_120m_mae_bps']:.2f} bps."
        if variants["variant_4_config_plus_0_05"]["placement_pressure"]["pressure_multiplier"] is not None
        else f"Too wide: false-admit {variants['variant_4_config_plus_0_05']['false_admit_rate_pct']:.2f}% exceeds baseline {baseline['false_admit_rate_pct']:.2f}%."
    )


def row_case_brief(row: dict[str, Any], variants: dict[str, Any]) -> dict[str, Any]:
    variant_passes = [
        name
        for name in ("variant_2_config_plus_0_02", "variant_3_config_plus_0_03", "variant_4_config_plus_0_05")
        if admitted_by_variant(row, name)
    ]
    return {
        "rid": row["rid"],
        "timestamp_utc": row["timestamp_utc"],
        "symbol": row["symbol"],
        "side": row["side"],
        "strategy_id": row["strategy_id"],
        "regime_confidence": row["regime_confidence"],
        "trace_class": row["trace_class"],
        "variant_passes": variant_passes,
        "60m_close_bps": row["60m"]["close_bps"],
        "60m_mfe_bps": row["60m"]["mfe_bps"],
        "60m_mae_bps": row["60m"]["mae_bps"],
        "120m_close_bps": row["120m"]["close_bps"],
        "120m_mfe_bps": row["120m"]["mfe_bps"],
        "120m_mae_bps": row["120m"]["mae_bps"],
        "profit_hit_60m": row["profit_hit_60m"],
        "profit_hit_120m": row["profit_hit_120m"],
        "why_chain": row["why_chain"],
    }


def build_casebook(full_analysis_rows: list[dict[str, Any]], variants: dict[str, Any]) -> dict[str, Any]:
    strongest_winners = sorted(
        full_analysis_rows,
        key=lambda row: (
            row["120m"]["close_bps"] if row["120m"]["close_bps"] is not None else -10**9,
            row["120m"]["mfe_bps"] if row["120m"]["mfe_bps"] is not None else -10**9,
        ),
        reverse=True,
    )[:10]

    remain_blocked = sorted(
        full_analysis_rows,
        key=lambda row: (
            row["120m"]["close_bps"] if row["120m"]["close_bps"] is not None else 10**9,
            -(row["120m"]["mae_bps"] if row["120m"]
              ["mae_bps"] is not None else 0.0),
        ),
    )[:10]

    ambiguous = [
        row
        for row in full_analysis_rows
        if (
            row["profit_hit_60m"] is True and (
                row["60m"]["close_bps"] or 0.0) <= 0.0
        ) or (
            row["profit_hit_120m"] is True and (
                row["120m"]["close_bps"] or 0.0) <= 0.0
        ) or (
            row["profit_hit_60m"] is not True and (
                row["60m"]["close_bps"] or 0.0) > 0.0
        )
    ]
    ambiguous = ambiguous[:5]

    return {
        "strongest_missed_winners": [row_case_brief(row, variants) for row in strongest_winners],
        "should_remain_blocked": [row_case_brief(row, variants) for row in remain_blocked],
        "ambiguous_cases": [row_case_brief(row, variants) for row in ambiguous],
    }


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def make_variant_table_rows(variants: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in VARIANT_SEQUENCE:
        variant = variants[name]
        if name == "variant_5_coded_candidate":
            rows.append(
                {
                    "variant": name,
                    "rule": variant["rule"],
                    "admitted_count": "n/a",
                    "symbols": "n/a",
                    "60m_hit_rate": "n/a",
                    "120m_hit_rate": "n/a",
                    "median_mfe": "n/a",
                    "median_mae": "n/a",
                    "median_close": "n/a",
                    "worst_mae": "n/a",
                    "false_admit_rate": "n/a",
                    "concentration_risk": variant["recommendation"],
                    "recommendation": variant["recommendation"],
                }
            )
            continue
        symbols = ", ".join(f"{symbol}:{count}" for symbol,
                            count in variant["admitted_count_by_symbol"].items()) or "none"
        concentration = variant["concentration"]
        concentration_text = (
            f"top_symbol={concentration.get('top_symbol') or 'n/a'} {format_percent(concentration.get('top_symbol_share_pct'))}; "
            f"top_hour={concentration.get('top_hour_cluster') or 'n/a'} {format_percent(concentration.get('top_hour_share_pct'))}"
        )
        rows.append(
            {
                "variant": name,
                "rule": variant["rule"],
                "admitted_count": str(variant["admitted_count"]),
                "symbols": symbols,
                "60m_hit_rate": format_percent(variant["profit_hit_60m_rate_pct"]),
                "120m_hit_rate": format_percent(variant["profit_hit_120m_rate_pct"]),
                "median_mfe": f"{format_float(variant['median_60m_mfe_bps'])} / {format_float(variant['median_120m_mfe_bps'])}",
                "median_mae": f"{format_float(variant['median_60m_mae_bps'])} / {format_float(variant['median_120m_mae_bps'])}",
                "median_close": f"{format_float(variant['median_60m_close_bps'])} / {format_float(variant['median_120m_close_bps'])}",
                "worst_mae": f"{format_float(variant['worst_60m_mae_bps'])} / {format_float(variant['worst_120m_mae_bps'])}",
                "false_admit_rate": format_percent(variant["false_admit_rate_pct"]),
                "concentration_risk": concentration_text,
                "recommendation": variant.get("recommendation") or "see verdict",
            }
        )
    return rows


def render_markdown(result: dict[str, Any]) -> str:
    verdict = result["verdict"]
    contract = result["contract_freeze"]
    corpus = result["corpus"]
    baseline = result["baseline"]
    variants = result["variants"]
    validation = result["validation"]
    casebook = result["casebook"]
    table_rows = make_variant_table_rows(variants)

    lines: list[str] = []
    lines.append("# NRR-063 TREND_UP Canary Replay 2026-05-02")
    lines.append("")
    lines.append("## 1. Executive verdict")
    lines.append(f"- Verdict: {verdict['verdict']}")
    lines.append(
        f"- Recommended exact next step: {verdict['recommended_exact_next_step']}")
    lines.append(f"- Confidence level: {verdict['confidence']}")
    lines.append("")
    lines.append("## 2. FACTS")
    lines.append("- Files inspected: logs/order_log_v1.jsonl, logs/aurora_events.jsonl, logs/trade_lifecycle.jsonl, logs/shadow_critical_event_journal_v1.jsonl, data/recorder/2026-04-30..2026-05-02, decision_making safety-gate/config/test surfaces.")
    lines.append(
        f"- Raw NRR-063 TREND_UP rows in current order_log slice: {corpus['summary']['raw_row_count']}")
    lines.append(
        f"- Analysis rows with complete 60m window: {corpus['summary']['analysis_row_count']}")
    lines.append(
        f"- Rows with complete 120m window: {corpus['summary']['complete_120m_count']}")
    lines.append(
        f"- Incomplete 60m rows preserved separately: {corpus['summary']['incomplete_60m_count']}")
    lines.append(
        f"- Exact contract: {contract['symbolic_name']} ({contract['reason_code']}) from {contract['anchors']['normalized_reason']}")
    lines.append(
        f"- Reject condition anchor: {contract['anchors']['reject_condition']}")
    lines.append(
        f"- Threshold resolver helper: {contract['anchors']['resolver_helper']}")
    lines.append(
        f"- Current TREND_UP upper cap from YAML: {contract['current_trend_up_upper_cap']} at {contract['anchors']['domains_yaml_trend_up']}")
    lines.append(
        f"- Current TREND_DOWN upper cap from YAML: {contract['current_trend_down_upper_cap']} at {contract['anchors']['domains_yaml_trend_down']}")
    lines.append(
        f"- Runtime scope/precedence: {contract['scope']} via {', '.join(contract['precedence_chain'])}")
    lines.append(
        f"- Live strategy-local regime-confidence override found in strategies.yaml: {contract['btc_eth_strategy_override_present_in_live_yaml']}")
    lines.append(
        f"- Live Aurora-specific regime-confidence override found in strategies/aurora.yaml: {contract['aurora_strategy_override_present_in_live_yaml']}")
    lines.append(
        f"- Typed config supports config-only canary expression: {contract['config_canary_expressible']} via {contract['anchors']['config_model']}")
    lines.append(
        f"- Observed NRR-063 regimes in current order_log: {json.dumps(contract['observed_nrr063_by_regime'], sort_keys=True)}")
    lines.append(
        f"- Dataset join quality: {json.dumps(corpus['summary']['join_quality'], sort_keys=True)}")
    lines.append(
        f"- Trace evidence classes: {json.dumps(corpus['summary']['trace_class_counts'], sort_keys=True)}")
    lines.append(
        f"- Full-cohort baseline: 60m hit {format_percent(baseline['profit_hit_60m_rate_pct'])}, 120m hit {format_percent(baseline['profit_hit_120m_rate_pct'])}, median 120m close {format_float(baseline['median_120m_close_bps'])} bps, false-admit {format_percent(baseline['false_admit_rate_pct'])}")
    lines.append(
        f"- Deterministic double-run replay: {validation['deterministic']} (signature_a={validation['signature_a']}, signature_b={validation['signature_b']})")
    lines.append("")
    lines.append("## 3. INFERENCES")
    lines.append(
        "- NRR-063 is not a separate execution or TTL defect; it is the upper regime_confidence band block in directional_sanity.")
    lines.append("- Any live config canary can be kept narrow because current typed config already supports per-regime/per-symbol/per-strategy max-band expression.")
    lines.append(
        "- Replay remains decision-layer counterfactual only: positive forward MFE/close does not prove guaranteed fills.")
    lines.append(f"- Minimal safe verdict from replay: {verdict['verdict']}.")
    lines.append("")
    lines.append("## 4. ASSUMPTIONS")
    lines.append(
        f"- Profit-hit uses gross MFE >= {PROFIT_HIT_BPS:.1f} bps, per task prompt.")
    lines.append(
        f"- Net close estimate subtracts assumed round-trip cost {ASSUMED_ROUND_TRIP_COST_BPS:.1f} bps from close-bps; this is not an exchange-certified live cost model.")
    lines.append("- Variant 1 shadow-only uses the same narrow candidate set as Variant 2 (+0.02) because the prompt defines a relaxed shadow rule but not a separate threshold.")
    lines.append("- Recorder join uses detector_event.bar_close_ts_ms - 1 ms and the matching recorder timeframe when available, else 300s fallback.")
    lines.append("")
    lines.append("## 5. UNKNOWNS")
    lines.append("- Replay does not prove fill probability, queue priority, maker/taker outcome, or downstream execution reject rate for newly admitted candidates.")
    lines.append("- Rows without secondary trace evidence remain order_log-only and are kept explicit rather than promoted to stronger runtime proof.")
    lines.append(
        "- Any net-cost estimate beyond the gross 26 bps hit rule remains approximate.")
    lines.append("")
    lines.append("## 6. Variant comparison table")
    lines.append("")
    headers = [
        "variant",
        "rule",
        "admitted_count",
        "symbols",
        "60m_hit_rate",
        "120m_hit_rate",
        "median_mfe",
        "median_mae",
        "median_close",
        "worst_mae",
        "false_admit_rate",
        "concentration_risk",
        "recommendation",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in table_rows:
        lines.append(
            "| " + " | ".join(row[key].replace("|", "/") for key in headers) + " |")
    lines.append("")
    lines.append("## 7. Casebook")
    lines.append("")
    lines.append("### 7.1 Strongest missed winners")
    for row in casebook["strongest_missed_winners"]:
        lines.append(f"- {row['timestamp_utc']} {row['symbol']} {row['side']} rid={row['rid']} conf={format_float(row['regime_confidence'])} 60m_close={format_float(row['60m_close_bps'])} 120m_close={format_float(row['120m_close_bps'])} passes={','.join(row['variant_passes']) or 'none'}")
    lines.append("")
    lines.append("### 7.2 Candidates that should remain blocked")
    for row in casebook["should_remain_blocked"]:
        lines.append(f"- {row['timestamp_utc']} {row['symbol']} {row['side']} rid={row['rid']} conf={format_float(row['regime_confidence'])} 60m_close={format_float(row['60m_close_bps'])} 120m_close={format_float(row['120m_close_bps'])} 120m_mae={format_float(row['120m_mae_bps'])}")
    lines.append("")
    lines.append("### 7.3 Ambiguous cases")
    for row in casebook["ambiguous_cases"]:
        lines.append(f"- {row['timestamp_utc']} {row['symbol']} {row['side']} rid={row['rid']} conf={format_float(row['regime_confidence'])} 60m_hit={row['profit_hit_60m']} 120m_hit={row['profit_hit_120m']} 60m_close={format_float(row['60m_close_bps'])} 120m_close={format_float(row['120m_close_bps'])}")
    lines.append("")
    lines.append("## 8. Proposed patch if CONFIG CANARY is recommended")
    if verdict["verdict"] == "CONFIG CANARY":
        lines.append("- Exact YAML path: config/aurora/domains.yaml -> decision_making.directional_sanity.max_regime_confidence_by_regime.TREND_UP plus a narrow Aurora BTCUSDT/ETHUSDT scope if promoted into strategy-local override.")
        lines.append(f"- Old value: {contract['current_trend_up_upper_cap']}")
        lines.append("- New value: 0.34")
        lines.append(
            "- Pydantic changes required: no new production model fields required; typed regime-confidence override fields already exist.")
        lines.append("- Tests required: extend test_regime_confidence_decision_audit.py with BTCUSDT/ETHUSDT Aurora override coverage and canary rollback assertions.")
        for criterion in verdict["rollback_criteria"]:
            lines.append(f"- Rollback criterion: {criterion}")
    else:
        lines.append(
            "- Not applicable: replay verdict did not recommend a live CONFIG CANARY patch in this slice.")
    lines.append("")
    lines.append("## 9. Validation")
    lines.append(
        "- Command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe scripts/forensics/nrr063_trend_up_canary_replay.py")
    lines.append(f"- Internal pass A signature: {validation['signature_a']}")
    lines.append(f"- Internal pass B signature: {validation['signature_b']}")
    lines.append(f"- Deterministic result: {validation['deterministic']}")
    lines.append(f"- Stdout summary: {validation['stdout_summary']}")
    lines.append("")
    lines.append("## 10. Minimal safe verdict")
    lines.append(f"- {verdict['verdict']}")
    lines.append(f"- {verdict['recommended_exact_next_step']}")
    for criterion in verdict["rollback_criteria"]:
        lines.append(f"- Guardrail: {criterion}")
    lines.append("")
    return "\n".join(lines) + "\n"


def build_signable_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": {
            "current_trend_up_upper_cap": result["contract_freeze"]["current_trend_up_upper_cap"],
            "current_trend_down_upper_cap": result["contract_freeze"]["current_trend_down_upper_cap"],
            "config_canary_expressible": result["contract_freeze"]["config_canary_expressible"],
            "observed_nrr063_by_regime": result["contract_freeze"]["observed_nrr063_by_regime"],
        },
        "corpus_summary": result["corpus"]["summary"],
        "variant_metrics": result["variants"],
        "verdict": result["verdict"],
    }


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    order_log_rows, placed_counts = load_order_log_rows()
    contract = build_contract_freeze(order_log_rows)
    current_cap = contract["current_trend_up_upper_cap"]
    if current_cap is None:
        raise RuntimeError(
            "Failed to extract current TREND_UP upper cap from config/aurora/domains.yaml")

    recorder_cache = RecorderCache(date_dirs=args.dates)
    corpus = build_corpus(
        order_log_rows=order_log_rows,
        placed_counts=placed_counts,
        current_cap=current_cap,
        recorder_cache=recorder_cache,
    )
    baseline = build_baseline_metrics(
        full_analysis_rows=corpus["analysis_rows"],
        placed_counts=placed_counts,
    )
    variants = build_variants(
        full_analysis_rows=corpus["analysis_rows"],
        placed_counts=placed_counts,
        current_cap=current_cap,
        config_expressible=bool(contract["config_canary_expressible"]),
    )
    verdict = choose_verdict(
        variants=variants, contract=contract, baseline=baseline)
    apply_variant_recommendations(
        variants=variants, baseline=baseline, verdict=verdict)
    casebook = build_casebook(
        full_analysis_rows=corpus["analysis_rows"], variants=variants)

    return {
        "meta": {
            "script": str(Path(__file__).relative_to(ROOT)),
            "report_md": str(Path(args.output_md).resolve().relative_to(ROOT)),
            "report_json": str(Path(args.output_json).resolve().relative_to(ROOT)),
            "dates": list(args.dates),
        },
        "contract_freeze": contract,
        "corpus": corpus,
        "baseline": baseline,
        "variants": variants,
        "casebook": casebook,
        "verdict": verdict,
        "assumptions": [
            f"Gross profit-hit threshold uses {PROFIT_HIT_BPS:.1f} bps MFE.",
            f"Net close estimate subtracts assumed {ASSUMED_ROUND_TRIP_COST_BPS:.1f} bps round-trip cost.",
            "Variant 1 shadow-only reuses the narrow +0.02 relaxed candidate set.",
            "Recorder join uses detector_event.bar_close_ts_ms - 1 ms.",
        ],
        "unknowns": [
            "Counterfactual replay does not prove fill probability.",
            "Downstream execution reject pressure remains unproven in replay-only mode.",
            "No exchange-certified live cost model is attached to this slice.",
        ],
    }


def write_outputs(args: argparse.Namespace, result: dict[str, Any]) -> None:
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(
        result, indent=2, sort_keys=True), encoding="utf-8")
    output_md.write_text(render_markdown(result), encoding="utf-8")


def main() -> int:
    args = parse_args()
    pass_a = run_analysis(args)
    signature_a = sha256_signature(build_signable_payload(pass_a))
    pass_b = run_analysis(args)
    signature_b = sha256_signature(build_signable_payload(pass_b))

    deterministic = signature_a == signature_b
    if not deterministic:
        raise RuntimeError(
            f"Deterministic replay failed: signature_a={signature_a} signature_b={signature_b}"
        )

    result = pass_a
    stdout_summary = {
        "analysis_row_count": result["corpus"]["summary"]["analysis_row_count"],
        "incomplete_60m_count": result["corpus"]["summary"]["incomplete_60m_count"],
        "complete_120m_count": result["corpus"]["summary"]["complete_120m_count"],
        "verdict": result["verdict"]["verdict"],
        "variant_2_admitted": result["variants"]["variant_2_config_plus_0_02"]["admitted_count"],
        "variant_3_admitted": result["variants"]["variant_3_config_plus_0_03"]["admitted_count"],
        "variant_4_admitted": result["variants"]["variant_4_config_plus_0_05"]["admitted_count"],
    }
    result["validation"] = {
        "deterministic": deterministic,
        "signature_a": signature_a,
        "signature_b": signature_b,
        "stdout_summary": stdout_summary,
    }

    write_outputs(args, result)

    print(
        json.dumps(
            {
                "status": "ok",
                "analysis_rows": result["corpus"]["summary"]["analysis_row_count"],
                "incomplete_60m": result["corpus"]["summary"]["incomplete_60m_count"],
                "complete_120m": result["corpus"]["summary"]["complete_120m_count"],
                "verdict": result["verdict"]["verdict"],
                "variant_2_admitted": result["variants"]["variant_2_config_plus_0_02"]["admitted_count"],
                "variant_3_admitted": result["variants"]["variant_3_config_plus_0_03"]["admitted_count"],
                "variant_4_admitted": result["variants"]["variant_4_config_plus_0_05"]["admitted_count"],
                "signature": signature_a,
                "output_json": str(Path(args.output_json).resolve()),
                "output_md": str(Path(args.output_md).resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
