import shutil

import pytest
from pydantic import ValidationError


def test_max_risk_score_override_enabled_requires_value():
    from apps.reference.config_models import MaxRiskScoreConfig

    with pytest.raises(ValidationError):
        MaxRiskScoreConfig(enabled=True, value=None)


def test_aurora_asset_max_risk_score_null_is_forbidden():
    from apps.reference.config_models import AuroraInstrumentConfig

    with pytest.raises(ValidationError):
        AuroraInstrumentConfig.model_validate(
            {
                "enabled": True,
                "position_mode": "STRICT",
                # MR-RISK-GATE-NONE-FIX-01: explicit null is not allowed as "inherit"
                "max_risk_score": None,
            }
        )


def test_domains_global_max_risk_score_cannot_be_null_in_config(tmp_path):
    from apps.reference.config_loader import ConfigLoader

    src = tmp_path / "cfg"
    shutil.copytree("config/aurora", src)
    domains_yaml = src / "domains.yaml"

    text = domains_yaml.read_text(encoding="utf-8")
    assert "trading_allowed_thresholds" in text
    assert "max_risk_score:" in text
    domains_yaml.write_text(text.replace("max_risk_score: 0.96", "max_risk_score: null"), encoding="utf-8")

    with pytest.raises(Exception):
        ConfigLoader(config_dir=src).load_config(is_live_execution=True)
