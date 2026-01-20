#!/usr/bin/env python3
"""
Money Run 2.0 - Final System Simulation
Replicates the 8-trade scenario with FIXED logic.
"""
import sys
import os
import shutil
import tempfile
import asyncio
import threading
import time
import math
import logging
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# External
import polars as pl
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x: x

# Project
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from apps.reference.config_loader import ConfigLoader
from vfoundation.core.fsm_core import FSMCore
from backtest_engine.engine import BacktestEngine
from backtest_engine.mock_broker import MockBroker
from backtest_engine.wrappers import BacktestExecPosFSM

# Domains
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.domains.decision_making.decision_making import DecisionMaking

# Logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s')
LOG = logging.getLogger("MoneyRun")
LOG.setLevel(logging.INFO)

# Force domain logs to INFO/WARNING
logging.getLogger("apps.reference.domains.execution_position").setLevel(logging.INFO)
logging.getLogger("apps.reference.domains.decision_making").setLevel(logging.INFO)
logging.getLogger("apps.reference.domains.feature_engineering").setLevel(logging.WARNING)
logging.getLogger("apps.reference.domains.regime_detector").setLevel(logging.WARNING)

def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()

def _copy_config_to_tmp(*, src: Path) -> Path:
    tmp_root = Path(tempfile.mkdtemp(prefix="aurora_backtest_cfg_"))
    dst = tmp_root / "aurora"
    shutil.copytree(src, dst)
    return dst

def generate_synthetic_data(bars=3000, start_price=27000.0) -> pl.DataFrame:
    """Generate 5m bars with sine wave pattern to trigger Mean Reversion."""
    LOG.info(f"Generating {bars} bars of synthetic data...")
    
    start_ts = datetime(2023, 1, 1, tzinfo=timezone.utc)
    rows = []
    
    # Sine wave parameters
    # Period 40 bars (3.3 hours)
    period = 40
    # Base amplitude 0.2% (triggers FLAT_NORMAL/FLAT_LOW)
    amp = start_price * 0.002
    
    for i in range(bars):
        ts = start_ts + timedelta(minutes=5 * i)
        
        # Sine wave + Noise
        angle = (i / period) * 2 * math.pi
        noise = random.uniform(-start_price*0.0005, start_price*0.0005)
        
        # Varied Regimes
        current_amp = amp
        if i < 500:
            current_amp = amp * 0.4 # FLAT_LOW (0.08%)
        elif i > 2500:
            current_amp = amp * 2.5 # HIGH_VOLATILITY (0.5%)
            
        val = start_price + (math.sin(angle) * current_amp) + noise
        
        # OHLC
        close = val
        # Use previous close as open to avoid gaps
        open_ = rows[-1]["close"] if rows else val
        high = max(open_, close) + abs(noise)
        low = min(open_, close) - abs(noise)
        vol = 1000.0 + random.uniform(0, 500)
        
        # FE Requirements
        best_bid = close - 1.0
        best_ask = close + 1.0
        bid_size = vol / 2
        ask_size = vol / 2
        
        row = {
            "ts": ts,
            "timestamp_ms": int(ts.timestamp() * 1000),
            "symbol": "BTCUSDT",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "price": close, # BacktestEngine/Handler compat
            "volume": vol,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "buy_volume": vol / 2,
            "sell_volume": vol / 2,
            "bid": best_bid, # Alias
            "ask": best_ask, # Alias
        }
        rows.append(row)
        
    return pl.DataFrame(rows)

def calculate_pnl(broker: MockBroker):
    """Calculate PnL from filled orders."""
    LOG.info("Calculating PnL...")
    orders = broker._orders
    filled = [o for o in orders.values() if o.status == "FILLED"]
    
    LOG.info(f"Total Filled Orders: {len(filled)}")
    
    # Simple FIFO matching for PnL
    buys = []
    sells = []
    
    realized_pnl = 0.0
    trades_count = 0
    wins = 0
    losses = 0
    
    # Sort by time
    filled.sort(key=lambda x: x.time)
    
    position = 0.0
    avg_entry = 0.0
    
    for o in filled:
        price = float(o.avg_price or o.price or 0)
        qty = float(o.executed_qty or o.orig_qty or 0)
        
        if o.side == "BUY":
            # If closing SHORT
            if position < -0.000001:
                cover_qty = min(abs(position), qty)
                trade_pnl = (avg_entry - price) * cover_qty
                realized_pnl += trade_pnl
                trades_count += 1
                if trade_pnl > 0: wins += 1
                else: losses += 1
                
                # Reduce short pos
                position += cover_qty
                # If flipped long? Not handled here for simplicity (assuming strict close first)
                if qty > cover_qty:
                    rem_qty = qty - cover_qty
                    avg_entry = price # New long
                    position += rem_qty
            else:
                # Open/Add LONG
                new_cost = (position * avg_entry) + (qty * price)
                position += qty
                avg_entry = new_cost / position if position > 0 else 0
                
        elif o.side == "SELL":
            # If closing LONG
            if position > 0.000001:
                close_qty = min(position, qty)
                trade_pnl = (price - avg_entry) * close_qty
                realized_pnl += trade_pnl
                trades_count += 1
                if trade_pnl > 0: wins += 1
                else: losses += 1
                
                position -= close_qty
                if qty > close_qty:
                    rem_qty = qty - close_qty
                    avg_entry = price # New short
                    position -= rem_qty
            else:
                # Open/Add SHORT
                current_val = abs(position) * avg_entry
                new_val = current_val + (qty * price)
                position -= qty
                avg_entry = new_val / abs(position)

    LOG.info("=" * 40)
    LOG.info(f"MONEY RUN RESULTS")
    LOG.info("=" * 40)
    LOG.info(f"Total Trades Closed: {trades_count}")
    LOG.info(f"Wins: {wins}")
    LOG.info(f"Losses: {losses}")
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0.0
    LOG.info(f"Win Rate: {win_rate:.1f}%")
    LOG.info(f"Realized PnL: {realized_pnl:.2f} USDT")
    LOG.info("=" * 40)
    
    return trades_count, realized_pnl

def main():
    random.seed(42)
    config_src = project_root / "config" / "aurora"
    cfg_dir = _copy_config_to_tmp(src=config_src)

    # Patch system.yaml
    system_yaml = cfg_dir / "system.yaml"
    txt = system_yaml.read_text()
    if "trading_mode:" in txt:
        txt = txt.replace('trading_mode: "paper"', 'trading_mode: "backtest"')
        txt = txt.replace('trading_mode: "live"', 'trading_mode: "backtest"')
    else:
        txt += '\ntrading_mode: "backtest"\n'
    system_yaml.write_text(txt)
    
    # Patch trading.yaml (Disable killswitch)
    trading_yaml = cfg_dir / "trading.yaml"
    t_txt = trading_yaml.read_text()
    t_txt = t_txt.replace("panic_killswitch: true", "panic_killswitch: false")
    trading_yaml.write_text(t_txt)

    # Load Config
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    
    # PATCH: Disable problematic features for simplified backtest
    LOG.info("PATCHING CONFIG: Disabling complex features...")
    if hasattr(config.domains, "feature_engineering"):
        fe = config.domains.feature_engineering
        # Disable macro_sync entirely (removes from readiness check)
        if hasattr(fe, "macro_sync"):
            fe.macro_sync.enabled = False
            LOG.info("Disabled macro_sync")
        # Disable macro_resid
        if hasattr(fe, "macro_resid"):
            fe.macro_resid.enabled = False
            LOG.info("Disabled macro_resid")
        # Disable Large Trade Imbalance (requires data)
        if hasattr(fe, "large_trade_imbalance"):
            fe.large_trade_imbalance.enabled = False
            LOG.info("Disabled large_trade_imbalance")
        # Disable Absorption (requires data)
        if hasattr(fe, "absorption"):
            fe.absorption.mode = "disabled"
            LOG.info("Disabled absorption")
            
    # PATCH: Switch to Tick-Based Regime Detection
    # BacktestEngine emits ticks (tf=0). To ensure RD receives data, we match basis_tf_sec=0.
    config.basis_tf_sec = 0
    LOG.info("Set basis_tf_sec=0 (Tick-Based Mode)")

    # PATCH: Relax warmup enforcement
    if hasattr(config.domains, "decision_making") and hasattr(config.domains.decision_making, "warmup"):
        config.domains.decision_making.warmup.enforcement_mode = "warn_only"
        LOG.info("Set enforcement_mode=warn_only")
    
    fsm = FSMCore()

    # DEBUG: Monitor FE Readiness
    def debug_fe(event):
        try:
             w = event.pld.get("warmup", {})
             if w.get("full_ready") is False:
                 ts = int(event.pld.get("ts", 0))
                 # Log periodically (every ~1 hour of sim time) to avoid spam
                 if (ts % 3600000) < 300000: 
                      LOG.warning(f"DEBUG FE: Not Ready! Reasons: {w.get('reasons')}")
                      ready = w.get("ready", {})
                      missing = [k for k,v in ready.items() if not v]
                      if missing:
                          LOG.warning(f"DEBUG FE: Missing Keys: {missing}")
        except Exception:
             pass

    fsm.listen("EVT:FEATURES_CALCULATED", debug_fe)
    
    # Setup OrderIndex if missing
    try:
        from apps.reference.domains.execution_position.order_index import OrderIndex
        fsm.order_index = OrderIndex(ttl_sec=3600)
    except Exception:
        pass

    # 1. Feature Engineering (Auto-wire)
    fe = FeatureEngineering(fsm, config)
    
    # 2. Regime Detector (Auto-wire)
    rd = RegimeDetector(config, fsm)
    
    # 3. Decision Making (Auto-wire)
    dm = DecisionMaking(fsm, config)
    
    # 4. Execution
    ep = BacktestExecPosFSM(config=config, fsm=fsm, shadow_mode=False)
    
    # Async Loop
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=_run_loop, args=(loop,), daemon=True)
    t.start()
    ep.set_async_loop(loop)
    
    # Data
    df = generate_synthetic_data(bars=3000) # 10 days
    
    # Engine
    engine = BacktestEngine(
        start_date=df["ts"][0],
        end_date=df["ts"][-1],
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        initial_balance=10000.0,
        event_bus=fsm
    )
    engine.feed = df
    engine.broker = ep.adapter
    
    # Prime
    engine._emit_portfolio_update()
    engine.broker._last_prices["BTCUSDT"] = df["close"][0]
    
    LOG.info("🚀 STARTING SIMULATION...")
    engine.run(max_ticks=len(df))
    LOG.info("🏁 SIMULATION COMPLETE.")
    
    calculate_pnl(engine.broker)
    
    # Cleanup
    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=1.0)
    shutil.rmtree(cfg_dir.parent)

if __name__ == "__main__":
    main()
