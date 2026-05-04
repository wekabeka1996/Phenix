import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config.shared.atoms import PrecisionConfig as SharedPrecisionConfig
from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.position_tracking import (
    PositionTrackingDomainConfig as DomainPositionTrackingDomainConfig,
)
from apps.reference.config_models import PositionTrackingDomainConfig


CONFIG_DIR = Path("config/aurora")


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    default_factories: dict[str, Any],
) -> None:
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(default_factories)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay required"
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay optional/defaulted"
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name, expected_factory in default_factories.items():
        field_info = fields[name]
        assert not field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay default-factory backed"
        assert field_info.default_factory is expected_factory


def test_current_aurora_config_loads_position_tracking_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    pt = cfg.domains.position_tracking
    assert pt.positions_stale_ttl_sec == 15
    assert pt.enable_market_tick_subscription is True
    assert pt.precision.quantity_min_threshold == pytest.approx(1e-9)
    assert pt.precision.flat_position_threshold == pytest.approx(1e-12)
    assert pt.precision.decimal_places == 2


def test_position_tracking_facade_reexports_are_exact_identity() -> None:
    assert PositionTrackingDomainConfig is DomainPositionTrackingDomainConfig


def test_position_tracking_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        PositionTrackingDomainConfig,
        required={
            "precision",
            "positions_stale_ttl_sec",
            "enable_market_tick_subscription",
        },
        defaults={},
        default_factories={},
    )

    fields = PositionTrackingDomainConfig.model_fields
    assert fields["precision"].annotation is SharedPrecisionConfig


def test_position_tracking_yaml_contract_fails_closed_without_positions_stale_ttl(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["position_tracking"].pop("positions_stale_ttl_sec", None)
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    assert "positions_stale_ttl_sec" in str(exc_info.value)
