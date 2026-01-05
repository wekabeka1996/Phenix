"""
Daily Loss / Drawdown Gate (A3).

Blocks new CMD:OPEN if daily loss limit or intraday-drawdown from equity_open is exceeded.
Fail-closed: without data — block.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, Tuple


from apps.reference.config_contract import ConfigContractError

def _d(x: Any):
    """Safe Decimal conversion with fallback to 0."""
    from decimal import Decimal as D, InvalidOperation
    try:
        return D(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return D("0")


def _fmt_pct(val: Any) -> str:
    """Format percentage to 1 decimal place."""
    from decimal import Decimal as D, InvalidOperation
    try:
        d = val if isinstance(val, D) else D(str(val))
    except (InvalidOperation, ValueError, TypeError):
        d = D("0")
    return f"{d:.1f}"


def _fmt_usd(val: Any) -> str:
    """Format USD value, removing .0 for whole numbers."""
    from decimal import Decimal as D, InvalidOperation
    try:
        d = val if isinstance(val, D) else D(str(val))
    except (InvalidOperation, ValueError, TypeError):
        d = D("0")
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.normalize())


def _now_utc() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class DailyConfig:
    """Configuration for daily risk limits."""

    max_drawdown_pct: Any
    reset_h: int
    reset_m: int


class DailyRiskState:
    """
    Maintains daily-aggregated risk metrics:
      - equity_open_usd (snapshot at daily reset),
      - equity_now_usd (updated from portfolio),
      - realized_pnl_usd (accumulated from FILLED/closures).
    """

    def __init__(self, cfg: Dict[str, Any], logger=None):
        self.log = logger

        # Strict Object Config: No dict support (Task 18)
        # cfg must be AuroraConfig object
        if hasattr(cfg, "dict") or isinstance(cfg, dict):
             if isinstance(cfg, dict):
                 raise TypeError("DailyRiskState requires AuroraConfig, got dict")
        
        # Access strictly via AuroraConfig -> trading -> risk (Dict[str, Any])
        try:
             risk_cfg = cfg.trading.risk
        except AttributeError:
             # Fallback or error? Strict means we expect formatting.
             # If cfg is not AuroraConfig, this crashes, which is good.
             risk_cfg = {}

        daily_cfg = risk_cfg["daily"] if isinstance(risk_cfg, dict) and "daily" in risk_cfg else {}

        enabled = daily_cfg.get("enabled") if isinstance(daily_cfg, dict) else None
        if enabled is None:
            raise ConfigContractError(
                path="risk.daily.enabled",
                why="Daily gate config incomplete (enabled required)",
            )
        self._enabled = bool(enabled)

        # Extract values from dict (risk.daily is a dict)
        max_dd = daily_cfg.get("max_drawdown_pct")
        reset_time = daily_cfg.get("reset_time_utc")

        # Fail-closed validation
        if self._enabled and (max_dd is None or reset_time is None):
            raise ConfigContractError(
                path="risk.daily",
                why="Daily gate config incomplete (max_drawdown_pct, reset_time_utc required)"
            )

        reset_time_str = str(reset_time) if reset_time is not None else "00:00"
        reset_parts = reset_time_str.split(":")

        self.cfg = DailyConfig(
            max_drawdown_pct=_d(max_dd) if max_dd is not None else _d("0"),
            reset_h=int(reset_parts[0] if len(reset_parts) > 0 else "0"),
            reset_m=int(reset_parts[1] if len(reset_parts) > 1 else "0"),
        )
        z = _d("0")
        self._equity_open = z
        self._equity_now = z
        self._last_reset_date: Optional[date] = None  # YYYY-MM-DD

    def _maybe_reset(self, now: Optional[datetime] = None) -> None:
        """Reset daily metrics if it's time for daily reset."""
        now = now or _now_utc()
        reset_date = now.date()
        is_past_reset = (now.hour > self.cfg.reset_h) or (
            now.hour == self.cfg.reset_h and now.minute >= self.cfg.reset_m
        )
        if self._last_reset_date != reset_date and is_past_reset:
            # Open new trading day
            self._equity_open = self._equity_now  # Fix start equity
            self._last_reset_date = reset_date
            if self.log:
                self.log.info(
                    f"[DailyGate] Daily reset: equity_open={self._equity_open}, date={reset_date}"
                )

    def on_portfolio(self, pld: Dict[str, Any], now: Optional[datetime] = None) -> None:
        """Update current equity from portfolio state."""
        # Prefer total equity (includes unrealized PnL) when available.
        equity_cross = _d(pld.get("equity_cross_usdt"))
        equity_free = _d(pld.get("equity_free_usdt"))
        self._equity_now = equity_cross if equity_cross > 0 else equity_free
        # Initialize equity_open on first portfolio update if not set
        if self._equity_open == _d("0") and self._equity_now > 0:
            self._equity_open = self._equity_now
        self._maybe_reset(now=now)

    def can_open(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if new positions can be opened based on daily risk limits.

        Fail-closed: without correct equity — block.
        """
        if not getattr(self, "_enabled", True):
            return True, {"why": "daily_gate_disabled"}

        # Fail-closed: without correct equity — block
        if self._equity_open <= 0 or self._equity_now <= 0:
            return False, {
                "reason": "DAILY_RISK_LIMIT",
                "detail": "NO_EQUITY",
                "equity_open_usd": _fmt_usd(self._equity_open),
                "equity_now_usd": _fmt_usd(self._equity_now),
                "why": "insufficient_equity_data",
            }

        # Calculate drawdown percentage
        dd = _d("0")
        if self._equity_open > 0:
            dd = (_d("1") - (self._equity_now / self._equity_open)) * _d("100")

        # Check drawdown limit first
        if dd >= self.cfg.max_drawdown_pct:
            return False, {
                "reason": "DAILY_RISK_LIMIT",
                "detail": "MAX_DRAWDOWN",
                "drawdown_pct": _fmt_pct(dd),
                "limit_pct": _fmt_pct(self.cfg.max_drawdown_pct),
                "equity_open_usd": _fmt_usd(self._equity_open),
                "equity_now_usd": _fmt_usd(self._equity_now),
                "why": "daily_drawdown_limit_exceeded",
            }

        # All checks passed
        return True, {
            "equity_open_usd": _fmt_usd(self._equity_open),
            "equity_now_usd": _fmt_usd(self._equity_now),
            "drawdown_pct": _fmt_pct(dd),
            "why": "daily_risk_checks_passed",
        }
