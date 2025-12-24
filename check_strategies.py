import yaml
from pathlib import Path

def check_strategies():
    path = Path("config/aurora/strategies.yaml")
    if not path.exists():
        print("File not found")
        return
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    
    assignments = data.get("assignments", {})
    for symbol, strategies in assignments.items():
        print(f"Symbol: {symbol!r}, Strategies: {strategies!r}")

if __name__ == "__main__":
    check_strategies()
