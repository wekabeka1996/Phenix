"""
Daily Loss / Drawdown Gate (A3).

Blocks new CMD:OPEN if daily loss limit or intraday-drawdown from equity_open is exceeded.
Fail-closed: without data — block.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, Tuple


def _d(x: Any) -> float:
    """Safe decimal conversion with fallback to 0."""
    from decimal import Decimal as D

    try:
        return float(D(str(x)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _fmt_pct(val: float) -> str:
    """Format percentage to 1 decimal place."""
    return f"{val:.1f}"


def _fmt_usd(val: float) -> str:
    """Format USD value, removing .0 for whole numbers."""
    return str(int(val)) if val == int(val) else str(val)


def _now_utc() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class DailyConfig:
    """Configuration for daily risk limits."""

    max_realized_loss_usd: float
    max_drawdown_pct: float
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
        rcfg = (cfg.get("risk") or {}).get("daily") or {}
        self.cfg = DailyConfig(
            max_realized_loss_usd=_d(rcfg.get("max_realized_loss_usd", 250)),
            max_drawdown_pct=_d(rcfg.get("max_drawdown_pct", 8)),
            reset_h=int(
                str(rcfg.get("reset_time_utc", "00:00")).split(":")[0]),
            reset_m=int(
                str(rcfg.get("reset_time_utc", "00:00")).split(":")[1]),
        )
        self._equity_open = 0.0
        self._equity_now = 0.0
        self._realized_pnl = 0.0
        self._last_reset_date = None  # YYYY-MM-DD

    def _maybe_reset(self, now: Optional[datetime] = None) -> None:
        """Reset daily metrics if it's time for daily reset."""
        now = now or _now_utc()
        reset_date = now.date()
        if (
            self._last_reset_date != reset_date
            and now.hour >= self.cfg.reset_h
            and now.minute >= self.cfg.reset_m
        ):
            # Open new trading day
            self._equity_open = self._equity_now  # Fix start equity
            self._realized_pnl = 0.0
            self._last_reset_date = reset_date
            if self.log:
                self.log.info(
                    f"[DailyGate] Daily reset: equity_open={self._equity_open}, date={reset_date}"
                )

    def on_portfolio(self, pld: Dict[str, Any]) -> None:
        """Update current equity from portfolio state."""
        self._equity_now = _d(pld.get("equity_free_usdt"))
        self._maybe_reset()

    def on_order_filled(self, pld: Dict[str, Any]) -> None:
        """
        Accumulate realized PnL from filled orders.

        Expects pld: {"realized_pnl_usd": "..."} or calculation from cumulative quotes.
        """
        realized = _d(pld.get("realized_pnl_usd"))
        self._realized_pnl += realized
        if self.log:
            self.log.debug(
                f"[DailyGate] Accumulated realized PnL: {realized}, total: {self._realized_pnl}"
            )

    def can_open(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if new positions can be opened based on daily risk limits.

        Fail-closed: without correct equity — block.
        """
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
        dd = 0.0
        if self._equity_open > 0:
            dd = (1.0 - (self._equity_now / self._equity_open)) * 100.0

        # Check realized loss limit
        if (-self._realized_pnl) >= self.cfg.max_realized_loss_usd:
            return False, {
                "reason": "DAILY_RISK_LIMIT",
                "detail": "MAX_REALIZED_LOSS",
                "realized_pnl_usd": _fmt_usd(self._realized_pnl),
                "limit_usd": _fmt_usd(self.cfg.max_realized_loss_usd),
                "why": "daily_loss_limit_exceeded",
            }

        # Check drawdown limit
        if dd >= self.cfg.max_drawdown_pct:
            return False, {
                "reason": "DAILY_RISK_LIMIT",
                "detail": "MAX_DRAWDOWN",
                "drawdown_pct": _fmt_pct(dd),
                "limit_pct": _fmt_usd(self.cfg.max_drawdown_pct),
                "equity_open_usd": _fmt_usd(self._equity_open),
                "equity_now_usd": _fmt_usd(self._equity_now),
                "why": "daily_drawdown_limit_exceeded",
            }

        # All checks passed
        return True, {
            "equity_open_usd": _fmt_usd(self._equity_open),
            "equity_now_usd": _fmt_usd(self._equity_now),
            "realized_pnl_usd": _fmt_usd(self._realized_pnl),
            "drawdown_pct": _fmt_pct(dd),
            "why": "daily_risk_checks_passed",
        }
