from __future__ import annotations

import json
import logging
import os
from collections import deque
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from apps.reference.domains.shadow_telemetry.contracts import (
    ActivePositionView,
    BracketStateView,
    DecisionHistoryView,
    RecentRejectionView,
)


LOG = logging.getLogger(
    "apps.reference.domains.shadow_telemetry.trading_read_models")


class TradingReadModelUnavailableError(RuntimeError):
    """Raised when canonical trading truth cannot be reconstructed safely."""


def _safe_json_loads(line: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(line)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _tail_jsonl(path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    rows: deque[Dict[str, Any]] = deque(maxlen=max(1, int(limit)))
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                obj = _safe_json_loads(line)
                if obj is not None:
                    rows.append(obj)
    except Exception as exc:
        LOG.debug("Failed to read JSONL tail from %s: %s", path, exc)
        return []
    return list(rows)


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    try:
        dec = Decimal(str(value))
    except Exception:
        return None
    return dec if dec.is_finite() else None


def _decimal_to_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _decimal_to_number(value: Any) -> Optional[float]:
    dec = _decimal_or_none(value)
    if dec is None:
        return None
    return float(dec)


class TradingReadModelService:
    """Normalized read-model service for trading/operator surfaces."""

    def __init__(
        self,
        *,
        project_root: Path,
        snapshot_store: Any | None = None,
        execution_position: Any | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.snapshot_store = snapshot_store
        self.execution_position = execution_position

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "shadow_telemetry" / "snapshots"

    def _snapshot_source_name(self) -> str:
        if self.snapshot_store is None:
            return "disk"
        return str(getattr(self.snapshot_store, "source_name", "memory"))

    def get_context_latest(self, *, symbol: str, tf_sec: int = 300) -> Dict[str, Any]:
        snapshot = self._latest_snapshot(symbol=symbol, tf_sec=tf_sec)
        if snapshot is None:
            raise TradingReadModelUnavailableError(
                f"missing snapshot truth for symbol={str(symbol).upper()} tf_sec={int(tf_sec)}"
            )
        execution_position_available = self.execution_position is not None and hasattr(
            self.execution_position, "manage_flows"
        )
        active_positions = self.get_active_positions(allow_degraded=True)
        degraded_reasons: List[str] = []
        if not execution_position_available:
            degraded_reasons.append("execution_position_unavailable")
        active_positions_source = "execution_position"
        if any(bool(item.get("portfolio_truth")) for item in active_positions) or not execution_position_available:
            active_positions_source = "portfolio_state"
        return {
            "symbol": str(symbol).upper(),
            "tf_sec": int(tf_sec),
            "snapshot": snapshot,
            "risk_gate": self._read_risk_gate_state(),
            "active_positions": active_positions,
            "recent_rejections": self.get_recent_rejections(limit=10),
            "recent_decisions": self.get_recent_decisions(limit=10),
            "runtime_health": {
                "execution_position_available": execution_position_available,
                "active_positions_source": active_positions_source,
                "degraded": bool(degraded_reasons),
                "degraded_reasons": degraded_reasons,
            },
            "provenance": {
                "snapshot_source": self._snapshot_source_name(),
                "risk_gate_path": str(self.data_dir / "risk_gate_state.json"),
                "order_log_path": str(self.logs_dir / "order_log_v1.jsonl"),
                "decision_ledger_path": str(self.logs_dir / "shadow_telemetry" / "decision_ledger_v1.jsonl"),
            },
        }

    def get_context_history(
        self,
        *,
        symbol: str,
        tf_sec: int = 300,
        limit: int = 50,
    ) -> Dict[str, Any]:
        items = self._snapshot_tail(symbol=symbol, tf_sec=tf_sec, limit=limit)
        return {
            "symbol": str(symbol).upper(),
            "tf_sec": int(tf_sec),
            "items": items,
            "count": len(items),
        }

    def get_active_positions(self, *, allow_degraded: bool = False) -> List[Dict[str, Any]]:
        runtime = self.execution_position
        if runtime is None:
            if allow_degraded:
                degraded_positions = self._active_positions_from_portfolio_truth()
                if degraded_positions is not None:
                    return degraded_positions
            raise TradingReadModelUnavailableError(
                "execution_position runtime is unavailable for active position truth"
            )

        if not hasattr(runtime, "manage_flows"):
            if allow_degraded:
                degraded_positions = self._active_positions_from_portfolio_truth()
                if degraded_positions is not None:
                    return degraded_positions
            raise TradingReadModelUnavailableError(
                "execution_position runtime does not expose manage_flows"
            )

        positions: List[Dict[str, Any]] = []
        manage_flows = getattr(runtime, "manage_flows", {}) or {}
        lifecycle_ids = getattr(
            runtime, "_last_lifecycle_ikey_by_symbol", {}) or {}
        brackets_by_symbol = getattr(runtime, "_symbol_brackets", {}) or {}
        close_reasons = getattr(
            runtime, "_last_close_reason_by_symbol", {}) or {}

        for symbol, flow in manage_flows.items():
            try:
                has_active = bool(flow.has_active_lifecycle())
            except Exception:
                has_active = False
            if not has_active:
                continue
            bracket_state = dict(brackets_by_symbol.get(symbol) or {})
            lifecycle_id = str(lifecycle_ids.get(symbol) or "").strip() or None
            positions.append(
                ActivePositionView(
                    symbol=symbol,
                    lifecycle_id=lifecycle_id,
                    state=str(getattr(getattr(flow, "state", None),
                              "value", getattr(flow, "state", None)) or ""),
                    side=str(getattr(flow, "position_side", None) or ""),
                    qty=str(getattr(flow, "position_qty", None) or ""),
                    entry_price=str(
                        getattr(flow, "position_entry_price", None) or ""),
                    entry_order_id=str(
                        getattr(flow, "entry_order_id", None) or ""),
                    entry_client_order_id=str(
                        getattr(flow, "entry_client_order_id", None) or ""),
                    sl_price=str(getattr(flow, "sl_price", None) or ""),
                    tp_price=str(getattr(flow, "tp_price", None) or ""),
                    sl_order_id=str(bracket_state.get("sl_order_id") or getattr(
                        flow, "sl_order_id", None) or ""),
                    tp_order_id=str(bracket_state.get("tp_order_id") or getattr(
                        flow, "tp_order_id", None) or ""),
                    closing_position=bool(
                        getattr(flow, "_closing_position", False)),
                    last_close_reason=str(close_reasons.get(symbol) or ""),
                ).model_dump(mode="json")
            )
        return positions

    def get_position(self, lifecycle_id: str) -> Optional[Dict[str, Any]]:
        lifecycle_id_s = str(lifecycle_id or "").strip()
        if not lifecycle_id_s:
            return None
        for position in self.get_active_positions():
            if str(position.get("lifecycle_id") or "") == lifecycle_id_s:
                return position
        return None

    def get_bracket_state(self, lifecycle_id: str) -> Optional[Dict[str, Any]]:
        position = self.get_position(lifecycle_id)
        if position is None:
            return None
        return BracketStateView(
            lifecycle_id=position.get("lifecycle_id"),
            symbol=position.get("symbol"),
            sl_price=position.get("sl_price"),
            tp_price=position.get("tp_price"),
            sl_order_id=position.get("sl_order_id"),
            tp_order_id=position.get("tp_order_id"),
            entry_order_id=position.get("entry_order_id"),
            entry_client_order_id=position.get("entry_client_order_id"),
        ).model_dump(mode="json")

    def get_recent_rejections(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        order_log = self.logs_dir / "order_log_v1.jsonl"
        if not order_log.exists():
            raise TradingReadModelUnavailableError(
                f"rejection ledger missing: {order_log}"
            )
        items = []
        rows = _tail_jsonl(order_log, limit=max(limit * 4, 40))
        if not rows:
            return []
        for row in reversed(rows):
            row_text = json.dumps(row, ensure_ascii=False)
            reason = str(row.get("reason_code") or row.get(
                "reason") or row.get("status") or "")
            if "reject" not in row_text.lower() and "reject" not in reason.lower():
                continue
            items.append(
                RecentRejectionView(
                    ts_ms=row.get("ts_ms") or row.get("ts"),
                    symbol=row.get("symbol") or row.get("instrument"),
                    reason_code=row.get("reason_code") or row.get(
                        "reject_reason_code"),
                    reason=row.get("reason") or row.get("why"),
                    strategy_id=row.get("strategy_id"),
                    source_path=str(order_log),
                ).model_dump(mode="json")
            )
            if len(items) >= limit:
                break
        return list(reversed(items))

    def get_recent_decisions(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        trading_decisions = self.logs_dir / \
            "shadow_telemetry" / "trading_decisions_v1.jsonl"
        ledger = self.logs_dir / "shadow_telemetry" / "decision_ledger_v1.jsonl"
        source_path = trading_decisions if trading_decisions.exists() else ledger
        items = []
        for row in reversed(_tail_jsonl(source_path, limit=max(limit * 3, 30))):
            items.append(
                DecisionHistoryView(
                    ts_ms=row.get("ts_ms") or row.get("ts"),
                    symbol=row.get("symbol"),
                    decision=row.get("action") or row.get(
                        "decision") or row.get("neocortex_action"),
                    confidence=row.get("confidence"),
                    rationale_short=row.get("rationale_short"),
                    packet_ref=row.get("packet_ref"),
                    gate_trace_summary=row.get("gate_trace_summary"),
                    raw_score=row.get("raw_score"),
                    source_path=str(source_path),
                ).model_dump(mode="json")
            )
            if len(items) >= limit:
                break
        return list(reversed(items))

    def get_market_overview(
        self,
        *,
        symbols: Optional[Iterable[str]] = None,
        tf_sec: int = 300,
        allow_degraded: bool = False,
    ) -> Dict[str, Any]:
        context_symbols = [str(symbol).upper()
                           for symbol in (symbols or []) if str(symbol).strip()]
        if not context_symbols:
            raise TradingReadModelUnavailableError(
                "market overview requires explicit symbols to reconstruct canonical snapshot truth"
            )
        snapshots: List[Dict[str, Any]] = []
        missing_snapshots: List[str] = []
        for symbol in context_symbols:
            snapshot = self._latest_snapshot(symbol=symbol, tf_sec=tf_sec)
            if snapshot is None:
                missing_snapshots.append(symbol)
                if not allow_degraded:
                    raise TradingReadModelUnavailableError(
                        f"missing snapshot truth for symbol={symbol} tf_sec={tf_sec}"
                    )
                snapshots.append(
                    {
                        "symbol": symbol,
                        "tf_sec": tf_sec,
                        "ts_ms": None,
                        "regime": None,
                        "features": None,
                        "execution": None,
                        "available": False,
                    }
                )
                continue
            snapshots.append(
                {
                    "symbol": symbol,
                    "tf_sec": tf_sec,
                    "ts_ms": snapshot.get("ts_ms"),
                    "regime": snapshot.get("regime"),
                    "features": snapshot.get("features"),
                    "execution": snapshot.get("execution"),
                    "available": True,
                }
            )
        risk_gate = self._read_risk_gate_state()
        if not bool(risk_gate.get("available")) and not allow_degraded:
            raise TradingReadModelUnavailableError(
                "risk gate truth is unavailable")
        degraded_reasons: List[str] = []
        portfolio_state = self._latest_portfolio_state()
        if missing_snapshots:
            degraded_reasons.append("missing_snapshot_truth")
        if not bool(risk_gate.get("available")):
            degraded_reasons.append("risk_gate_unavailable")
        if portfolio_state is None:
            degraded_reasons.append("portfolio_truth_unavailable")
        try:
            active_positions = self.get_active_positions(
                allow_degraded=allow_degraded)
        except TradingReadModelUnavailableError:
            if not allow_degraded:
                raise
            active_positions = []
            degraded_reasons.append("active_positions_unavailable")
        try:
            recent_rejections = self.get_recent_rejections(limit=10)
        except TradingReadModelUnavailableError:
            if not allow_degraded:
                raise
            recent_rejections = []
            degraded_reasons.append("recent_rejections_unavailable")
        if self.execution_position is None:
            degraded_reasons.append("execution_position_unavailable")
        equity_usd = (
            _decimal_to_number(portfolio_state.get("equity"))
            if isinstance(portfolio_state, dict)
            else None
        )
        positions_usd = (
            _decimal_to_number(portfolio_state.get("open_positions_usd"))
            if isinstance(portfolio_state, dict)
            else None
        )
        available_balance = (
            _decimal_to_number(portfolio_state.get("available_balance"))
            if isinstance(portfolio_state, dict)
            else None
        )
        unrealized_pnl = (
            _decimal_to_number(portfolio_state.get("unrealized_pnl"))
            if isinstance(portfolio_state, dict)
            else None
        )
        realized_pnl = (
            _decimal_to_number(portfolio_state.get("realized_pnl"))
            if isinstance(portfolio_state, dict)
            else None
        )
        return {
            "symbols": context_symbols,
            "snapshots": snapshots,
            "active_positions": active_positions,
            "recent_rejections": recent_rejections,
            "risk_gate": risk_gate,
            "equity_usd": equity_usd,
            "positions_usd": positions_usd,
            "available_balance": available_balance,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "positions_last_ts_ms": portfolio_state.get("positions_last_ts_ms") if isinstance(portfolio_state, dict) else None,
            "runtime_health": {
                "execution_position_available": self.execution_position is not None,
                "snapshot_source": self._snapshot_source_name(),
                "risk_gate_available": bool(risk_gate.get("available")),
                "portfolio_truth_available": isinstance(portfolio_state, dict),
                "degraded": bool(degraded_reasons),
                "degraded_reasons": degraded_reasons,
            },
        }

    def _latest_snapshot(self, *, symbol: str, tf_sec: int) -> Optional[Dict[str, Any]]:
        symbol_key = str(symbol).upper()
        if self.snapshot_store is not None:
            row = self.snapshot_store.latest(symbol=symbol_key, tf_sec=tf_sec)
            return dict(row) if isinstance(row, dict) else None
        tail = self._snapshot_tail(symbol=symbol_key, tf_sec=tf_sec, limit=1)
        return tail[-1] if tail else None

    def _snapshot_tail(self, *, symbol: str, tf_sec: int, limit: int) -> List[Dict[str, Any]]:
        symbol_key = str(symbol).upper()
        if self.snapshot_store is not None:
            rows = self.snapshot_store.tail(symbol=symbol_key, limit=limit)
            return [dict(row) for row in rows if isinstance(row, dict) and int(row.get("tf_sec", -1)) == int(tf_sec)]

        symbol_dir = self.snapshots_dir / symbol_key
        if not symbol_dir.exists():
            return []
        files = sorted(symbol_dir.glob("*/*.jsonl"))
        rows: List[Dict[str, Any]] = []
        for file_path in reversed(files):
            for row in reversed(_tail_jsonl(file_path, limit=max(limit * 2, 100))):
                if int(row.get("tf_sec", -1)) != int(tf_sec):
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    return list(reversed(rows))
        return list(reversed(rows))

    def _latest_portfolio_state(self) -> Optional[Dict[str, Any]]:
        journal_path = self.logs_dir / "shadow_critical_event_journal_v1.jsonl"
        for row in reversed(_tail_jsonl(journal_path, limit=400)):
            payload_fragment = row.get("payload_fragment")
            if not isinstance(payload_fragment, dict):
                continue
            portfolio_state = payload_fragment.get("portfolio_state")
            if isinstance(portfolio_state, dict):
                return dict(portfolio_state)
        return None

    def _active_positions_from_portfolio_truth(self) -> Optional[List[Dict[str, Any]]]:
        portfolio_state = self._latest_portfolio_state()
        if portfolio_state is None:
            return None
        raw_positions = portfolio_state.get("positions")
        if not isinstance(raw_positions, list):
            return []
        positions_last_ts_ms = portfolio_state.get("positions_last_ts_ms")
        items: List[Dict[str, Any]] = []
        for raw_position in raw_positions:
            if not isinstance(raw_position, dict):
                continue
            symbol = str(raw_position.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            net_position = _decimal_or_none(raw_position.get("net_position"))
            if net_position is None:
                net_position = _decimal_or_none(
                    raw_position.get("positionAmt") or raw_position.get(
                        "position_amt")
                )
            if net_position is None or net_position == 0:
                continue
            side = str(raw_position.get("side") or (
                "BUY" if net_position > 0 else "SELL")).upper().strip()
            entry_price_raw = (
                raw_position.get("avg_entry_price")
                or raw_position.get("avgEntryPrice")
                or raw_position.get("entryPrice")
            )
            item = ActivePositionView(
                symbol=symbol,
                lifecycle_id=raw_position.get("lifecycle_id"),
                state="PORTFOLIO_ONLY",
                side=side,
                qty=_decimal_to_text(abs(net_position)),
                entry_price=str(entry_price_raw) if entry_price_raw not in (
                    None, "") else None,
                closing_position=False,
            ).model_dump(mode="json")
            item["source"] = "portfolio_state"
            item["portfolio_truth"] = True
            item["positions_last_ts_ms"] = positions_last_ts_ms
            if raw_position.get("markPrice") is not None:
                item["markPrice"] = raw_position.get("markPrice")
            if raw_position.get("unrealizedPnl") is not None:
                item["unrealizedPnl"] = raw_position.get("unrealizedPnl")
            if raw_position.get("unrealizedPnlPct") is not None:
                item["unrealizedPnlPct"] = raw_position.get("unrealizedPnlPct")
            items.append(item)
        return items

    def _read_risk_gate_state(self) -> Dict[str, Any]:
        raw_path = os.getenv("AURORA_RISK_GATE_STATE_PATH",
                             "data/risk_gate_state.json")
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.project_root / path
        if not path.exists():
            return {"available": False, "source_path": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "available": False,
                "source_path": str(path),
                "error": str(exc),
            }
        if not isinstance(payload, dict):
            return {"available": False, "source_path": str(path)}
        return {
            **payload,
            "available": True,
            "source_path": str(path),
        }
