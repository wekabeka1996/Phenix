"""
Daily Loss / Drawdown Gate (A3).

Blocks new CMD:OPEN if daily loss limit or intraday-drawdown from equity_open is exceeded.
Fail-closed: without data — block.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
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
        # BACKTEST-SAFETY: In backtest mode we intentionally do NOT persist daily gate state.
        # Persisted state is keyed by *wall-clock* date and will leak across runs, causing
        # false drawdown breaches (e.g., reference_equity from a prior run).
        try:
            trading_mode = str(getattr(cfg, "trading_mode", "")).strip().lower()
        except Exception:
            trading_mode = ""
        self._persist_state = trading_mode != "backtest"

        self._state_path = Path(os.environ.get("AURORA_RISK_GATE_STATE_PATH", "data/risk_gate_state.json"))
        if self._persist_state:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_gate_open: Optional[bool] = None

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
        if self._persist_state:
            self._load_state()
        else:
            # Backtest: always start from a clean slate (in-memory only).
            self.reset()

    @property
    def reference_equity(self):
        return self._equity_open

    @reference_equity.setter
    def reference_equity(self, value: Any) -> None:
        self._equity_open = _d(value)
        self._save_state()

    @property
    def is_gate_open(self) -> bool:
        if self._last_gate_open is None:
            allowed, _ = self.can_open()
            self._last_gate_open = bool(allowed)
        return bool(self._last_gate_open)

    def reset(self) -> None:
        """Reset state to an uninitialized fail-closed baseline (new day or missing state)."""
        z = _d("0")
        self._equity_open = z
        self._equity_now = z
        self._last_reset_date = None
        self._last_gate_open = None

    def _active_trading_date(self, now: Optional[datetime] = None) -> date:
        """Compute the active 'trading day' date based on reset_time_utc."""
        now = now or _now_utc()
        is_past_reset = (now.hour > self.cfg.reset_h) or (
            now.hour == self.cfg.reset_h and now.minute >= self.cfg.reset_m
        )
        if is_past_reset:
            return now.date()
        # Before reset time, trading day is considered the previous date.
        return (now.date() - timedelta(days=1))

    def _save_state(self) -> None:
        if not getattr(self, "_persist_state", True):
            return
        payload = {
            "reference_equity": _fmt_usd(self._equity_open),
            "last_reset_date": self._last_reset_date.isoformat() if self._last_reset_date else None,
            "is_gate_open": bool(self.is_gate_open),
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception:
            # Fail-safe: persistence errors must never crash trading loop.
            if self.log:
                self.log.exception("[DailyGate] Failed to save state")

    def _load_state(self) -> None:
        if not getattr(self, "_persist_state", True):
            self.reset()
            return
        now = _now_utc()
        active_date = self._active_trading_date(now=now)
        try:
            if not self._state_path.exists():
                self.reset()
                return
            raw = self._state_path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
            last_reset = data.get("last_reset_date")
            if not last_reset:
                self.reset()
                return
            stored_date = date.fromisoformat(str(last_reset))
            if stored_date != active_date:
                self.reset()
                return
            self._equity_open = _d(data.get("reference_equity"))
            self._last_reset_date = stored_date
            self._last_gate_open = bool(data.get("is_gate_open", True))
        except Exception:
            # Corrupt state → fail-closed reset (and drop the bad file)
            try:
                self._state_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.reset()

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
            self._save_state()

    def on_portfolio(self, pld: Dict[str, Any], now: Optional[datetime] = None) -> None:
        """Update current equity from portfolio state."""
        # Prefer total equity (includes unrealized PnL) when available.
        equity_cross = _d(pld.get("equity_cross_usdt"))
        equity_free = _d(pld.get("equity_free_usdt"))
        self._equity_now = equity_cross if equity_cross > 0 else equity_free
        # Initialize reference equity ONLY on first run (or after explicit reset).
        # Do NOT blindly re-anchor if state was loaded from disk (amnesia fix).
        if self._equity_open <= 0 and self._equity_now > 0 and self._last_reset_date is None:
            self._equity_open = self._equity_now
            self._save_state()
        self._maybe_reset(now=now)
        self._last_gate_open = None  # force recompute on next access

    def update_portfolio(self, pld: Dict[str, Any], now: Optional[datetime] = None) -> None:
        """Alias for on_portfolio (for legacy naming)."""
        self.on_portfolio(pld, now=now)

    def can_open(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if new positions can be opened based on daily risk limits.

        Fail-closed: without correct equity — block.
        """
        if not getattr(self, "_enabled", True):
            self._last_gate_open = True
            return True, {"why": "daily_gate_disabled"}

        # Fail-closed: without correct equity — block
        if self._equity_open <= 0 or self._equity_now <= 0:
            self._last_gate_open = False
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
            self._last_gate_open = False
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
        self._last_gate_open = True
        return True, {
            "equity_open_usd": _fmt_usd(self._equity_open),
            "equity_now_usd": _fmt_usd(self._equity_now),
            "drawdown_pct": _fmt_pct(dd),
            "why": "daily_risk_checks_passed",
        }
