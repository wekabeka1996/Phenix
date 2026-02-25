import pytest
import yaml
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from apps.reference.config_contract import ConfigContractError

CONFIG_DIR = Path("config/aurora")

class StrictYAMLLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = []
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in [k for k, v in mapping]:
                raise ValueError(f"Duplicate key '{key}' found in YAML at {node.start_mark}")
            value = self.construct_object(value_node, deep=deep)
            mapping.append((key, value))
        return dict(mapping)

def test_no_duplicate_yaml_keys():
    """Verify that no YAML file has duplicate keys at the same level."""
    yaml_files = list(CONFIG_DIR.glob("*.yaml")) + list((CONFIG_DIR / "strategies").glob("*.yaml"))
    
    for yf in yaml_files:
        if not yf.exists(): continue
        with open(yf, "r", encoding="utf-8") as f:
            try:
                yaml.load(f, Loader=StrictYAMLLoader)
            except ValueError as e:
                pytest.fail(f"Duplicate key in {yf.name}: {e}")

def test_no_critical_key_overlaps_between_trading_and_domains():
    """Verify that trading.yaml and domains.yaml do not have overlapping leaf paths."""
    trading_path = CONFIG_DIR / "trading.yaml"
    domains_path = CONFIG_DIR / "domains.yaml"
    
    if not (trading_path.exists() and domains_path.exists()):
        pytest.skip("Config files missing")
        
    loader = ConfigLoader()
    with open(trading_path, "r", encoding="utf-8") as f:
        trading_data = yaml.safe_load(f) or {}
    with open(domains_path, "r", encoding="utf-8") as f:
        domains_data = yaml.safe_load(f) or {}
        
    flat_trading = loader._flatten_leaf_paths(trading_data)
    flat_domains = loader._flatten_leaf_paths(domains_data)
    
    overlaps = set(flat_trading.keys()) & set(flat_domains.keys())
    # Whitelist known/intentional overlaps if any (should be empty for SSOT)
    whitelist = set() 
    
    critical_overlaps = overlaps - whitelist
    assert not critical_overlaps, f"Critical overlaps found between trading.yaml and domains.yaml: {critical_overlaps}"

def test_strategy_assignment_requires_strategy_config():
    """Verify that every strategy assigned in strategies.yaml has a corresponding profile."""
    strategies_path = CONFIG_DIR / "strategies.yaml"
    if not strategies_path.exists():
        pytest.skip("strategies.yaml missing")
        
    with open(strategies_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        
    assignments = data.get("assignments", {})
    if not isinstance(assignments, dict):
        return
        
    strategy_ids = set()
    for symbol, strats in assignments.items():
        if isinstance(strats, list):
            strategy_ids.update(strats)
            
    strategies_dir = CONFIG_DIR / "strategies"
    for sid in strategy_ids:
        profile_path = strategies_dir / f"{sid}.yaml"
        assert profile_path.exists(), f"Strategy '{sid}' assigned but profile missing: {profile_path}"

def test_config_loader_provenance_integration():
    """Verify that ConfigLoader now tracks provenance correctly."""
    loader = ConfigLoader()
    config = loader.load_config()
    
    assert hasattr(loader, "provenance_map")
    assert len(loader.provenance_map) > 0
    # Check a known key
    if "trading.mode" in loader.provenance_map:
        assert loader.provenance_map["trading.mode"] == "trading.yaml"
