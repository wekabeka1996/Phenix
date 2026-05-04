from __future__ import annotations

import csv
import json
import math
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT / "logs"
RECORDER_DIR = ROOT / "data" / "recorder"
REPORTS_DIR = ROOT / "reports"
ARTIFACTS_DIR = ROOT / "artifacts"
REPORTS_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR.mkdir(exist_ok=True)

ORDER_LOG_PATH = LOGS_DIR / "order_log_v1.jsonl"
COLLECTED_LOGS_DIR = ROOT / "data" / "order_logs_collected"
DM_LOG_PATH = LOGS_DIR / "domain_decision_making.log"
FE_LOG_PATH = LOGS_DIR / "domain_feature_engineering.log"
BASELINE_REPORT_PATH = REPORTS_DIR / "BASELINE_NRR027_REPORT.md"
DOMAINS_YAML_PATH = ROOT / "config" / "aurora" / "domains.yaml"
MODEL_PATH = ROOT / "apps" / "reference" / \
    "config" / "domains" / "decision_making.py"
GATE_PATH = ROOT / "apps" / "reference" / "domains" / \
    "decision_making" / "gates" / "safety_gates.py"

REPORT_MD_PATH = REPORTS_DIR / "NRR027_FULL_SYMBOL_REGIME_CALIBRATION_REPORT.md"
REPORT_JSON_PATH = ARTIFACTS_DIR / "nrr027_full_symbol_regime_results.json"

TARGET_NRR = "NRR-027"
ROUND_TRIP_FEE_BPS = 10.0

GRID_HARD_VETO = [2, 3, 4, 5]
GRID_MIN_ABS_DELTA_BPS = [0, 1, 2, 3, 5, 8, 10]
GRID_CUMULATIVE_MOVE_BPS = [0, 3, 5, 8, 12, 15]
GRID_MODE = ["hard"]

REGIME_BUCKETS = [
    "LOW_VOLATILITY",
    "TREND_UP",
    "TREND_DOWN",
    "HIGH_VOLATILITY",
    "MEAN_REVERSION",
    "UNCERTAIN",
]

SYM_BUCKETS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "1000PEPEUSDT",
]

MIN_PATCH_SAMPLE_SIZE = 15
TAIL_WORSEN_ABS_BPS = 10.0
TAIL_WORSEN_RATIO = 0.15

BASELINE_CANDIDATE = {
    "mode": "hard",
    "hard_veto_consecutive_bars": 2,
    "min_abs_delta_price_bps": 0,
    "cumulative_move_bps": 0,
}


@dataclass
class CaseSeed:
    rid: str
    ts_ms: int
    symbol: str
    side: str
    regime: str
    regime_confidence: Optional[float]
    why: str
    source: str


def safe_float(v: Any) -> Optional[float]:
    if v in (None, "", "None", "null"):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def safe_int(v: Any) -> Optional[int]:
    if v in (None, "", "None", "null"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def parse_rid_ts(rid: str) -> Optional[int]:
    m = re.search(r"(\d{10,})$", str(rid or ""))
    if not m:
        return None
    return safe_int(m.group(1))


def normalize_side(side: str) -> str:
    s = str(side or "").strip().upper()
    if s in {"BUY", "LONG"}:
        return "BUY"
    if s in {"SELL", "SHORT"}:
        return "SELL"
    return s or "UNKNOWN"


def normalize_regime(regime: str) -> str:
    return str(regime or "UNKNOWN").strip().upper() or "UNKNOWN"


def ts_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def _iter_all_order_log_sources() -> Iterable[dict]:
    """Yield records from collected logs folder first, then live log as fallback."""
    if COLLECTED_LOGS_DIR.exists():
        for f in sorted(COLLECTED_LOGS_DIR.glob("*.jsonl"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
            yield from iter_jsonl(f)
    elif ORDER_LOG_PATH.exists():
        yield from iter_jsonl(ORDER_LOG_PATH)


def load_nrr027_from_order_log() -> list[CaseSeed]:
    out: list[CaseSeed] = []
    for rec in _iter_all_order_log_sources():
        if str(rec.get("nrr_code") or "") != TARGET_NRR:
            continue
        rid = str(rec.get("rid") or rec.get("decision_id")
                  or rec.get("intent_id") or "")
        ts_ms = safe_int(rec.get("timestamp") or rec.get("ts_ms"))
        if ts_ms is None:
            ts_ms = parse_rid_ts(rid)
        if ts_ms is None:
            continue
        out.append(
            CaseSeed(
                rid=rid or f"nrr027_{ts_ms}",
                ts_ms=ts_ms,
                symbol=str(rec.get("symbol") or ""),
                side=normalize_side(str(rec.get("side") or "")),
                regime=normalize_regime(str(rec.get("regime") or "")),
                regime_confidence=safe_float(
                    rec.get("regime_confidence") or rec.get("regime_conf")),
                why=str(rec.get("why_rejected") or rec.get("why") or ""),
                source="data/order_logs_collected",
            )
        )
    return out


def load_nrr027_from_baseline_report() -> list[CaseSeed]:
    out: list[CaseSeed] = []
    if not BASELINE_REPORT_PATH.exists():
        return out

    inv_header = "## 8. All NRR-027 Events (Complete Inventory)"
    text = BASELINE_REPORT_PATH.read_text(encoding="utf-8", errors="replace")
    if inv_header not in text:
        return out

    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(inv_header):
            in_table = True
            continue
        if not in_table:
            continue
        if not line:
            if out:
                break
            continue
        if not line.startswith("|"):
            if out:
                break
            continue
        if line.startswith("|---") or "| # |" in line:
            continue

        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 8:
            continue

        rid = cols[1].strip("`")
        ts_ms = parse_rid_ts(rid)
        if ts_ms is None:
            continue

        regime_conf = safe_float(cols[5])
        out.append(
            CaseSeed(
                rid=rid,
                ts_ms=ts_ms,
                symbol=cols[2],
                side=normalize_side(cols[3]),
                regime=normalize_regime(cols[4]),
                regime_confidence=regime_conf,
                why=cols[6],
                source="reports/BASELINE_NRR027_REPORT.md",
            )
        )
    return out


def dedupe_cases(cases: list[CaseSeed]) -> list[CaseSeed]:
    by_key: dict[tuple[str, int, str], CaseSeed] = {}
    for case in cases:
        key = (case.symbol, case.ts_ms, case.side)
        prev = by_key.get(key)
        if prev is None or prev.source.startswith("reports/"):
            by_key[key] = case
    return sorted(by_key.values(), key=lambda c: (c.ts_ms, c.symbol, c.side))


def read_recorder_rows(day: str, symbol: str, tf_sec: int, cache: dict[tuple[str, str, int], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    key = (day, symbol, tf_sec)
    if key in cache:
        return cache[key]
    path = RECORDER_DIR / day / f"{symbol}_{tf_sec}.csv"
    rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = safe_int(row.get("timestamp"))
                if ts is None:
                    continue
                row["timestamp"] = ts
                rows.append(row)
    cache[key] = rows
    return rows


def row_timestamps(rows: list[dict[str, Any]]) -> list[int]:
    return [int(r["timestamp"]) for r in rows]


def find_le_idx(rows: list[dict[str, Any]], ts_ms: int) -> int:
    if not rows:
        return -1
    tss = row_timestamps(rows)
    pos = bisect_right(tss, ts_ms) - 1
    return pos if pos >= 0 else -1


def load_domain_feature_index() -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    if not FE_LOG_PATH.exists():
        return out
    for line in FE_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if "Calculated features for" not in line or "{" not in line:
            continue
        jpos = line.find("{")
        if jpos < 0:
            continue
        try:
            payload = json.loads(line[jpos:])
        except json.JSONDecodeError:
            continue
        symbol = str(payload.get("symbol") or "")
        ts_ms = safe_int(payload.get("timestamp") or payload.get(
            "ts_ms") or payload.get("bar_ts") or payload.get("bar_close_ts"))
        if not symbol or ts_ms is None:
            continue
        out[(symbol, ts_ms)] = payload
    return out


def load_domain_decision_index() -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    if not DM_LOG_PATH.exists():
        return out
    for line in DM_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        l = line.strip()
        if "{" not in l:
            continue
        jpos = l.find("{")
        try:
            payload = json.loads(l[jpos:])
        except json.JSONDecodeError:
            continue
        ts_ms = safe_int(payload.get("ts") or payload.get(
            "ts_ms") or payload.get("timestamp"))
        symbol = str(payload.get("symbol") or payload.get("instrument") or "")
        if ts_ms is None or not symbol:
            continue
        out[(symbol, ts_ms)] = payload
    return out


def sign_of_adverse(side: str) -> int:
    return -1 if normalize_side(side) == "BUY" else 1


def bps_return(side: str, entry: float, price: float) -> float:
    if normalize_side(side) == "BUY":
        return (price - entry) / entry * 10000.0
    return (entry - price) / entry * 10000.0


def list_recorder_coverage(symbols: Iterable[str]) -> dict[str, list[int]]:
    requested = {str(symbol).strip().upper() for symbol in symbols}
    found: dict[str, set[int]] = {symbol: set() for symbol in requested}
    if not RECORDER_DIR.exists():
        return {symbol: [] for symbol in sorted(requested)}

    for path in RECORDER_DIR.rglob("*.csv"):
        stem = path.stem
        if "_" not in stem:
            continue
        symbol, tf_text = stem.rsplit("_", 1)
        symbol = str(symbol).strip().upper()
        if symbol not in requested or not tf_text.isdigit():
            continue
        found.setdefault(symbol, set()).add(int(tf_text))

    return {symbol: sorted(found.get(symbol, set())) for symbol in sorted(requested)}


def build_case_dataset(cases: list[CaseSeed]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    recorder_cache: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    recorder_coverage = list_recorder_coverage(SYM_BUCKETS)
    available_timeframes = sorted(
        {tf for tfs in recorder_coverage.values() for tf in tfs}
    )

    dataset: list[dict[str, Any]] = []
    missing = defaultdict(int)

    for case in cases:
        symbol = str(case.symbol or "").strip().upper()
        regime = normalize_regime(case.regime)
        if symbol not in SYM_BUCKETS:
            missing[f"unsupported_symbol::{symbol or 'UNKNOWN'}"] += 1
            continue
        if regime not in REGIME_BUCKETS:
            missing[f"unsupported_regime::{regime or 'UNKNOWN'}"] += 1
            continue

        day = datetime.fromtimestamp(
            case.ts_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")
        symbol_tfs = recorder_coverage.get(symbol, [])
        if not symbol_tfs:
            missing[f"no_recorder_timeframes::{symbol}"] += 1
            continue

        for tf_sec in symbol_tfs:
            rows = read_recorder_rows(day, symbol, tf_sec, recorder_cache)
            if not rows:
                missing[f"recorder_missing::{symbol}::{tf_sec}"] += 1
                continue

            idx = find_le_idx(rows, case.ts_ms)
            if idx < 0:
                missing[f"recorder_ts_miss::{symbol}::{tf_sec}"] += 1
                continue

            row = rows[idx]
            entry_price = safe_float(row.get("close"))
            if entry_price is None or entry_price <= 0.0:
                missing[f"entry_price_missing::{symbol}::{tf_sec}"] += 1
                continue

            delta_price = safe_float(row.get("feat_delta_price"))
            adverse_sign = sign_of_adverse(case.side)
            adverse_consecutive = 0
            cumulative_adverse_bps = 0.0
            j = idx
            while j >= 0:
                d = safe_float(rows[j].get("feat_delta_price"))
                if d is None or d == 0.0:
                    break
                sgn = 1 if d > 0 else -1
                if sgn != adverse_sign:
                    break
                adverse_consecutive += 1
                cumulative_adverse_bps += abs(d) / entry_price * 10000.0
                j -= 1

            horizon_steps = max(1, 3600 // int(tf_sec))
            fwd = rows[idx + 1:idx + 1 + horizon_steps]
            highs = [safe_float(x.get("high")) for x in fwd]
            lows = [safe_float(x.get("low")) for x in fwd]
            closes = [safe_float(x.get("close")) for x in fwd]
            highs = [x for x in highs if x is not None]
            lows = [x for x in lows if x is not None]
            closes = [x for x in closes if x is not None]

            if highs and lows:
                if normalize_side(case.side) == "BUY":
                    mfe_bps = (max(highs) - entry_price) / \
                        entry_price * 10000.0
                    mae_bps = (entry_price - min(lows)) / entry_price * 10000.0
                else:
                    mfe_bps = (entry_price - min(lows)) / entry_price * 10000.0
                    mae_bps = (max(highs) - entry_price) / \
                        entry_price * 10000.0
            else:
                mfe_bps = None
                mae_bps = None

            close_horizon_bps = (
                bps_return(case.side, entry_price,
                           closes[-1]) if closes else None
            )
            net_after_fees = (
                close_horizon_bps - ROUND_TRIP_FEE_BPS
                if close_horizon_bps is not None
                else None
            )

            dataset.append(
                {
                    "rid": case.rid,
                    "source": case.source,
                    "ts_ms": case.ts_ms,
                    "ts_iso": ts_to_iso(case.ts_ms),
                    "symbol": symbol,
                    "side": normalize_side(case.side),
                    "regime": regime,
                    "recorder_regime": normalize_regime(
                        str(row.get("regime") or regime)
                    ),
                    "regime_confidence": case.regime_confidence,
                    "tf_sec": int(tf_sec),
                    "entry_price": entry_price,
                    "delta_price": delta_price,
                    "delta_abs_bps": (
                        abs(delta_price) / entry_price * 10000.0
                    ) if delta_price is not None else None,
                    "adverse_consecutive_bars": adverse_consecutive,
                    "cumulative_adverse_move_bps": cumulative_adverse_bps,
                    "mfe_bps": mfe_bps,
                    "mae_bps": mae_bps,
                    "close_horizon_bps": close_horizon_bps,
                    "net_after_fees": net_after_fees,
                    "horizon_minutes": int((horizon_steps * int(tf_sec)) / 60),
                }
            )

    sources_checked = []
    if COLLECTED_LOGS_DIR.exists():
        sources_checked.append("data/order_logs_collected/*.jsonl")
    elif ORDER_LOG_PATH.exists():
        sources_checked.append("logs/order_log_v1.jsonl")
    sources_checked.append("reports/BASELINE_NRR027_REPORT.md")
    for symbol in SYM_BUCKETS:
        for tf_sec in available_timeframes:
            sources_checked.append(f"data/recorder/**/{symbol}_{tf_sec}.csv")

    provenance = {
        "sources_checked": sources_checked,
        "recorder_coverage": recorder_coverage,
        "available_timeframes": available_timeframes,
        "missing_counts": dict(sorted(missing.items())),
    }
    return dataset, provenance


def candidate_denies(
    case: dict[str, Any],
    veto: int,
    min_abs_delta_bps: int,
    cumulative_move_bps: int,
    mode: str,
) -> bool:
    if mode != "hard":
        return False

    run = int(case.get("adverse_consecutive_bars") or 0)
    delta_abs = safe_float(case.get("delta_abs_bps"))
    cum = safe_float(case.get("cumulative_adverse_move_bps"))

    if delta_abs is None or cum is None:
        return False

    return (
        run >= int(veto)
        and delta_abs >= float(min_abs_delta_bps)
        and cum >= float(cumulative_move_bps)
    )


def confidence_label(sample_size: int) -> str:
    if sample_size >= 30:
        return "HIGH"
    if sample_size >= 15:
        return "MEDIUM"
    return "LOW"


def iter_candidate_grid() -> Iterable[dict[str, Any]]:
    for mode in GRID_MODE:
        for veto in GRID_HARD_VETO:
            for min_abs in GRID_MIN_ABS_DELTA_BPS:
                for cum in GRID_CUMULATIVE_MOVE_BPS:
                    yield {
                        "mode": mode,
                        "hard_veto_consecutive_bars": veto,
                        "min_abs_delta_price_bps": min_abs,
                        "cumulative_move_bps": cum,
                    }


def candidate_spec_key(candidate: Optional[dict[str, Any]]) -> tuple[str, int, int, int]:
    if candidate is None:
        return ("", 0, 0, 0)
    return (
        str(candidate.get("mode") or ""),
        int(candidate.get("hard_veto_consecutive_bars") or 0),
        int(candidate.get("min_abs_delta_price_bps") or 0),
        int(candidate.get("cumulative_move_bps") or 0),
    )


def is_baseline_candidate(candidate: Optional[dict[str, Any]]) -> bool:
    return candidate_spec_key(candidate) == candidate_spec_key(BASELINE_CANDIDATE)


def format_candidate(candidate: Optional[dict[str, Any]]) -> str:
    if candidate is None:
        return "n/a"
    return (
        f"mode={candidate.get('mode')}"
        f", veto={candidate.get('hard_veto_consecutive_bars')}"
        f", min_abs={candidate.get('min_abs_delta_price_bps')}"
        f", cum={candidate.get('cumulative_move_bps')}"
    )


def evaluate_candidate_metrics(
    cohort: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    by_rid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cohort:
        by_rid[str(row.get("rid") or "")].append(row)

    recovered_good_count = 0
    recovered_good_bps = 0.0
    exposed_bad_count = 0
    exposed_bad_bps = 0.0
    net_after_fees = 0.0
    max_adverse_bps = 0.0
    max_favorable_bps = 0.0
    true_blocks_preserved_count = 0
    allowed_event_count = 0

    for rows in by_rid.values():
        allowed_rows = [
            row
            for row in rows
            if not candidate_denies(
                row,
                int(candidate["hard_veto_consecutive_bars"]),
                int(candidate["min_abs_delta_price_bps"]),
                int(candidate["cumulative_move_bps"]),
                str(candidate["mode"]),
            )
        ]

        if not allowed_rows:
            denied_nets = [
                safe_float(row.get("net_after_fees"))
                for row in rows
                if safe_float(row.get("net_after_fees")) is not None
            ]
            if denied_nets and any(net <= 0.0 for net in denied_nets):
                true_blocks_preserved_count += 1
            continue

        allowed_event_count += 1
        event_nets = [
            safe_float(row.get("net_after_fees"))
            for row in allowed_rows
            if safe_float(row.get("net_after_fees")) is not None
        ]
        if not event_nets:
            continue

        adverse_values = [
            safe_float(row.get("mae_bps"))
            for row in allowed_rows
            if safe_float(row.get("mae_bps")) is not None
        ]
        favorable_values = [
            safe_float(row.get("mfe_bps"))
            for row in allowed_rows
            if safe_float(row.get("mfe_bps")) is not None
        ]
        if adverse_values:
            max_adverse_bps = max(max_adverse_bps, max(adverse_values))
        if favorable_values:
            max_favorable_bps = max(max_favorable_bps, min(favorable_values))

        if any(net <= 0.0 for net in event_nets):
            event_loss = max(abs(net) for net in event_nets if net <= 0.0)
            exposed_bad_count += 1
            exposed_bad_bps += event_loss
            net_after_fees -= event_loss
        else:
            event_gain = min(event_nets)
            recovered_good_count += 1
            recovered_good_bps += event_gain
            net_after_fees += event_gain

    penalty_bps = exposed_bad_bps * 1.5 + exposed_bad_count * 5.0
    objective = recovered_good_bps - penalty_bps

    result = {
        **candidate,
        "sample_size": len(by_rid),
        "observation_count": len(cohort),
        "confidence": confidence_label(len(by_rid)),
        "recovered_good_count": recovered_good_count,
        "recovered_good_bps": round(recovered_good_bps, 4),
        "exposed_bad_count": exposed_bad_count,
        "exposed_bad_bps": round(exposed_bad_bps, 4),
        "net_after_fees": round(net_after_fees, 4),
        "objective": round(objective, 4),
        "max_adverse_bps": round(max_adverse_bps, 4),
        "max_favorable_bps": round(max_favorable_bps, 4),
        "true_blocks_preserved_count": true_blocks_preserved_count,
        "allowed_event_count": allowed_event_count,
        "penalty_bps": round(penalty_bps, 4),
    }
    return result


def materially_worse_tail(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    baseline_tail = float(baseline.get("max_adverse_bps") or 0.0)
    candidate_tail = float(candidate.get("max_adverse_bps") or 0.0)
    threshold = max(TAIL_WORSEN_ABS_BPS, baseline_tail * TAIL_WORSEN_RATIO)
    return candidate_tail > baseline_tail + threshold


def candidate_beats_baseline(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return (
        not is_baseline_candidate(candidate)
        and float(candidate.get("objective") or 0.0) > float(baseline.get("objective") or 0.0)
        and float(candidate.get("net_after_fees") or 0.0) > float(baseline.get("net_after_fees") or 0.0)
    )


def candidate_safety_failures(candidate: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if int(candidate.get("sample_size") or 0) < MIN_PATCH_SAMPLE_SIZE:
        reasons.append(f"sample_below_{MIN_PATCH_SAMPLE_SIZE}")
    if float(candidate.get("net_after_fees") or 0.0) <= 0.0:
        reasons.append("net_after_fees_non_positive")
    if float(candidate.get("objective") or 0.0) <= 0.0:
        reasons.append("objective_non_positive")
    if float(candidate.get("exposed_bad_bps") or 0.0) >= float(candidate.get("recovered_good_bps") or 0.0):
        reasons.append("exposed_bad_bps_gte_recovered_good_bps")
    if materially_worse_tail(candidate, baseline):
        reasons.append("max_adverse_tail_materially_worse")
    return reasons


def find_candidate_result(
    results: list[dict[str, Any]],
    key: tuple[str, int, int, int],
) -> Optional[dict[str, Any]]:
    for row in results:
        if candidate_spec_key(row) == key:
            return row
    return None


def summarize_named_cohort(
    name: str,
    cohort: list[dict[str, Any]],
    *,
    meta: Optional[dict[str, Any]] = None,
    negative_control_evals: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    rows = [evaluate_candidate_metrics(cohort, candidate)
            for candidate in iter_candidate_grid()]
    rows.sort(
        key=lambda row: (
            -float(row["objective"]),
            -float(row["net_after_fees"]),
            -float(row["recovered_good_bps"]),
            float(row["exposed_bad_bps"]),
            0 if is_baseline_candidate(row) else 1,
        )
    )

    summary: dict[str, Any] = {
        "cohort": name,
        "verdict": "INSUFFICIENT_DATA",
        "decision_reasons": [],
        "baseline": None,
        "best": rows[0] if rows else None,
        "best_nonbaseline": None,
        "selected_candidate": None,
        "negative_control_failures": [],
        "qualified_negative_controls": 0,
        "results": rows,
        **(meta or {}),
    }

    if not rows:
        return summary

    baseline = find_candidate_result(
        rows, candidate_spec_key(BASELINE_CANDIDATE))
    best_nonbaseline = next(
        (row for row in rows if not is_baseline_candidate(row)), None)
    summary["baseline"] = baseline
    summary["best_nonbaseline"] = best_nonbaseline
    summary["selected_candidate"] = baseline
    summary["sample_size"] = int(baseline.get(
        "sample_size") or 0) if baseline else 0
    summary["observation_count"] = int(baseline.get(
        "observation_count") or 0) if baseline else 0
    summary["confidence"] = str(baseline.get(
        "confidence") or "LOW") if baseline else "LOW"

    if baseline is None or summary["sample_size"] == 0:
        summary["decision_reasons"] = ["no_rows"]
        return summary

    if summary["sample_size"] < MIN_PATCH_SAMPLE_SIZE:
        summary["decision_reasons"] = [f"sample_below_{MIN_PATCH_SAMPLE_SIZE}"]
        return summary

    if best_nonbaseline is None:
        summary["verdict"] = "KEEP_BASELINE"
        summary["decision_reasons"] = ["no_nonbaseline_candidate"]
        return summary

    if not candidate_beats_baseline(best_nonbaseline, baseline):
        summary["verdict"] = "KEEP_BASELINE"
        summary["decision_reasons"] = ["baseline_outperforms_candidate"]
        return summary

    safety_failures = candidate_safety_failures(best_nonbaseline, baseline)
    negative_failures: list[dict[str, Any]] = []
    qualified_controls = 0
    candidate_key = candidate_spec_key(best_nonbaseline)

    for control in negative_control_evals or []:
        if int(control.get("sample_size") or 0) < MIN_PATCH_SAMPLE_SIZE:
            continue
        qualified_controls += 1
        control_baseline = control.get("baseline")
        matched = find_candidate_result(
            control.get("results") or [], candidate_key)
        if control_baseline is None or matched is None:
            negative_failures.append(
                {
                    "cohort": control.get("cohort"),
                    "reasons": ["candidate_missing_in_negative_control"],
                }
            )
            continue
        control_reasons = candidate_safety_failures(matched, control_baseline)
        if not candidate_beats_baseline(matched, control_baseline):
            control_reasons.append("baseline_outperforms_candidate")
        if control_reasons:
            negative_failures.append(
                {
                    "cohort": control.get("cohort"),
                    "sample_size": control.get("sample_size"),
                    "reasons": sorted(set(control_reasons)),
                }
            )

    summary["qualified_negative_controls"] = qualified_controls
    summary["negative_control_failures"] = negative_failures

    if negative_control_evals and qualified_controls == 0:
        summary["decision_reasons"] = ["no_qualified_negative_controls"]
        return summary

    if safety_failures:
        summary["verdict"] = "REJECT_OVERFIT"
        summary["decision_reasons"] = safety_failures
        return summary

    if negative_failures:
        summary["verdict"] = "REJECT_OVERFIT"
        summary["decision_reasons"] = ["negative_controls_failed"]
        return summary

    summary["verdict"] = "PATCH_CANDIDATE"
    summary["selected_candidate"] = best_nonbaseline
    summary["confidence"] = str(best_nonbaseline.get(
        "confidence") or summary["confidence"])
    summary["decision_reasons"] = ["positive_after_fees_and_negative_controls"]
    return summary


def read_current_directional_sanity_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "from_file": str(DOMAINS_YAML_PATH.relative_to(ROOT)).replace("\\", "/"),
        "hard_veto_consecutive_bars": None,
        "hard_veto_consecutive_bars_by_regime": {},
        "min_abs_delta_price": None,
        "consecutive_bars": None,
    }
    if not DOMAINS_YAML_PATH.exists():
        return snapshot

    lines = DOMAINS_YAML_PATH.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines()
    for i, line in enumerate(lines):
        text = line.strip()
        if text.startswith("hard_veto_consecutive_bars:") and "_by_regime" not in text:
            snapshot["hard_veto_consecutive_bars"] = safe_int(
                text.split(":", 1)[1].strip())
        if text.startswith("min_abs_delta_price:"):
            snapshot["min_abs_delta_price"] = safe_float(
                text.split(":", 1)[1].strip())
        if text.startswith("consecutive_bars:"):
            snapshot["consecutive_bars"] = safe_int(
                text.split(":", 1)[1].strip())
        if text.startswith("hard_veto_consecutive_bars_by_regime:"):
            for j in range(i + 1, min(i + 16, len(lines))):
                nxt = lines[j]
                if not nxt.startswith("      "):
                    break
                if ":" not in nxt:
                    continue
                key, value = nxt.strip().split(":", 1)
                snapshot["hard_veto_consecutive_bars_by_regime"][key.strip()] = safe_int(
                    value.strip())
    return snapshot


def derive_bucket_verdict(children: list[dict[str, Any]]) -> str:
    verdict_counts = Counter(child.get("verdict") for child in children)
    if verdict_counts.get("PATCH_CANDIDATE", 0) > 0:
        return "PATCH_CANDIDATE"
    if verdict_counts.get("REJECT_OVERFIT", 0) > 0:
        return "REJECT_OVERFIT"
    if verdict_counts.get("KEEP_BASELINE", 0) > 0:
        return "KEEP_BASELINE"
    return "INSUFFICIENT_DATA"


def summarize_parent_bucket(
    name: str,
    rows: list[dict[str, Any]],
    children: list[dict[str, Any]],
    *,
    label_key: str,
    label_value: str,
) -> dict[str, Any]:
    verdict_counts = Counter(child.get("verdict") for child in children)
    return {
        "cohort": name,
        label_key: label_value,
        "sample_size": len({str(row.get('rid') or '') for row in rows}),
        "observation_count": len(rows),
        "timeframes": sorted({int(row.get('tf_sec') or 0) for row in rows if row.get('tf_sec') is not None}),
        "verdict": derive_bucket_verdict(children),
        "patch_candidate_count": verdict_counts.get("PATCH_CANDIDATE", 0),
        "reject_overfit_count": verdict_counts.get("REJECT_OVERFIT", 0),
        "keep_baseline_count": verdict_counts.get("KEEP_BASELINE", 0),
        "insufficient_data_count": verdict_counts.get("INSUFFICIENT_DATA", 0),
        "candidate_labels": sorted(
            {
                format_candidate(child.get("selected_candidate"))
                for child in children
                if child.get("verdict") == "PATCH_CANDIDATE"
            }
        ),
    }


def runtime_change_need(symbol_regime_evals: list[dict[str, Any]]) -> dict[str, Any]:
    patch_rows = [
        row for row in symbol_regime_evals if row.get("verdict") == "PATCH_CANDIDATE"
    ]
    if not patch_rows:
        return {
            "classification": "no change",
            "reason": "No symbol x regime candidate stayed positive after fees and timeframe negative controls.",
        }

    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in symbol_regime_evals:
        by_regime[str(row.get("regime") or "")].append(row)

    yaml_only = True
    for regime, rows in by_regime.items():
        patch_candidates = [row for row in rows if row.get(
            "verdict") == "PATCH_CANDIDATE"]
        if not patch_candidates:
            continue
        candidate_keys = {candidate_spec_key(
            row.get("selected_candidate")) for row in patch_candidates}
        if len(candidate_keys) != 1:
            yaml_only = False
            break
        candidate = patch_candidates[0].get("selected_candidate")
        if (
            str(candidate.get("mode")) != "hard"
            or int(candidate.get("min_abs_delta_price_bps") or 0) != 0
            or int(candidate.get("cumulative_move_bps") or 0) != 0
        ):
            yaml_only = False
            break
        for row in rows:
            if int(row.get("sample_size") or 0) < MIN_PATCH_SAMPLE_SIZE:
                continue
            if row.get("verdict") != "PATCH_CANDIDATE":
                yaml_only = False
                break
            if candidate_spec_key(row.get("selected_candidate")) != candidate_spec_key(candidate):
                yaml_only = False
                break
        if not yaml_only:
            break

    if yaml_only:
        return {
            "classification": "YAML-only per-regime patch",
            "reason": "All accepted candidates collapse to regime-wide hard_veto overrides already supported by hard_veto_consecutive_bars_by_regime.",
        }

    if any(
        int(row.get("selected_candidate", {}).get(
            "cumulative_move_bps") or 0) != 0
        for row in patch_rows
    ):
        return {
            "classification": "Python logic patch",
            "reason": "Accepted candidates require cumulative_move_bps, which current runtime/config does not compute or resolve.",
        }

    return {
        "classification": "Pydantic schema extension",
        "reason": "Accepted candidates are symbol/regime-specific and cannot be expressed with the current YAML directional_sanity contract.",
    }


def format_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def report_candidate_for_summary(summary: dict[str, Any]) -> Optional[dict[str, Any]]:
    if summary.get("verdict") == "PATCH_CANDIDATE":
        return summary.get("selected_candidate")
    if summary.get("verdict") == "REJECT_OVERFIT":
        return summary.get("best_nonbaseline") or summary.get("baseline")
    return summary.get("baseline")


def build_report(
    *,
    seed_cases: list[CaseSeed],
    dataset: list[dict[str, Any]],
    provenance: dict[str, Any],
    current_cfg: dict[str, Any],
    per_symbol: list[dict[str, Any]],
    per_regime: list[dict[str, Any]],
    per_symbol_regime: list[dict[str, Any]],
    patch_candidates: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]],
    global_summary: dict[str, Any],
    runtime_need: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# NRR027_FULL_SYMBOL_REGIME_CALIBRATION_REPORT")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(f"- Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Global verdict: {global_summary['verdict']}")
    lines.append(f"- Runtime change need: {runtime_need['classification']}")
    lines.append(f"- Unique NRR-027 events: {len(seed_cases)}")
    lines.append(f"- Observation rows (event x timeframe): {len(dataset)}")
    lines.append(
        f"- Timeframes covered: {', '.join(str(tf) for tf in provenance.get('available_timeframes', [])) or 'none'}")
    lines.append(f"- Patch candidates: {len(patch_candidates)}")
    lines.append(f"- Rejected candidates: {len(rejected_candidates)}")
    lines.append("")

    lines.append("## Current Runtime Contract")
    lines.append(
        "- Runtime gate: apps/reference/domains/decision_making/gates/safety_gates.py::_check_directional_gate")
    lines.append(
        "- Config model: apps/reference/config/domains/decision_making.py::DirectionalSanityConfig")
    lines.append(
        f"- hard_veto_consecutive_bars: {current_cfg.get('hard_veto_consecutive_bars')}")
    lines.append(
        f"- hard_veto_consecutive_bars_by_regime: {current_cfg.get('hard_veto_consecutive_bars_by_regime')}")
    lines.append(
        f"- min_abs_delta_price: {current_cfg.get('min_abs_delta_price')}")
    lines.append(f"- consecutive_bars: {current_cfg.get('consecutive_bars')}")
    lines.append("")

    lines.append("## Dataset Coverage")
    lines.append("- Sources inspected:")
    for src in provenance.get("sources_checked", []):
        lines.append(f"  - {src}")
    lines.append("- Recorder coverage:")
    for symbol in SYM_BUCKETS:
        timeframes = provenance.get("recorder_coverage", {}).get(symbol, [])
        lines.append(f"  - {symbol}: {timeframes or 'none'}")
    if provenance.get("missing_counts"):
        lines.append("- Missing/partial counters:")
        for key, value in provenance["missing_counts"].items():
            lines.append(f"  - {key}: {value}")
    lines.append("")

    lines.append("## Global Verdict")
    lines.append(f"- Verdict: {global_summary['verdict']}")
    lines.append(f"- sample_size: {global_summary['sample_size']}")
    lines.append(f"- observation_count: {global_summary['observation_count']}")
    lines.append(
        f"- patch_candidate_count: {global_summary['patch_candidate_count']}")
    lines.append(
        f"- reject_overfit_count: {global_summary['reject_overfit_count']}")
    lines.append(
        f"- keep_baseline_count: {global_summary['keep_baseline_count']}")
    lines.append(
        f"- insufficient_data_count: {global_summary['insufficient_data_count']}")
    lines.append("")

    lines.append("## Per-Regime Verdict")
    lines.append(
        "| Regime | sample_size | obs | verdict | patch | reject | keep | insufficient |")
    lines.append("|---|---:|---:|---|---:|---:|---:|---:|")
    for row in per_regime:
        lines.append(
            f"| {row['regime']} | {row['sample_size']} | {row['observation_count']} | {row['verdict']} | "
            f"{row['patch_candidate_count']} | {row['reject_overfit_count']} | {row['keep_baseline_count']} | {row['insufficient_data_count']} |"
        )
    lines.append("")

    lines.append("## Per-Symbol Verdict")
    lines.append(
        "| Symbol | sample_size | obs | verdict | patch | reject | keep | insufficient |")
    lines.append("|---|---:|---:|---|---:|---:|---:|---:|")
    for row in per_symbol:
        lines.append(
            f"| {row['symbol']} | {row['sample_size']} | {row['observation_count']} | {row['verdict']} | "
            f"{row['patch_candidate_count']} | {row['reject_overfit_count']} | {row['keep_baseline_count']} | {row['insufficient_data_count']} |"
        )
    lines.append("")

    lines.append("## Per-Symbol x Per-Regime Table")
    lines.append(
        "| Symbol | Regime | sample_size | obs | timeframes | verdict | candidate | recovered_good_count | recovered_good_bps | exposed_bad_count | exposed_bad_bps | net_after_fees | objective | max_adverse_bps | max_favorable_bps | confidence |"
    )
    lines.append(
        "|---|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for summary in per_symbol_regime:
        candidate = report_candidate_for_summary(summary)
        timeframes = ",".join(str(tf)
                              for tf in summary.get("timeframes", [])) or "-"
        lines.append(
            f"| {summary['symbol']} | {summary['regime']} | {summary['sample_size']} | {summary['observation_count']} | {timeframes} | "
            f"{summary['verdict']} | {format_candidate(candidate)} | {candidate.get('recovered_good_count', 0) if candidate else 0} | "
            f"{format_metric(candidate.get('recovered_good_bps') if candidate else None)} | "
            f"{candidate.get('exposed_bad_count', 0) if candidate else 0} | "
            f"{format_metric(candidate.get('exposed_bad_bps') if candidate else None)} | "
            f"{format_metric(candidate.get('net_after_fees') if candidate else None)} | "
            f"{format_metric(candidate.get('objective') if candidate else None)} | "
            f"{format_metric(candidate.get('max_adverse_bps') if candidate else None)} | "
            f"{format_metric(candidate.get('max_favorable_bps') if candidate else None)} | "
            f"{candidate.get('confidence', summary.get('confidence', 'LOW')) if candidate else summary.get('confidence', 'LOW')} |"
        )
    lines.append("")

    lines.append("## Exact Candidates Worth Patching")
    if not patch_candidates:
        lines.append("- None")
    else:
        for row in patch_candidates:
            candidate = row.get("selected_candidate")
            lines.append(
                f"- {row['symbol']} / {row['regime']}: {format_candidate(candidate)}; sample={row['sample_size']}; "
                f"net_after_fees={format_metric(candidate.get('net_after_fees'))}; objective={format_metric(candidate.get('objective'))}; "
                f"timeframes={','.join(str(tf) for tf in row.get('timeframes', [])) or '-'}"
            )
    lines.append("")

    lines.append("## Exact Candidates Rejected")
    if not rejected_candidates:
        lines.append("- None")
    else:
        for row in rejected_candidates:
            candidate = row.get("best_nonbaseline") or row.get("baseline")
            failed_controls = "; ".join(
                f"{item.get('cohort')}[{','.join(item.get('reasons', []))}]"
                for item in row.get("negative_control_failures", [])
            ) or "none"
            lines.append(
                f"- {row['symbol']} / {row['regime']}: {format_candidate(candidate)}; sample={row['sample_size']}; "
                f"net_after_fees={format_metric(candidate.get('net_after_fees') if candidate else None)}; "
                f"objective={format_metric(candidate.get('objective') if candidate else None)}; "
                f"reasons={','.join(row.get('decision_reasons', [])) or 'none'}; failed_controls={failed_controls}"
            )
    lines.append("")

    lines.append("## Runtime Change Need")
    lines.append(f"- classification: {runtime_need['classification']}")
    lines.append(f"- reason: {runtime_need['reason']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def run_calibration() -> None:
    order_cases = load_nrr027_from_order_log()
    report_cases = load_nrr027_from_baseline_report()
    seed_cases = [
        case
        for case in dedupe_cases(order_cases + report_cases)
        if str(case.symbol or "").strip().upper() in SYM_BUCKETS
    ]

    dataset, provenance = build_case_dataset(seed_cases)
    current_cfg = read_current_directional_sanity_snapshot()

    symbol_regime_rows: dict[tuple[str, str],
                             list[dict[str, Any]]] = defaultdict(list)
    symbol_regime_tf_rows: dict[tuple[str, str, int],
                                list[dict[str, Any]]] = defaultdict(list)
    regime_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    symbol_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dataset:
        symbol = str(row.get("symbol") or "")
        regime = str(row.get("regime") or "")
        tf_sec = int(row.get("tf_sec") or 0)
        symbol_regime_rows[(symbol, regime)].append(row)
        symbol_regime_tf_rows[(symbol, regime, tf_sec)].append(row)
        regime_rows[regime].append(row)
        symbol_rows[symbol].append(row)

    available_timeframes = provenance.get("available_timeframes", [])
    symbol_regime_tf_evals: list[dict[str, Any]] = []
    symbol_regime_tf_index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for symbol in SYM_BUCKETS:
        for regime in REGIME_BUCKETS:
            for tf_sec in available_timeframes:
                rows = symbol_regime_tf_rows.get((symbol, regime, tf_sec), [])
                summary = summarize_named_cohort(
                    f"SYMBOL_REGIME_TF::{symbol}::{regime}::{tf_sec}",
                    rows,
                    meta={
                        "symbol": symbol,
                        "regime": regime,
                        "tf_sec": int(tf_sec),
                        "timeframes": [int(tf_sec)] if rows else [],
                    },
                )
                symbol_regime_tf_evals.append(summary)
                symbol_regime_tf_index[(symbol, regime, int(tf_sec))] = summary

    symbol_regime_evals: list[dict[str, Any]] = []
    for symbol in SYM_BUCKETS:
        for regime in REGIME_BUCKETS:
            rows = symbol_regime_rows.get((symbol, regime), [])
            timeframes = sorted({int(row.get("tf_sec") or 0)
                                for row in rows if row.get("tf_sec") is not None})
            negative_controls = [
                symbol_regime_tf_index[(symbol, regime, tf_sec)]
                for tf_sec in timeframes
            ]
            summary = summarize_named_cohort(
                f"SYMBOL_REGIME::{symbol}::{regime}",
                rows,
                meta={
                    "symbol": symbol,
                    "regime": regime,
                    "timeframes": timeframes,
                },
                negative_control_evals=negative_controls,
            )
            symbol_regime_evals.append(summary)

    per_regime = [
        summarize_parent_bucket(
            f"REGIME::{regime}",
            regime_rows.get(regime, []),
            [row for row in symbol_regime_evals if row.get(
                "regime") == regime],
            label_key="regime",
            label_value=regime,
        )
        for regime in REGIME_BUCKETS
    ]
    per_symbol = [
        summarize_parent_bucket(
            f"SYMBOL::{symbol}",
            symbol_rows.get(symbol, []),
            [row for row in symbol_regime_evals if row.get(
                "symbol") == symbol],
            label_key="symbol",
            label_value=symbol,
        )
        for symbol in SYM_BUCKETS
    ]

    global_counts = Counter(row.get("verdict") for row in symbol_regime_evals)
    global_summary = {
        "verdict": (
            "TARGETED_PATCH_CANDIDATES"
            if global_counts.get("PATCH_CANDIDATE", 0) > 0
            else "NO_CHANGE"
            if (global_counts.get("KEEP_BASELINE", 0) + global_counts.get("REJECT_OVERFIT", 0)) > 0
            else "INSUFFICIENT_DATA"
        ),
        "sample_size": len({str(row.get('rid') or '') for row in dataset}),
        "observation_count": len(dataset),
        "patch_candidate_count": global_counts.get("PATCH_CANDIDATE", 0),
        "reject_overfit_count": global_counts.get("REJECT_OVERFIT", 0),
        "keep_baseline_count": global_counts.get("KEEP_BASELINE", 0),
        "insufficient_data_count": global_counts.get("INSUFFICIENT_DATA", 0),
    }

    patch_candidates = [
        row for row in symbol_regime_evals if row.get("verdict") == "PATCH_CANDIDATE"
    ]
    rejected_candidates = [
        row for row in symbol_regime_evals if row.get("verdict") == "REJECT_OVERFIT"
    ]
    runtime_need = runtime_change_need(symbol_regime_evals)

    artifact = {
        "report_id": "NRR027_FULL_SYMBOL_REGIME_CALIBRATION_V2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_nrr": TARGET_NRR,
        "requested_symbols": SYM_BUCKETS,
        "requested_regimes": REGIME_BUCKETS,
        "available_timeframes": available_timeframes,
        "grid": {
            "hard_veto_consecutive_bars": GRID_HARD_VETO,
            "min_abs_delta_price_bps": GRID_MIN_ABS_DELTA_BPS,
            "cumulative_move_bps": GRID_CUMULATIVE_MOVE_BPS,
            "mode": GRID_MODE,
        },
        "current_config_snapshot": current_cfg,
        "provenance": provenance,
        "seed_case_count": len(seed_cases),
        "dataset_observation_count": len(dataset),
        "dataset_unique_event_count": len({str(row.get('rid') or '') for row in dataset}),
        "dataset": dataset,
        "cohorts": {
            "symbol_regime_timeframe": symbol_regime_tf_evals,
            "symbol_regime": symbol_regime_evals,
        },
        "per_regime": per_regime,
        "per_symbol": per_symbol,
        "global": global_summary,
        "patch_candidates": patch_candidates,
        "rejected_candidates": rejected_candidates,
        "runtime_change_need": runtime_need,
    }

    REPORT_JSON_PATH.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = build_report(
        seed_cases=seed_cases,
        dataset=dataset,
        provenance=provenance,
        current_cfg=current_cfg,
        per_symbol=per_symbol,
        per_regime=per_regime,
        per_symbol_regime=symbol_regime_evals,
        patch_candidates=patch_candidates,
        rejected_candidates=rejected_candidates,
        global_summary=global_summary,
        runtime_need=runtime_need,
    )
    REPORT_MD_PATH.write_text(report, encoding="utf-8")

    print(
        "NRR-027 calibrator done:",
        json.dumps(
            {
                "seed_cases": len(seed_cases),
                "dataset_observation_count": len(dataset),
                "dataset_unique_event_count": len({str(row.get('rid') or '') for row in dataset}),
                "global_verdict": global_summary["verdict"],
                "patch_candidates": len(patch_candidates),
                "rejected_candidates": len(rejected_candidates),
                "runtime_change_need": runtime_need["classification"],
                "report": str(REPORT_MD_PATH.relative_to(ROOT)).replace("\\", "/"),
                "artifact": str(REPORT_JSON_PATH.relative_to(ROOT)).replace("\\", "/"),
            },
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    run_calibration()
