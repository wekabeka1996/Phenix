from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


CONFIG_DIR = Path("config/aurora")


def test_regime_loss_embargo_is_explicit_in_domains_yaml() -> None:
    domains_path = CONFIG_DIR / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))

    regime_loss_embargo = domains["decision_making"]["regime_loss_embargo"]

    assert regime_loss_embargo["enabled"] is True
    assert regime_loss_embargo["min_loss_threshold_net"] == 0.0
    assert regime_loss_embargo["fee_only_close_policy"] == "ignore"


def test_regime_loss_embargo_loads_through_aurora_config() -> None:
    config = ConfigLoader(config_dir=CONFIG_DIR).load_config()

    regime_loss_embargo = config.domains.decision_making.regime_loss_embargo

    assert regime_loss_embargo.enabled is True
    assert regime_loss_embargo.min_loss_threshold_net == 0.0
    assert regime_loss_embargo.fee_only_close_policy == "ignore"


def test_missing_regime_loss_embargo_block_fails_validation(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"].pop("regime_loss_embargo", None)
    domains_path.write_text(yaml.safe_dump(
        domains, sort_keys=False), encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    assert "regime_loss_embargo" in str(exc_info.value)


def test_missing_fee_only_close_policy_fails_validation(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"]["regime_loss_embargo"].pop(
        "fee_only_close_policy", None)
    domains_path.write_text(yaml.safe_dump(
        domains, sort_keys=False), encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    assert "fee_only_close_policy" in str(exc_info.value)


def test_negative_min_loss_threshold_net_fails_validation(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"]["regime_loss_embargo"]["min_loss_threshold_net"] = -0.01
    domains_path.write_text(yaml.safe_dump(
        domains, sort_keys=False), encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    assert "min_loss_threshold_net" in str(exc_info.value)


def test_unknown_regime_loss_embargo_field_fails_validation(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"]["regime_loss_embargo"]["unexpected_field"] = True
    domains_path.write_text(yaml.safe_dump(
        domains, sort_keys=False), encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    assert "unexpected_field" in str(exc_info.value)
