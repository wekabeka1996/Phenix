from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from apps.reference.domains.neocortex.config_models import load_config


CONFIG_DIR = Path("apps/reference/domains/neocortex/config")


def _write_system_yaml(
    tmp_path: Path,
    *,
    trust_enabled: bool,
    authority_mode: str,
    evidence_mode: str,
) -> Path:
    cfg_dir = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    system_path = cfg_dir / "system.yaml"
    data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    data["trust_enabled"] = trust_enabled
    data["authority"]["mode"] = authority_mode
    data["evidence_capture"]["mode"] = evidence_mode
    data["evidence_capture"]["collect_observation"] = True
    data["evidence_capture"]["collect_authority_request"] = True
    data["evidence_capture"]["collect_authority_response"] = True
    data["evidence_capture"]["emit_shadow_decision_logged"] = True
    system_path.write_text(yaml.safe_dump(
        data, sort_keys=False), encoding="utf-8")
    return cfg_dir


def test_load_config_accepts_shadow_counterfactual_when_shadow_and_trust_disabled(
    tmp_path: Path,
) -> None:
    cfg_dir = _write_system_yaml(
        tmp_path,
        trust_enabled=False,
        authority_mode="shadow",
        evidence_mode="shadow_counterfactual",
    )

    config = load_config(cfg_dir)

    assert config.evidence_capture.mode == "shadow_counterfactual"
    assert config.authority.mode == "shadow"
    assert config.trust_enabled is False


def test_load_config_rejects_shadow_counterfactual_when_trust_enabled(
    tmp_path: Path,
) -> None:
    cfg_dir = _write_system_yaml(
        tmp_path,
        trust_enabled=True,
        authority_mode="shadow",
        evidence_mode="shadow_counterfactual",
    )

    with pytest.raises(
        ValueError,
        match="evidence_capture.mode='shadow_counterfactual' requires trust_enabled=false",
    ):
        load_config(cfg_dir)


def test_load_config_rejects_shadow_counterfactual_when_authority_not_shadow(
    tmp_path: Path,
) -> None:
    cfg_dir = _write_system_yaml(
        tmp_path,
        trust_enabled=False,
        authority_mode="advisory",
        evidence_mode="shadow_counterfactual",
    )

    with pytest.raises(
        ValueError,
        match="evidence_capture.mode='shadow_counterfactual' requires authority.mode='shadow'",
    ):
        load_config(cfg_dir)
