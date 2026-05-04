
import pytest
from pydantic import ValidationError
from apps.reference.config_models import FeatureEngineeringConfig

def test_feature_engineering_config_extra_forbid():
    """
    Verify that FeatureEngineeringConfig is strict (extra='forbid').
    """
    # Valid config
    valid_data = {
        "ema": {},
        "volume": {}
    }
    
    extra_data = {
        "ema": {},
        "ZOMBIE_FIELD": "I should cause a crash"
    }
    
    with pytest.raises(ValidationError) as excinfo:
        FeatureEngineeringConfig(**extra_data)
    
    assert "ZOMBIE_FIELD" in str(excinfo.value)
    # Pydantic V2 message
    assert "extra inputs are not permitted" in str(excinfo.value).lower()
