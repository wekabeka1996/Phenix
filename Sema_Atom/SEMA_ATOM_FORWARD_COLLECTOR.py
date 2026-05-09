from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from SEMA_ATOM_POC_02_REAL_LOG_ADAPTER import (
    CONFIDENCE_BUCKETS,
    DEFAULT_TF_SEC,
    FEE_FLOOR_BPS,
    REJECT_HORIZONS,
    Bar,
)


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE_SAF_PATH = REPO_ROOT / "aurora_real_logs_v02.saf.jsonl"
DEFAULT_POC02_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
DEFAULT_POC03_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
DEFAULT_POC03B_MANIFEST_PATH = REPO_ROOT / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
DEFAULT_POC04_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md"
DEFAULT_ORDER_LOG_PATH = REPO_ROOT / "logs" / "order_log_v1.jsonl"
DEFAULT_TRADE_LIFECYCLE_PATH = REPO_ROOT / "logs" / "trade_lifecycle.jsonl"
DEFAULT_SHADOW_TELEMETRY_DIR = REPO_ROOT / "logs" / "shadow_telemetry"
DEFAULT_RECORDER_ROOT = REPO_ROOT / "data" / "recorder"
DEFAULT_INDEX_PATH = REPO_ROOT / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json"

REQUIRED_INPUT_LABELS = (
    "order_log",
    "baseline_saf",
)
OPTIONAL_INPUT_LABELS = (
    "trade_lifecycle",
    "shadow_telemetry",
    "poc02_report",
    "poc03_report",
    "poc03b_manifest",
    "poc04_report",
    "recorder_root",
)


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
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
    return int(numeric)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_symbol(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text else None


def _normalize_side(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    upper = text.upper()
    if upper in {"BUY", "SELL"}:
        return upper
    return None


def _bucketize_confidence(value: float | None) -> str:
    if value is None:
        return "unknown"
    for lower, upper, label in CONFIDENCE_BUCKETS:
        if lower <= value < upper:
            return label
    return "unknown"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str], int]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    line_count = 0
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line_count += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: json_decode_error:{exc.msg}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{path}:{line_number}: expected_object:{type(payload).__name__}")
                continue
            payload["_source_path"] = str(path)
            payload["_source_line"] = line_number
            rows.append(payload)
    return rows, errors, line_count


def _extract_first_float(mapping: dict[str, Any], paths: Sequence[Sequence[str]]) -> float | None:
    for path in paths:
        current: Any = mapping
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        numeric = _safe_float(current)
        if numeric is not None:
            return numeric
    return None


def _extract_first_text(mapping: dict[str, Any], paths: Sequence[Sequence[str]]) -> str | None:
    for path in paths:
        current: Any = mapping
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        value = _text(current)
        if value is not None:
            return value
    return None


def _date_to_range(day: date) -> tuple[int, int]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _ts_in_window(ts_ms: int | None, start_ms: int, end_ms: int) -> bool:
    if ts_ms is None:
        return False
    return start_ms <= ts_ms < end_ms


@dataclass(slots=True)
class RawContract:
    contract_kind: str
    contract_id: str
    decision_id: str | None
    decision_type: str
    symbol: str | None
    side: str | None
    strategy_id: str | None
    regime: str | None
    regime_confidence: float | None
    direction_confidence: float | None
    confidence_bucket: str
    spread_bps: float | None
    signal_score: float | None
    reference_price: float | None
    entry_price: float | None
    close_price: float | None
    entry_ts_ms: int | None
    event_ts_ms: int | None
    close_ts_ms: int | None
    realized_pnl_net: float | None
    fees: float | None
    trade_id: str | None
    close_reason: str | None
    pnl_status: str | None
    reject_reason: str | None
    lifecycle_id: str | None
    outcome_snapshot: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SemaAtomV01:
    atom_id: str
    atom_kind: str
    context: dict[str, Any]
    outcome_code: str
    confidence: float
    reward_bps: float
    threat_bps: float
    net_score: float
    surprise: float
    importance: float
    missing_fields: list[str]
    raw_contract: dict[str, Any]
    outcome_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_id"] = "SemaAtomV01"
        payload["schema_version"] = "1.0.0"
        return payload


class SideAwareMfeMaeCalculator:
    @staticmethod
    def calculate(side: str, entry_price: float, bars: Sequence[Bar]) -> tuple[float | None, float | None]:
        if not bars:
            return None, None
        normalized_side = _normalize_side(side)
        if normalized_side is None:
            return None, None
        mfe_values: list[float] = []
        mae_values: list[float] = []
        if normalized_side == "BUY":
            for bar in bars:
                mfe_values.append((bar.high - entry_price) / entry_price * 10000.0)
                mae_values.append((bar.low - entry_price) / entry_price * 10000.0)
        else:
            for bar in bars:
                mfe_values.append((entry_price - bar.low) / entry_price * 10000.0)
                mae_values.append((entry_price - bar.high) / entry_price * 10000.0)
        return max(mfe_values), min(mae_values)


class RecorderStore:
    def __init__(self, recorder_root: Path, tf_sec: int) -> None:
        self.recorder_root = recorder_root
        self.tf_sec = tf_sec
        self._cache: dict[str, list[Bar]] = {}

    def load_symbol(self, symbol: str) -> list[Bar]:
        normalized = _normalize_symbol(symbol)
        if normalized is None:
            return []
        if normalized in self._cache:
            return self._cache[normalized]
        pattern = f"{normalized}_{self.tf_sec}.csv"
        bars: list[Bar] = []
        for path in sorted(self.recorder_root.rglob(pattern)):
            with path.open("r", encoding="utf-8-sig") as handle:
                header = _text(handle.readline())
                if not header:
                    continue
                columns = [part.strip() for part in header.split(",")]
                index = {name: idx for idx, name in enumerate(columns)}
                required = {"timestamp", "close", "high", "low"}
                if not required.issubset(index):
                    continue
                max_index = max(index[name] for name in required)
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = [part.strip() for part in line.split(",")]
                    if len(parts) <= max_index:
                        continue
                    ts_ms = _safe_int(parts[index["timestamp"]])
                    close = _safe_float(parts[index["close"]])
                    high = _safe_float(parts[index["high"]])
                    low = _safe_float(parts[index["low"]])
                    if ts_ms is None or close is None or high is None or low is None:
                        continue
                    bars.append(Bar(ts_ms=ts_ms, close=close, high=high, low=low))
        deduped: dict[int, Bar] = {}
        for bar in bars:
            deduped[bar.ts_ms] = bar
        ordered = [deduped[key] for key in sorted(deduped)]
        self._cache[normalized] = ordered
        return ordered


class AcceptedLifecycleReducer:
    def __init__(self, rows: Sequence[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.incomplete_buckets: Counter[str] = Counter()

    def reduce(self) -> tuple[list[RawContract], dict[str, Any]]:
        contracts: list[RawContract] = []
        decision_intents_by_lifecycle: dict[str, dict[str, Any]] = {}
        decision_intents_by_rid: dict[str, dict[str, Any]] = {}
        entry_fills_by_lifecycle: dict[str, dict[str, Any]] = {}

        for row in self.rows:
            event_type = row.get("event_type")
            if event_type == "ORDER_INTENT" and row.get("source_fsm") == "DecisionMaking":
                lifecycle_id = _text(row.get("lifecycle_id"))
                rid = _text(row.get("rid"))
                if lifecycle_id:
                    decision_intents_by_lifecycle[lifecycle_id] = row
                if rid:
                    decision_intents_by_rid[rid] = row
            elif event_type == "ORDER_FILLED" and _text(row.get("order_kind")) == "ENTRY":
                lifecycle_id = _text(row.get("lifecycle_id"))
                if lifecycle_id:
                    entry_fills_by_lifecycle[lifecycle_id] = row

        accepted_close_events_found = 0
        accepted_contracts_completed = 0
        for row in self.rows:
            if row.get("event_type") != "POSITION_CLOSED":
                continue
            accepted_close_events_found += 1
            rid = _text(row.get("rid")) or f"position_closed_line_{row.get('_source_line')}"
            lifecycle_id = _text(row.get("lifecycle_id"))
            base_rid = rid.split(":", 1)[0]
            decision_row = (
                (decision_intents_by_lifecycle.get(lifecycle_id) if lifecycle_id else None)
                or decision_intents_by_rid.get(base_rid)
                or decision_intents_by_rid.get(rid)
            )
            entry_fill = entry_fills_by_lifecycle.get(lifecycle_id or "")

            symbol = _normalize_symbol(row.get("symbol")) or _normalize_symbol((decision_row or {}).get("symbol"))
            side = _normalize_side(row.get("side")) or _normalize_side((decision_row or {}).get("side"))
            strategy_id = _text((decision_row or {}).get("strategy_id")) or "aurora"
            regime = _text((decision_row or {}).get("regime"))
            regime_confidence = _safe_float((decision_row or {}).get("regime_confidence"))
            direction_confidence = _extract_first_float(
                decision_row or {},
                (
                    ("metadata", "direction_confidence"),
                    ("metadata", "low_vol_cost_floor", "direction_confidence"),
                    ("signal_score",),
                ),
            )
            spread_bps = _extract_first_float(
                decision_row or {},
                (
                    ("metadata", "liquidity_context", "spread_bps"),
                    ("metadata", "spread_bps"),
                ),
            )
            signal_score = _extract_first_float(
                decision_row or {},
                (
                    ("metadata", "score_context", "signal_score"),
                    ("metadata", "final_score_raw"),
                    ("metadata", "low_vol_cost_floor", "final_score_raw"),
                    ("signal_score",),
                ),
            )
            entry_price = _safe_float((entry_fill or {}).get("price"))
            entry_price_source = "entry_fill"
            if entry_price is None:
                entry_price = _safe_float((decision_row or {}).get("price"))
                entry_price_source = "decision_intent" if entry_price is not None else "missing"
            close_price = _extract_first_float(
                row,
                (
                    ("metadata", "close_price"),
                    ("close_price",),
                ),
            )
            entry_ts_ms = _safe_int((entry_fill or {}).get("timestamp")) or _safe_int((decision_row or {}).get("timestamp"))
            close_ts_ms = _safe_int(row.get("timestamp"))
            realized_pnl_net = _safe_float(row.get("realized_pnl_net"))
            fees = _safe_float(row.get("fees"))
            pnl_status = _text(row.get("pnl_status"))
            missing_fields: list[str] = []
            if regime_confidence is None:
                missing_fields.append("regime_confidence")
            if entry_price is None:
                missing_fields.append("entry_price")
                self.incomplete_buckets["accepted_missing_entry_price"] += 1
            if entry_ts_ms is None:
                missing_fields.append("entry_ts_ms")
            if close_ts_ms is None:
                missing_fields.append("close_ts_ms")
            if realized_pnl_net is None:
                missing_fields.append("realized_pnl_net")
                self.incomplete_buckets["incomplete_accepted_missing_realized_pnl_net"] += 1
            if pnl_status == "unresolved":
                self.incomplete_buckets["incomplete_accepted_unresolved_pnl_status"] += 1
            if symbol is None:
                missing_fields.append("symbol")
                self.incomplete_buckets["accepted_missing_symbol"] += 1
            if side is None:
                missing_fields.append("side")
                self.incomplete_buckets["accepted_missing_side"] += 1
            if regime is None:
                missing_fields.append("regime")
                self.incomplete_buckets["accepted_missing_regime"] += 1

            decision_id = _text((decision_row or {}).get("rid")) or rid
            contract = RawContract(
                contract_kind="ACCEPTED",
                contract_id=rid,
                decision_id=decision_id,
                decision_type="ACCEPTED",
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                regime=regime,
                regime_confidence=regime_confidence,
                direction_confidence=direction_confidence,
                confidence_bucket=_bucketize_confidence(regime_confidence),
                spread_bps=spread_bps,
                signal_score=signal_score,
                reference_price=entry_price,
                entry_price=entry_price,
                close_price=close_price,
                entry_ts_ms=entry_ts_ms,
                event_ts_ms=close_ts_ms,
                close_ts_ms=close_ts_ms,
                realized_pnl_net=realized_pnl_net,
                fees=fees,
                trade_id=_text(row.get("trade_id")),
                close_reason=_text(row.get("close_reason")) or _text(row.get("why")),
                pnl_status=pnl_status,
                reject_reason=None,
                lifecycle_id=lifecycle_id,
                missing_fields=missing_fields,
                provenance={
                    "close_source_path": row.get("_source_path"),
                    "close_source_line": row.get("_source_line"),
                    "decision_intent_source_line": (decision_row or {}).get("_source_line"),
                    "entry_fill_source_line": (entry_fill or {}).get("_source_line"),
                    "entry_price_source": entry_price_source,
                },
            )
            if symbol and side and regime and realized_pnl_net is not None and pnl_status != "unresolved":
                accepted_contracts_completed += 1
            contracts.append(contract)

        return contracts, {
            "accepted_close_events_found": accepted_close_events_found,
            "accepted_contracts_completed": accepted_contracts_completed,
            "incomplete_accepted_missing_realized_pnl_net": self.incomplete_buckets.get(
                "incomplete_accepted_missing_realized_pnl_net",
                0,
            ),
            "accepted_incomplete_buckets": dict(self.incomplete_buckets),
        }


class RejectedDecisionCollector:
    def __init__(self, rows: Sequence[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.incomplete_buckets: Counter[str] = Counter()

    def collect(self) -> tuple[list[RawContract], dict[str, Any]]:
        contracts: list[RawContract] = []
        rejected_events_found = 0
        rejected_with_reference_price = 0
        rejected_evaluated = 0
        for row in self.rows:
            if row.get("event_type") != "DECISION_INTENT_REJECTED":
                continue
            rejected_events_found += 1
            symbol = _normalize_symbol(row.get("symbol"))
            side = _normalize_side(row.get("side"))
            strategy_id = _text(row.get("strategy_id")) or "aurora"
            regime = _text(row.get("regime"))
            if symbol is None or side is None or regime is None:
                self.incomplete_buckets["incomplete_rejected_missing_critical_fields"] += 1
                continue

            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            low_vol_cost_floor = metadata.get("low_vol_cost_floor") if isinstance(metadata.get("low_vol_cost_floor"), dict) else {}
            regime_confidence = _safe_float(row.get("regime_confidence"))
            direction_confidence = _extract_first_float(
                row,
                (
                    ("metadata", "low_vol_cost_floor", "direction_confidence"),
                    ("metadata", "direction_confidence"),
                    ("direction_confidence",),
                ),
            )
            reference_price = _extract_first_float(
                row,
                (
                    ("metadata", "low_vol_cost_floor", "entry_price"),
                    ("metadata", "reference_price"),
                    ("metadata", "intended_entry_price"),
                    ("metadata", "economics_context", "entry_price"),
                    ("reference_price",),
                    ("intended_entry_price",),
                ),
            )
            spread_bps = _extract_first_float(
                row,
                (
                    ("metadata", "liquidity_context", "spread_bps"),
                    ("metadata", "spread_bps"),
                ),
            )
            signal_score = _extract_first_float(
                row,
                (
                    ("metadata", "low_vol_cost_floor", "direction_confidence"),
                    ("metadata", "score_context", "signal_score"),
                    ("metadata", "final_score_raw"),
                    ("final_score",),
                ),
            )
            missing_fields: list[str] = []
            if regime_confidence is None:
                missing_fields.append("regime_confidence")
            if reference_price is None:
                self.incomplete_buckets["incomplete_rejected_missing_reference_price"] += 1
                continue
            rejected_with_reference_price += 1
            ts_ms = _safe_int(row.get("timestamp"))
            if ts_ms is None:
                missing_fields.append("timestamp")
            contract = RawContract(
                contract_kind="REJECTED",
                contract_id=_text(row.get("rid")) or f"rejected_line_{row.get('_source_line')}",
                decision_id=_text(row.get("decision_id")) or _text(row.get("rid")),
                decision_type="REJECTED",
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                regime=regime,
                regime_confidence=regime_confidence,
                direction_confidence=direction_confidence,
                confidence_bucket=_bucketize_confidence(regime_confidence),
                spread_bps=spread_bps,
                signal_score=signal_score,
                reference_price=reference_price,
                entry_price=reference_price,
                close_price=None,
                entry_ts_ms=ts_ms,
                event_ts_ms=ts_ms,
                close_ts_ms=None,
                realized_pnl_net=None,
                fees=None,
                trade_id=_text(row.get("decision_id")) or _text(row.get("rid")),
                close_reason=None,
                pnl_status=None,
                reject_reason=_extract_first_text(
                    row,
                    (
                        ("metadata", "reject_reason"),
                        ("metadata", "deny_reason"),
                        ("why",),
                    ),
                ),
                lifecycle_id=None,
                missing_fields=missing_fields,
                provenance={
                    "reject_source_path": row.get("_source_path"),
                    "reject_source_line": row.get("_source_line"),
                    "reference_price_source": "metadata.low_vol_cost_floor.entry_price"
                    if _safe_float(low_vol_cost_floor.get("entry_price")) is not None
                    else "fallback_nested_field",
                },
            )
            rejected_evaluated += 1
            contracts.append(contract)

        coverage = None
        if rejected_events_found:
            coverage = rejected_with_reference_price / rejected_events_found
        return contracts, {
            "rejected_events_found": rejected_events_found,
            "rejected_with_reference_price": rejected_with_reference_price,
            "rejected_missing_reference_price": self.incomplete_buckets.get("incomplete_rejected_missing_reference_price", 0),
            "rejected_missing_critical_fields": self.incomplete_buckets.get("incomplete_rejected_missing_critical_fields", 0),
            "rejected_evaluated": rejected_evaluated,
            "rejected_reference_price_coverage": coverage,
            "rejected_incomplete_buckets": dict(self.incomplete_buckets),
        }


class OfflineMarketReplayEvaluator:
    def __init__(self, recorder_store: RecorderStore) -> None:
        self.recorder_store = recorder_store
        self.mfe_mae_computed_count = 0
        self.mfe_mae_missing_count = 0
        self.rejected_missing_market_coverage = 0

    def evaluate_accepted(self, contract: RawContract) -> None:
        if (
            contract.symbol is None
            or contract.side is None
            or contract.entry_price is None
            or contract.entry_ts_ms is None
            or contract.close_ts_ms is None
        ):
            self.mfe_mae_missing_count += 1
            return
        bars = [
            bar
            for bar in self.recorder_store.load_symbol(contract.symbol)
            if contract.entry_ts_ms <= bar.ts_ms <= contract.close_ts_ms
        ]
        mfe_bps, mae_bps = SideAwareMfeMaeCalculator.calculate(contract.side, contract.entry_price, bars)
        if mfe_bps is None or mae_bps is None:
            self.mfe_mae_missing_count += 1
            return
        self.mfe_mae_computed_count += 1
        contract.outcome_snapshot["mfe_bps"] = mfe_bps
        contract.outcome_snapshot["mae_bps"] = mae_bps

    def evaluate_rejected(self, contract: RawContract) -> None:
        if (
            contract.symbol is None
            or contract.side is None
            or contract.entry_price is None
            or contract.event_ts_ms is None
        ):
            self.rejected_missing_market_coverage += 1
            return
        bars = self.recorder_store.load_symbol(contract.symbol)
        horizons: dict[str, dict[str, Any]] = {}
        any_coverage = False
        for label, delta_ms in REJECT_HORIZONS:
            target_ts = contract.event_ts_ms + delta_ms
            future_bar = next((bar for bar in bars if bar.ts_ms >= target_ts), None)
            if future_bar is None:
                horizons[label] = {"future_ts_ms": None, "future_price": None, "post_move_bps": None}
                continue
            any_coverage = True
            if contract.side == "BUY":
                post_move_bps = (future_bar.close - contract.entry_price) / contract.entry_price * 10000.0
            else:
                post_move_bps = (contract.entry_price - future_bar.close) / contract.entry_price * 10000.0
            horizons[label] = {
                "future_ts_ms": future_bar.ts_ms,
                "future_price": future_bar.close,
                "post_move_bps": post_move_bps,
            }
        if not any_coverage:
            self.rejected_missing_market_coverage += 1
        contract.outcome_snapshot["post_move_horizons"] = horizons
        contract.outcome_snapshot["post_move_bps"] = (
            horizons.get("T+30m", {}).get("post_move_bps")
            if isinstance(horizons.get("T+30m"), dict)
            else None
        )


class SemaEncoder:
    def __init__(self) -> None:
        self.encoding_errors: list[str] = []

    def encode(self, contract: RawContract) -> SemaAtomV01 | None:
        symbol = _normalize_symbol(contract.symbol)
        side = _normalize_side(contract.side)
        regime = _text(contract.regime)
        if symbol is None or side is None or regime is None:
            return None
        strategy_id = _text(contract.strategy_id) or "aurora"
        missing_fields = list(dict.fromkeys(contract.missing_fields))
        confidence_bucket = contract.confidence_bucket
        if contract.regime_confidence is None:
            confidence_bucket = "unknown"
            if "regime_confidence" not in missing_fields:
                missing_fields.append("regime_confidence")

        try:
            if contract.contract_kind == "ACCEPTED":
                return self._encode_accepted(contract, symbol, side, regime, strategy_id, confidence_bucket, missing_fields)
            return self._encode_rejected(contract, symbol, side, regime, strategy_id, confidence_bucket, missing_fields)
        except Exception as exc:
            self.encoding_errors.append(f"{contract.contract_id}: {type(exc).__name__}: {exc}")
            return None

    def _confidence_score(self, missing_fields: Sequence[str], contract: RawContract) -> float:
        score = 1.0
        score -= min(0.5, len(missing_fields) * 0.1)
        if contract.provenance.get("entry_price_source") == "decision_intent":
            score -= 0.1
        return max(0.25, round(score, 4))

    def _encode_accepted(
        self,
        contract: RawContract,
        symbol: str,
        side: str,
        regime: str,
        strategy_id: str,
        confidence_bucket: str,
        missing_fields: list[str],
    ) -> SemaAtomV01:
        realized_move_bps: float | None = None
        if contract.entry_price is not None and contract.close_price is not None:
            if side == "BUY":
                realized_move_bps = (contract.close_price - contract.entry_price) / contract.entry_price * 10000.0
            else:
                realized_move_bps = (contract.entry_price - contract.close_price) / contract.entry_price * 10000.0

        mfe_bps = _safe_float(contract.outcome_snapshot.get("mfe_bps"))
        mae_bps = _safe_float(contract.outcome_snapshot.get("mae_bps"))
        reward_bps = max(realized_move_bps or 0.0, 0.0)
        threat_bps = abs(min(mae_bps if mae_bps is not None else (realized_move_bps or 0.0), 0.0))
        surprise = 0.0
        if mfe_bps is not None and realized_move_bps is not None:
            surprise = abs(mfe_bps - realized_move_bps)
        importance = abs(realized_move_bps or 0.0) + threat_bps
        outcome_code = "ACCEPTED_UNSCORABLE"
        if realized_move_bps is not None:
            if realized_move_bps > 0:
                outcome_code = "ACCEPTED_WIN"
            elif realized_move_bps < 0:
                outcome_code = "ACCEPTED_LOSS"
            else:
                outcome_code = "ACCEPTED_FLAT"
        if outcome_code in {"ACCEPTED_UNSCORABLE", "ACCEPTED_FLAT"} and contract.realized_pnl_net is not None:
            if contract.realized_pnl_net > 0:
                outcome_code = "ACCEPTED_WIN"
            elif contract.realized_pnl_net < 0:
                outcome_code = "ACCEPTED_LOSS"
        if (
            outcome_code == "ACCEPTED_WIN"
            and mfe_bps is not None
            and realized_move_bps is not None
            and mfe_bps > FEE_FLOOR_BPS * 2.0
            and realized_move_bps < mfe_bps * 0.25
        ):
            outcome_code = "BAD_EXIT"

        if realized_move_bps is not None:
            contract.outcome_snapshot["realized_move_bps"] = realized_move_bps
        return SemaAtomV01(
            atom_id=f"accepted::{contract.contract_id}",
            atom_kind="ACCEPTED",
            context={
                "symbol": symbol,
                "side": side,
                "strategy_id": strategy_id,
                "regime": regime,
                "confidence_bucket": confidence_bucket,
            },
            outcome_code=outcome_code,
            confidence=self._confidence_score(missing_fields, contract),
            reward_bps=round(reward_bps, 6),
            threat_bps=round(threat_bps, 6),
            net_score=round(reward_bps - threat_bps, 6),
            surprise=round(surprise, 6),
            importance=round(importance, 6),
            missing_fields=missing_fields,
            raw_contract=contract.to_dict(),
            outcome_snapshot=contract.outcome_snapshot,
        )

    def _encode_rejected(
        self,
        contract: RawContract,
        symbol: str,
        side: str,
        regime: str,
        strategy_id: str,
        confidence_bucket: str,
        missing_fields: list[str],
    ) -> SemaAtomV01:
        post_move_bps = _safe_float(contract.outcome_snapshot.get("post_move_bps"))
        reward_bps = 0.0
        threat_bps = 0.0
        outcome_code = "REJECT_UNSCORABLE"
        if post_move_bps is not None:
            if post_move_bps < 0:
                reward_bps = abs(post_move_bps)
                outcome_code = "REJECT_CORRECT_BLOCK"
            elif post_move_bps > 0:
                threat_bps = post_move_bps
                outcome_code = "REJECT_MISSED_POSITIVE"
            else:
                outcome_code = "REJECT_FLAT"
        importance = abs(post_move_bps or 0.0)
        surprise = abs(post_move_bps or 0.0)
        return SemaAtomV01(
            atom_id=f"rejected::{contract.contract_id}",
            atom_kind="REJECTED",
            context={
                "symbol": symbol,
                "side": side,
                "strategy_id": strategy_id,
                "regime": regime,
                "confidence_bucket": confidence_bucket,
            },
            outcome_code=outcome_code,
            confidence=self._confidence_score(missing_fields, contract),
            reward_bps=round(reward_bps, 6),
            threat_bps=round(threat_bps, 6),
            net_score=round(reward_bps - threat_bps, 6),
            surprise=round(surprise, 6),
            importance=round(importance, 6),
            missing_fields=missing_fields,
            raw_contract=contract.to_dict(),
            outcome_snapshot=contract.outcome_snapshot,
        )


class ForwardCollectionIndexer:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path

    def update(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {"version": 1, "slices": []}
        if self.index_path.exists():
            try:
                payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"version": 1, "slices": []}
            if not isinstance(payload, dict):
                payload = {"version": 1, "slices": []}
        slices = payload.get("slices")
        if not isinstance(slices, list):
            slices = []
        replaced = False
        next_slices: list[dict[str, Any]] = []
        for existing in slices:
            if isinstance(existing, dict) and existing.get("slice_id") == record.get("slice_id"):
                next_slices.append(record)
                replaced = True
            else:
                next_slices.append(existing)
        if not replaced:
            next_slices.append(record)
        payload = {"version": 1, "slices": next_slices}
        self.index_path.write_text(_json_dumps(payload) + "\n", encoding="utf-8")
        return payload


class ForwardCollectionReportGenerator:
    def generate(
        self,
        *,
        status: str,
        scope_note: str,
        inputs_read: Sequence[str],
        missing_required_inputs: Sequence[str],
        missing_optional_inputs: Sequence[str],
        time_window: dict[str, Any],
        outputs: Sequence[Path],
        line_counts: dict[str, int],
        accepted_results: dict[str, Any],
        rejected_results: dict[str, Any],
        replay_results: dict[str, Any],
        encoding_summary: dict[str, Any],
        context_migration: dict[str, Any],
        missing_field_histogram: dict[str, int],
        dedupe_summary: dict[str, Any],
        error_samples: Sequence[str],
    ) -> str:
        lines = [
            f"# SEMA_ATOM_FORWARD_COLLECTION_{time_window['slice_id']}_REPORT",
            "",
            "## Verdict",
            status,
            "",
            "## Scope",
            f"- {scope_note}",
            "- Read-only batch collection only. No live logic, policy, gates, enforcement, or runtime journal writes.",
            "",
            "## Inputs Read",
        ]
        for item in inputs_read:
            lines.append(f"- {item}")
        lines.extend(
            [
                f"- missing_required_inputs: {_json_dumps(list(missing_required_inputs))}",
                f"- missing_optional_inputs: {_json_dumps(list(missing_optional_inputs))}",
                "",
                "## Time Window",
                f"- from: {time_window['from']}",
                f"- to: {time_window['to']}",
                f"- slice_id: {time_window['slice_id']}",
                f"- window_start_ts_ms: {time_window['start_ts_ms']}",
                f"- window_end_ts_ms_exclusive: {time_window['end_ts_ms']}",
                f"- log_dates_observed: {_json_dumps(time_window['log_dates_observed'])}",
                f"- recorder_dates_available: {_json_dumps(time_window['recorder_dates_available'])}",
                f"- recorder_dates_missing: {_json_dumps(time_window['recorder_dates_missing'])}",
                "",
                "## Output Artifacts",
            ]
        )
        for path in outputs:
            lines.append(f"- {path.name}")
        lines.extend(
            [
                "",
                "## Accepted Reducer Results",
                f"- log lines read: {sum(line_counts.values())}",
                f"- accepted close events found: {accepted_results.get('accepted_close_events_found', 0)}",
                f"- accepted contracts completed: {accepted_results.get('accepted_contracts_completed', 0)}",
                f"- incomplete_accepted_missing_realized_pnl_net: {accepted_results.get('incomplete_accepted_missing_realized_pnl_net', 0)}",
                f"- accepted incomplete buckets: {_json_dumps(accepted_results.get('accepted_incomplete_buckets', {}))}",
                "",
                "## Rejected Collector Results",
                f"- rejected events found: {rejected_results.get('rejected_events_found', 0)}",
                f"- rejected with reference_price: {rejected_results.get('rejected_with_reference_price', 0)}",
                f"- rejected missing reference_price: {rejected_results.get('rejected_missing_reference_price', 0)}",
                f"- rejected missing critical fields: {rejected_results.get('rejected_missing_critical_fields', 0)}",
                f"- rejected evaluated: {rejected_results.get('rejected_evaluated', 0)}",
                "",
                "## Offline Replay Results",
                f"- MFE/MAE computed: {replay_results.get('mfe_mae_computed_count', 0)}",
                f"- MFE/MAE missing: {replay_results.get('mfe_mae_missing_count', 0)}",
                f"- rejected missing market coverage: {replay_results.get('rejected_missing_market_coverage', 0)}",
                "",
                "## SemaAtom Encoding Results",
                f"- atoms created: {encoding_summary.get('atoms_created', 0)}",
                f"- accepted_atoms_created: {encoding_summary.get('accepted_atoms_created', 0)}",
                f"- rejected_atoms_created: {encoding_summary.get('rejected_atoms_created', 0)}",
                f"- diagnostics_only_atoms_created: {encoding_summary.get('diagnostics_only_atoms_created', 0)}",
                f"- atoms_created_reconciliation_ok: {encoding_summary.get('atoms_created_reconciliation_ok', False)}",
                f"- atoms skipped: {encoding_summary.get('atoms_skipped', 0)}",
                f"- encoding errors: {encoding_summary.get('encoding_errors_count', 0)}",
                "",
                "## Context Migration",
                f"- new contexts: {context_migration.get('new_contexts', 0)}",
                f"- existing contexts updated: {context_migration.get('existing_contexts_updated', 0)}",
                f"- contexts promoted from low-support: {context_migration.get('contexts_promoted_from_low_support', 0)}",
                f"- contexts still low-support: {context_migration.get('contexts_still_low_support', 0)}",
                f"- new_context_keys: {_json_dumps(context_migration.get('new_context_keys', []))}",
                "",
                "## Reference Price Coverage",
                f"- rejected_reference_price_coverage: {json.dumps(rejected_results.get('rejected_reference_price_coverage'))}",
                "",
                "## MFE/MAE Coverage",
                f"- computed: {replay_results.get('mfe_mae_computed_count', 0)}",
                f"- missing: {replay_results.get('mfe_mae_missing_count', 0)}",
                "",
                "## Missing Field Histogram",
                f"- histogram: {_json_dumps(missing_field_histogram)}",
                "",
                "## Deduplication",
                f"- duplicates_detected: {dedupe_summary.get('duplicates_detected', 0)}",
                f"- duplicates_skipped: {dedupe_summary.get('duplicates_skipped', 0)}",
                "",
                "## Error Samples",
            ]
        )
        if error_samples:
            for sample in error_samples:
                lines.append(f"- {sample}")
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "## Residual Risks",
            ]
        )
        if missing_required_inputs:
            lines.append("- Required inputs were missing, so results are blocked or partial.")
        if time_window["recorder_dates_missing"]:
            lines.append("- Requested date window exceeds recorder date coverage for at least one day.")
        if replay_results.get("rejected_missing_market_coverage", 0):
            lines.append("- Some rejected rows had no forward replay bar coverage at one or more horizons.")
        if replay_results.get("mfe_mae_missing_count", 0):
            lines.append("- Some accepted rows lacked entry_price or replay bar coverage for MFE/MAE reconstruction.")
        if not any(
            [
                missing_required_inputs,
                time_window["recorder_dates_missing"],
                replay_results.get("rejected_missing_market_coverage", 0),
                replay_results.get("mfe_mae_missing_count", 0),
            ]
        ):
            lines.append("- No additional residuals beyond standard offline replay limits.")
        lines.extend(
            [
                "",
                "## Next Recommended Step",
                "- SEMA_ATOM_FC_02_MULTI_SLICE_REVALIDATION",
                "",
            ]
        )
        return "\n".join(lines)


def _input_inventory(paths: dict[str, Path]) -> tuple[list[str], list[str], list[str]]:
    inputs_read: list[str] = []
    missing_required: list[str] = []
    missing_optional: list[str] = []
    for label, path in paths.items():
        if path.exists():
            inputs_read.append(f"{label}: {path}")
        elif label in REQUIRED_INPUT_LABELS:
            missing_required.append(label)
        elif label in OPTIONAL_INPUT_LABELS:
            missing_optional.append(label)
    return inputs_read, missing_required, missing_optional


def _load_existing_atoms(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    atoms: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                atoms.append(payload)
    return atoms


def _accepted_dedupe_key(contract: RawContract) -> str:
    return ":".join(
        [
            "accepted",
            contract.lifecycle_id or "",
            contract.trade_id or "",
            str(contract.close_ts_ms or ""),
        ]
    )


def _rejected_dedupe_key(contract: RawContract) -> str:
    return ":".join(
        [
            "rejected",
            contract.decision_id or "",
            contract.symbol or "",
            contract.side or "",
            str(contract.event_ts_ms or ""),
            contract.reject_reason or "",
        ]
    )


def _atom_dedupe_key_from_payload(atom: dict[str, Any]) -> str | None:
    raw_contract = atom.get("raw_contract")
    if not isinstance(raw_contract, dict):
        return None
    contract_kind = raw_contract.get("contract_kind")
    if contract_kind == "ACCEPTED":
        lifecycle_id = _text(raw_contract.get("lifecycle_id")) or ""
        trade_id = _text(raw_contract.get("trade_id")) or ""
        close_ts_ms = str(_safe_int(raw_contract.get("close_ts_ms")) or "")
        return f"accepted:{lifecycle_id}:{trade_id}:{close_ts_ms}"
    if contract_kind == "REJECTED":
        decision_id = _text(raw_contract.get("decision_id")) or _text(raw_contract.get("trade_id")) or ""
        symbol = _normalize_symbol(raw_contract.get("symbol")) or ""
        side = _normalize_side(raw_contract.get("side")) or ""
        timestamp = str(_safe_int(raw_contract.get("event_ts_ms")) or "")
        reject_reason = _text(raw_contract.get("reject_reason")) or ""
        return f"rejected:{decision_id}:{symbol}:{side}:{timestamp}:{reject_reason}"
    return None


def _context_key_from_atom(atom: dict[str, Any]) -> str | None:
    context = atom.get("context")
    if not isinstance(context, dict):
        return None
    symbol = _normalize_symbol(context.get("symbol"))
    side = _normalize_side(context.get("side"))
    strategy_id = _text(context.get("strategy_id"))
    regime = _text(context.get("regime"))
    confidence_bucket = _text(context.get("confidence_bucket"))
    if None in {symbol, side, strategy_id, regime, confidence_bucket}:
        return None
    return "|".join([symbol, side, strategy_id, regime, confidence_bucket])


def _context_key_from_contract(contract: RawContract) -> str | None:
    symbol = _normalize_symbol(contract.symbol)
    side = _normalize_side(contract.side)
    strategy_id = _text(contract.strategy_id)
    regime = _text(contract.regime)
    confidence_bucket = _text(contract.confidence_bucket)
    if None in {symbol, side, strategy_id, regime, confidence_bucket}:
        return None
    return "|".join([symbol, side, strategy_id, regime, confidence_bucket])


def _load_low_support_baseline(manifest_path: Path) -> dict[str, int]:
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    baseline: dict[str, int] = {}
    for bucket in ("PROMISING_LOW_SUPPORT", "INCONCLUSIVE_LOW_POWER"):
        items = payload.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            context_id = _text(item.get("context_id"))
            if context_id is None:
                continue
            train_count = _safe_int(item.get("train_count")) or 0
            validation_count = _safe_int(item.get("validation_count")) or 0
            baseline[context_id] = train_count + validation_count
    return baseline


def _count_contexts(atoms: Sequence[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for atom in atoms:
        key = _context_key_from_atom(atom)
        if key is not None:
            counts[key] += 1
    return counts


def _missing_field_histogram(contracts: Sequence[RawContract]) -> dict[str, int]:
    histogram: Counter[str] = Counter()
    for contract in contracts:
        histogram.update(contract.missing_fields)
    return dict(sorted(histogram.items()))


def _collect_dates_in_range(start_day: date, end_day: date) -> list[str]:
    result: list[str] = []
    current = start_day
    while current <= end_day:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _window_rows(rows: Sequence[dict[str, Any]], start_ms: int, end_ms: int) -> tuple[list[dict[str, Any]], list[str]]:
    filtered: list[dict[str, Any]] = []
    observed_dates: set[str] = set()
    for row in rows:
        ts_ms = _safe_int(row.get("timestamp"))
        if not _ts_in_window(ts_ms, start_ms, end_ms):
            continue
        filtered.append(row)
        if ts_ms is not None:
            observed_dates.add(datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).date().isoformat())
    return filtered, sorted(observed_dates)


def _write_jsonl(path: Path, atoms: Sequence[SemaAtomV01]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for atom in atoms:
            handle.write(_json_dumps(atom.to_dict()))
            handle.write("\n")


def _accepted_contract_is_trainable(contract: RawContract) -> bool:
    if contract.contract_kind != "ACCEPTED":
        return True
    if _text(contract.pnl_status) == "unresolved":
        return False
    if contract.realized_pnl_net is None:
        return False
    return True


def _determine_status(
    *,
    missing_required_inputs: Sequence[str],
    atoms_created: int,
    atoms_created_reconciliation_ok: bool,
    encoding_errors_count: int,
    recorder_dates_missing: Sequence[str],
    rejected_missing_market_coverage: int,
    mfe_mae_missing_count: int,
    dedupe_failed: bool,
) -> str:
    if missing_required_inputs:
        return "BLOCKED_BY_MISSING_REQUIRED_INPUTS"
    if dedupe_failed:
        return "FAILED_DEDUPLICATION_GUARD"
    if not atoms_created_reconciliation_ok:
        return "FAILED_SCHEMA_VALIDATION"
    if encoding_errors_count:
        return "FAILED_SCHEMA_VALIDATION"
    if atoms_created == 0:
        return "PARTIAL_COLLECTION_ONLY"
    if recorder_dates_missing and rejected_missing_market_coverage == 0 and mfe_mae_missing_count == 0:
        return "FORWARD_COLLECTION_COMPLETED_WITH_RESIDUALS"
    if rejected_missing_market_coverage or mfe_mae_missing_count or recorder_dates_missing:
        return "FORWARD_COLLECTION_COMPLETED_WITH_RESIDUALS"
    return "FORWARD_COLLECTION_COMPLETED"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only forward SemaAtom collector.")
    parser.add_argument("--from", dest="from_day", required=True, help="Inclusive UTC start date in YYYY-MM-DD.")
    parser.add_argument("--to", dest="to_day", required=True, help="Inclusive UTC end date in YYYY-MM-DD.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from_day = _parse_day(args.from_day)
    to_day = _parse_day(args.to_day)
    if to_day < from_day:
        raise SystemExit("--to must be >= --from")

    start_ts_ms, _ = _date_to_range(from_day)
    _, end_ts_ms = _date_to_range(to_day)
    slice_id = f"{from_day.isoformat()}_{to_day.isoformat()}"
    slice_path = REPO_ROOT / f"aurora_forward_slice_{slice_id}.saf.jsonl"
    report_path = REPO_ROOT / f"SEMA_ATOM_FORWARD_COLLECTION_{slice_id}_REPORT.md"

    inputs = {
        "order_log": DEFAULT_ORDER_LOG_PATH,
        "trade_lifecycle": DEFAULT_TRADE_LIFECYCLE_PATH,
        "shadow_telemetry": DEFAULT_SHADOW_TELEMETRY_DIR,
        "recorder_root": DEFAULT_RECORDER_ROOT,
        "baseline_saf": DEFAULT_BASELINE_SAF_PATH,
        "poc02_report": DEFAULT_POC02_REPORT_PATH,
        "poc03_report": DEFAULT_POC03_REPORT_PATH,
        "poc03b_manifest": DEFAULT_POC03B_MANIFEST_PATH,
        "poc04_report": DEFAULT_POC04_REPORT_PATH,
    }
    inputs_read, missing_required_inputs, missing_optional_inputs = _input_inventory(inputs)

    outputs = [slice_path, report_path, DEFAULT_INDEX_PATH]
    error_samples: list[str] = []
    line_counts: dict[str, int] = {}

    rows: list[dict[str, Any]] = []
    log_dates_observed: list[str] = []
    if inputs["order_log"].exists():
        parsed_rows, parse_errors, line_count = _parse_jsonl(inputs["order_log"])
        line_counts["order_log_lines"] = line_count
        rows, log_dates_observed = _window_rows(parsed_rows, start_ts_ms, end_ts_ms)
        error_samples.extend(parse_errors[:10])

    recorder_dates_expected = _collect_dates_in_range(from_day, to_day)
    recorder_dates_available = [
        day for day in recorder_dates_expected if (inputs["recorder_root"] / day).exists()
    ] if inputs["recorder_root"].exists() else []
    recorder_dates_missing = [day for day in recorder_dates_expected if day not in recorder_dates_available]

    accepted_contracts: list[RawContract] = []
    rejected_contracts: list[RawContract] = []
    accepted_results = {
        "accepted_close_events_found": 0,
        "accepted_contracts_completed": 0,
        "incomplete_accepted_missing_realized_pnl_net": 0,
        "accepted_incomplete_buckets": {},
    }
    rejected_results = {
        "rejected_events_found": 0,
        "rejected_with_reference_price": 0,
        "rejected_missing_reference_price": 0,
        "rejected_missing_critical_fields": 0,
        "rejected_evaluated": 0,
        "rejected_reference_price_coverage": None,
        "rejected_incomplete_buckets": {},
    }
    replay_results = {
        "mfe_mae_computed_count": 0,
        "mfe_mae_missing_count": 0,
        "rejected_missing_market_coverage": 0,
    }
    atoms: list[SemaAtomV01] = []
    dedupe_summary = {
        "duplicates_detected": 0,
        "duplicates_skipped": 0,
    }

    baseline_atoms = _load_existing_atoms(inputs["baseline_saf"])
    baseline_dedupe_keys = {key for key in (_atom_dedupe_key_from_payload(atom) for atom in baseline_atoms) if key}

    if rows:
        accepted_contracts, accepted_results = AcceptedLifecycleReducer(rows).reduce()
        rejected_contracts, rejected_results = RejectedDecisionCollector(rows).collect()
        if inputs["recorder_root"].exists():
            replay = OfflineMarketReplayEvaluator(RecorderStore(inputs["recorder_root"], DEFAULT_TF_SEC))
            for contract in accepted_contracts:
                replay.evaluate_accepted(contract)
            for contract in rejected_contracts:
                replay.evaluate_rejected(contract)
            replay_results = {
                "mfe_mae_computed_count": replay.mfe_mae_computed_count,
                "mfe_mae_missing_count": replay.mfe_mae_missing_count,
                "rejected_missing_market_coverage": replay.rejected_missing_market_coverage,
            }

        encoder = SemaEncoder()
        seen_keys: set[str] = set(baseline_dedupe_keys)
        accepted_atoms_created = 0
        rejected_atoms_created = 0
        diagnostics_only_atoms_created = 0
        for contract in accepted_contracts:
            if not _accepted_contract_is_trainable(contract):
                continue
            dedupe_key = _accepted_dedupe_key(contract)
            if dedupe_key in seen_keys:
                dedupe_summary["duplicates_detected"] += 1
                dedupe_summary["duplicates_skipped"] += 1
                continue
            seen_keys.add(dedupe_key)
            atom = encoder.encode(contract)
            if atom is not None:
                atoms.append(atom)
                accepted_atoms_created += 1
        for contract in rejected_contracts:
            dedupe_key = _rejected_dedupe_key(contract)
            if dedupe_key in seen_keys:
                dedupe_summary["duplicates_detected"] += 1
                dedupe_summary["duplicates_skipped"] += 1
                continue
            seen_keys.add(dedupe_key)
            atom = encoder.encode(contract)
            if atom is not None:
                atoms.append(atom)
                rejected_atoms_created += 1
        error_samples.extend(encoder.encoding_errors[:10])
        encoding_errors_count = len(encoder.encoding_errors)
    else:
        encoding_errors_count = 0
        accepted_atoms_created = 0
        rejected_atoms_created = 0
        diagnostics_only_atoms_created = 0

    _write_jsonl(slice_path, atoms)

    baseline_context_counts = _count_contexts(baseline_atoms)
    new_context_counts = Counter()
    for atom in atoms:
        key = _context_key_from_atom(atom.to_dict())
        if key is not None:
            new_context_counts[key] += 1
    new_context_keys = sorted(key for key in new_context_counts if key not in baseline_context_counts)
    existing_context_keys = sorted(key for key in new_context_counts if key in baseline_context_counts)
    low_support_baseline = _load_low_support_baseline(inputs["poc03b_manifest"])
    contexts_promoted_from_low_support = 0
    contexts_still_low_support = 0
    for key, new_count in sorted(new_context_counts.items()):
        baseline_count = low_support_baseline.get(key)
        if baseline_count is None:
            continue
        total = baseline_count + new_count
        if total >= 5:
            contexts_promoted_from_low_support += 1
        else:
            contexts_still_low_support += 1
    context_migration = {
        "new_contexts": len(new_context_keys),
        "existing_contexts_updated": len(existing_context_keys),
        "contexts_promoted_from_low_support": contexts_promoted_from_low_support,
        "contexts_still_low_support": contexts_still_low_support,
        "new_context_keys": new_context_keys,
    }

    missing_histogram = _missing_field_histogram([*accepted_contracts, *rejected_contracts])
    atoms_created = accepted_atoms_created + rejected_atoms_created + diagnostics_only_atoms_created
    atoms_created_reconciliation_ok = atoms_created == len(atoms)
    if not atoms_created_reconciliation_ok:
        error_samples.append("atoms_created_source_reconciliation_failed")
    encoding_summary = {
        "atoms_created": atoms_created,
        "accepted_atoms_created": accepted_atoms_created,
        "rejected_atoms_created": rejected_atoms_created,
        "diagnostics_only_atoms_created": diagnostics_only_atoms_created,
        "atoms_created_reconciliation_ok": atoms_created_reconciliation_ok,
        "atoms_skipped": len(accepted_contracts) + len(rejected_contracts) - len(atoms) - dedupe_summary["duplicates_skipped"],
        "encoding_errors_count": encoding_errors_count,
    }
    status = _determine_status(
        missing_required_inputs=missing_required_inputs,
        atoms_created=atoms_created,
        atoms_created_reconciliation_ok=atoms_created_reconciliation_ok,
        encoding_errors_count=encoding_errors_count,
        recorder_dates_missing=recorder_dates_missing,
        rejected_missing_market_coverage=replay_results["rejected_missing_market_coverage"],
        mfe_mae_missing_count=replay_results["mfe_mae_missing_count"],
        dedupe_failed=False,
    )

    index_payload = ForwardCollectionIndexer(DEFAULT_INDEX_PATH).update(
        {
            "slice_id": slice_id,
            "from": from_day.isoformat(),
            "to": to_day.isoformat(),
            "artifact": slice_path.name,
            "report": report_path.name,
            "atoms_created": atoms_created,
            "accepted_contracts_completed": accepted_results.get("accepted_contracts_completed", 0),
            "accepted_atoms_created": accepted_atoms_created,
            "rejected_atoms_created": rejected_atoms_created,
            "diagnostics_only_atoms_created": diagnostics_only_atoms_created,
            "incomplete_accepted_missing_realized_pnl_net": accepted_results.get(
                "incomplete_accepted_missing_realized_pnl_net",
                0,
            ),
            "rejected_evaluated": rejected_results.get("rejected_evaluated", 0),
            "rejected_reference_price_coverage": rejected_results.get("rejected_reference_price_coverage"),
        }
    )
    if not isinstance(index_payload.get("slices"), list):
        error_samples.append("index_update_failed")

    report_text = ForwardCollectionReportGenerator().generate(
        status=status,
        scope_note="Offline forward collector from frozen Aurora log slice to new SAF slice and index.",
        inputs_read=inputs_read,
        missing_required_inputs=missing_required_inputs,
        missing_optional_inputs=missing_optional_inputs,
        time_window={
            "from": from_day.isoformat(),
            "to": to_day.isoformat(),
            "slice_id": slice_id,
            "start_ts_ms": start_ts_ms,
            "end_ts_ms": end_ts_ms,
            "log_dates_observed": log_dates_observed,
            "recorder_dates_available": recorder_dates_available,
            "recorder_dates_missing": recorder_dates_missing,
        },
        outputs=outputs,
        line_counts=line_counts,
        accepted_results=accepted_results,
        rejected_results=rejected_results,
        replay_results=replay_results,
        encoding_summary=encoding_summary,
        context_migration=context_migration,
        missing_field_histogram=missing_histogram,
        dedupe_summary=dedupe_summary,
        error_samples=error_samples[:10],
    )
    report_path.write_text(report_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
