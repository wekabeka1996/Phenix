
import sys
import os
import yaml
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from apps.reference.config_loader import ConfigLoader

def dump_resolved_config():
    print("Loading config with trading_mode='backtest'...")
    
    # Force env var for strict mode if needed, or rely on defaults
    # Simulate Backtest Mode
    loader = ConfigLoader()
    
    # We need to ensure the loader knows we are in backtest.
    # ConfigLoader reads system/trading/etc.
    # We can try to manually inject 'backtest' into the loaded raw dicts if needed, 
    # but the loader usually reads from files.
    # However, _apply_backtest_overlay checks resolved_config.get("trading_mode") or trading.mode.
    
    # Let's load normally. The trading.yaml should have mode: backtest 
    # (or we rely on backtest_override.yaml if applied? No, overlay is applied IF mode is backtest).
    # So headers in trading.yaml must say backtest, OR we must force it.
    
    # Actually, main.py might set it? 
    # Let's check how main.py works. It usually loads config first.
    
    # For this dump, we want to see what happens when trading.yaml has mode: backtest.
    # I will assume trading.yaml is already set to backtest or I might need to tweak it temporarily.
    # Based on previous turns, trading.yaml had "mode: backtest".
    
    try:
        config = loader.load_config()
        
        # Checking if overlay was applied
        # We can look for something specific from backtest_override.yaml
        # e.g. trading.backtest (dates) or relaxed TCA
        
        output_path = Path("reports/resolved_backtest_config.yaml")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            # We dump the Pydantic model to dict
            yaml.dump(config.model_dump(), f, sort_keys=False)
            
        print(f"Resolved config dumped to {output_path}")
        
    except Exception as e:
        print(f"Error loading config: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    dump_resolved_config()
