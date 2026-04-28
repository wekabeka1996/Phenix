#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import pandas as pd


INTENT_EVENT_TYPES = {
    "ORDER_INTENT",
    "TRADE_INTENT",
    "TRADE_INTENT_PROPOSED",
    "EVT:TRADE_INTENT_PROPOSED",
    "DECISION_INTENT",
    "DECISION_INTENT_PROPOSED",
}

SYSTEM_BLOCK_EVENT_TYPES = {
    "DECISION_INTENT_REJECTED",
    "TRADE_INTENT_REJECTED",
    "EVT:TRADE_INTENT_REJECTED",
    "DECISION_BLOCKED",
    "EVT:DECISION_BLOCKED",
    "EXECUTION_GUARD_BLOCKED",
    "EVT:EXECUTION_GUARD_BLOCKED",
    "TRADE_INTENT_BLOCKED",
    "EVT:TRADE_INTENT_BLOCKED",
}

TERMINAL_PNL_EVENT_TYPES = {
    "POSITION_CLOSED",
    "EVT:POSITION_CLOSED",
    "TRADE_CLOSED",
    "TRADE_EPISODE_CLOSED",
    "POSITION_FLAT",
    "ORDER_EXECUTED",
    "TRADE_EXECUTED",
}

ANSI = {
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


@dataclass(slots=True)
class IntentEpisode:
    primary_id: str
    first_seen_ts_ms: int
    first_seen_seq: int
    aliases: set[str] = field(default_factory=set)
    symbol: Optional[str] = None
    side: Optional[str] = None
    source_fsm: Optional[str] = None
    intent_event_type: Optional[str] = None
    proposed_ts_ms: Optional[int] = None
    proposed_seq: Optional[int] = None
    has_explicit_intent: bool = False
    synthetic_from_system_block: bool = False
    system_blocked_historically: bool = False
    system_block_event_type: Optional[str] = None
    system_block_reason: Optional[str] = None
    system_block_ts_ms: Optional[int] = None
    terminal_event_type: Optional[str] = None
    terminal_reason: Optional[str] = None
    terminal_ts_ms: Optional[int] = None
    terminal_seq: Optional[int] = None
    realized_pnl_net: Optional[float] = None

    def register_aliases(self, aliases: Iterable[str]) -> None:
        for alias in aliases:
            normalized = _normalize_text(alias)
            if normalized:
                self.aliases.add(normalized)

    def absorb(self, other: "IntentEpisode") -> None:
        self.register_aliases(other.aliases)
        if other.first_seen_ts_ms < self.first_seen_ts_ms:
            self.first_seen_ts_ms = other.first_seen_ts_ms
            self.first_seen_seq = other.first_seen_seq
        if other.has_explicit_intent:
            if (
                self.proposed_ts_ms is None
                or other.proposed_ts_ms is None
                or (other.proposed_ts_ms, other.proposed_seq or other.first_seen_seq)
                < (self.proposed_ts_ms, self.proposed_seq or self.first_seen_seq)
            ):
                self.proposed_ts_ms = other.proposed_ts_ms
                self.proposed_seq = other.proposed_seq
                self.intent_event_type = other.intent_event_type or self.intent_event_type
            self.has_explicit_intent = True
        self.synthetic_from_system_block = (
            self.synthetic_from_system_block or other.synthetic_from_system_block
        )
        self.system_blocked_historically = (
            self.system_blocked_historically or other.system_blocked_historically
        )
        self.symbol = self.symbol or other.symbol
        self.side = self.side or other.side
        self.source_fsm = self.source_fsm or other.source_fsm
        self.system_block_event_type = (
            self.system_block_event_type or other.system_block_event_type
        )
        self.system_block_reason = self.system_block_reason or other.system_block_reason
        if self.system_block_ts_ms is None or (
            other.system_block_ts_ms is not None
            and other.system_block_ts_ms < self.system_block_ts_ms
        ):
            self.system_block_ts_ms = other.system_block_ts_ms
        if self.terminal_ts_ms is None or (
            other.terminal_ts_ms is not None
            and other.terminal_ts_ms < self.terminal_ts_ms
        ):
            self.terminal_ts_ms = other.terminal_ts_ms
            self.terminal_seq = other.terminal_seq
            self.terminal_event_type = other.terminal_event_type
            self.terminal_reason = other.terminal_reason
            self.realized_pnl_net = other.realized_pnl_net

    def attach_intent(
        self,
        *,
        event_type: str,
        ts_ms: int,
        seq: int,
        symbol: Optional[str],
        side: Optional[str],
        source_fsm: Optional[str],
    ) -> None:
        self.has_explicit_intent = True
        if self.proposed_ts_ms is None or (ts_ms, seq) < (
            self.proposed_ts_ms,
            self.proposed_seq or self.first_seen_seq,
        ):
            self.proposed_ts_ms = ts_ms
            self.proposed_seq = seq
            self.intent_event_type = event_type
        self.symbol = self.symbol or symbol
        self.side = self.side or side
        self.source_fsm = self.source_fsm or source_fsm

    def attach_system_block(
        self,
        *,
        event_type: str,
        ts_ms: int,
        symbol: Optional[str],
        side: Optional[str],
        source_fsm: Optional[str],
        reason: Optional[str],
    ) -> None:
        self.system_blocked_historically = True
        self.synthetic_from_system_block = self.synthetic_from_system_block or not self.has_explicit_intent
        self.system_block_event_type = self.system_block_event_type or event_type
        self.system_block_reason = self.system_block_reason or reason
        if self.system_block_ts_ms is None or ts_ms < self.system_block_ts_ms:
            self.system_block_ts_ms = ts_ms
        if self.proposed_ts_ms is None:
            self.proposed_ts_ms = ts_ms
            self.proposed_seq = self.proposed_seq or self.first_seen_seq
        self.symbol = self.symbol or symbol
        self.side = self.side or side
        self.source_fsm = self.source_fsm or source_fsm

    def attach_terminal(
        self,
        *,
        event_type: str,
        ts_ms: int,
        seq: int,
        symbol: Optional[str],
        side: Optional[str],
        reason: Optional[str],
        realized_pnl_net: float,
    ) -> None:
        if self.terminal_ts_ms is None or (ts_ms, seq) < (
            self.terminal_ts_ms,
            self.terminal_seq or self.first_seen_seq,
        ):
            self.terminal_ts_ms = ts_ms
            self.terminal_seq = seq
            self.terminal_event_type = event_type
            self.terminal_reason = reason
            self.realized_pnl_net = realized_pnl_net
        self.symbol = self.symbol or symbol
        self.side = self.side or side
        if self.proposed_ts_ms is None:
            self.proposed_ts_ms = ts_ms
            self.proposed_seq = seq


@dataclass(slots=True)
class ParseSummary:
    ledger: pd.DataFrame
    parsed_lines: int
    malformed_lines: int
    ignored_lines: int
    merged_episode_count: int


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_timestamp_ms(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric <= 0.0:
        return None
    if numeric >= 1e11:
        return int(round(numeric))
    if numeric >= 1e9:
        return int(round(numeric * 1000.0))
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _event_type_of(event: Mapping[str, Any]) -> str:
    raw = event.get("event_type")
    if raw is None:
        raw = event.get("event_name")
    return (_normalize_text(raw) or "UNKNOWN").upper()


def _timestamp_of(event: Mapping[str, Any]) -> Optional[int]:
    for key in ("timestamp", "event_ts_ms", "timestamp_ms", "ts_ms", "ts"):
        if key in event:
            normalized = _normalize_timestamp_ms(event.get(key))
            if normalized is not None:
                return normalized
    return None


def _metadata_of(event: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = event.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _adapter_response_of(event: Mapping[str, Any]) -> Mapping[str, Any]:
    adapter_response = event.get("adapter_response")
    return adapter_response if isinstance(adapter_response, Mapping) else {}


def _extract_candidate_ids(event: Mapping[str, Any]) -> list[str]:
    metadata = _metadata_of(event)
    adapter_response = _adapter_response_of(event)
    ordered_candidates = [
        event.get("rid"),
        event.get("lifecycle_id"),
        metadata.get("idempotent_key"),
        event.get("reservation_id"),
        metadata.get("corr_id"),
        event.get("decision_id"),
        event.get("client_order_id"),
        adapter_response.get("clientOrderId"),
        event.get("order_id"),
        adapter_response.get("orderId"),
        event.get("trade_id"),
        metadata.get("fill_trade_id"),
    ]
    aliases: list[str] = []
    seen: set[str] = set()
    for candidate in ordered_candidates:
        normalized = _normalize_text(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            aliases.append(normalized)
    return aliases


def _extract_symbol(event: Mapping[str, Any]) -> Optional[str]:
    return _normalize_text(event.get("symbol") or event.get("instrument"))


def _extract_side(event: Mapping[str, Any]) -> Optional[str]:
    return _normalize_text(event.get("side") or event.get("position_side"))


def _extract_reason(event: Mapping[str, Any]) -> Optional[str]:
    metadata = _metadata_of(event)
    return (
        _normalize_text(event.get("why"))
        or _normalize_text(event.get("close_reason"))
        or _normalize_text(metadata.get("reject_reason"))
        or _normalize_text(metadata.get("deny_reason"))
        or _normalize_text(metadata.get("error"))
    )


def _extract_realized_pnl_net(event: Mapping[str, Any]) -> Optional[float]:
    metadata = _metadata_of(event)
    direct_net = (
        _safe_float(event.get("realized_pnl_net"))
        or _safe_float(event.get("pnl_net"))
        or _safe_float(metadata.get("realized_pnl_net"))
        or _safe_float(metadata.get("pnl_net"))
    )
    if direct_net is not None:
        return direct_net
    realized = _safe_float(event.get("realized_pnl"))
    if realized is None:
        realized = _safe_float(metadata.get("realized_pnl"))
    if realized is None:
        return None
    fees = (
        _safe_float(event.get("fees"))
        or _safe_float(metadata.get("fees"))
        or _safe_float(event.get("commission"))
        or _safe_float(metadata.get("commission"))
        or 0.0
    )
    return realized - fees


def _is_decision_intent(event_type: str, event: Mapping[str, Any]) -> bool:
    if event_type not in INTENT_EVENT_TYPES:
        return False
    if event_type != "ORDER_INTENT":
        return True
    metadata = _metadata_of(event)
    source_fsm = _normalize_text(event.get("source_fsm"))
    return bool(metadata.get("intent_proposed") is True or source_fsm == "DecisionMaking")


def _is_system_block_event(event_type: str, event: Mapping[str, Any]) -> bool:
    if event_type in SYSTEM_BLOCK_EVENT_TYPES:
        return True
    metadata = _metadata_of(event)
    reject_reason = _normalize_text(metadata.get("reject_reason"))
    if reject_reason in {"SAFETY_GATES_DENY", "EXECUTION_GUARD_BLOCKED"}:
        return True
    if event_type == "ORDER_REJECTED":
        return False
    canonical_family = _normalize_text(metadata.get("canonical_event_family"))
    return canonical_family in {"TRADE_INTENT_REJECTED", "DECISION_BLOCKED"}


def _is_terminal_pnl_event(event_type: str, event: Mapping[str, Any]) -> bool:
    if event_type in TERMINAL_PNL_EVENT_TYPES:
        return _extract_realized_pnl_net(event) is not None
    if event_type in {"ORDER_FILLED", "ORDER_CLOSED", "TRADE_FILLED"}:
        return False
    return False


def _resolve_episode(
    *,
    aliases: Sequence[str],
    alias_map: dict[str, str],
    episodes: dict[str, IntentEpisode],
    ts_ms: int,
    seq: int,
    merge_counter: list[int],
) -> IntentEpisode:
    primary_ids = []
    seen_primary_ids: set[str] = set()
    for alias in aliases:
        primary_id = alias_map.get(alias)
        if primary_id and primary_id in episodes and primary_id not in seen_primary_ids:
            seen_primary_ids.add(primary_id)
            primary_ids.append(primary_id)

    if not primary_ids:
        primary_id = aliases[0] if aliases else f"anon::{ts_ms}::{seq}"
        episode = IntentEpisode(primary_id=primary_id,
                                first_seen_ts_ms=ts_ms, first_seen_seq=seq)
        episodes[primary_id] = episode
    else:
        episode = min(
            (episodes[primary_id] for primary_id in primary_ids),
            key=lambda current: (current.first_seen_ts_ms,
                                 current.first_seen_seq, current.primary_id),
        )
        for other_primary_id in primary_ids:
            if other_primary_id == episode.primary_id:
                continue
            other = episodes.pop(other_primary_id)
            episode.absorb(other)
            for alias in other.aliases:
                alias_map[alias] = episode.primary_id
            merge_counter[0] += 1

    episode.register_aliases(aliases)
    for alias in episode.aliases:
        alias_map[alias] = episode.primary_id
    return episode


def _build_ledger(episodes: Iterable[IntentEpisode]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        proposed_ts_ms = episode.proposed_ts_ms or episode.system_block_ts_ms or episode.first_seen_ts_ms
        if episode.realized_pnl_net is not None and episode.terminal_ts_ms is not None:
            historical_status = "EXECUTED"
            realized_pnl_net = float(episode.realized_pnl_net)
            terminal_ts_ms = episode.terminal_ts_ms
        elif episode.system_blocked_historically:
            historical_status = "SYSTEM_BLOCKED"
            realized_pnl_net = 0.0
            terminal_ts_ms = episode.system_block_ts_ms or proposed_ts_ms
        else:
            historical_status = "UNRESOLVED"
            realized_pnl_net = math.nan
            terminal_ts_ms = math.nan

        rows.append(
            {
                "episode_id": episode.primary_id,
                "symbol": episode.symbol or "UNKNOWN",
                "side": episode.side or "UNKNOWN",
                "proposed_ts_ms": int(proposed_ts_ms),
                "terminal_ts_ms": terminal_ts_ms,
                "historical_status": historical_status,
                "realized_pnl_net": realized_pnl_net,
                "intent_event_type": episode.intent_event_type or "SYNTHETIC_BLOCK_INTENT",
                "terminal_event_type": episode.terminal_event_type or episode.system_block_event_type or "UNKNOWN",
                "system_block_reason": episode.system_block_reason,
                "source_fsm": episode.source_fsm,
                "synthetic_from_system_block": episode.synthetic_from_system_block,
                "alias_count": len(episode.aliases),
                "close_reason": episode.terminal_reason,
            }
        )

    ledger = pd.DataFrame(rows)
    if ledger.empty:
        return ledger
    ledger = ledger.sort_values(
        by=["proposed_ts_ms", "terminal_ts_ms", "episode_id"],
        na_position="last",
    ).reset_index(drop=True)
    return ledger


def parse_log_to_ledger(log_path: Path) -> ParseSummary:
    alias_map: dict[str, str] = {}
    episodes: dict[str, IntentEpisode] = {}
    malformed_lines = 0
    parsed_lines = 0
    ignored_lines = 0
    merge_counter = [0]

    with log_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                malformed_lines += 1
                continue
            if not isinstance(event, Mapping):
                malformed_lines += 1
                continue

            parsed_lines += 1
            event_type = _event_type_of(event)
            ts_ms = _timestamp_of(event)
            if ts_ms is None:
                ignored_lines += 1
                continue

            is_intent = _is_decision_intent(event_type, event)
            is_system_block = _is_system_block_event(event_type, event)
            is_terminal = _is_terminal_pnl_event(event_type, event)
            if not (is_intent or is_system_block or is_terminal):
                ignored_lines += 1
                continue

            aliases = _extract_candidate_ids(event)
            episode = _resolve_episode(
                aliases=aliases,
                alias_map=alias_map,
                episodes=episodes,
                ts_ms=ts_ms,
                seq=line_number,
                merge_counter=merge_counter,
            )

            symbol = _extract_symbol(event)
            side = _extract_side(event)
            source_fsm = _normalize_text(event.get("source_fsm"))
            reason = _extract_reason(event)

            if is_intent:
                episode.attach_intent(
                    event_type=event_type,
                    ts_ms=ts_ms,
                    seq=line_number,
                    symbol=symbol,
                    side=side,
                    source_fsm=source_fsm,
                )

            if is_system_block:
                episode.attach_system_block(
                    event_type=event_type,
                    ts_ms=ts_ms,
                    symbol=symbol,
                    side=side,
                    source_fsm=source_fsm,
                    reason=reason,
                )

            if is_terminal:
                realized_pnl_net = _extract_realized_pnl_net(event)
                if realized_pnl_net is not None:
                    episode.attach_terminal(
                        event_type=event_type,
                        ts_ms=ts_ms,
                        seq=line_number,
                        symbol=symbol,
                        side=side,
                        reason=reason,
                        realized_pnl_net=realized_pnl_net,
                    )

    ledger = _build_ledger(episodes.values())
    return ParseSummary(
        ledger=ledger,
        parsed_lines=parsed_lines,
        malformed_lines=malformed_lines,
        ignored_lines=ignored_lines,
        merged_episode_count=merge_counter[0],
    )


def _safe_improvement_pct(baseline: float, oracle: float) -> float:
    if not math.isfinite(baseline) or not math.isfinite(oracle):
        return math.nan
    if abs(baseline) < 1e-12:
        delta = oracle - baseline
        if abs(delta) < 1e-12:
            return 0.0
        return math.inf if delta > 0.0 else -math.inf
    return ((oracle - baseline) / abs(baseline)) * 100.0


def _estimated_hourly_sharpe(cashflows: pd.DataFrame, pnl_column: str) -> float:
    if cashflows.empty:
        return math.nan
    series = pd.Series(
        cashflows[pnl_column].astype(float).to_numpy(),
        index=pd.to_datetime(cashflows["cashflow_ts_ms"].astype(
            "int64"), unit="ms", utc=True),
    ).sort_index()
    hourly = series.resample("1h").sum()
    if hourly.empty or len(hourly) < 2:
        return math.nan
    std = float(hourly.std(ddof=1))
    if not math.isfinite(std) or std <= 0.0:
        return math.nan
    mean = float(hourly.mean())
    return math.sqrt(24.0 * 365.0) * mean / std


def _estimated_max_drawdown(cashflows: pd.DataFrame, pnl_column: str) -> float:
    if cashflows.empty:
        return 0.0
    series = cashflows.sort_values(
        by=["cashflow_ts_ms", "proposed_ts_ms", "episode_id"])[pnl_column].astype(float)
    equity = pd.concat([pd.Series([0.0]), series.cumsum()], ignore_index=True)
    running_peak = equity.cummax()
    drawdown = equity - running_peak
    return float((-drawdown).max())


def _win_rate(executed_mask: pd.Series, pnl_series: pd.Series) -> float:
    executed_count = int(executed_mask.sum())
    if executed_count == 0:
        return math.nan
    wins = int((pnl_series[executed_mask] > 0.0).sum())
    return wins / executed_count


def simulate_oracle(
    ledger: pd.DataFrame,
    *,
    cooldown_seconds: int,
    block_budget_ratio: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    analyzable = ledger[ledger["historical_status"] != "UNRESOLVED"].copy()
    if analyzable.empty:
        raise ValueError("No analyzable intents were found in the input log.")

    analyzable = analyzable.sort_values(
        by=["proposed_ts_ms", "episode_id"]).reset_index(drop=True)
    total_intents = len(analyzable)
    max_oracle_blocks = math.floor(total_intents * block_budget_ratio)
    cooldown_ms = int(cooldown_seconds * 1000)

    oracle_actions: list[str] = []
    oracle_reasons: list[str] = []
    oracle_pnl: list[float] = []
    oracle_executed: list[bool] = []

    cooldown_until_ms = -1
    blocks_used = 0

    for row in analyzable.itertuples(index=False):
        historical_status = str(row.historical_status)
        proposed_ts_ms = int(row.proposed_ts_ms)
        realized_pnl_net = 0.0 if historical_status != "EXECUTED" else float(
            row.realized_pnl_net)

        if historical_status == "SYSTEM_BLOCKED":
            oracle_actions.append("ALLOW_BASELINE_BLOCK")
            oracle_reasons.append(
                "Baseline system already blocked this intent")
            oracle_pnl.append(0.0)
            oracle_executed.append(False)
            continue

        if proposed_ts_ms < cooldown_until_ms:
            oracle_actions.append("ALLOW_COOLDOWN")
            oracle_reasons.append("Oracle cooldown is active")
            oracle_pnl.append(realized_pnl_net)
            oracle_executed.append(True)
            continue

        if blocks_used >= max_oracle_blocks:
            oracle_actions.append("ALLOW_BUDGET_EXHAUSTED")
            oracle_reasons.append("Oracle intervention budget exhausted")
            oracle_pnl.append(realized_pnl_net)
            oracle_executed.append(True)
            continue

        if realized_pnl_net < 0.0:
            oracle_actions.append("BLOCK")
            oracle_reasons.append("Oracle blocks historically losing intent")
            oracle_pnl.append(0.0)
            oracle_executed.append(False)
            blocks_used += 1
            cooldown_until_ms = proposed_ts_ms + cooldown_ms
            continue

        oracle_actions.append("ALLOW")
        oracle_reasons.append("Oracle allows historically non-losing intent")
        oracle_pnl.append(realized_pnl_net)
        oracle_executed.append(True)

    analyzable["oracle_action"] = oracle_actions
    analyzable["oracle_reason"] = oracle_reasons
    analyzable["baseline_pnl"] = analyzable["realized_pnl_net"].where(
        analyzable["historical_status"] == "EXECUTED",
        0.0,
    )
    analyzable["oracle_pnl"] = oracle_pnl
    analyzable["baseline_executed"] = analyzable["historical_status"] == "EXECUTED"
    analyzable["oracle_executed"] = oracle_executed
    analyzable["cashflow_ts_ms"] = analyzable["terminal_ts_ms"].where(
        analyzable["historical_status"] == "EXECUTED",
        analyzable["proposed_ts_ms"],
    )
    analyzable["cashflow_ts_ms"] = analyzable["cashflow_ts_ms"].fillna(
        analyzable["proposed_ts_ms"]).astype("int64")

    baseline_total_pnl = float(analyzable["baseline_pnl"].sum())
    oracle_total_pnl = float(analyzable["oracle_pnl"].sum())
    baseline_sharpe = _estimated_hourly_sharpe(analyzable, "baseline_pnl")
    oracle_sharpe = _estimated_hourly_sharpe(analyzable, "oracle_pnl")
    baseline_drawdown = _estimated_max_drawdown(analyzable, "baseline_pnl")
    oracle_drawdown = _estimated_max_drawdown(analyzable, "oracle_pnl")

    summary = {
        "total_intents": total_intents,
        "system_blocked_intents": int((analyzable["historical_status"] == "SYSTEM_BLOCKED").sum()),
        "baseline_executed_trades": int(analyzable["baseline_executed"].sum()),
        "oracle_executed_trades": int(analyzable["oracle_executed"].sum()),
        "oracle_blocked_trades": int((analyzable["oracle_action"] == "BLOCK").sum()),
        "max_oracle_blocks": max_oracle_blocks,
        "baseline_total_pnl": baseline_total_pnl,
        "oracle_total_pnl": oracle_total_pnl,
        "baseline_win_rate": _win_rate(analyzable["baseline_executed"], analyzable["baseline_pnl"]),
        "oracle_win_rate": _win_rate(analyzable["oracle_executed"], analyzable["oracle_pnl"]),
        "baseline_sharpe": baseline_sharpe,
        "oracle_sharpe": oracle_sharpe,
        "baseline_max_drawdown": baseline_drawdown,
        "oracle_max_drawdown": oracle_drawdown,
        "pnl_improvement_pct": _safe_improvement_pct(baseline_total_pnl, oracle_total_pnl),
        "sharpe_improvement_pct": _safe_improvement_pct(baseline_sharpe, oracle_sharpe),
    }
    return analyzable, summary


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def _colorize(text: str, color: str) -> str:
    if not _supports_color():
        return text
    return f"{ANSI[color]}{text}{ANSI['reset']}"


def _format_float(value: Any, *, decimals: int = 2, signed: bool = False) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    if math.isinf(numeric):
        return "+inf" if numeric > 0.0 else "-inf"
    format_spec = f"{'+.' if signed else '.'}{decimals}f"
    return format(numeric, format_spec)


def _format_money(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    if math.isinf(numeric):
        return "+inf" if numeric > 0.0 else "-inf"
    if abs(numeric) < 5e-13:
        numeric = 0.0
    return f"{numeric:,.6f}"


def _format_pct(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    if math.isinf(numeric):
        return "+inf%" if numeric > 0.0 else "-inf%"
    return f"{numeric * 100.0:.2f}%"


def _format_delta_pct(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    if math.isinf(numeric):
        return "+inf%" if numeric > 0.0 else "-inf%"
    return f"{numeric:+.2f}%"


def _choose_gate_metric(summary: Mapping[str, Any]) -> tuple[str, float]:
    sharpe_improvement_pct = _safe_float(summary.get("sharpe_improvement_pct"))
    if sharpe_improvement_pct is not None and math.isfinite(sharpe_improvement_pct):
        return "Sharpe", sharpe_improvement_pct
    pnl_improvement_pct = _safe_float(summary.get("pnl_improvement_pct"))
    if pnl_improvement_pct is None:
        return "PnL", math.nan
    return "PnL", pnl_improvement_pct


def build_report(
    *,
    log_path: Path,
    parse_summary: ParseSummary,
    analyzable: pd.DataFrame,
    summary: Mapping[str, Any],
    cooldown_seconds: int,
    block_budget_ratio: float,
) -> str:
    unresolved_count = int((parse_summary.ledger["historical_status"] == "UNRESOLVED").sum(
    )) if not parse_summary.ledger.empty else 0

    comparison = pd.DataFrame(
        [
            {
                "Metric": "Total Realized PnL",
                "Baseline": _format_money(summary["baseline_total_pnl"]),
                "Oracle": _format_money(summary["oracle_total_pnl"]),
                "Delta": _format_money(_safe_float(summary["oracle_total_pnl"]) - _safe_float(summary["baseline_total_pnl"])),
            },
            {
                "Metric": "Win Rate",
                "Baseline": _format_pct(summary["baseline_win_rate"]),
                "Oracle": _format_pct(summary["oracle_win_rate"]),
                "Delta": _format_delta_pct(
                    (_safe_float(summary["oracle_win_rate"]) or 0.0) * 100.0
                    - (_safe_float(summary["baseline_win_rate"]) or 0.0) * 100.0
                ),
            },
            {
                "Metric": "Executed Trades",
                "Baseline": str(summary["baseline_executed_trades"]),
                "Oracle": str(summary["oracle_executed_trades"]),
                "Delta": f"{int(summary['oracle_executed_trades']) - int(summary['baseline_executed_trades']):+d}",
            },
            {
                "Metric": "Oracle Blocked Trades",
                "Baseline": "0",
                "Oracle": str(summary["oracle_blocked_trades"]),
                "Delta": f"+{int(summary['oracle_blocked_trades'])}",
            },
            {
                "Metric": "Estimated Sharpe (hourly)",
                "Baseline": _format_float(summary["baseline_sharpe"], decimals=4),
                "Oracle": _format_float(summary["oracle_sharpe"], decimals=4),
                "Delta": _format_float(
                    (_safe_float(summary["oracle_sharpe"]) or 0.0)
                    - (_safe_float(summary["baseline_sharpe"]) or 0.0),
                    decimals=4,
                    signed=True,
                ),
            },
            {
                "Metric": "Max Drawdown",
                "Baseline": _format_money(summary["baseline_max_drawdown"]),
                "Oracle": _format_money(summary["oracle_max_drawdown"]),
                "Delta": _format_money(
                    (_safe_float(summary["oracle_max_drawdown"]) or 0.0)
                    - (_safe_float(summary["baseline_max_drawdown"]) or 0.0)
                ),
            },
        ]
    )

    gate_metric_name, gate_improvement_pct = _choose_gate_metric(summary)
    if math.isfinite(gate_improvement_pct) and gate_improvement_pct > 15.0:
        verdict = _colorize(
            "[GO] Significant alpha detected. Proceed with Neocortex engineering.",
            "green",
        )
    elif math.isfinite(gate_improvement_pct) and gate_improvement_pct >= 5.0:
        verdict = _colorize(
            "[CONDITIONAL GO] Marginal alpha detected. Requires further baseline testing.",
            "yellow",
        )
    else:
        verdict = _colorize(
            "[NO-GO] Theoretical alpha is too low. Infrastructure overhead will consume profits.",
            "red",
        )

    lines = [
        _colorize("Experiment 0.0: Perfect Oracle Retrospective", "bold"),
        f"Log path: {log_path}",
        "",
        "Dataset",
        f"  Parsed JSON rows: {parse_summary.parsed_lines}",
        f"  Malformed JSON rows skipped: {parse_summary.malformed_lines}",
        f"  Irrelevant or untimestamped rows ignored: {parse_summary.ignored_lines}",
        f"  Episode merges from alias reconciliation: {parse_summary.merged_episode_count}",
        f"  Total intents in dataset: {summary['total_intents']}",
        f"  Baseline system-blocked intents: {summary['system_blocked_intents']}",
        f"  Unresolved intents skipped from scoring: {unresolved_count}",
        f"  Oracle cooldown: {cooldown_seconds} seconds",
        f"  Oracle intervention budget: {int(summary['max_oracle_blocks'])}/{int(summary['total_intents'])} ({block_budget_ratio:.0%})",
        "",
        "Comparison",
        comparison.to_string(index=False),
        "",
        "Improvements",
        f"  PnL improvement: {_format_delta_pct(summary['pnl_improvement_pct'])}",
        f"  Sharpe improvement: {_format_delta_pct(summary['sharpe_improvement_pct'])}",
        f"  Primary gate metric: {gate_metric_name}",
        "",
        verdict,
    ]
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrospective perfect-oracle PnL analysis over Aurora/Phenix WAL logs.",
    )
    parser.add_argument(
        "--log_path",
        required=True,
        help="Path to logs/order_log_v1.jsonl or logs/trade_lifecycle.jsonl.",
    )
    parser.add_argument(
        "--cooldown_seconds",
        type=int,
        default=900,
        help="Oracle cooldown after a BLOCK action. Default: 900 seconds.",
    )
    parser.add_argument(
        "--block_budget_ratio",
        type=float,
        default=0.20,
        help="Maximum fraction of total intents the oracle may block. Default: 0.20.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    log_path = Path(args.log_path).expanduser()
    if not log_path.is_absolute():
        log_path = Path.cwd() / log_path
    log_path = log_path.resolve()

    if not log_path.exists() or not log_path.is_file():
        parser.error(f"Log file does not exist: {log_path}")
    if args.cooldown_seconds < 0:
        parser.error("--cooldown_seconds must be >= 0")
    if not 0.0 <= args.block_budget_ratio <= 1.0:
        parser.error("--block_budget_ratio must be between 0.0 and 1.0")

    parse_summary = parse_log_to_ledger(log_path)
    if parse_summary.ledger.empty:
        raise SystemExit(
            "No relevant intent or terminal events were found in the input log.")

    analyzable, summary = simulate_oracle(
        parse_summary.ledger,
        cooldown_seconds=args.cooldown_seconds,
        block_budget_ratio=args.block_budget_ratio,
    )
    report = build_report(
        log_path=log_path,
        parse_summary=parse_summary,
        analyzable=analyzable,
        summary=summary,
        cooldown_seconds=args.cooldown_seconds,
        block_budget_ratio=args.block_budget_ratio,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
