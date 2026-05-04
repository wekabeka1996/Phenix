import logging
import json
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from pydantic import ValidationError

from .config_models import ShadowSimulatorConfig
from .contracts import ShadowEntryPlan
from .simulation_models import ShadowSimulationResult, SimulationOutcome

LOG = logging.getLogger(__name__)


class ShadowPlanSimulator:
    """
    Deterministic forensic simulator for replaying ShadowEntryPlans
    against historical OHLC data from data/recorder/.
    """

    def __init__(self, config: ShadowSimulatorConfig):
        self.config = config

    def run_batch(self, plans_file: Path, data_dir: Path) -> List[ShadowSimulationResult]:
        """Runs simulation for all plans in a JSONL file."""
        if not plans_file.exists():
            LOG.error(f"Plans file not found: {plans_file}")
            return []

        results = []
        
        # Group plans by (symbol, tf_sec) to avoid reloading CSVs too many times
        # But for simplicity in v0, we just load as needed.
        # Recorder files are organized by date: data/recorder/YYYY-MM-DD/SYMBOL_TF.csv
        # Shadow plans also have date in filename or we extract from ts_ms.
        
        with open(plans_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    raw = json.loads(line)
                    plan = ShadowEntryPlan.model_validate(raw)
                    
                    if not plan.actionable or plan.suppressed:
                        continue
                        
                    # Extract date from ts_ms (UTC)
                    ts = pd.to_datetime(plan.ts_ms, unit="ms", utc=True)
                    date_str = ts.strftime("%Y-%m-%d")
                    
                    bars = self._load_bars(data_dir, date_str, plan.symbol, plan.tf_sec)
                    if bars.empty:
                        LOG.warning(f"No market data for {plan.symbol} on {date_str}")
                        continue
                        
                    result = self.simulate_plan(plan, bars)
                    results.append(result)
                    
                except (json.JSONDecodeError, ValidationError) as e:
                    LOG.error(f"Failed to parse plan line: {e}")
                except Exception as e:
                    LOG.error(f"Unexpected error simulating plan: {e}")

        return results

    def _load_bars(self, data_dir: Path, date: str, symbol: str, tf_sec: int) -> pd.DataFrame:
        """Loads OHLC bars for a specific symbol/tf/date."""
        csv_path = data_dir / date / f"{symbol}_{tf_sec}.csv"
        if not csv_path.exists():
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(csv_path, on_bad_lines='skip')
            if "timestamp" not in df.columns:
                LOG.error(f"CSV missing 'timestamp' column: {csv_path}")
                return pd.DataFrame()
                
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    
            df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
                    
            return df.sort_values("timestamp")
        except Exception as e:
            LOG.error(f"Error reading CSV {csv_path}: {e}")
            return pd.DataFrame()

    def simulate_plan(self, plan: ShadowEntryPlan, bars: pd.DataFrame) -> ShadowSimulationResult:
        """Replays one plan against bars."""
        # Find the signal bar index (where signal was emitted)
        # The signal bar is the one where close_ts <= plan.ts_ms
        # Actually, ts_ms is the close timestamp of the signal bar.
        
        signal_bar_idx_series = bars.index[bars["timestamp"] == plan.ts_ms]
        if signal_bar_idx_series.empty:
            # Maybe it's a sub-bar signal or slightly off? Find first bar at or after.
            signal_bar_idx_series = bars.index[bars["timestamp"] >= plan.ts_ms]
            
        if signal_bar_idx_series.empty:
            return self._error_result(plan, "Signal bar not found in data")
            
        signal_bar_idx = signal_bar_idx_series[0]
        
        # 1. Detect Fill
        fill_info = self._detect_fill(plan, bars, signal_bar_idx)
        if not fill_info:
            return self._timeout_result(plan, "NOT_FILLED_TIMEOUT")
            
        fill_idx, fill_price, fill_ts = fill_info
        
        # 2. Detect Exit
        exit_info = self._detect_exit(plan, bars, fill_idx, fill_price)
        exit_idx, exit_price, exit_ts, outcome, reason = exit_info
        
        # 3. Calculate PnL
        pnl_stats = self._calculate_pnl(plan, fill_price, exit_price, outcome)
        
        return ShadowSimulationResult(
            plan_id=plan.plan_id,
            cycle_key=plan.cycle_key or "N/A",
            symbol=plan.symbol,
            ts_ms=plan.ts_ms,
            entry_side=plan.entry_side,
            confidence_tier=plan.confidence_tier,
            limit_price=plan.limit_price,
            tp_price=plan.tp_price,
            sl_price=plan.sl_price,
            outcome=outcome,
            outcome_reason=reason,
            fill_ts_ms=fill_ts,
            fill_price=fill_price,
            fill_bar_idx=int(fill_idx),
            exit_ts_ms=exit_ts,
            exit_price=exit_price,
            exit_bar_idx=int(exit_idx) if exit_idx is not None else None,
            duration_bars=int(exit_idx - fill_idx) if exit_idx is not None else None,
            **pnl_stats
        )

    def _detect_fill(self, plan: ShadowEntryPlan, bars: pd.DataFrame, start_idx: int) -> Optional[Tuple[int, float, int]]:
        """
        Finds the first bar where the LIMIT price is hit.
        Checks from start_idx up to start_idx + max_bars_after_signal.
        """
        limit = plan.limit_price
        side = plan.entry_side
        
        end_idx = min(len(bars), start_idx + self.config.max_bars_after_signal + 1)
        
        for i in range(start_idx, end_idx):
            bar = bars.iloc[i]
            low, high = bar["low"], bar["high"]
            
            if side == "BUY":
                if low <= limit:
                    # Filled at limit price (assuming liquidity)
                    return i, limit, int(bar["timestamp"])
            elif side == "SELL":
                if high >= limit:
                    return i, limit, int(bar["timestamp"])
                    
        return None

    def _detect_exit(self, plan: ShadowEntryPlan, bars: pd.DataFrame, fill_idx: int, fill_price: float) -> Tuple[Optional[int], Optional[float], Optional[int], SimulationOutcome, str]:
        """
        Detects TP, SL or Timeout after fill.
        """
        tp = plan.tp_price
        sl = plan.sl_price
        side = plan.entry_side
        
        # Search from fill_idx onwards
        # In the fill bar itself, we check if TP/SL were hit AFTER fill.
        # Since we don't have ticks, we apply the ambiguity policy if both are hit in any bar.
        
        end_idx = min(len(bars), fill_idx + self.config.max_bars_after_signal + 1)
        
        for i in range(fill_idx, end_idx):
            bar = bars.iloc[i]
            low, high = bar["low"], bar["high"]
            
            tp_hit = False
            sl_hit = False
            
            if side == "BUY":
                if high >= tp: tp_hit = True
                if low <= sl: sl_hit = True
            else: # SELL
                if low <= tp: tp_hit = True
                if high >= sl: sl_hit = True
                
            if tp_hit and sl_hit:
                policy = self.config.intrabar_ambiguity_policy
                if policy == "mark_ambiguous":
                    return i, None, int(bar["timestamp"]), "AMBIGUOUS_INTRABAR", f"TP and SL hit in bar {i}"
                elif policy == "prioritize_sl":
                    return i, sl, int(bar["timestamp"]), "FILLED_SL", f"SL hit in bar {i} (prioritized)"
                elif policy == "prioritize_tp":
                    return i, tp, int(bar["timestamp"]), "FILLED_TP", f"TP hit in bar {i} (prioritized)"
                    
            if tp_hit:
                return i, tp, int(bar["timestamp"]), "FILLED_TP", f"TP hit in bar {i}"
            if sl_hit:
                return i, sl, int(bar["timestamp"]), "FILLED_SL", f"SL hit in bar {i}"
                
        # If we reach here, it's a timeout
        last_bar = bars.iloc[end_idx - 1]
        return end_idx - 1, last_bar["close"], int(last_bar["timestamp"]), "FILLED_TIMEOUT", "Reached max_bars_after_signal"

    def _calculate_pnl(self, plan: ShadowEntryPlan, fill_price: float, exit_price: Optional[float], outcome: SimulationOutcome) -> dict:
        """Calculates gross/net PnL %."""
        if outcome == "AMBIGUOUS_INTRABAR" or exit_price is None:
            return {"gross_pnl_pct": 0.0, "net_pnl_pct": 0.0, "fees_paid_pct": 0.0}
            
        side_mult = 1 if plan.entry_side == "BUY" else -1
        
        # Slippage: apply to entry and exit (if exit is not LIMIT)
        # For simplicity, we assume 1.0 bps slippage per trade
        slippage = self.config.slippage_bps / 10000.0
        fees = self.config.fees_bps / 10000.0
        
        # Realized gross PnL
        gross_pnl = (exit_price - fill_price) / fill_price * side_mult
        
        # Net PnL = Gross - (entry_fees + exit_fees) - (entry_slippage + exit_slippage)
        # Note: In a limit order, slippage on entry might be 0, but we stay conservative.
        total_costs = (fees * 2) + (slippage * 2)
        net_pnl = gross_pnl - total_costs
        
        return {
            "gross_pnl_pct": round(gross_pnl * 100, 4),
            "net_pnl_pct": round(net_pnl * 100, 4),
            "fees_paid_pct": round(total_costs * 100, 4)
        }

    def _error_result(self, plan: ShadowEntryPlan, reason: str) -> ShadowSimulationResult:
        return ShadowSimulationResult(
            plan_id=plan.plan_id, cycle_key=plan.cycle_key or "N/A", symbol=plan.symbol,
            ts_ms=plan.ts_ms, entry_side=plan.entry_side, confidence_tier=plan.confidence_tier,
            limit_price=plan.limit_price, tp_price=plan.tp_price, sl_price=plan.sl_price,
            outcome="ERROR", outcome_reason=reason
        )

    def _timeout_result(self, plan: ShadowEntryPlan, outcome: SimulationOutcome) -> ShadowSimulationResult:
        return ShadowSimulationResult(
            plan_id=plan.plan_id, cycle_key=plan.cycle_key or "N/A", symbol=plan.symbol,
            ts_ms=plan.ts_ms, entry_side=plan.entry_side, confidence_tier=plan.confidence_tier,
            limit_price=plan.limit_price, tp_price=plan.tp_price, sl_price=plan.sl_price,
            outcome=outcome
        )
