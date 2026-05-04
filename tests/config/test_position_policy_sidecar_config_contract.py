import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_production_config_exposes_position_policy_sidecar_contract() -> None:
    cfg = ConfigLoader().load_config()

    sidecar = cfg.domains.execution_position.position_policy_sidecar
    assert sidecar.mode.value == "enable"
    assert sidecar.thresholds.recommend_soft_close_at == 0.30
    assert sidecar.allowed_actions.soft_close_symbol_current_net_only is True
    assert sidecar.allowed_actions.partial_reduce is False
    assert sidecar.shadow_percent_notional_arm.enabled is True
    assert sidecar.shadow_percent_notional_arm.candidate_pcts == [
        0.02, 0.05, 0.07]


def test_invalid_position_policy_sidecar_mode_is_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["mode"] = "SHADOW"
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "position_policy_sidecar" in str(exc_info.value)
    assert "SHADOW" in str(exc_info.value)


def test_unknown_position_policy_sidecar_field_is_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["logging"]["phantom_field"] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "phantom_field" in str(exc_info.value)


def test_forbidden_bounded_action_scope_is_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["allowed_actions"]["partial_reduce"] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "partial_reduce" in str(exc_info.value)
    assert "Bounded" in str(exc_info.value)


def test_position_policy_sidecar_structural_aliases_are_normalized(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    thresholds = domains["execution_position"]["position_policy_sidecar"]["thresholds"]
    thresholds["adverse_regimes_long"] = ["BEAR_TREND"]
    thresholds["adverse_regimes_short"] = ["BULL_TREND"]
    _write_yaml(domains_path, domains)

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()
    sidecar = cfg.domains.execution_position.position_policy_sidecar

    assert sidecar.thresholds.adverse_regimes_long == ["TREND_DOWN"]
    assert sidecar.thresholds.adverse_regimes_short == ["TREND_UP"]


@pytest.mark.parametrize("invalid_label", ["BEARISH", "BULLISH", "DOWNTREND", "SELL_DOMINANT", "FLAT_LOW"])
def test_unproven_sidecar_regime_labels_are_rejected(tmp_path: Path, invalid_label: str) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["thresholds"]["adverse_regimes_long"] = [
        invalid_label
    ]
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert invalid_label in str(exc_info.value)
    assert "structural labels" in str(
        exc_info.value) or "strategy-local flat buckets" in str(exc_info.value)


def test_shadow_percent_notional_arm_negative_candidate_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["shadow_percent_notional_arm"][
        "candidate_pcts"
    ] = [0.02, -0.05]
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "candidate_pcts" in str(exc_info.value)
    assert "positive percent" in str(exc_info.value)


def test_shadow_percent_notional_arm_zero_candidate_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["shadow_percent_notional_arm"][
        "candidate_pcts"
    ] = [0.02, 0.0]
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "candidate_pcts" in str(exc_info.value)
    assert "positive percent" in str(exc_info.value)


def test_shadow_percent_notional_arm_extra_field_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["shadow_percent_notional_arm"][
        "phantom"
    ] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "shadow_percent_notional_arm" in str(exc_info.value)
    assert "phantom" in str(exc_info.value)


def test_shadow_percent_notional_arm_missing_candidates_rejected_when_enabled(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    block = domains["execution_position"]["position_policy_sidecar"]["shadow_percent_notional_arm"]
    block["enabled"] = True
    block.pop("candidate_pcts", None)
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "shadow_percent_notional_arm" in str(exc_info.value)
    assert "candidate_pcts" in str(exc_info.value)


def test_shadow_percent_notional_arm_disabled_block_is_explicit_and_loads(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    block = domains["execution_position"]["position_policy_sidecar"]["shadow_percent_notional_arm"]
    block["enabled"] = False
    block["candidate_pcts"] = [0.02, 0.05]
    _write_yaml(domains_path, domains)

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()
    sidecar = cfg.domains.execution_position.position_policy_sidecar

    assert sidecar.shadow_percent_notional_arm.enabled is False
    assert sidecar.shadow_percent_notional_arm.candidate_pcts == [0.02, 0.05]
