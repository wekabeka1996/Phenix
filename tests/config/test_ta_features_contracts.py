import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.ta_features import (
    TAFeaturesDomainConfig as DomainTAFeaturesDomainConfig,
)
from apps.reference.config_models import TAFeaturesDomainConfig


CONFIG_DIR = Path("config/aurora")


def _assert_field_contract(model_cls: type, *, required: set[str]) -> None:
    fields = model_cls.model_fields

    assert set(fields) == required
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay required"
        assert field_info.default_factory is None


def test_current_aurora_config_loads_ta_features_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    ta = cfg.domains.ta_features
    assert ta is not None
    assert ta.enabled is True
    assert ta.timeframes_sec == [180, 300, 900]
    assert ta.warm_up_bars == 30
    assert ta.buffer_max_bars == 300
    assert ta.log_calculations is True
    assert ta.log_max_bytes == 10485760
    assert ta.log_backup_count == 5


def test_ta_features_facade_reexport_is_exact_identity() -> None:
    assert TAFeaturesDomainConfig is DomainTAFeaturesDomainConfig


def test_ta_features_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        TAFeaturesDomainConfig,
        required={
            "enabled",
            "timeframes_sec",
            "warm_up_bars",
            "buffer_max_bars",
            "log_calculations",
            "log_max_bytes",
            "log_backup_count",
        },
    )


def test_ta_features_yaml_contract_fails_closed_on_invalid_buffer_length(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    warm_up_bars = domains["ta_features"]["warm_up_bars"]
    domains["ta_features"]["buffer_max_bars"] = warm_up_bars - 1
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    message = str(exc_info.value)
    assert "buffer_max_bars" in message
    assert "warm_up_bars" in message
