"""Test script to verify auto-trading config loading."""

from pathlib import Path
import pytest
from apps.reference.config_loader import ConfigLoader


def test_config_auto_trading_loads():
    """Test that config loads successfully with auto-trading settings."""
    # Load config from correct project root
    project_root = Path(__file__).resolve().parent.parent
    config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
    config = config_loader.load_config()

    # Check auto-trading setting (using Pydantic model access)
    cfg_exec = config.trading.execution if hasattr(config.trading, 'execution') else None
    if cfg_exec:
        manage_cfg = cfg_exec.manage if hasattr(cfg_exec, 'manage') else None
        if manage_cfg:
            auto_enabled = manage_cfg.auto if hasattr(manage_cfg, 'auto') else False
            assert isinstance(auto_enabled, bool)

    # Check position sizing config
    decision_config = config.trading.decision
    assert hasattr(decision_config, 'position_sizing')
    position_sizing = decision_config.position_sizing
    assert position_sizing.min_position_size_usd > 0
    assert position_sizing.liquidity_based_cap_usd > 0

    # Check instruments config (CFG-INSTRUMENTS-AURORA-SSOT-01: canonical field)
    instruments = config.instruments
    assert len(instruments) > 0, "Should have at least one instrument configured"
    
    # Check that at least one instrument has required fields
    for symbol, specs in instruments.items():
        assert hasattr(specs, 'step_size'), f"{symbol} missing step_size"
        assert hasattr(specs, 'tick_size'), f"{symbol} missing tick_size"
        break  # Check at least one
