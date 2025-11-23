"""
ExecPos Tools Metrics Aggregator
================================

Canonical tooling-side metrics (does not change runtime metrics).

Counters:
- execpos_trades_total{result, source}
- execpos_bracket_violations_total{severity, kind}
- execpos_watchdog_alerts_total{severity, kind}
- execpos_trailing_signals_total{kind}

Outputs:
- `to_dict()` for JSON/CLI consumption.
- `to_prometheus_text()` for text exposition.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Supported label values
TRADE_RESULTS = {"win", "loss", "flat", "unknown"}
TRADE_SOURCES = {"tca", "trace", "runtime", "unknown"}
SEVERITIES = {"WARN", "ALERT"}
TRAILING_KINDS = {"EXIT", "MOVE_SL", "BREAKEVEN", "TIME_EXIT", "UNKNOWN"}


def _norm(value: Optional[str], allowed: Iterable[str], default: str) -> str:
    """Normalize a string to upper case and constrain to allowed set."""
    if not value:
        return default
    val = str(value).upper()
    return val if val in allowed else default


class ExecPosMetricsAggregator:
    """Aggregates canonical ExecPos metrics for tooling."""

    def __init__(self):
        # key -> count
        self.trades_total: Dict[Tuple[str, str], int] = defaultdict(int)
        self.bracket_violations_total: Dict[Tuple[str, str], int] = defaultdict(int)
        self.watchdog_alerts_total: Dict[Tuple[str, str], int] = defaultdict(int)
        self.trailing_signals_total: Dict[str, int] = defaultdict(int)

    # ------------------
    # Public API
    # ------------------
    def add_trade(self, result: Optional[str], source: Optional[str] = None) -> None:
        """Add a trade outcome counter."""
        res = _norm(result, {r.upper() for r in TRADE_RESULTS}, "UNKNOWN")
        src = _norm(source or "unknown", {s.upper() for s in TRADE_SOURCES}, "UNKNOWN")
        self.trades_total[(res, src)] += 1

    def add_bracket_violation(self, severity: Optional[str], kind: Optional[str]) -> None:
        """Add a bracket violation (from BracketService plans)."""
        sev = _norm(severity, SEVERITIES, "WARN")
        k = (kind or "UNKNOWN").upper()
        self.bracket_violations_total[(sev, k)] += 1

    def add_watchdog_alert(self, severity: Optional[str], kind: Optional[str]) -> None:
        """Add a watchdog alert/warn (severity-based)."""
        sev = _norm(severity, SEVERITIES, "WARN")
        k = (kind or "UNKNOWN").upper()
        self.watchdog_alerts_total[(sev, k)] += 1

    def add_trailing_signal(self, kind: Optional[str]) -> None:
        """Add a trailing-related signal."""
        k = _norm(kind, TRAILING_KINDS, "UNKNOWN")
        self.trailing_signals_total[k] += 1

    # ------------------
    # Helpers for tool inputs
    # ------------------
    def consume_tca_records(self, records: Iterable[Any]) -> None:
        """Consume TCA trade records (pnl-less -> result=unknown)."""
        for _ in records:
            self.add_trade(result="unknown", source="tca")

    def consume_trace_events(self, events: Iterable[Any]) -> None:
        """Consume trace events (order_trace TraceEvent)."""
        for event in events:
            etype = str(getattr(event, "event_type", "") or "").upper()
            payload = getattr(event, "payload", {}) or {}

            if etype == "EXEC_TRADE":
                # PnL usually absent in event; mark as executed/unknown result
                source = str(getattr(event, "source", "") or "trace").lower()
                self.add_trade(result="unknown", source=source)
            elif etype.startswith("WATCHDOG"):
                sev = payload.get("severity") or payload.get("kind_severity")
                kind = payload.get("kind") or payload.get("reason_code")
                self.add_watchdog_alert(sev, kind)
            elif "BRACKET" in etype:
                sev = payload.get("severity")
                kind = payload.get("kind") or payload.get("reason_code")
                self.add_bracket_violation(sev, kind)
            elif etype.startswith("TRAILING"):
                self.add_trailing_signal(payload.get("kind") or payload.get("reason_code"))

    # ------------------
    # Output
    # ------------------
    def to_dict(self) -> Dict[str, List[Dict[str, object]]]:
        """Return metrics as a list-of-dicts per metric name."""
        return {
            "execpos_trades_total": [
                {"labels": {"result": r, "source": s}, "value": v}
                for (r, s), v in sorted(self.trades_total.items())
            ],
            "execpos_bracket_violations_total": [
                {"labels": {"severity": sev, "kind": kind}, "value": v}
                for (sev, kind), v in sorted(self.bracket_violations_total.items())
            ],
            "execpos_watchdog_alerts_total": [
                {"labels": {"severity": sev, "kind": kind}, "value": v}
                for (sev, kind), v in sorted(self.watchdog_alerts_total.items())
            ],
            "execpos_trailing_signals_total": [
                {"labels": {"kind": kind}, "value": v}
                for kind, v in sorted(self.trailing_signals_total.items())
            ],
        }

    def to_prometheus_text(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        lines: List[str] = []
        for (r, s), v in sorted(self.trades_total.items()):
            lines.append(f'execpos_trades_total{{result="{r}",source="{s}"}} {v}')
        for (sev, kind), v in sorted(self.bracket_violations_total.items()):
            lines.append(f'execpos_bracket_violations_total{{severity="{sev}",kind="{kind}"}} {v}')
        for (sev, kind), v in sorted(self.watchdog_alerts_total.items()):
            lines.append(f'execpos_watchdog_alerts_total{{severity="{sev}",kind="{kind}"}} {v}')
        for kind, v in sorted(self.trailing_signals_total.items()):
            lines.append(f'execpos_trailing_signals_total{{kind="{kind}"}} {v}')
        return "\n".join(lines)


def summarize_trace_metrics(trace: Any) -> ExecPosMetricsAggregator:
    """
    Build metrics from a TradeTrace-like object (with .events, optional .exit_info).
    """
    agg = ExecPosMetricsAggregator()

    # Derive trade result from exit_info pnl when available
    exit_info = getattr(trace, "exit_info", None) or {}
    pnl = exit_info.get("pnl")
    if pnl is not None:
        res = "flat"
        if pnl > 0:
            res = "win"
        elif pnl < 0:
            res = "loss"
        agg.add_trade(result=res, source="trace")

    # Fall back to counting EXEC_TRADE events
    events = getattr(trace, "events", []) or []
    agg.consume_trace_events(events)
    return agg
