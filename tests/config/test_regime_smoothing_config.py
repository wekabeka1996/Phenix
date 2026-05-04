import pytest
from pydantic import ValidationError
from apps.reference.config_models import RegimeSmoothingConfig

def test_valid_config():
    cfg = RegimeSmoothingConfig(enabled=True, method="ema", ema_alpha=0.3, ramp_bars=6)
    assert cfg.enabled is True
    assert cfg.method == "ema"

def test_alpha_bounds():
    with pytest.raises(ValidationError):
        RegimeSmoothingConfig(ema_alpha=0.0)
    with pytest.raises(ValidationError):
        RegimeSmoothingConfig(ema_alpha=1.1)

def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        RegimeSmoothingConfig(enabled=True, unknown_field=123)
