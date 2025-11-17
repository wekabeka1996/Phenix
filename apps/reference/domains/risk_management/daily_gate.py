"""
Daily Loss / Drawdown Gate (A3).

Blocks new CMD:OPEN if daily loss limit or intraday-drawdown from equity_open is exceeded.
Fail-closed: without data — block.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, Tuple


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


def _as_dict(value: Any) -> Dict[str, Any]:
    """Best-effort conversion of config fragments to dict."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:  # pragma: no cover - defensive
            pass
    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    return {}


def _normalize_percent(value: Any) -> Optional[float]:
    """Normalize config percent values to 0-100 scale."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric * 100.0 if 0 <= numeric <= 1.0 else numeric


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

        # Safe extraction of risk config from dict or Pydantic object
        raw_risk_cfg = cfg.get("risk", {}) if isinstance(
            cfg, dict) else getattr(cfg, "risk", {})
        risk_cfg = _as_dict(raw_risk_cfg)
        daily_limits_cfg = _as_dict(risk_cfg.get("daily_limits"))
        daily_cfg = _as_dict(risk_cfg.get("daily"))

        max_loss_usd = None
        for candidate in (
            daily_limits_cfg.get("max_loss_usd"),
            daily_cfg.get("max_realized_loss_usd"),
            risk_cfg.get("max_realized_loss_usd"),
        ):
            if candidate is None:
                continue
            value = _d(candidate)
            if value > 0:
                max_loss_usd = value
                break
        if not max_loss_usd:
            max_loss_usd = 250.0

        max_drawdown_pct = None
        for candidate in (
            daily_limits_cfg.get("max_drawdown_pct"),
            risk_cfg.get("max_daily_drawdown_limit"),
            daily_cfg.get("max_drawdown_pct"),
        ):
            normalized = _normalize_percent(candidate)
            if normalized is not None:
                max_drawdown_pct = normalized
                break
        if max_drawdown_pct is None:
            max_drawdown_pct = 8.0

        reset_time = (
            daily_cfg.get("reset_time_utc")
            or daily_limits_cfg.get("reset_time_utc")
            or "00:00"
        )

        reset_time_str = str(reset_time)
        reset_parts = reset_time_str.split(":")

        self.cfg = DailyConfig(
            max_realized_loss_usd=_d(max_loss_usd),
            max_drawdown_pct=_d(max_drawdown_pct),
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
