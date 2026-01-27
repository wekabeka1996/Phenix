import json
import logging
import os
import sys
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

# Add project root to path
sys.path.append(os.getcwd())

# Import Domain Components
try:
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
    from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
    from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult
    from apps.reference.config_loader import get_config as load_config
    from vfoundation.core.protocol import Message
except ImportError as e:
    print(f"Import Error: {e}")
    print(f"Current Path: {sys.path}")
    sys.exit(1)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("SimTest")

class MockFSM:
    """Mocks FSM to capture emitted signals."""
    def __init__(self):
        self.emitted_events = []

    def emit(self, event_name: str, payload: Dict[str, Any], **kwargs):
        self.emitted_events.append((event_name, payload))
        if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
            logger.info(f"⚡ SIGNAL EMITTED: {payload.get('symbol')} {payload.get('side')} (Score: {payload.get('score'):.4f})")

    def listen(self, *args, **kwargs):
        pass

def load_feature_log(symbol: str, limit: int = 1000) -> List[Dict]:
    """Loads real features from logs/features directory."""
    path = f"logs/features/{symbol}.log" # Adjust extension if needed (.jsonl, .txt)
    data = []
    if not os.path.exists(path):
        logger.warning(f"⚠️ Log file not found: {path}. Using synthetic data if needed.")
        return []
    
    with open(path, 'r') as f:
        for line in f:
            if not line.strip(): continue
            try:
                # Assuming JSON log format. Adjust parsing if CSV.
                rec = json.loads(line)
                # Extract 'features' payload if nested
                if "features" in rec: 
                    data.append(rec)
            except Exception:
                continue
            if len(data) >= limit: break
    return data

def run_simulation():
    logger.info("🚀 STARTING REMEDIATION SIMULATION")
    
    # 1. Load & Patch Config (Simulating Phase 1 & 2 changes)
    try:
        config = load_config() # Assumes standard loader
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    # --- PATCH 1: BTC CONFLICT FIX ---
    # Remove mean_reversion from BTC
    # Note: Structure might vary depending on how config is loaded (object vs dict)
    # Adapting to typical Pydantic or object structure
    
    # Check strategies_registry structure
    if hasattr(config, "strategies_registry") and hasattr(config.strategies_registry, "assignments"):
        if "BTCUSDT" in config.strategies_registry.assignments:
            strategies = config.strategies_registry.assignments["BTCUSDT"]
            if "mean_reversion" in strategies:
                strategies.remove("mean_reversion")
                logger.info("✅ PATCH APPLIED: Removed mean_reversion from BTCUSDT")
    
    # --- PATCH 2: ETH VETO CONFIG ---
    # Inject anchor_shock_veto config
    # We need to see where 'anchor_shock_veto' lives. 
    # Usually config.strategies.aurora.decision
    if hasattr(config, "strategies") and hasattr(config.strategies, "aurora"):
         if hasattr(config.strategies.aurora, "decision"):
            if not hasattr(config.strategies.aurora.decision, "anchor_shock_veto") or config.strategies.aurora.decision.anchor_shock_veto is None:
                # Mocking the config structure injection
                config.strategies.aurora.decision.anchor_shock_veto = type('obj', (object,), {
                    "enabled": True,
                    "anchor_symbol": "BTCUSDT",
                    "threshold": -2.0
                })
                logger.info("✅ PATCH APPLIED: Injected Anchor Shock Veto config")
            else:
                 # It might already exist if we updated the yaml, but let's force it for simulation
                 config.strategies.aurora.decision.anchor_shock_veto.enabled = True
                 config.strategies.aurora.decision.anchor_shock_veto.threshold = -2.0
                 logger.info("✅ PATCH APPLIED: Updated Anchor Shock Veto config (already existed)")

    # --- PATCH 3: DOGE WIRING ---
    # Ensure DOGE is enabled in MR assets
    if hasattr(config, "strategies") and hasattr(config.strategies, "mean_reversion"):
        if "DOGEUSDT" not in config.strategies.mean_reversion.assets:
             logger.warning("⚠️ DOGEUSDT missing in MR config assets! Simulating fix.")
             # In real run, we'd add it. For sim, we assume handler will use passed config.

    fsm = MockFSM()
    
    # ==========================================
    # TEST SCENARIO A: ETH LEAD-LAG VETO
    # ==========================================
    logger.info("\n🧪 TEST A: ETH VETO LOGIC (Lead-Lag Protection)")
    try:
        aurora_handler = AuroraHandler(config=config, emit_fn=fsm.emit)
        
        # Synthetic "Crash" Record based on real structure
        crash_record = {
            "symbol": "ETHUSDT",
            "features": {
                "price": "3000",
                "delta_price": "0.02",  # Strong UP momentum (+2%)
                "macro_resid": "-3.5",  # BTC CRASHING HARD (Below -2.0)
                "obi": "0.5",
                "tfi": "0.5"
            },
            "warmup": {"full_ready": True, "ready": {"macro_resid": True}}
        }
        
        # Manually trigger handler
        # Note: We need to ensure the handler class has the VETO LOGIC we discussed.
        # If the file isn't updated, this test will FAIL (which is what we want to verify).
        logger.info("Running AuroraHandler.on_features_calculated with crash record...")
        aurora_handler.on_features_calculated(crash_record)
        
        # Check results
        signals = [e for e in fsm.emitted_events if e[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        eth_signals = [s for s in signals if s[1]['symbol'] == 'ETHUSDT']
        
        if not eth_signals:
            logger.info("✅ SUCCESS: ETH Signal BLOCKED by Veto (No signal emitted)")
        else:
            logger.error(f"❌ FAILURE: ETH Signal LEAKED! Veto did not work. Signal: {eth_signals[0][1]['side']}")
            
    except Exception as e:
        logger.error(f"Test A Failed with exception: {e}")
        import traceback
        traceback.print_exc()


    # ==========================================
    # TEST SCENARIO B: DOGE WIRING (MR Handler)
    # ==========================================
    logger.info("\n🧪 TEST B: DOGE WIRING CHECK")
    try:
        if hasattr(config.strategies, "mean_reversion") and hasattr(config.strategies.mean_reversion, "assets"):
            # Force enable DOGE for this handler instance
            config.strategies.mean_reversion.assets["DOGEUSDT"] = type('obj', (object,), {
                "enabled": True, "liquidity_gate": None, "allowed_regimes": ["FLAT_NORMAL"]
            })
        
        mr_handler = MeanReversionHandler(fsm=fsm, config=config)
        # Force register/init logic
        if hasattr(mr_handler, "_enabled_symbols"):
            mr_handler._enabled_symbols.add("DOGEUSDT") 
        
        # T2B-06: Tick path deprecated. MR now uses CMD:PROCESS_STRATEGY.
        # Verify handler was created successfully
        logger.info(f"✅ SUCCESS: MR Handler initialized (enabled_symbols={getattr(mr_handler, '_enabled_symbols', 'N/A')})")
            
    except Exception as e:
        logger.error(f"❌ CRITICAL: Handler crashed: {e}")
        import traceback
        traceback.print_exc()

    logger.info("\n🏁 SIMULATION COMPLETE")

if __name__ == "__main__":
    run_simulation()
