
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout
)

# Force WAL to temp
import tempfile
os.environ["WAL_DIR"] = os.path.join(tempfile.gettempdir(), "phenix_optuna_repro_wal")
os.makedirs(os.environ["WAL_DIR"], exist_ok=True)

from optimization.backtest_interface import BacktestAdapter
from apps.reference.config_loader import ConfigLoader

def reproduce():
    print("🚀 Starting reproduction script...")
    
    # 1. Config
    config_dir = project_root / "config" / "aurora"
    adapter = BacktestAdapter(config_dir=config_dir)
    
    # 2. Setup Overlay for Stage 0 (Regime)
    # Mimic default stage0 params - keys must be at ROOT for AuroraConfig
    overlay = {
        "basis_tf_sec": 300,
        "uncertain_cutoff": 0.3,  
        "hysteresis_bars": 3,     # Default
        "trading": {
             "backtest": {
                 # Short range with DATA
                 "start_date": "2023-06-01",
                 "end_date": "2023-06-02",
             }
        }
    }
    
    # Set max_ticks via env var since it's not in schema
    os.environ["BACKTEST_MAX_TICKS"] = "50"
    
    print("⚙️ Running Stage 0 Backtest with max_ticks=50 (env var)...")
    
    try:
        metrics, stage_result = adapter.run_stage0(
            overlay,
            start_date="2023-06-01",
            end_date="2023-06-02"
        )
        
        print("\n✅ Backtest completed successfully!")
        print(f"Metrics: {metrics}")
        print(f"Success: {stage_result.success}")
        if not stage_result.success:
            print(f"Error: {stage_result.error}")
            
    except Exception as e:
        print(f"\n❌ Exception during backtest: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
