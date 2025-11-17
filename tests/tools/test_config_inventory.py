import pytest
from tools.config_inventory import load_yaml_files, flatten_keys, build_inventory


def test_load_yaml_files():
    """Test that load_yaml_files returns at least one file with non-None content."""
    result = load_yaml_files()
    assert isinstance(result, dict)
    assert len(result) > 0
    # Check that at least one file has content (assuming trading.yaml exists)
    has_content = any(content is not None for content in result.values())
    assert has_content, "At least one YAML file should have been loaded successfully"


def test_flatten_keys():
    """Test flatten_keys on a sample data structure."""
    data = {"a": {"b": 1, "c": [{"d": 2}, 3]}}
    keys = flatten_keys(data)
    expected_keys = ["a.b", "a.c[0].d", "a.c[1]"]
    # Sort both for comparison since order might vary
    assert sorted(keys) == sorted(expected_keys)


def test_build_inventory():
    """Test that build_inventory returns a dict with expected file keys."""
    inventory = build_inventory()
    assert isinstance(inventory, dict)
    # Check for known files
    expected_files = [
        "config/core.yaml",
        "config/instruments.yaml",
        "config/domains/decision.yaml",
        "config/domains/execution.yaml",
        "config/domains/sizing.yaml",
        "configs/master_config_v1.yaml",
    ]
    for file_path in expected_files:
        assert file_path in inventory, f"Expected file {file_path} in inventory"
        assert "keys" in inventory[file_path]
        assert isinstance(inventory[file_path]["keys"], list)
