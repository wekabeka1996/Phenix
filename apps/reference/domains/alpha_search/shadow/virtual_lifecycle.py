"""
Shadow Virtual Lifecycle Engine
=================================

Simulates per-scenario virtual trade lifecycles from shadow signals + price data.

AUTHORITY BOUNDARY:
  This engine NEVER emits real ORDER_INTENT, CMD:OPEN, CMD:CLOSE.
  It NEVER interacts with real position FSM, real risk gates, real exchange.
  All positions are virtual / shadow only.

Virtual lifecycle per signal:
  signal → virtual_entry → track_price → virtual_exit → virtual_pnl
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Exit reason
# ---------------------------------------------------------------------------

class VirtualExitReason(str, Enum):
    HORIZON_EXPIRED = "HORIZON_EXPIRED"
    FIXED_TP = "FIXED_TP"
    FIXED_SL = "FIXED_SL"
    TRAILING_GIVEBACK = "TRAILING_GIVEBACK"
    MICROSTRUCTURE_REVERSAL = "MICROSTRUCTURE_REVERSAL"
    NO_EXIT_DATA = "NO_EXIT_DATA"


# ---------------------------------------------------------------------------
# Virtual trade lifecycle
# ---------------------------------------------------------------------------

@dataclass
class VirtualLifecycle:
    """Complete shadow virtual trade lifecycle record."""

    # Identity
    scenario_id: str
    scenario_version: str
    symbol: str

    # Signal
    side: str
    signal_ts: int
    signal_price: float

    # Entry
    virtual_entry_price: float
    virtual_fee_bps: float
    virtual_slippage_bps: float
    virtual_entry_cost_bps: float

    # Exit
    virtual_exit_ts: Optional[int]
    virtual_exit_price: Optional[float]
    exit_reason: VirtualExitReason

    # PnL
    virtual_pnl_bps: Optional[float]
    virtual_pnl_usdt: Optional[float]

    # Excursion
    max_favorable_excursion_bps: float = 0.0
    max_adverse_excursion_bps: float = 0.0
    time_to_mfe_bars: Optional[int] = None
    time_to_mae_bars: Optional[int] = None

    # Context
    regime_at_entry: str = "UNKNOWN"
    regime_at_exit: str = "UNKNOWN"
    bars_held: int = 0

    # Authority boundary
    shadow_only: bool = field(default=True, init=False)
    authority_applied: bool = field(default=False, init=False)
    no_effect: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "shadow_only", True)
        object.__setattr__(self, "authority_applied", False)
        object.__setattr__(self, "no_effect", True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "symbol": self.symbol,
            "side": self.side,
            "signal_ts": self.signal_ts,
            "signal_price": self.signal_price,
            "virtual_entry_price": self.virtual_entry_price,
            "virtual_fee_bps": self.virtual_fee_bps,
            "virtual_slippage_bps": self.virtual_slippage_bps,
            "virtual_entry_cost_bps": self.virtual_entry_cost_bps,
            "virtual_exit_ts": self.virtual_exit_ts,
            "virtual_exit_price": self.virtual_exit_price,
            "exit_reason": self.exit_reason.value,
            "virtual_pnl_bps": self.virtual_pnl_bps,
            "virtual_pnl_usdt": self.virtual_pnl_usdt,
            "max_favorable_excursion_bps": self.max_favorable_excursion_bps,
            "max_adverse_excursion_bps": self.max_adverse_excursion_bps,
            "time_to_mfe_bars": self.time_to_mfe_bars,
            "time_to_mae_bars": self.time_to_mae_bars,
            "regime_at_entry": self.regime_at_entry,
            "regime_at_exit": self.regime_at_exit,
            "bars_held": self.bars_held,
            "shadow_only": True,
            "authority_applied": False,
            "no_effect": True,
        }


# ---------------------------------------------------------------------------
# Price bar
# ---------------------------------------------------------------------------

@dataclass
class PriceBar:
    ts: int
    close: float
    high: Optional[float] = None
    low: Optional[float] = None
    regime: str = "UNKNOWN"


# ---------------------------------------------------------------------------
# Lifecycle engine
# ---------------------------------------------------------------------------

class VirtualLifecycleEngine:
    """
    Simulates shadow virtual trade lifecycles.

    Inputs:
      - Shadow signal (side, price, ts)
      - Future price bars
      - Exit config (model, tp_bps, sl_bps, max_bars)
      - Fee + slippage models

    Output:
      VirtualLifecycle with pnl, excursion, exit reason.

    NEVER emits real events.
    """

    # Fee models in bps
    FEE_MODELS = {
        "taker_10bps": 10.0,
        "taker_7bps": 7.0,
        "maker_5bps": 5.0,
        "zero_fee": 0.0,
    }

    # Slippage models in bps
    SLIPPAGE_MODELS = {
        "zero": 0.0,
        "spread_half": 2.5,
        "spread_full": 5.0,
        "market_impact_05bps": 0.5,
    }

    def simulate(
        self,
        *,
        scenario_id: str,
        scenario_version: str,
        symbol: str,
        side: str,
        signal_ts: int,
        signal_price: float,
        future_bars: List[PriceBar],
        exit_model: str = "horizon_3_bar",
        tp_bps: Optional[float] = None,
        sl_bps: Optional[float] = None,
        max_hold_bars: int = 6,
        trail_activation_bps: Optional[float] = None,
        trail_distance_bps: Optional[float] = None,
        fee_model: str = "taker_10bps",
        slippage_model: str = "spread_half",
        regime_at_entry: str = "UNKNOWN",
        notional_usdt: float = 1000.0,
    ) -> VirtualLifecycle:
        """
        Simulate a complete virtual lifecycle for one shadow signal.

        Args:
            future_bars: Price bars AFTER signal_ts, in chronological order.
            exit_model: One of horizon_1_bar, horizon_3_bar, horizon_6_bar,
                        fixed_tp_sl, trailing_giveback, microstructure_reversal_exit.
        """
        fee_bps = self.FEE_MODELS.get(fee_model, 10.0)
        slip_bps = self.SLIPPAGE_MODELS.get(slippage_model, 2.5)
        entry_cost_bps = fee_bps + slip_bps

        # Entry price = signal price + slippage
        if side == "BUY":
            entry_price = signal_price * (1 + slip_bps / 10000)
        else:
            entry_price = signal_price * (1 - slip_bps / 10000)

        if not future_bars:
            return VirtualLifecycle(
                scenario_id=scenario_id,
                scenario_version=scenario_version,
                symbol=symbol,
                side=side,
                signal_ts=signal_ts,
                signal_price=signal_price,
                virtual_entry_price=entry_price,
                virtual_fee_bps=fee_bps,
                virtual_slippage_bps=slip_bps,
                virtual_entry_cost_bps=entry_cost_bps,
                virtual_exit_ts=None,
                virtual_exit_price=None,
                exit_reason=VirtualExitReason.NO_EXIT_DATA,
                virtual_pnl_bps=None,
                virtual_pnl_usdt=None,
                regime_at_entry=regime_at_entry,
            )

        # Determine horizon
        horizon_map = {
            "horizon_1_bar": 1,
            "horizon_3_bar": 3,
            "horizon_6_bar": 6,
        }
        horizon_bars = horizon_map.get(exit_model, max_hold_bars)
        bars = future_bars[:max(horizon_bars, max_hold_bars)]

        mfe_bps = 0.0
        mae_bps = 0.0
        mfe_bar = None
        mae_bar = None
        peak_bps_for_trail = 0.0
        exit_bar_idx = len(bars) - 1
        exit_reason = VirtualExitReason.HORIZON_EXPIRED

        for i, bar in enumerate(bars):
            close = bar.close
            # Price move in bps
            if side == "BUY":
                move_bps = (close - entry_price) / entry_price * 10000
            else:
                move_bps = (entry_price - close) / entry_price * 10000

            # Update MFE/MAE
            if move_bps > mfe_bps:
                mfe_bps = move_bps
                mfe_bar = i + 1

            if move_bps < mae_bps:
                mae_bps = move_bps
                mae_bar = i + 1

            # Fixed TP/SL exits
            if exit_model in ("fixed_tp_sl", "trailing_giveback"):
                if tp_bps and move_bps >= tp_bps:
                    exit_bar_idx = i
                    exit_reason = VirtualExitReason.FIXED_TP
                    break
                if sl_bps and move_bps <= -sl_bps:
                    exit_bar_idx = i
                    exit_reason = VirtualExitReason.FIXED_SL
                    break

            # Trailing giveback
            if exit_model == "trailing_giveback" and trail_activation_bps and trail_distance_bps:
                if move_bps >= trail_activation_bps:
                    peak_bps_for_trail = max(peak_bps_for_trail, move_bps)
                    if peak_bps_for_trail - move_bps >= trail_distance_bps:
                        exit_bar_idx = i
                        exit_reason = VirtualExitReason.TRAILING_GIVEBACK
                        break

            # Horizon exit
            if exit_model in ("horizon_1_bar", "horizon_3_bar", "horizon_6_bar"):
                if i + 1 >= horizon_bars:
                    exit_bar_idx = i
                    exit_reason = VirtualExitReason.HORIZON_EXPIRED
                    break

        exit_bar = bars[min(exit_bar_idx, len(bars) - 1)]
        exit_price = exit_bar.close
        regime_exit = exit_bar.regime

        # Gross PnL in bps
        if side == "BUY":
            gross_bps = (exit_price - entry_price) / entry_price * 10000
        else:
            gross_bps = (entry_price - exit_price) / entry_price * 10000

        net_bps = gross_bps - entry_cost_bps - fee_bps  # round-trip fees
        pnl_usdt = net_bps / 10000 * notional_usdt if net_bps is not None else None

        return VirtualLifecycle(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            symbol=symbol,
            side=side,
            signal_ts=signal_ts,
            signal_price=signal_price,
            virtual_entry_price=entry_price,
            virtual_fee_bps=fee_bps,
            virtual_slippage_bps=slip_bps,
            virtual_entry_cost_bps=entry_cost_bps,
            virtual_exit_ts=exit_bar.ts,
            virtual_exit_price=exit_price,
            exit_reason=exit_reason,
            virtual_pnl_bps=round(net_bps, 4),
            virtual_pnl_usdt=round(pnl_usdt, 4) if pnl_usdt is not None else None,
            max_favorable_excursion_bps=round(mfe_bps, 4),
            max_adverse_excursion_bps=round(mae_bps, 4),
            time_to_mfe_bars=mfe_bar,
            time_to_mae_bars=mae_bar,
            regime_at_entry=regime_at_entry,
            regime_at_exit=regime_exit,
            bars_held=exit_bar_idx + 1,
        )

    def simulate_batch(
        self,
        signals: List[Dict[str, Any]],
        price_bars_by_symbol: Dict[str, List[PriceBar]],
        scenario_id: str,
        scenario_version: str,
        exit_model: str = "horizon_3_bar",
        tp_bps: Optional[float] = None,
        sl_bps: Optional[float] = None,
        max_hold_bars: int = 6,
        fee_model: str = "taker_10bps",
        slippage_model: str = "spread_half",
        notional_usdt: float = 1000.0,
    ) -> List[VirtualLifecycle]:
        """Simulate virtual lifecycles for a batch of shadow signals."""
        results = []
        for sig in signals:
            symbol = sig.get("symbol", "")
            side = sig.get("side", "NEUTRAL")
            if side == "NEUTRAL":
                continue

            ts = sig.get("ts_ms", 0)
            price = sig.get("signal_price", 0.0)
            regime = sig.get("regime", "UNKNOWN")

            all_bars = price_bars_by_symbol.get(symbol, [])
            future_bars = [b for b in all_bars if b.ts > ts]

            lc = self.simulate(
                scenario_id=scenario_id,
                scenario_version=scenario_version,
                symbol=symbol,
                side=side,
                signal_ts=ts,
                signal_price=price,
                future_bars=future_bars,
                exit_model=exit_model,
                tp_bps=tp_bps,
                sl_bps=sl_bps,
                max_hold_bars=max_hold_bars,
                fee_model=fee_model,
                slippage_model=slippage_model,
                regime_at_entry=regime,
                notional_usdt=notional_usdt,
            )
            results.append(lc)

        return results
