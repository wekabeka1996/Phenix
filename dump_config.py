
import sys
import os
import yaml
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from apps.reference.config_loader import ConfigLoader

def dump_resolved_config():
    print("Loading resolved config (SSOT-only)...")
    
    # Force env var for strict mode if needed, or rely on defaults
    # Simulate Backtest Mode
    loader = ConfigLoader()
    
    try:
        config = loader.load_config()

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
