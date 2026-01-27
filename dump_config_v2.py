
import sys
import os
import yaml
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

try:
    from apps.reference.config_loader import ConfigLoader
    from apps.reference.config_models import AuroraConfig, FallbackConfig
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

def dump_resolved_config_v2():
    print("Loading config...")
    loader = ConfigLoader()
    
    try:
        # Full load attempt to trigger validation error and inspect it
        print("Trying to load full config with loader...")
        try:
            config = loader.load_config()
            print("Full config loaded successfully.")
            
            output_path = Path("reports/resolved_backtest_config.yaml")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w") as f:
                yaml.dump(config.model_dump(), f, sort_keys=False)
            print(f"Dumped resolved config to {output_path}")

        except Exception as e:
            print(f"Loader failed as expected: {e}")

    except Exception as e:
        print(f"Runtime error: {e}")

if __name__ == "__main__":
    dump_resolved_config_v2()
