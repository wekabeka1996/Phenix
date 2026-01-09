"""
Test strategy timeframe config validation.

CFG-STRATEGY-SSOT-FREEZE-03: Validate timeframe_sec is mandatory in strategy profiles.
Note: Updated 2026-01-08 to use real SSOT YAMLs to ensure schema compliance.
"""
import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from apps.reference.config_models import MeanReversion1mStrategyConfig, AuroraStrategyConfig

# Paths to SSOT configs
AURORA_YAML = Path("config/aurora/strategies/aurora.yaml")
MR_YAML = Path("config/aurora/strategies/mean_reversion.yaml")

def load_config_section(yaml_path: Path, section_key: str):
    """Load specific section from YAML file."""
    if not yaml_path.exists():
        pytest.skip(f"Config file not found: {yaml_path}")
    
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    
    return data.get(section_key)

def test_mean_reversion_timeframe_required():
    """MR strategy must have timeframe_sec."""
    config = load_config_section(MR_YAML, "mean_reversion")
    assert config is not None, "mean_reversion section failing to load"
    
    # Validation should pass on unmodified config
    mr = MeanReversion1mStrategyConfig(**config)
    assert mr.timeframe_sec == 180  # Default 3m (180s)
    
    # Missing timeframe_sec
    config_missing = config.copy()
    del config_missing["timeframe_sec"]
    with pytest.raises(ValidationError) as exc_info:
        MeanReversion1mStrategyConfig(**config_missing)
    assert "timeframe_sec" in str(exc_info.value)
    
    # Invalid timeframe_sec
    config_invalid = config.copy()
    config_invalid["timeframe_sec"] = 30 # Too small (min 60)
    with pytest.raises(ValidationError) as exc_info:
        MeanReversion1mStrategyConfig(**config_invalid)
    assert "timeframe_sec" in str(exc_info.value)

def test_aurora_timeframe_required():
    """Aurora strategy must have timeframe_sec."""
    config = load_config_section(AURORA_YAML, "aurora")
    assert config is not None, "aurora section failing to load"
    
    aurora = AuroraStrategyConfig(**config)
    assert aurora.timeframe_sec >= 60
    
    # Missing timeframe_sec
    config_missing = config.copy()
    del config_missing["timeframe_sec"]
    with pytest.raises(ValidationError) as exc_info:
        AuroraStrategyConfig(**config_missing)
    assert "timeframe_sec" in str(exc_info.value)

    # Invalid timeframe_sec
    config_invalid = config.copy()
    config_invalid["timeframe_sec"] = 5000 # Too large
    with pytest.raises(ValidationError) as exc_info:
        AuroraStrategyConfig(**config_invalid)
    assert "timeframe_sec" in str(exc_info.value)