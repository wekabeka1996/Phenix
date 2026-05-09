from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SAF_PATH = REPO_ROOT / "aurora_real_logs_v02.saf.jsonl"
DEFAULT_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
DEFAULT_TF_SEC = 300
FEE_FLOOR_BPS = 5.0
REJECT_HORIZONS = (
    ("T+15m", 15 * 60 * 1000),
    ("T+30m", 30 * 60 * 1000),
    ("T+60m", 60 * 60 * 1000),
)
CONFIDENCE_BUCKETS = (
    (0.00, 0.25, "0.00..0.25"),
    (0.25, 0.50, "0.25..0.50"),
    (0.50, 0.75, "0.50..0.75"),
    (0.75, 1.01, "0.75..1.00"),
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


def _walk_nested_values(root: Any) -> Iterable[Any]:
    if isinstance(root, dict):
        for value in root.values():
            yield value
            yield from _walk_nested_values(value)
    elif isinstance(root, list):
        for value in root:
            yield value
            yield from _walk_nested_values(value)


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


def _find_recorder_root(order_log_path: Path) -> Path | None:
    repo_candidate = REPO_ROOT / "data" / "recorder"
    capture_root = order_log_path.parent.parent
    capture_candidate = capture_root / "data" / "recorder"
    if capture_candidate.exists():
        return capture_candidate
    if repo_candidate.exists():
        return repo_candidate
    return None


def _candidate_order_logs() -> list[Path]:
    candidates: list[Path] = []
    current = REPO_ROOT / "logs" / "order_log_v1.jsonl"
    if current.exists():
        candidates.append(current)
    frozen_root = REPO_ROOT / "logs" / "frozen"
    if frozen_root.exists():
        candidates.extend(sorted(frozen_root.glob("*/logs/order_log_v1.jsonl")))
    return candidates


def _score_order_log(path: Path) -> tuple[int, int, int]:
    accepted = 0
    rejected = 0
    line_count = 0
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line_count += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = row.get("event_type")
            if event_type == "POSITION_CLOSED" and _safe_float(row.get("realized_pnl_net")) is not None:
                accepted += 1
            elif event_type == "DECISION_INTENT_REJECTED":
                rejected += 1
    return accepted, rejected, line_count


def discover_best_input_surface() -> tuple[Path | None, Path | None, dict[str, Any]]:
    best_path: Path | None = None
    best_score: tuple[int, int, int] = (-1, -1, -1)
    inventory: list[dict[str, Any]] = []
    for path in _candidate_order_logs():
        accepted, rejected, line_count = _score_order_log(path)
        recorder_root = _find_recorder_root(path)
        score = (accepted, rejected, 1 if recorder_root is not None else 0)
        inventory.append(
            {
                "order_log": str(path),
                "accepted_with_realized_pnl_net": accepted,
                "rejected_events": rejected,
                "has_recorder_root": recorder_root is not None,
                "line_count": line_count,
            }
        )
        if score > best_score:
            best_score = score
            best_path = path
    recorder_root = _find_recorder_root(best_path) if best_path else None
    return best_path, recorder_root, {"candidate_inventory": inventory, "selected_score": best_score}


@dataclass(slots=True)
class Bar:
    ts_ms: int
    close: float
    high: float
    low: float


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
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
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


@dataclass(slots=True)
class RawContract:
    contract_kind: str
    contract_id: str
    symbol: str | None
    side: str | None
    strategy_id: str | None
    regime: str | None
    regime_confidence: float | None
    direction_confidence: float | None
    confidence_bucket: str
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
            if symbol is None:
                missing_fields.append("symbol")
                self.incomplete_buckets["accepted_missing_symbol"] += 1
            if side is None:
                missing_fields.append("side")
                self.incomplete_buckets["accepted_missing_side"] += 1
            if regime is None:
                missing_fields.append("regime")
                self.incomplete_buckets["accepted_missing_regime"] += 1

            contract = RawContract(
                contract_kind="ACCEPTED",
                contract_id=rid,
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                regime=regime,
                regime_confidence=regime_confidence,
                direction_confidence=None,
                confidence_bucket=_bucketize_confidence(regime_confidence),
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
                pnl_status=_text(row.get("pnl_status")),
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
            if symbol and side and regime and realized_pnl_net is not None:
                accepted_contracts_completed += 1
            contracts.append(contract)

        return contracts, {
            "accepted_close_events_found": accepted_close_events_found,
            "accepted_contracts_completed": accepted_contracts_completed,
            "incomplete_accepted_buckets": dict(self.incomplete_buckets),
        }


class RejectedDecisionCollector:
    def __init__(self, rows: Sequence[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.incomplete_buckets: Counter[str] = Counter()

    def collect(self) -> tuple[list[RawContract], dict[str, Any]]:
        contracts: list[RawContract] = []
        rejected_events_found = 0
        rejected_contracts_evaluated = 0
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
            low_vol_cost_floor = (
                metadata.get("low_vol_cost_floor")
                if isinstance(metadata.get("low_vol_cost_floor"), dict)
                else {}
            )
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
            missing_fields: list[str] = []
            if regime_confidence is None:
                missing_fields.append("regime_confidence")
            if reference_price is None:
                self.incomplete_buckets["incomplete_rejected_missing_reference_price"] += 1
                continue
            ts_ms = _safe_int(row.get("timestamp"))
            if ts_ms is None:
                missing_fields.append("timestamp")
            contract = RawContract(
                contract_kind="REJECTED",
                contract_id=_text(row.get("rid")) or f"rejected_line_{row.get('_source_line')}",
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                regime=regime,
                regime_confidence=regime_confidence,
                direction_confidence=direction_confidence,
                confidence_bucket=_bucketize_confidence(regime_confidence),
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
            rejected_contracts_evaluated += 1
            contracts.append(contract)
        return contracts, {
            "rejected_events_found": rejected_events_found,
            "rejected_contracts_evaluated": rejected_contracts_evaluated,
            "incomplete_rejected_buckets": dict(self.incomplete_buckets),
        }


class OfflineMarketReplayEvaluator:
    def __init__(self, recorder_store: RecorderStore) -> None:
        self.recorder_store = recorder_store
        self.mfe_mae_computed_count = 0
        self.mfe_mae_missing_count = 0

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
            return
        bars = self.recorder_store.load_symbol(contract.symbol)
        horizons: dict[str, dict[str, Any]] = {}
        for label, delta_ms in REJECT_HORIZONS:
            target_ts = contract.event_ts_ms + delta_ms
            future_bar = next((bar for bar in bars if bar.ts_ms >= target_ts), None)
            if future_bar is None:
                horizons[label] = {"future_ts_ms": None, "future_price": None, "post_move_bps": None}
                continue
            if contract.side == "BUY":
                post_move_bps = (future_bar.close - contract.entry_price) / contract.entry_price * 10000.0
            else:
                post_move_bps = (contract.entry_price - future_bar.close) / contract.entry_price * 10000.0
            horizons[label] = {
                "future_ts_ms": future_bar.ts_ms,
                "future_price": future_bar.close,
                "post_move_bps": post_move_bps,
            }
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


class SemaMemory:
    def summarize(self, atoms: Sequence[SemaAtomV01]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str, str, str], list[SemaAtomV01]] = defaultdict(list)
        for atom in atoms:
            ctx = atom.context
            key = (
                str(ctx["symbol"]),
                str(ctx["side"]),
                str(ctx["strategy_id"]),
                str(ctx["regime"]),
                str(ctx["confidence_bucket"]),
            )
            grouped[key].append(atom)

        verdicts: list[dict[str, Any]] = []
        for key in sorted(grouped):
            group = grouped[key]
            atom_count = len(group)
            avg_reward = sum(atom.reward_bps for atom in group) / atom_count
            avg_threat = sum(atom.threat_bps for atom in group) / atom_count
            net_score = sum(atom.net_score for atom in group) / atom_count
            avg_surprise = sum(atom.surprise for atom in group) / atom_count
            avg_importance = sum(atom.importance for atom in group) / atom_count
            verdict, recommendation = self._verdict(atom_count, net_score)
            verdicts.append(
                {
                    "symbol": key[0],
                    "side": key[1],
                    "strategy_id": key[2],
                    "regime": key[3],
                    "confidence_bucket": key[4],
                    "atom_count": atom_count,
                    "verdict": verdict,
                    "recommendation": recommendation,
                    "outcome_stats": dict(sorted(Counter(atom.outcome_code for atom in group).items())),
                    "avg_reward": round(avg_reward, 6),
                    "avg_threat": round(avg_threat, 6),
                    "net_score": round(net_score, 6),
                    "avg_surprise": round(avg_surprise, 6),
                    "avg_importance": round(avg_importance, 6),
                }
            )
        return verdicts

    @staticmethod
    def _verdict(atom_count: int, net_score: float) -> tuple[str, str]:
        if atom_count < 2:
            return "LOW_SUPPORT", "collect_more_atoms"
        if net_score >= 20.0:
            return "FAVORABLE_CONTEXT", "retain_or_promote"
        if net_score <= -20.0:
            return "TOXIC_CONTEXT", "avoid_or_review"
        return "MIXED_CONTEXT", "monitor"


class RawContractExporter:
    @staticmethod
    def export(contracts: Sequence[RawContract]) -> list[dict[str, Any]]:
        return [contract.to_dict() for contract in contracts]


class ReportGenerator:
    def generate(
        self,
        *,
        status: str,
        files_created_or_changed: Sequence[Path],
        inputs_read: Sequence[Path],
        line_counts: dict[str, int],
        accepted_results: dict[str, Any],
        rejected_results: dict[str, Any],
        replay_results: dict[str, Any],
        encoding_summary: dict[str, Any],
        memory_verdicts: Sequence[dict[str, Any]],
        missing_field_histogram: dict[str, int],
        error_samples: Sequence[str],
    ) -> str:
        lines = [
            "# SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT",
            "",
            "## Verdict",
            f"SEMA_ATOM_POC_02_STATUS:",
            status,
            "",
            "## Scope",
            "- Read-only real-log adapter run from Aurora log surfaces to SemaAtom memory artifacts.",
            "- No live trading logic, gates, or runtime behavior modified.",
            "",
            "## Files Created/Changed",
        ]
        for path in files_created_or_changed:
            lines.append(f"- {path.name}")
        lines.extend(
            [
                "",
                "## Inputs Read",
            ]
        )
        for path in inputs_read:
            lines.append(f"- {path}")
        lines.extend(
            [
                "",
                f"- log lines read: {sum(line_counts.values())}",
            ]
        )
        for label, count in sorted(line_counts.items()):
            lines.append(f"- {label}: {count}")

        lines.extend(
            [
                "",
                "## Accepted Reducer Results",
                f"- accepted close events found: {accepted_results.get('accepted_close_events_found', 0)}",
                f"- accepted contracts completed: {accepted_results.get('accepted_contracts_completed', 0)}",
                "",
                "## Rejected Evaluator Results",
                f"- rejected events found: {rejected_results.get('rejected_events_found', 0)}",
                f"- rejected contracts evaluated: {rejected_results.get('rejected_contracts_evaluated', 0)}",
                "",
                "## MFE/MAE Reconstruction Results",
                f"- MFE/MAE computed count: {replay_results.get('mfe_mae_computed_count', 0)}",
                f"- MFE/MAE missing count: {replay_results.get('mfe_mae_missing_count', 0)}",
                "",
                "## SemaAtom Encoding Results",
                f"- atoms created: {encoding_summary.get('atoms_created', 0)}",
                f"- atoms discarded: {encoding_summary.get('atoms_discarded', 0)}",
                f"- encoding errors: {encoding_summary.get('encoding_errors_count', 0)}",
                "",
                "## Memory Verdicts by Context",
            ]
        )
        if memory_verdicts:
            for verdict in memory_verdicts:
                lines.extend(
                    [
                        f"- symbol: {verdict['symbol']}",
                        f"  side={verdict['side']} strategy_id={verdict['strategy_id']} regime={verdict['regime']} confidence_bucket={verdict['confidence_bucket']}",
                        f"  atom_count={verdict['atom_count']} verdict={verdict['verdict']} recommendation={verdict['recommendation']}",
                        f"  outcome_stats={_json_dumps(verdict['outcome_stats'])}",
                        f"  avg_reward={verdict['avg_reward']} avg_threat={verdict['avg_threat']} net_score={verdict['net_score']}",
                        f"  avg_surprise={verdict['avg_surprise']} avg_importance={verdict['avg_importance']}",
                    ]
                )
        else:
            lines.append("- none")

        lines.extend(
            [
                "",
                "## Incomplete Buckets",
                f"- incomplete accepted buckets: {_json_dumps(accepted_results.get('incomplete_accepted_buckets', {}))}",
                f"- incomplete rejected buckets: {_json_dumps(rejected_results.get('incomplete_rejected_buckets', {}))}",
                "",
                "## Missing Field Histogram",
                f"- {_json_dumps(missing_field_histogram)}",
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
                "- Accepted MFE/MAE is replayed from recorder bars and depends on recorder coverage for the chosen symbol/time window.",
                "- Rejected reference price extraction is strongest for low-vol rejects with nested economics metadata; other reject families can fall into incomplete buckets by design.",
                "- Memory verdicts are heuristic aggregations over encoded atoms and do not claim forward predictive validity.",
                "",
                "## Next Recommended Step",
                "- SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION",
                "",
            ]
        )
        return "\n".join(lines) + "\n"


@dataclass(slots=True)
class RunResult:
    status: str
    saf_path: Path
    report_path: Path
    atoms: list[SemaAtomV01]
    raw_contracts: list[RawContract]
    line_counts: dict[str, int]
    inputs_read: list[Path]
    summary: dict[str, Any]


def _missing_field_histogram(contracts: Sequence[RawContract], atoms: Sequence[SemaAtomV01]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for contract in contracts:
        counter.update(contract.missing_fields)
    for atom in atoms:
        counter.update(atom.missing_fields)
    return dict(sorted(counter.items()))


def _status_from_summary(
    *,
    order_log_path: Path | None,
    recorder_root: Path | None,
    atoms_created: int,
    raw_contract_count: int,
    mfe_mae_computed_count: int,
) -> str:
    if order_log_path is None or recorder_root is None:
        return "BLOCKED_BY_MISSING_LOG_INPUTS"
    if atoms_created <= 0 and raw_contract_count > 0:
        return "PARTIAL_EXTRACTION_ONLY"
    if raw_contract_count <= 0:
        return "BLOCKED_BY_MISSING_LOG_INPUTS"
    if mfe_mae_computed_count <= 0:
        return "FAILED_MFE_MAE_RECONSTRUCTION"
    return "READ_ONLY_REAL_LOG_RUN_COMPLETED"


def run_pipeline(
    *,
    order_log_path: Path | None = None,
    recorder_root: Path | None = None,
    output_saf_path: Path = DEFAULT_SAF_PATH,
    output_report_path: Path = DEFAULT_REPORT_PATH,
    tf_sec: int = DEFAULT_TF_SEC,
) -> RunResult:
    discovery_meta: dict[str, Any] = {}
    if order_log_path is None:
        order_log_path, discovered_recorder_root, discovery_meta = discover_best_input_surface()
        if recorder_root is None:
            recorder_root = discovered_recorder_root
    elif recorder_root is None:
        recorder_root = _find_recorder_root(order_log_path)

    if order_log_path is None or not order_log_path.exists():
        status = "BLOCKED_BY_MISSING_LOG_INPUTS"
        output_saf_path.write_text("", encoding="utf-8")
        report_text = ReportGenerator().generate(
            status=status,
            files_created_or_changed=[output_saf_path, output_report_path],
            inputs_read=[],
            line_counts={},
            accepted_results={},
            rejected_results={},
            replay_results={"mfe_mae_computed_count": 0, "mfe_mae_missing_count": 0},
            encoding_summary={"atoms_created": 0, "atoms_discarded": 0, "encoding_errors_count": 0},
            memory_verdicts=[],
            missing_field_histogram={},
            error_samples=["order_log_v1.jsonl not found"],
        )
        output_report_path.write_text(report_text, encoding="utf-8")
        return RunResult(status, output_saf_path, output_report_path, [], [], {}, [], {"discovery": discovery_meta})

    rows, parse_errors, line_count = _parse_jsonl(order_log_path)
    recorder_store = RecorderStore(recorder_root, tf_sec) if recorder_root is not None else None

    accepted_reducer = AcceptedLifecycleReducer(rows)
    accepted_contracts, accepted_results = accepted_reducer.reduce()

    rejected_collector = RejectedDecisionCollector(rows)
    rejected_contracts, rejected_results = rejected_collector.collect()

    all_contracts = accepted_contracts + rejected_contracts
    replay = OfflineMarketReplayEvaluator(recorder_store) if recorder_store is not None else None
    if replay is not None:
        for contract in accepted_contracts:
            replay.evaluate_accepted(contract)
        for contract in rejected_contracts:
            replay.evaluate_rejected(contract)

    encoder = SemaEncoder()
    atoms: list[SemaAtomV01] = []
    discarded = 0
    for contract in all_contracts:
        atom = encoder.encode(contract)
        if atom is None:
            discarded += 1
            continue
        atoms.append(atom)

    output_saf_path.parent.mkdir(parents=True, exist_ok=True)
    with output_saf_path.open("w", encoding="utf-8") as handle:
        for atom in atoms:
            handle.write(_json_dumps(atom.to_dict()) + "\n")

    memory_verdicts = SemaMemory().summarize(atoms)
    replay_results = {
        "mfe_mae_computed_count": replay.mfe_mae_computed_count if replay is not None else 0,
        "mfe_mae_missing_count": replay.mfe_mae_missing_count if replay is not None else 0,
    }
    status = _status_from_summary(
        order_log_path=order_log_path,
        recorder_root=recorder_root,
        atoms_created=len(atoms),
        raw_contract_count=len(all_contracts),
        mfe_mae_computed_count=replay_results["mfe_mae_computed_count"],
    )
    missing_field_histogram = _missing_field_histogram(all_contracts, atoms)
    error_samples = parse_errors[:3] + encoder.encoding_errors[:7]
    report_text = ReportGenerator().generate(
        status=status,
        files_created_or_changed=[output_saf_path, output_report_path],
        inputs_read=[path for path in [order_log_path, recorder_root] if path is not None],
        line_counts={"order_log": line_count},
        accepted_results=accepted_results,
        rejected_results=rejected_results,
        replay_results=replay_results,
        encoding_summary={
            "atoms_created": len(atoms),
            "atoms_discarded": discarded,
            "encoding_errors_count": len(encoder.encoding_errors),
        },
        memory_verdicts=memory_verdicts,
        missing_field_histogram=missing_field_histogram,
        error_samples=error_samples,
    )
    output_report_path.write_text(report_text, encoding="utf-8")
    return RunResult(
        status=status,
        saf_path=output_saf_path,
        report_path=output_report_path,
        atoms=atoms,
        raw_contracts=all_contracts,
        line_counts={"order_log": line_count},
        inputs_read=[path for path in [order_log_path, recorder_root] if path is not None],
        summary={
            "accepted_results": accepted_results,
            "rejected_results": rejected_results,
            "replay_results": replay_results,
            "memory_verdicts": memory_verdicts,
            "missing_field_histogram": missing_field_histogram,
            "encoding_errors": encoder.encoding_errors,
            "parse_errors": parse_errors,
            "discovery": discovery_meta,
            "raw_contracts": RawContractExporter.export(all_contracts),
        },
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Aurora real-log adapter for SemaAtom POC_02.",
    )
    parser.add_argument("--order-log", type=Path, default=None, help="Explicit order_log_v1.jsonl path")
    parser.add_argument("--recorder-root", type=Path, default=None, help="Explicit recorder root path")
    parser.add_argument("--output-saf", type=Path, default=DEFAULT_SAF_PATH, help="Output .saf.jsonl path")
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT_PATH, help="Output markdown report path")
    parser.add_argument("--tf-sec", type=int, default=DEFAULT_TF_SEC, help="Recorder timeframe to use for replay")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_pipeline(
        order_log_path=args.order_log,
        recorder_root=args.recorder_root,
        output_saf_path=args.output_saf,
        output_report_path=args.output_report,
        tf_sec=args.tf_sec,
    )
    print(f"status={result.status}")
    print(f"saf={result.saf_path}")
    print(f"report={result.report_path}")
    print(f"atoms_created={len(result.atoms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
