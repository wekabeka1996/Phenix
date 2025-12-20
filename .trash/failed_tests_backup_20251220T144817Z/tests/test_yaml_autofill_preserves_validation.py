#!/usr/bin/env python3
"""
Test YAML Autofill Preserves Validation

TASK21A: Ensure autofill adds defaults without changing behavior.
"""

import pytest
import yaml
from pathlib import Path


def load_yaml_file(file_path: Path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_nested_value(data, path):
    keys = path.split('.')
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def test_yaml_autofill_preserves_validation():
    """Test that autofilled YAML has expected values."""
    # Load trading.yaml
    trading_data = load_yaml_file(Path('config/aurora/trading.yaml'))
    
    # Assert critical values are present
    assert get_nested_value(trading_data, 'trading.decision.signal_threshold') is not None
    assert get_nested_value(trading_data, 'trading.decision.position_sizing.min_position_size_usd') is not None
    assert get_nested_value(trading_data, 'trading.decision.bar_gating.enable') is not None
    
    # Load domains.yaml
    domains_data = load_yaml_file(Path('config/aurora/domains.yaml'))
    assert get_nested_value(domains_data, 'domains.decision_making.bar_gating.enable') is not None


def test_autofilled_defaults_match_expected():
    """Test that autofilled values are reasonable."""
    trading_data = load_yaml_file(Path('config/aurora/trading.yaml'))
    
    # Check some known defaults
    assert get_nested_value(trading_data, 'trading.decision.bar_gating.enable') == False
    assert get_nested_value(trading_data, 'trading.decision.behavior_fsm.enable') == False
    assert get_nested_value(trading_data, 'trading.decision.signals.normalize') == True