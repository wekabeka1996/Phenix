"""Tests for the coordination configuration YAML and Pydantic SSOT."""
from __future__ import annotations

from pathlib import Path
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.coordination_config import (
    load_coordination_config,
    CoordinationConfig,
)


def test_load_default_coordination_config():
    """Verify that the default coordination config loads successfully and validates."""
    config = load_coordination_config()
    assert isinstance(config, CoordinationConfig)
    assert config.schema_version == 1
    assert config.environment == "testnet"
    
    # Assert there are 2 configured agents
    assert len(config.agents) == 2
    
    # Verify Agent 1 (API Agent)
    api_agent = config.agent("api_agent_01")
    assert api_agent.agent_number == 1
    assert api_agent.interface == "api"
    assert "ETHUSDT" in api_agent.symbols
    assert "SOLUSDT" in api_agent.symbols
    
    # Verify Agent 2 (CLI Agent)
    cli_agent = config.agent("cli_agent_01")
    assert cli_agent.agent_number == 2
    assert cli_agent.interface == "cli"
    assert "XRPUSDT" in cli_agent.symbols
    assert "BNBUSDT" in cli_agent.symbols


def test_symbol_owners():
    """Verify correct symbol lease ownership rules."""
    config = load_coordination_config()
    
    # ETHUSDT and SOLUSDT should be owned by api_agent_01
    assert config.owner_for_symbol("ETHUSDT").agent_id == "api_agent_01"
    assert config.owner_for_symbol("SOLUSDT").agent_id == "api_agent_01"
    
    # XRPUSDT and BNBUSDT should be owned by cli_agent_01
    assert config.owner_for_symbol("XRPUSDT").agent_id == "cli_agent_01"
    assert config.owner_for_symbol("BNBUSDT").agent_id == "cli_agent_01"
    
    # Case insensitivity and whitespace stripping
    assert config.owner_for_symbol("  ethusdt  ").agent_id == "api_agent_01"
    
    # Unknown symbol should raise ValueError
    with pytest.raises(ValueError, match="symbol has no configured owner"):
        config.owner_for_symbol("BTCUSDT")


def test_invalid_coordination_validation():
    """Verify model validations for duplicate agent properties or missing tools."""
    # We can load the config dict, modify it to be invalid, and test validation
    import yaml
    from deepseek_terminal_agent.sessions.coordination_config import DEFAULT_COORDINATION_CONFIG_PATH
    
    raw = yaml.safe_load(DEFAULT_COORDINATION_CONFIG_PATH.read_text(encoding="utf-8"))
    
    # Case 1: Duplicate agent_id
    bad_agents = [
        {"agent_id": "api_agent_01", "agent_number": 1, "interface": "api", "symbols": ["ETHUSDT"]},
        {"agent_id": "api_agent_01", "agent_number": 2, "interface": "cli", "symbols": ["SOLUSDT"]},
    ]
    raw_bad = raw.copy()
    raw_bad["agents"] = bad_agents
    with pytest.raises(ValidationError, match="agent_id values must be unique"):
        CoordinationConfig.model_validate(raw_bad)
        
    # Case 2: Duplicate symbol ownership
    bad_symbols = [
        {"agent_id": "api_agent_01", "agent_number": 1, "interface": "api", "symbols": ["ETHUSDT"]},
        {"agent_id": "cli_agent_01", "agent_number": 2, "interface": "cli", "symbols": ["ETHUSDT"]},
    ]
    raw_bad = raw.copy()
    raw_bad["agents"] = bad_symbols
    with pytest.raises(ValidationError, match="each symbol must have exactly one configured owner"):
        CoordinationConfig.model_validate(raw_bad)
