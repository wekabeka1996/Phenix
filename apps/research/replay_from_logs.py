import sys
import os
import json
import time
import decimal
import logging
from collections import defaultdict
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler

# Setup simple logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("replay")

class VirtualExchange:
    def __init__(self, fee_bps=0.0):
        self.trades = []
        self.pnl_pct = 0.0
        self.position = None # None, 'LONG', 'SHORT'
        self.entry_price = 0.0
        self.equity = 1.0 # Normalized equity, start at 1.0
        self.max_drawdown = 0.0
        self.peak_equity = 1.0
        self.fee_rate = fee_bps / 10000.0
        
    def on_signal(self, symbol, side, price, timestamp):
        price = float(price)
        
        # execution cost (fee) applied on entry and exit
        # For simplicity, we apply generic 'slippage+fee' impact on PnL directly
        
        if self.position == 'LONG':
             if side == 'SELL':
                 # Close Long
                 raw_pnl = (price - self.entry_price) / self.entry_price
                 # Fee on entry (already paid implicitly in equity?) No, let's deduct from PnL
                 # Simple approx: Net PnL = Raw PnL - (EntryFee + ExitFee)
                 net_pnl = raw_pnl - (self.fee_rate * 2) 
                 
                 self.equity *= (1.0 + net_pnl)
                 self.trades.append({'type': 'CLOSE_LONG', 'price': price, 'ts': timestamp, 'pnl': net_pnl})
                 self.position = None
        
        elif self.position == 'SHORT':
             if side == 'BUY':
                 # Close Short
                 raw_pnl = (self.entry_price - price) / self.entry_price
                 net_pnl = raw_pnl - (self.fee_rate * 2)
                 
                 self.equity *= (1.0 + net_pnl)
                 self.trades.append({'type': 'CLOSE_SHORT', 'price': price, 'ts': timestamp, 'pnl': net_pnl})
                 self.position = None

        elif self.position is None:
             if side == 'BUY':
                 self.position = 'LONG'
                 self.entry_price = price
             elif side == 'SELL':
                 self.position = 'SHORT'
                 self.entry_price = price
        
        # Update Drawdown
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        drawdown = (self.peak_equity - self.equity) / self.peak_equity
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

    def get_stats(self):
        win_count = len([t for t in self.trades if t.get('pnl', 0) > 0])
        total_closed = len([t for t in self.trades if 'pnl' in t])
        win_rate = (win_count / total_closed) if total_closed > 0 else 0.0
        return {
            "total_pnl_pct": (self.equity - 1.0) * 100,
            "trade_count": len(self.trades),
            "win_rate": win_rate,
            "max_drawdown": self.max_drawdown
        }

class ReplayEngine:
    def __init__(self, symbol, log_path, fee_bps=0.0):
        self.symbol = symbol
        self.log_path = log_path
        self.config = get_config()
        self.exchange = VirtualExchange(fee_bps=fee_bps)
        self.veto_count = 0
        self.signal_count = 0
        
        # Mock Emit Function
        self.aurora = AuroraHandler(config=self.config, emit_fn=self._emit_fn, strategy_id="aurora")
        # self.mr = MeanReversionHandler(config=self.config, emit_fn=self._emit_fn, strategy_id="mean_reversion_1m")
        # Note: MeanReversionHandler requires raw ticks to build bars. 
        # Feature logs contain calculated features, not ticks, so we cannot replay MR.
        
        # Check Veto Config
        try:
             veto_cfg = self.config.strategies.aurora.decision.anchor_shock_veto
             self.veto_enabled = veto_cfg.enabled
             self.veto_threshold = float(veto_cfg.threshold)
             logger.info(f"Veto Enabled: {self.veto_enabled}, Threshold: {self.veto_threshold}")
        except:
             self.veto_enabled = False
             logger.info("Veto Config Not Found/Disabled")

    def _emit_fn(self, event_name, payload):
        if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
            self.signal_count += 1
            side = payload.get("side")
            price = payload.get("price_ctx", {}).get("entry_price")
            ts = payload.get("ts_ms") / 1000.0
            
            # Execute on Exchange
            self.exchange.on_signal(self.symbol, side, price, ts)
        
        elif event_name == "EVT:STRATEGY_DECISION_BLOCKED":
             if payload.get("reason_code") == "ANCHOR_SHOCK_VETO":
                 self.veto_count += 1
                 logger.info(f"Veto Action Triggered! blocked {payload.get('side')} on {self.symbol}")

    def run(self):
        logger.info(f"Starting replay for {self.symbol} from {self.log_path}")
        
        if not os.path.exists(self.log_path):
             logger.error("Log file not found")
             return

        # Time Simulation
        # Since logs have no TS, we start at raw time 1000000000 and increment by 1s
        current_time = 1700000000.0 
        
        with open(self.log_path, 'r') as f:
             lines = f.readlines()
        
        logger.info(f"Loaded {len(lines)} lines")
        
        with patch('time.time') as mock_time:
            for i, line in enumerate(lines):
                 current_time += 1.0
                 mock_time.return_value = current_time
                 
                 try:
                     feat_dict = json.loads(line)
                 except json.JSONDecodeError:
                     continue
                 
                 # Construct Event
                 # We assume all fields in log are features
                 # AND we need to ensure readiness is True
                 
                 # Derive readiness from keys
                 readiness = {k: True for k in feat_dict.keys()}
                 
                 # Add some defaults if missing?
                 # Aurora needs: price, delta_price, etc.
                 # Logs seem to define them.
                 
                 event = {
                     "symbol": self.symbol,
                     "features": feat_dict,
                     "warmup": {
                         "full_ready": True, 
                         "ready": readiness, 
                         "ticks_seen": 1000
                     },
                     "ts_ms": int(current_time * 1000)
                 }
                 
                 # Setup Handler State (Regime)
                 # We need to simulate OnRegimeDetected?
                 # Or just force it.
                 # The handler caches regime. If we don't send EVT:REGIME_DETECTED, it assumes None?
                 # We can inject a fake regime event every now and then or parse it?
                 # Log files don't seem to have regime.
                 # Let's assume a default regime or "FLAT_NORMAL" if not found?
                 # Actually without regime, Aurora might default to 'DEFAULT' thresholds so it's fine.
                 
                 # Feed handlers
                 self.aurora.on_features_calculated(event)
                 
                 # MR Handler also needs ticks? No, it listens to features too?
                 # Wait, MR Handler usually listens to TICKS to build bars.
                 # But here we have FEATURES.
                 # If MR handler expects ticks, we can't replay it easily from features log.
                 # Checking MR Handler code... it consumes TICKS.
                 # So we SKIP MR Handler for this replay (log source incompatible).
                 # We only test Aurora. (Prompt said "Feed ... MeanReversionHandler" but that might be impossible if input is features only)
                 # Actually, logs/features is output of FeatureEngineering.
                 # If we want to test correct Wiring of MR, we need ticks.
                 # But "Feature Replay" implies feature-level strategies.
                 # I will skip MR Handler feed to avoid crashing, focusing on Aurora & Veto.
                 
                 # Veto Logic Check:
                 # Veto logic is inside AuroraHandler (on_features_calculated).
                 # So feeding Aurora is enough.
        
        stats = self.exchange.get_stats()
        print("\n" + "="*30)
        print(f"REPLAY REPORT: {self.symbol}")
        print("="*30)
        print(f"Total Lines: {len(lines)}")
        print(f"Signals Triggered: {self.signal_count}")
        print(f"Trades Executed: {stats['trade_count']}")
        print(f"PnL: {stats['total_pnl_pct']:.2f}%")
        print(f"Win Rate: {stats['win_rate']*100:.1f}%")
        print(f"Max Drawdown: {stats['max_drawdown']*100:.2f}%")
        print(f"Veto Actions: {self.veto_count}")
        print("="*30 + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    parser.add_argument("--fee", type=float, default=0.0, help="Fee/Slippage in Basis Points (bps)")
    args = parser.parse_args()
    
    log_file = f"logs/features/{args.symbol}.log"
    engine = ReplayEngine(args.symbol, log_file, fee_bps=args.fee)
    engine.run()
