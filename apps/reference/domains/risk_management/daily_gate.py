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

def _d(x: Any) -> float:
    """Safe decimal conversion with fallback to 0."""
    from decimal import Decimal as D, InvalidOperation
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

        daily_cfg = risk_cfg.get("daily", {}) if isinstance(risk_cfg, dict) else {}
        
        # Extract values from dict (risk.daily is a dict)
        max_loss = daily_cfg.get("max_realized_loss_usd")
        max_dd = daily_cfg.get("max_drawdown_pct")
        reset_time = daily_cfg.get("reset_time_utc")
        
        # Fail-closed validation
        if max_loss is None or max_dd is None or reset_time is None:
            raise ConfigContractError(
                path="risk.daily",
                why="Daily gate config incomplete (max_realized_loss_usd, max_drawdown_pct, reset_time_utc required)"
            )

        reset_time_str = str(reset_time)
        reset_parts = reset_time_str.split(":")

        self.cfg = DailyConfig(
            max_realized_loss_usd=_d(max_loss),
            max_drawdown_pct=_d(max_dd),
            reset_h=int(reset_parts[0] if len(reset_parts) > 0 else "0"),
            reset_m=int(reset_parts[1] if len(reset_parts) > 1 else "0"),
        )
        self._equity_open = 0.0
        self._equity_now = 0.0
        self._realized_pnl = 0.0
        self._last_reset_date: Optional[date] = None  # YYYY-MM-DD

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
        # Initialize equity_open on first portfolio update if not set
        if self._equity_open == 0.0 and self._equity_now > 0:
            self._equity_open = self._equity_now
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

        # Check drawdown limit first
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

        # Check realized loss limit
        if (-self._realized_pnl) >= self.cfg.max_realized_loss_usd:
            return False, {
                "reason": "DAILY_RISK_LIMIT",
                "detail": "MAX_REALIZED_LOSS",
                "realized_pnl_usd": _fmt_usd(self._realized_pnl),
                "limit_usd": _fmt_usd(self.cfg.max_realized_loss_usd),
                "why": "daily_loss_limit_exceeded",
            }

        # All checks passed
        return True, {
            "equity_open_usd": _fmt_usd(self._equity_open),
            "equity_now_usd": _fmt_usd(self._equity_now),
            "realized_pnl_usd": _fmt_usd(self._realized_pnl),
            "drawdown_pct": _fmt_pct(dd),
            "why": "daily_risk_checks_passed",
        }
