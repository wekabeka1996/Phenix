from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .contracts import (
    COMPACT_FEATURE_ALIASES,
    AdvisoryWarning,
    AgentFeedHealth,
    AgentFeedPacket,
    BusinessWarningsCard,
    CardMeta,
    ExecutionBodyCard,
    FeatureSignalCard,
    FreshnessSummary,
    GlobalMarketCard,
    MechanicalInvariant,
    PacketBudget,
    PositionLifeCard,
    PositionSummary,
    SourceInventoryItem,
    SymbolMarketCard,
)
from .execution_readiness import build_execution_readiness_snapshot
from .publication import RuntimePublicationReader
from .capabilities import project_execution_readiness_snapshot


DEFAULT_MAX_TOKENS = 4_400
MIN_MAX_TOKENS = 1_500
MAX_SYMBOLS = 12


@dataclass(frozen=True)
class FreshnessPolicy:
    market_ms: int = 15 * 60 * 1_000
    portfolio_ms: int = 2 * 60 * 1_000
    decision_ms: int = 60 * 60 * 1_000
    execution_ms: int = 2 * 60 * 1_000
    future_skew_ms: int = 5 * 60 * 1_000


@dataclass(frozen=True)
class TailPolicy:
    max_bytes: int = 512 * 1_024
    max_lines: int = 200


def bounded_tail_jsonl(
    path: Path,
    *,
    max_bytes: int,
    max_lines: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Read only the bounded end of a JSONL file, tolerating partial lines."""

    diagnostics = [f"bounded_tail:max_bytes={max_bytes}:max_lines={max_lines}"]
    if not path.exists() or not path.is_file():
        return [], diagnostics + ["source_missing"]
    try:
        size = path.stat().st_size
        start = max(0, size - max(1, int(max_bytes)))
        with path.open("rb") as handle:
            handle.seek(start)
            raw = handle.read(max(1, int(max_bytes)))
    except OSError as exc:
        return [], diagnostics + [f"source_read_error:{type(exc).__name__}"]

    if start > 0:
        newline = raw.find(b"\n")
        raw = raw[newline + 1 :] if newline >= 0 else b""
        diagnostics.append("leading_partial_line_discarded")
    rows: List[Dict[str, Any]] = []
    for raw_line in raw.splitlines()[-max(1, int(max_lines)) :]:
        try:
            value = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows, diagnostics


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None else None


def _first(mapping: Dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return None


def _timestamp(row: Optional[Dict[str, Any]]) -> Optional[int]:
    if not row:
        return None
    return _integer(
        _first(
            row,
            (
                "ts_ms",
                "timestamp",
                "event_ts_ms",
                "response_ts_ms",
                "bar_close_ts_ms",
                "bar_close_ts",
                "ts",
            ),
        )
    )


class AgentFeedReducer:
    """Produce compact cards from runtime state or bounded local read models."""

    def __init__(
        self,
        *,
        project_root: Path,
        snapshot_store: Any | None = None,
        execution_position: Any | None = None,
        freshness: FreshnessPolicy = FreshnessPolicy(),
        tail_policy: TailPolicy = TailPolicy(),
        now_ms: Optional[int] = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.snapshot_store = snapshot_store
        self.execution_position = execution_position
        self.freshness = freshness
        self.tail_policy = tail_policy
        self._fixed_now_ms = now_ms
        self.publication_reader = RuntimePublicationReader(
            self.project_root / "ops" / "agent_bridge" / "runtime"
        )
        self._publication_market_cache: Any = ...
        self._publication_market_diagnostics: List[str] = []

    @property
    def now_ms(self) -> int:
        return self._fixed_now_ms if self._fixed_now_ms is not None else int(time.time() * 1_000)

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    def _freshness(self, ts_ms: Optional[int], max_age_ms: int) -> str:
        if ts_ms is None:
            return "missing"
        age_ms = self.now_ms - ts_ms
        if age_ms < -self.freshness.future_skew_ms:
            return "unknown"
        return "fresh" if age_ms <= max_age_ms else "stale"

    def _meta(
        self,
        *,
        source_ts_ms: Optional[int],
        max_age_ms: int,
        source_refs: Sequence[str],
        missing_fields: Sequence[str] = (),
        diagnostics: Sequence[str] = (),
        source_ownership: str = "missing",
    ) -> CardMeta:
        freshness = self._freshness(source_ts_ms, max_age_ms)
        card_diagnostics = list(diagnostics)[:12]
        if source_ts_ms is not None and self.now_ms - source_ts_ms < -self.freshness.future_skew_ms:
            card_diagnostics.append("source_clock_ahead")
        return CardMeta(
            source_ts_ms=source_ts_ms,
            produced_ts_ms=self.now_ms,
            freshness=freshness,
            source_refs=list(source_refs)[:8],
            missing_fields=list(dict.fromkeys(missing_fields))[:24],
            diagnostics=card_diagnostics[:12],
            source_ownership=source_ownership,
        )

    @staticmethod
    def _ownership(diagnostics: Sequence[str]) -> str:
        joined = " ".join(diagnostics)
        if "publication_owner:aurora_main_event_bus" in joined:
            return "direct_main_publication"
        if "publication_owner:aurora_main_feature_mirror_relay" in joined:
            return "publication_relay"
        if "runtime_publication" in joined:
            return "runtime_publication"
        if "runtime_owned" in joined:
            return "runtime_object"
        if "fallback" in joined or "bounded_tail" in joined:
            return "bounded_disk_fallback"
        return "missing"

    def _publication_market(self):
        if self._publication_market_cache is ...:
            value, diagnostics = self.publication_reader.market()
            self._publication_market_cache = value
            self._publication_market_diagnostics = diagnostics
        return self._publication_market_cache, list(self._publication_market_diagnostics)

    def _tail(self, relative_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        return bounded_tail_jsonl(
            self.project_root / relative_path,
            max_bytes=self.tail_policy.max_bytes,
            max_lines=self.tail_policy.max_lines,
        )

    def _latest_snapshot(self, symbol: str, tf_sec: int) -> Tuple[Optional[Dict[str, Any]], str, List[str]]:
        publication, publication_diagnostics = self._publication_market()
        if publication is not None:
            for item in publication.symbols:
                if item.symbol == symbol and int(item.tf_sec) == int(tf_sec):
                    flattened: Dict[str, Any] = {}
                    for group in item.features.model_dump(exclude_none=True).values():
                        flattened.update(group)
                    return {
                        "ts_ms": item.source_ts_ms,
                        "symbol": item.symbol,
                        "tf_sec": item.tf_sec,
                        "bar": {"close": item.last_price, "close_ts": item.bar_close_ts_ms},
                        "features": flattened,
                        "regime": {"name": item.regime_label, "confidence": item.regime_confidence},
                        "publication_missing_fields": item.missing_fields,
                    }, f"aurora-publication://market/{symbol}/{tf_sec}", publication_diagnostics + [
                        f"publication_owner:{item.source_owner}"
                    ]
        ref = f"aurora://shadow-snapshot/{symbol}/{tf_sec}/latest"
        if self.snapshot_store is not None and hasattr(self.snapshot_store, "latest"):
            try:
                row = self.snapshot_store.latest(symbol=symbol, tf_sec=tf_sec)
            except Exception as exc:
                return None, ref, [f"runtime_snapshot_error:{type(exc).__name__}"]
            if isinstance(row, dict):
                return dict(row), ref, ["runtime_owned_snapshot"]

        symbol_dir = self.data_dir / "shadow_telemetry" / "snapshots" / symbol
        try:
            candidates = sorted(
                symbol_dir.glob("*/*.jsonl"),
                key=lambda item: item.stat().st_mtime_ns,
                reverse=True,
            )
        except OSError:
            candidates = []
        for candidate in candidates[:3]:
            rows, diagnostics = bounded_tail_jsonl(
                candidate,
                max_bytes=self.tail_policy.max_bytes,
                max_lines=self.tail_policy.max_lines,
            )
            for row in reversed(rows):
                if int(_integer(row.get("tf_sec")) or -1) == int(tf_sec):
                    return row, ref, diagnostics + ["disk_snapshot_fallback"]
        return None, ref, ["snapshot_missing"]

    def _decision_rows(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        preferred = "logs/shadow_telemetry/trading_decisions_v1.jsonl"
        fallback = "logs/shadow_telemetry/decision_ledger_v1.jsonl"
        path = preferred if (self.project_root / preferred).exists() else fallback
        rows, diagnostics = self._tail(path)
        return rows, diagnostics + [f"source:{Path(path).name}"]

    def _latest_decision(self, rows: Sequence[Dict[str, Any]], symbol: str) -> Optional[Dict[str, Any]]:
        for row in reversed(rows):
            if str(row.get("symbol") or "").upper() == symbol:
                return row
        return None

    def _portfolio_state(self) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        rows, diagnostics = self._tail("logs/shadow_critical_event_journal_v1.jsonl")
        for row in reversed(rows):
            fragment = row.get("payload_fragment")
            state = fragment.get("portfolio_state") if isinstance(fragment, dict) else None
            if isinstance(state, dict):
                result = dict(state)
                result.setdefault("ts_ms", row.get("ts_ms"))
                return result, diagnostics
        return None, diagnostics + ["portfolio_state_not_in_bounded_tail"]

    def _active_positions(self, portfolio: Optional[Dict[str, Any]]) -> Tuple[List[PositionSummary], bool, List[str]]:
        runtime = self.execution_position
        if runtime is not None and hasattr(runtime, "manage_flows"):
            positions: List[PositionSummary] = []
            manage_flows = getattr(runtime, "manage_flows", {}) or {}
            lifecycle_ids = getattr(runtime, "_last_lifecycle_ikey_by_symbol", {}) or {}
            brackets = getattr(runtime, "_symbol_brackets", {}) or {}
            for raw_symbol, flow in list(manage_flows.items())[:20]:
                try:
                    if not bool(flow.has_active_lifecycle()):
                        continue
                except Exception:
                    continue
                symbol = str(raw_symbol).upper()
                bracket = dict(brackets.get(raw_symbol) or {})
                positions.append(
                    PositionSummary(
                        symbol=symbol,
                        lifecycle_id=str(lifecycle_ids.get(raw_symbol) or "") or None,
                        side=str(getattr(flow, "position_side", "") or "") or None,
                        state=str(getattr(getattr(flow, "state", None), "value", getattr(flow, "state", "")) or "") or None,
                        qty=str(getattr(flow, "position_qty", "") or "") or None,
                        entry_price=str(getattr(flow, "position_entry_price", "") or "") or None,
                        sl_price=str(getattr(flow, "sl_price", "") or "") or None,
                        tp_price=str(getattr(flow, "tp_price", "") or "") or None,
                        bracket_status="owned" if bracket else "missing",
                    )
                )
            return positions, True, ["runtime_owned_execution_position"]

        raw_positions = portfolio.get("positions") if isinstance(portfolio, dict) else None
        if not isinstance(raw_positions, list):
            return [], False, ["execution_runtime_and_portfolio_positions_missing"]
        positions = []
        for item in raw_positions[:20]:
            if not isinstance(item, dict):
                continue
            net = _number(item.get("net_position"))
            positions.append(
                PositionSummary(
                    symbol=str(item.get("symbol") or "UNKNOWN").upper(),
                    side="LONG" if net is not None and net > 0 else "SHORT" if net is not None and net < 0 else None,
                    state="portfolio_truth",
                    qty=str(item.get("net_position")) if item.get("net_position") is not None else None,
                    entry_price=str(item.get("avg_entry_price")) if item.get("avg_entry_price") is not None else None,
                    mark_price=str(item.get("markPrice")) if item.get("markPrice") is not None else None,
                    unrealized_pnl=str(item.get("unrealizedPnl")) if item.get("unrealizedPnl") is not None else None,
                    bracket_status="unknown",
                )
            )
        return positions, False, ["bounded_portfolio_fallback"]

    def _snapshot_values(
        self,
        snapshot: Optional[Dict[str, Any]],
        decision: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        snapshot = snapshot or {}
        bar = snapshot.get("bar") if isinstance(snapshot.get("bar"), dict) else {}
        features = snapshot.get("features") if isinstance(snapshot.get("features"), dict) else {}
        regime_raw = snapshot.get("regime")
        regime = regime_raw if isinstance(regime_raw, dict) else {}
        market = {
            "close_price": _number(_first(bar, ("close", "c", "close_price"))) or _number(_first(snapshot, ("close", "price"))),
            "volume": _number(_first(bar, ("volume", "v"))) or _number(snapshot.get("volume")),
            "regime": _first(regime, ("name", "regime", "label")) or (regime_raw if isinstance(regime_raw, str) else None),
            "regime_confidence": _number(_first(regime, ("confidence", "probability"))),
            "decision_score": _number(_first(snapshot, ("decision_score", "raw_score", "score"))),
        }
        if decision:
            market["close_price"] = market["close_price"] or _number(
                ((decision.get("causal_state_snapshot") or {}).get("candidate_intent_summary") or {}).get("limit_price")
            )
            market["regime"] = market["regime"] or decision.get("regime")
            market["regime_confidence"] = market["regime_confidence"] or _number(decision.get("regime_confidence"))
            market["decision_score"] = market["decision_score"] or _number(decision.get("decision_score") or decision.get("raw_score"))

        compact_features: Dict[str, Any] = {}
        for output_name, aliases in COMPACT_FEATURE_ALIASES.items():
            compact_features[output_name] = _number(_first(features, aliases))
        compact_features["signal_side"] = snapshot.get("side") or (decision or {}).get("side")
        compact_features["signal_confidence"] = _number(snapshot.get("confidence") or (decision or {}).get("confidence"))
        return market, compact_features

    def _warning_rows(
        self,
        order_rows: Sequence[Dict[str, Any]],
        missing_symbols: Sequence[str],
    ) -> List[AdvisoryWarning]:
        warnings: List[AdvisoryWarning] = []
        seen = set()
        for row in reversed(order_rows):
            event_type = str(row.get("event_type") or row.get("status") or "").upper()
            reason_code = str(row.get("reason_code") or row.get("reject_reason_code") or "UNKNOWN")
            if "BLOCK" not in event_type and "REJECT" not in event_type and "WARN" not in event_type:
                continue
            symbol = str(row.get("symbol") or "").upper() or None
            key = (reason_code, symbol)
            if key in seen:
                continue
            seen.add(key)
            warnings.append(
                AdvisoryWarning(
                    code=reason_code,
                    disposition="would_block" if "BLOCK" in event_type or "REJECT" in event_type else "warning",
                    symbol=symbol,
                    message=str(row.get("reason") or event_type or reason_code)[:240],
                    source_ref="aurora://order-log/recent#bounded-tail",
                    source_ts_ms=_timestamp(row),
                )
            )
            if len(warnings) >= 12:
                break
        for symbol in missing_symbols:
            warnings.append(
                AdvisoryWarning(
                    code="READINESS_DATA_MISSING",
                    disposition="warning",
                    symbol=symbol,
                    message="No safe current market snapshot was available in the bounded source window.",
                    source_ref=f"aurora://shadow-snapshot/{symbol}/latest",
                )
            )
        return warnings[:24]

    def _execution_card(
        self,
        positions_runtime_owned: bool,
        decision_rows: Sequence[Dict[str, Any]],
        symbols: Sequence[str],
    ) -> ExecutionBodyCard:
        runtime = self.execution_position
        published_readiness, published_diagnostics = self.publication_reader.readiness()
        runtime_available = runtime is not None
        mode = None
        for owner in (runtime, getattr(runtime, "adapter", None) if runtime is not None else None):
            value = getattr(owner, "mode", None) if owner is not None else None
            if value is not None:
                mode = str(getattr(value, "value", value))
                break
        trace_available = any(bool(row.get("rid") or row.get("decision_id")) for row in decision_rows[-20:])
        if published_readiness is not None:
            readiness = project_execution_readiness_snapshot(
                published_readiness.snapshot, symbols
            )
            runtime_available = readiness.runtime_available
            source_ts = published_readiness.produced_ts_ms
            source_refs = ["aurora-publication://execution-readiness/v0"]
            execution_diagnostics = published_diagnostics + ["mechanical_invariants_are_not_business_gates"]
            source_ownership = (
                "direct_main_publication"
                if published_readiness.source_owner == "aurora_main_execution_position"
                else "publication_relay"
            )
        else:
            readiness = build_execution_readiness_snapshot(
                runtime=runtime,
                symbols=symbols,
                produced_ts_ms=self.now_ms,
                trace_available=trace_available,
            )
            source_ts = max((_timestamp(row) or 0 for row in decision_rows[-20:]), default=0) or None
            if runtime_available:
                source_ts = self.now_ms
            source_refs = ["aurora://execution-position/runtime", "aurora://decision-ledger/recent#bounded-tail"]
            execution_diagnostics = ["mechanical_invariants_are_not_business_gates"]
            source_ownership = "runtime_object" if runtime_available else "bounded_disk_fallback"
        return ExecutionBodyCard(
            meta=self._meta(
                source_ts_ms=source_ts,
                max_age_ms=self.freshness.execution_ms,
                source_refs=source_refs,
                missing_fields=[] if runtime_available else ["runtime_execution_position"],
                diagnostics=execution_diagnostics,
                source_ownership=source_ownership,
            ),
            mode=mode,
            execution_available=runtime_available,
            invariants=readiness.invariants,
            capability_descriptors=readiness.capability_descriptors,
            constraint_summary=readiness.constraint_summary,
            readiness_summary=readiness.readiness_summary,
            readiness_reasons=readiness.readiness_summary.reasons,
            trace_ref="aurora://decision-ledger/recent#trace" if trace_available else None,
            # Avoid duplicating invariants/descriptors inside the bounded packet.
            # The full snapshot remains available on the GET-only readiness route.
            readiness_snapshot=None,
        )

    def execution_readiness(self, *, symbols: Sequence[str]):
        normalized = list(dict.fromkeys(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()))[:MAX_SYMBOLS]
        published, _ = self.publication_reader.readiness()
        if published is not None:
            return project_execution_readiness_snapshot(published.snapshot, normalized)
        decision_rows, _ = self._decision_rows()
        trace_available = any(bool(row.get("rid") or row.get("decision_id")) for row in decision_rows[-20:])
        return build_execution_readiness_snapshot(
            runtime=self.execution_position,
            symbols=normalized,
            produced_ts_ms=self.now_ms,
            trace_available=trace_available,
        )

    def build_packet(
        self,
        *,
        symbols: Sequence[str],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tf_sec: int = 300,
    ) -> AgentFeedPacket:
        build_started = time.perf_counter()
        timings: Dict[str, float] = {}
        normalized = list(dict.fromkeys(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()))[:MAX_SYMBOLS]
        if not normalized:
            raise ValueError("at least one explicit symbol is required")
        requested_budget = max(MIN_MAX_TOKENS, min(int(max_tokens), DEFAULT_MAX_TOKENS))
        phase_started = time.perf_counter()
        publication, _ = self._publication_market()
        direct_current = {
            (item.symbol, int(item.tf_sec))
            for item in (publication.symbols if publication is not None else [])
            if item.source_owner == "aurora_main_event_bus"
            and self._freshness(item.source_ts_ms, self.freshness.market_ms) == "fresh"
        }
        if all((symbol, int(tf_sec)) in direct_current for symbol in normalized):
            decision_rows = []
            decision_diagnostics = [
                "decision_tail_skipped:direct_main_publication_current",
                "advisory_warning_visibility_preserved:order_log_tail",
            ]
        else:
            decision_rows, decision_diagnostics = self._decision_rows()
        timings["decision_tail"] = round((time.perf_counter() - phase_started) * 1000, 3)
        phase_started = time.perf_counter()
        order_rows, order_diagnostics = self._tail("logs/order_log_v1.jsonl")
        timings["order_tail"] = round((time.perf_counter() - phase_started) * 1000, 3)
        phase_started = time.perf_counter()
        portfolio, portfolio_diagnostics = self._portfolio_state()
        timings["portfolio_tail"] = round((time.perf_counter() - phase_started) * 1000, 3)
        phase_started = time.perf_counter()
        positions, runtime_positions, position_diagnostics = self._active_positions(portfolio)
        timings["positions"] = round((time.perf_counter() - phase_started) * 1000, 3)

        symbol_cards: List[SymbolMarketCard] = []
        feature_cards: List[FeatureSignalCard] = []
        missing_symbols: List[str] = []
        source_timestamps: List[int] = []
        raw_refs: List[str] = []
        phase_started = time.perf_counter()
        market_ownerships: List[str] = []
        for symbol in normalized:
            snapshot, snapshot_ref, snapshot_diagnostics = self._latest_snapshot(symbol, tf_sec)
            decision = self._latest_decision(decision_rows, symbol)
            source_ts = _timestamp(snapshot) or _timestamp(decision)
            if source_ts is not None:
                source_timestamps.append(source_ts)
            if snapshot is None:
                missing_symbols.append(symbol)
            market, features = self._snapshot_values(snapshot, decision)
            source_refs = [snapshot_ref]
            if decision is not None:
                source_refs.append("aurora://decision-ledger/recent#bounded-tail")
            raw_refs.extend(source_refs)
            market_missing = [name for name in ("close_price", "regime") if market.get(name) is None]
            snapshot_ownership = self._ownership(snapshot_diagnostics)
            market_ownerships.append(snapshot_ownership)
            symbol_cards.append(
                SymbolMarketCard(
                    meta=self._meta(
                        source_ts_ms=source_ts,
                        max_age_ms=self.freshness.market_ms,
                        source_refs=source_refs,
                        missing_fields=market_missing,
                        diagnostics=snapshot_diagnostics,
                        source_ownership=snapshot_ownership,
                    ),
                    symbol=symbol,
                    tf_sec=tf_sec,
                    **market,
                )
            )
            feature_missing = [name for name in COMPACT_FEATURE_ALIASES if features.get(name) is None]
            feature_cards.append(
                FeatureSignalCard(
                    meta=self._meta(
                        source_ts_ms=_timestamp(snapshot),
                        max_age_ms=self.freshness.market_ms,
                        source_refs=source_refs,
                        missing_fields=feature_missing,
                        diagnostics=snapshot_diagnostics,
                        source_ownership=snapshot_ownership if snapshot is not None else "missing",
                    ),
                    symbol=symbol,
                    **features,
                )
            )
        timings["market_sources"] = round((time.perf_counter() - phase_started) * 1000, 3)

        portfolio_ts = _timestamp(portfolio)
        if portfolio_ts is not None:
            source_timestamps.append(portfolio_ts)
        global_missing = [] if portfolio else ["portfolio_state"]
        global_card = GlobalMarketCard(
            meta=self._meta(
                source_ts_ms=max(source_timestamps, default=0) or None,
                max_age_ms=self.freshness.market_ms,
                source_refs=["aurora://portfolio/latest#bounded-tail"] + [item.meta.source_refs[0] for item in symbol_cards],
                missing_fields=global_missing + (["market_snapshots"] if len(missing_symbols) == len(normalized) else []),
                diagnostics=portfolio_diagnostics,
                source_ownership=(
                    "mixed" if any(item in market_ownerships for item in ("direct_main_publication", "publication_relay", "runtime_publication")) and portfolio is not None
                    else "direct_main_publication" if "direct_main_publication" in market_ownerships
                    else "publication_relay" if "publication_relay" in market_ownerships
                    else "runtime_publication" if "runtime_publication" in market_ownerships
                    else "bounded_disk_fallback" if portfolio is not None
                    else "missing"
                ),
            ),
            symbols_requested=normalized,
            symbols_available=[card.symbol for card in symbol_cards if card.symbol not in missing_symbols],
            equity_usd=_number((portfolio or {}).get("equity")),
            available_balance_usd=_number((portfolio or {}).get("available_balance")),
            open_positions_usd=_number((portfolio or {}).get("open_positions_usd")),
            unrealized_pnl_usd=_number((portfolio or {}).get("unrealized_pnl")),
            realized_pnl_usd=_number((portfolio or {}).get("realized_pnl")),
            active_position_count=len(positions) if portfolio is not None or runtime_positions else None,
        )

        position_card = PositionLifeCard(
            meta=self._meta(
                source_ts_ms=portfolio_ts if not runtime_positions else self.now_ms,
                max_age_ms=self.freshness.portfolio_ms,
                source_refs=["aurora://execution-position/runtime" if runtime_positions else "aurora://portfolio/latest#bounded-tail"],
                missing_fields=[] if positions or portfolio is not None else ["active_positions"],
                diagnostics=position_diagnostics,
                source_ownership="runtime_object" if runtime_positions else "bounded_disk_fallback" if portfolio is not None else "missing",
            ),
            positions=positions,
            lifecycle_reconciliation_available=runtime_positions,
        )
        warning_items = self._warning_rows(order_rows, missing_symbols)
        warning_ts = max((_timestamp(row) or 0 for row in order_rows), default=0) or None
        warning_card = BusinessWarningsCard(
            meta=self._meta(
                source_ts_ms=warning_ts,
                max_age_ms=self.freshness.decision_ms,
                source_refs=["aurora://order-log/recent#bounded-tail"],
                missing_fields=[] if order_rows else ["recent_decisions_rejections"],
                diagnostics=order_diagnostics + ["advisory_only:not_enforced"],
                source_ownership="bounded_disk_fallback" if order_rows else "missing",
            ),
            warnings=warning_items,
        )
        execution_card = self._execution_card(runtime_positions, decision_rows, normalized)
        timings["cards_total"] = round((time.perf_counter() - build_started) * 1000, 3)
        metas = [global_card.meta, *[card.meta for card in symbol_cards], *[card.meta for card in feature_cards], position_card.meta, warning_card.meta, execution_card.meta]
        freshness_summary = FreshnessSummary()
        for meta in metas:
            setattr(freshness_summary, meta.freshness, getattr(freshness_summary, meta.freshness) + 1)
        valid_timestamps = [meta.source_ts_ms for meta in metas if meta.source_ts_ms is not None]
        oldest_age = max((max(0, self.now_ms - ts) for ts in valid_timestamps), default=None)
        packet = AgentFeedPacket(
            packet_id=f"afp_{uuid.uuid4().hex}",
            produced_ts_ms=self.now_ms,
            symbols=normalized,
            global_market=global_card,
            symbol_markets=symbol_cards,
            feature_signals=feature_cards,
            position_life=position_card,
            business_warnings=warning_card,
            execution_body=execution_card,
            budget=PacketBudget(max_tokens_requested=requested_budget),
            oldest_source_age_ms=oldest_age,
            freshness_summary=freshness_summary,
            raw_refs=list(dict.fromkeys(raw_refs + ["aurora://portfolio/latest#bounded-tail", "aurora://order-log/recent#bounded-tail"]))[:32],
            diagnostics=list(dict.fromkeys(decision_diagnostics + order_diagnostics + portfolio_diagnostics))[:24],
            reducer_timings_ms=timings,
        )
        return self._enforce_budget(packet)

    def _measure(self, packet: AgentFeedPacket) -> Tuple[int, int]:
        raw = packet.model_dump_json(exclude_none=True).encode("utf-8")
        return len(raw), math.ceil(len(raw) / 4)

    def _stabilize_budget_metadata(self, packet: AgentFeedPacket) -> Tuple[int, int]:
        for _ in range(4):
            payload_bytes, tokens = self._measure(packet)
            packet.budget.payload_bytes = payload_bytes
            packet.budget.estimated_tokens = tokens
        return self._measure(packet)

    def _enforce_budget(self, packet: AgentFeedPacket) -> AgentFeedPacket:
        max_tokens = packet.budget.max_tokens_requested
        payload_bytes, tokens = self._stabilize_budget_metadata(packet)
        if tokens <= max_tokens:
            packet.budget.payload_bytes, packet.budget.estimated_tokens = payload_bytes, tokens
            return packet

        packet.budget.truncated = True
        reductions = [
            ("business_warnings_tail", lambda: setattr(packet.business_warnings, "warnings", packet.business_warnings.warnings[:4])),
            ("position_tail", lambda: setattr(packet.position_life, "positions", packet.position_life.positions[:4])),
            ("additional_feature_cards", lambda: setattr(packet, "feature_signals", packet.feature_signals[:1])),
            ("additional_symbol_cards", lambda: setattr(packet, "symbol_markets", packet.symbol_markets[:1])),
            ("packet_diagnostics", lambda: setattr(packet, "diagnostics", [])),
            ("raw_refs_tail", lambda: setattr(packet, "raw_refs", packet.raw_refs[:4])),
        ]
        for label, reduction in reductions:
            reduction()
            packet.budget.omitted_sections.append(label)
            payload_bytes, tokens = self._stabilize_budget_metadata(packet)
            if tokens <= max_tokens:
                break
        packet.budget.payload_bytes, packet.budget.estimated_tokens = self._stabilize_budget_metadata(packet)
        return packet

    def source_inventory(self) -> List[SourceInventoryItem]:
        sources = [
            ("runtime_market_publication", self.project_root / "ops" / "agent_bridge" / "runtime" / "market_snapshot_v0.json", "aurora-publication://market/v0", "atomic compact publication"),
            ("runtime_execution_readiness_publication", self.project_root / "ops" / "agent_bridge" / "runtime" / "execution_readiness_v0.json", "aurora-publication://execution-readiness/v0", "atomic compact publication"),
            ("public_exchange_info_cache", self.project_root / "ops" / "agent_bridge" / "exchange_info" / "public_exchange_info_cache_v0.json", "aurora-publication://exchange-info/public-exchange-info-cache/v0", "atomic bounded public metadata"),
            ("market_features_regime", self.data_dir / "shadow_telemetry" / "snapshots", "aurora://shadow-snapshot/*/latest", "runtime latest or bounded newest-file tail"),
            ("positions_portfolio", self.logs_dir / "shadow_critical_event_journal_v1.jsonl", "aurora://portfolio/latest#bounded-tail", "bounded tail"),
            ("decisions", self.logs_dir / "shadow_telemetry" / "decision_ledger_v1.jsonl", "aurora://decision-ledger/recent#bounded-tail", "bounded tail"),
            ("rejections_warnings", self.logs_dir / "order_log_v1.jsonl", "aurora://order-log/recent#bounded-tail", "bounded tail"),
            ("execution_body", self.project_root / "apps" / "reference" / "main.py", "aurora://execution-position/runtime", "runtime introspection only"),
        ]
        items = []
        for family, path, ref, policy in sources:
            try:
                stat = path.stat()
                size = stat.st_size if path.is_file() else None
                modified = int(stat.st_mtime * 1_000)
                available = True
            except OSError:
                size, modified, available = None, None, False
            if family == "execution_body":
                available = self.execution_position is not None
                size = None
            items.append(SourceInventoryItem(family=family, available=available, source_ref=ref, size_bytes=size, modified_ts_ms=modified, read_policy=policy))
        return items

    def health(self) -> AgentFeedHealth:
        inventory = self.source_inventory()
        available = sum(1 for item in inventory if item.available)
        return AgentFeedHealth(
            status="ready" if available == len(inventory) else "degraded",
            produced_ts_ms=self.now_ms,
            source_families_available=available,
            source_families_total=len(inventory),
            diagnostics=[] if available == len(inventory) else ["one_or_more_source_families_unavailable"],
        )
