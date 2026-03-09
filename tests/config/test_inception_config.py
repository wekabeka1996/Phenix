import pytest
from pydantic import ValidationError
from apps.reference.config_models import RegimeShiftInceptionConfig

def test_valid_config():
    cfg = RegimeShiftInceptionConfig(enabled=True, action="micro_size", micro_size_fraction=0.25)
    assert cfg.enabled is True
    assert cfg.action == "micro_size"
    assert cfg.micro_size_fraction == 0.25

def test_micro_fraction_bounds():
    with pytest.raises(ValidationError):
        RegimeShiftInceptionConfig(micro_size_fraction=0.0)
    with pytest.raises(ValidationError):
        RegimeShiftInceptionConfig(micro_size_fraction=1.1)

def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        RegimeShiftInceptionConfig(enabled=True, unknown_field="foo")
