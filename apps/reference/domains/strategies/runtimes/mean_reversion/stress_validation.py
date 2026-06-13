"""Fee/slippage stress validation for mean-reversion promotion gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency guard
    yaml = None


@dataclass(frozen=True)
class MRStressConfig:
    fee_multiplier: float = 2.0
    slippage_spread_fraction: float = 1.0
    taker_round_trip_fee_bps: float = 12.0
    max_drawdown_guardrail: float | None = None

    @classmethod
    def from_judge_simulator(
        cls,
        path: str | Path = "config/judge_simulator.yaml",
        *,
        overrides: dict[str, Any] | None = None,
    ) -> "MRStressConfig":
        data: dict[str, Any] = {}
        cfg_path = Path(path)
        if yaml is not None and cfg_path.exists():
            loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                data.update(loaded)
        research = data.get("research", {}) if isinstance(data.get("research"), dict) else {}
        mr_stress = research.get("mr_stress", {}) if isinstance(research.get("mr_stress"), dict) else {}
        fee_cfg = data.get("fees", {}) if isinstance(data.get("fees"), dict) else {}
        merged = {
            "fee_multiplier": mr_stress.get("fee_multiplier", 2.0),
            "slippage_spread_fraction": mr_stress.get("slippage_spread_fraction", 1.0),
            "taker_round_trip_fee_bps": (
                mr_stress.get("taker_round_trip_fee_bps")
                or fee_cfg.get("taker_round_trip_fee_bps")
                or fee_cfg.get("round_trip_taker_bps")
                or 12.0
            ),
            "max_drawdown_guardrail": mr_stress.get("max_drawdown_guardrail"),
        }
        merged.update(overrides or {})
        return cls(
            fee_multiplier=float(merged["fee_multiplier"]),
            slippage_spread_fraction=float(merged["slippage_spread_fraction"]),
            taker_round_trip_fee_bps=float(merged["taker_round_trip_fee_bps"]),
            max_drawdown_guardrail=(
                float(merged["max_drawdown_guardrail"])
                if merged["max_drawdown_guardrail"] is not None
                else None
            ),
        )


@dataclass(frozen=True)
class MRStressBucketReport:
    symbol: str
    flat_regime: str
    gross_pnl: float
    net_pnl: float
    expectancy: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    fee_coverage: float
    capital_ready: bool


def build_mr_stress_report(
    trades: Iterable[dict[str, Any]],
    config: MRStressConfig,
) -> list[MRStressBucketReport]:
    buckets: dict[tuple[str, str], list[float]] = {}
    gross_buckets: dict[tuple[str, str], list[float]] = {}
    fees_buckets: dict[tuple[str, str], list[float]] = {}
    for trade in trades:
        symbol = str(trade.get("symbol") or "UNKNOWN").upper()
        flat_regime = str(
            trade.get("flat_regime")
            or trade.get("regime")
            or trade.get("structural_regime")
            or "UNKNOWN"
        ).upper()
        gross = _float(trade.get("gross_pnl", trade.get("pnl", 0.0)))
        notional = abs(_float(trade.get("notional", trade.get("entry_notional", 0.0))))
        spread_bps = abs(_float(trade.get("spread_bps", trade.get("estimated_spread_bps", 0.0))))
        fee_cost = notional * (config.taker_round_trip_fee_bps * config.fee_multiplier) / 10_000.0
        slippage_cost = notional * (spread_bps * config.slippage_spread_fraction) / 10_000.0
        net = gross - fee_cost - slippage_cost
        key = (symbol, flat_regime)
        gross_buckets.setdefault(key, []).append(gross)
        buckets.setdefault(key, []).append(net)
        fees_buckets.setdefault(key, []).append(fee_cost)

    reports: list[MRStressBucketReport] = []
    for key in sorted(buckets):
        symbol, flat_regime = key
        gross_values = gross_buckets[key]
        net_values = buckets[key]
        fee_values = fees_buckets[key]
        gross_pnl = sum(gross_values)
        net_pnl = sum(net_values)
        trade_count = len(net_values)
        expectancy = net_pnl / trade_count if trade_count else 0.0
        max_drawdown = _max_drawdown(net_values)
        win_rate = sum(1 for value in net_values if value > 0.0) / trade_count if trade_count else 0.0
        fee_total = sum(fee_values)
        fee_coverage = gross_pnl / fee_total if fee_total > 0.0 else float("inf")
        drawdown_ok = (
            True
            if config.max_drawdown_guardrail is None
            else max_drawdown <= config.max_drawdown_guardrail
        )
        reports.append(
            MRStressBucketReport(
                symbol=symbol,
                flat_regime=flat_regime,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                expectancy=expectancy,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                trade_count=trade_count,
                fee_coverage=fee_coverage,
                capital_ready=expectancy > 0.0 and net_pnl > 0.0 and drawdown_ok,
            )
        )
    return reports


def promotion_gate_passes(reports: Iterable[MRStressBucketReport]) -> bool:
    reports_list = list(reports)
    return bool(reports_list) and all(report.capital_ready for report in reports_list)


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "MRStressBucketReport",
    "MRStressConfig",
    "build_mr_stress_report",
    "promotion_gate_passes",
]
