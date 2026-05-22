from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class CanonicalEntry:
    entry_id: str
    lifecycle_id: str
    rid: str
    trade_id: str
    symbol: str
    side: str
    strategy_id: str
    entry_ts_ms: int
    entry_time_iso: str
    entry_price: float
    qty: float
    leverage: float
    timestamp_quality: str
    reconstruction_confidence: str
    regime_at_entry: str
    regime_confidence_at_entry: float | None
    regime_source: str
    entry_origin: str = "actual_order_log_fill"
    actual_close_ts_ms: int | None = None
    actual_close_price: float | None = None
    actual_outcome_status: str = ""
    notes: tuple[str, ...] = ()
    trend_dir: str | None = None
    trend_confidence: float | None = None
    trend_run_length: int | None = None
    pm_norm_10s: float | None = None
    pm_norm_60s: float | None = None
    pm_norm_300s: float | None = None
    resolved_min_regime_confidence: float | None = None
    resolved_min_regime_confidence_source: str | None = None
    resolved_max_regime_confidence: float | None = None
    resolved_max_regime_confidence_source: str | None = None
    raw_surface: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_row(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "lifecycle_id": self.lifecycle_id,
            "rid": self.rid,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "strategy_id": self.strategy_id,
            "entry_ts_ms": self.entry_ts_ms,
            "entry_time_iso": self.entry_time_iso,
            "entry_price": self.entry_price,
            "qty": self.qty,
            "leverage": self.leverage,
            "timestamp_quality": self.timestamp_quality,
            "reconstruction_confidence": self.reconstruction_confidence,
            "regime_at_entry": self.regime_at_entry,
            "regime_confidence_at_entry": self.regime_confidence_at_entry,
            "regime_source": self.regime_source,
            "entry_origin": self.entry_origin,
            "actual_close_ts_ms": self.actual_close_ts_ms,
            "actual_close_price": self.actual_close_price,
            "actual_outcome_status": self.actual_outcome_status,
            "notes": "|".join(self.notes),
            "trend_dir": self.trend_dir,
            "trend_confidence": self.trend_confidence,
            "trend_run_length": self.trend_run_length,
            "pm_norm_10s": self.pm_norm_10s,
            "pm_norm_60s": self.pm_norm_60s,
            "pm_norm_300s": self.pm_norm_300s,
            "resolved_min_regime_confidence": self.resolved_min_regime_confidence,
            "resolved_min_regime_confidence_source": self.resolved_min_regime_confidence_source,
            "resolved_max_regime_confidence": self.resolved_max_regime_confidence,
            "resolved_max_regime_confidence_source": self.resolved_max_regime_confidence_source,
        }


@dataclass(frozen=True)
class ExitEvent:
    reason: str
    ts_ms: int | None
    price: float | None
    source: str
    support_quality: str


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    gate_id: str
    reason: str
    detail: str
    support_quality: str

    def to_row(self, scenario_id: str, entry: CanonicalEntry) -> dict[str, Any]:
        return {
            "scenario_id": scenario_id,
            "entry_id": entry.entry_id,
            "symbol": entry.symbol,
            "side": entry.side,
            "gate_id": self.gate_id,
            "allowed": "true" if self.allowed else "false",
            "reason": self.reason,
            "detail": self.detail,
            "support_quality": self.support_quality,
        }


@dataclass
class CandleSeries:
    symbol: str
    rows: list[dict[str, Any]]
    timestamps: list[int]


@dataclass
class ScenarioRuntime:
    workspace_root: Path
    runtime_root: Path
    report_root: Path
    config: dict[str, Any]
    candles_by_symbol: dict[str, CandleSeries]
    strict: bool
    sidecar_requests: list[dict[str, Any]] = field(default_factory=list)
    sidecar_request_index: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    synthetic_entry_sets: dict[str, list[CanonicalEntry]] = field(default_factory=dict)


EntryFilter = Callable[[CanonicalEntry, ScenarioRuntime], GateDecision]
ExitPolicy = Callable[[CanonicalEntry, ScenarioRuntime], tuple[ExitEvent, dict[str, Any]]]
EntryProvider = Callable[[list[CanonicalEntry], ScenarioRuntime], list[CanonicalEntry]]


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    entry_filter: EntryFilter
    exit_policy: ExitPolicy
    required_surfaces: tuple[str, ...]
    report_contract: str
    allow_regime_flip_exits: bool = True
    entry_provider: EntryProvider | None = None
