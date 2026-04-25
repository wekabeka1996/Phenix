import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.domains.decision_making as domain_dm
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")
ARTIFACT = (
    Path(__file__).resolve().parent
    / "_artifacts"
    / "decision_making_contract.generated.json"
)


@pytest.fixture(scope="module")
def frozen_manifest() -> dict[str, Any]:
    assert ARTIFACT.exists(), (
        f"Frozen decision_making contract not found at {ARTIFACT}. "
        "Regenerate only when the roadmap explicitly authorizes a package contract update."
    )
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _serialize_default(field_info: Any) -> str:
    if field_info.is_required():
        return repr("<required>")

    default = field_info.default
    if isinstance(default, list):
        return "list"
    if isinstance(default, dict):
        return "dict"
    if isinstance(default, set):
        return type(default).__name__
    return repr(default)


def _serialize_default_factory(field_info: Any) -> str | None:
    if field_info.default_factory is None:
        return None
    return field_info.default_factory.__name__


def _assert_model_contract(model_cls: type, snapshot: dict[str, Any]) -> None:
    fields = model_cls.model_fields

    assert model_cls.model_config.get("extra") == snapshot["extra"]
    assert set(fields) == set(snapshot["fields"])

    for field_name, expected in snapshot["fields"].items():
        field_info = fields[field_name]
        assert field_info.is_required() is expected["required"], (
            f"{model_cls.__name__}.{field_name} required drift"
        )
        assert _serialize_default(field_info) == expected["default"], (
            f"{model_cls.__name__}.{field_name} default drift"
        )
        assert _serialize_default_factory(field_info) == expected["default_factory"], (
            f"{model_cls.__name__}.{field_name} default_factory drift"
        )


def test_decision_making_facade_reexports_are_exact_identity(
    frozen_manifest: dict[str, Any],
) -> None:
    for name in frozen_manifest:
        assert getattr(cm, name) is getattr(domain_dm, name)


def test_decision_making_extraction_preserves_field_contract(
    frozen_manifest: dict[str, Any],
) -> None:
    for name, snapshot in frozen_manifest.items():
        _assert_model_contract(getattr(cm, name), snapshot)


def test_current_aurora_config_loads_decision_making_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    dm_domain = cfg.domains.decision_making
    assert dm_domain.entry_plan.enabled is True
    assert dm_domain.entry_plan.atr_period == 14
    assert dm_domain.entry_plan.entry_k_atr == 0.3
    assert dm_domain.entry_plan.sl_k_atr == 1.5
    assert dm_domain.entry_plan.tp_k_atr == 2.0
    assert dm_domain.entry_plan.structural_stop_enabled is False
    assert dm_domain.entry_plan.min_stop_bps == 15
    assert dm_domain.flip.enabled is False
    assert dm_domain.risk_skew.max_skew_sec == 5
    assert dm_domain.arming.require_regime_warmup is True
    assert dm_domain.directional_sanity.min_regime_confidence == 0.42
    assert dm_domain.price_motion_sanity.pm_norm_clip_abs == 10.0
    assert set(dm_domain.degraded_context_contracts_by_strategy) == {
        "aurora",
        "mean_reversion",
        "md_amr",
    }

    fe = cfg.domains.feature_engineering
    assert fe.readiness_registry is not None
    assert "macro_resid" in fe.readiness_registry.declared_keys
    assert fe.warmup is not None
    assert fe.warmup.enforcement_mode == "fail_fast"
    assert fe.warmup.degraded_allowed_strategies == ["md_amr"]

    aurora = cfg.strategies.aurora
    assert aurora.safety_gates.enabled is True
    assert aurora.safety_gates.system_stress_policy == "attenuate"
    assert aurora.safety_gates.stress_attenuation_factor == 0.5

    decision = aurora.decision
    assert decision.testnet is not None
    assert decision.testnet.signal_threshold == 0.162
    assert decision.production is not None
    assert decision.production.signal_threshold == 0.162
    assert decision.signal_threshold == 0.162
    assert decision.mean_reversion is None
    assert decision.scoring_version == "quadratic"
    assert decision.decision_geometry is not None
    assert decision.decision_geometry.admission_mode == "linear"
    assert decision.decision_geometry.sizing_mode == "quadratic"
    assert decision.scoring_engine is not None
    assert decision.scoring_engine.shield_enabled is True
    assert decision.scoring_engine.danger_zone_shield.vol_threshold == 0.98
    assert (
        decision.scoring_engine.context_shield.regime_multipliers["HIGH_VOLATILITY"]
        == 0.30
    )
    assert decision.scoring_engine.memory_shield.unknown_threshold == 10
    assert decision.holding_period is not None
    assert decision.holding_period.enabled is True
    assert decision.holding_period.min_duration_sec == 900
    assert decision.gates is not None
    assert decision.gates.enabled is True
    assert decision.gates.anti_flat_sigma == 0.48
    assert decision.gates.motion_window_sec == 300

    assert cfg.instruments["SOLUSDT"].flip.enabled is True
    assert cfg.instruments["SOLUSDT"].flip.hysteresis_mult == 1.3
    assert cfg.instruments["BTCUSDT"].flip.enabled is True
    assert cfg.instruments["BTCUSDT"].flip.hysteresis_mult == 3.0


def test_decision_making_yaml_contract_fails_closed_on_forbidden_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"]["unexpected_pkg7_field"] = True
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg7_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_decision_making_yaml_contract_fails_closed_on_invalid_decision_geometry(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    strategy_path = cfg_dir / "strategies" / "aurora.yaml"
    strategy = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))
    strategy["aurora"]["decision"]["decision_geometry"]["admission_mode"] = "soft_power"
    strategy_path.write_text(
        yaml.safe_dump(strategy, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "admission_power" in message
    assert "soft_power" in message


def test_decision_making_yaml_contract_fails_closed_on_missing_flip_hysteresis(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    instruments_path = cfg_dir / "instruments.yaml"
    instruments = yaml.safe_load(instruments_path.read_text(encoding="utf-8"))
    del instruments["instruments"]["BTCUSDT"]["flip"]["hysteresis_mult"]
    instruments_path.write_text(
        yaml.safe_dump(instruments, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "hysteresis_mult" in message
    assert "field required" in message.lower()
