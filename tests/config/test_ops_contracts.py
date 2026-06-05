from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.system.ops as system_ops
import apps.reference.config_models as cm
from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
from vfoundation.core.protocol import Message


CONFIG_DIR = Path("config/aurora")


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _annotation_includes(tp: Any, expected: Any) -> bool:
    return tp is expected or expected in get_args(tp)


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    optional_fields: set[str] | None = None,
) -> None:
    optional_fields = optional_fields or set()
    fields = model_cls.model_fields
    expected_fields = required | set(defaults)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay required"
        )
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay optional/defaulted"
        )
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name in optional_fields:
        assert _is_optional_union(fields[name].annotation), (
            f"{model_cls.__name__}.{name} must stay Optional in the extraction contract"
        )


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Module-level structure
# ---------------------------------------------------------------------------

def test_ops_facade_reexport_is_exact_identity() -> None:
    assert cm.OpsConfig is system_ops.OpsConfig


def test_ops_canonical_definition_lives_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    module_source = Path(system_ops.__file__).read_text(encoding="utf-8")
    marker = "\nclass OpsConfig("

    assert facade_source.count(marker) == 0, (
        "OpsConfig should no longer be defined in config_models.py after Phase 4 / Pkg 2 extraction."
    )
    assert module_source.count(marker) == 1, (
        "OpsConfig must have exactly one top-level definition in apps.reference.config.system.ops."
    )


def test_ops_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        cm.OpsConfig,
        required={"panic_killswitch", "metrics_url", "reports_dir"},
        defaults={},
        optional_fields={"metrics_url", "reports_dir"},
    )

    fields = cm.OpsConfig.model_fields
    assert fields["panic_killswitch"].annotation is bool


def test_ops_extraction_preserves_assembly_annotations() -> None:
    trading_fields = cm.TradingConfig.model_fields
    aurora_fields = cm.AuroraConfig.model_fields

    assert _annotation_includes(trading_fields["ops"].annotation, cm.OpsConfig)
    # T-OPS-SSOT-2026-05-09: AuroraConfig.ops is now Optional (alias from trading.ops)
    assert _annotation_includes(aurora_fields["ops"].annotation, cm.OpsConfig), (
        "AuroraConfig.ops must include OpsConfig in its annotation (Optional[OpsConfig])"
    )
    assert _is_optional_union(aurora_fields["ops"].annotation), (
        "AuroraConfig.ops must be Optional after T-OPS-SSOT-2026-05-09 repair"
    )


# ---------------------------------------------------------------------------
# SSOT structural checks: system.yaml must NOT have root ops
# ---------------------------------------------------------------------------

def test_system_yaml_has_no_root_ops_block() -> None:
    """T-OPS-SSOT-2026-05-09: ops block must be absent from system.yaml root."""
    payload = _load_yaml(CONFIG_DIR / "system.yaml")
    assert "ops" not in payload, (
        "system.yaml must not have a root-level ops block. "
        "Canonical source: trading.yaml -> trading.ops.*"
    )


def test_trading_yaml_has_ops_block() -> None:
    """Canonical ops source (trading.yaml -> trading.ops.*) must be present."""
    payload = _load_yaml(CONFIG_DIR / "trading.yaml")
    trading = payload.get("trading", {})
    assert "ops" in trading, "trading.yaml must contain trading.ops.*"
    ops = trading["ops"]
    assert "panic_killswitch" in ops
    assert "metrics_url" in ops
    assert "reports_dir" in ops


# ---------------------------------------------------------------------------
# Runtime load: alias correctness
# ---------------------------------------------------------------------------

def test_current_aurora_config_loads_ops_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    # cfg.ops is populated via alias from trading.ops
    assert type(cfg.ops) is cm.OpsConfig
    assert cfg.ops.panic_killswitch is False
    assert cfg.ops.metrics_url == "http://127.0.0.1:8000/metrics"
    assert cfg.ops.reports_dir == "reports"

    # cfg.trading.ops is the canonical source
    assert type(cfg.trading.ops) is cm.OpsConfig
    assert cfg.trading.ops.panic_killswitch is False
    assert cfg.trading.ops.metrics_url == "http://127.0.0.1:8000/metrics"
    assert cfg.trading.ops.reports_dir == "reports"


def test_ops_alias_is_same_object_as_trading_ops() -> None:
    """After T-OPS-SSOT-2026-05-09 repair, cfg.ops must be the exact same object as cfg.trading.ops."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.ops is cfg.trading.ops, (
        "cfg.ops must be aliased from cfg.trading.ops (same object). "
        "If this fails, the _alias_ops_from_trading_ops validator is broken."
    )


def test_ops_runtime_import_smoke() -> None:
    modules = {
        name: importlib.import_module(name)
        for name in (
            "apps.reference.config_models",
            "apps.reference.config.system.ops",
            "apps.reference.config.system.observability",
            "apps.reference.config_loader",
            "apps.reference.domains.execution_position.flows.open.fsm_open",
        )
    }

    assert hasattr(modules["apps.reference.config.system.ops"], "OpsConfig")
    assert hasattr(
        modules["apps.reference.domains.execution_position.flows.open.fsm_open"], "OpenFlowFSM")


# ---------------------------------------------------------------------------
# Fail-closed: split-brain detection
# ---------------------------------------------------------------------------

def test_ops_split_brain_rejected_when_root_ops_present_in_system_yaml(
    tmp_path: Path,
) -> None:
    """If ops block is re-added to system.yaml, config load must fail with split-brain error."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    # Simulate someone accidentally adding ops back to system.yaml
    payload["ops"] = {
        "panic_killswitch": False,
        "metrics_url": "http://127.0.0.1:8000/metrics",
        "reports_dir": "reports",
    }
    _write_yaml(system_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "split-brain" in message or "T-OPS-SSOT" in message, (
        f"Expected split-brain error, got: {message}"
    )


def test_ops_missing_trading_ops_fails_closed(tmp_path: Path) -> None:
    """Removing trading.ops from trading.yaml must fail closed at startup."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    del payload["trading"]["ops"]
    _write_yaml(trading_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "trading.ops" in message, (
        f"Expected trading.ops missing error, got: {message}"
    )


# ---------------------------------------------------------------------------
# Fail-closed: canonical path (trading.ops) field contract
# ---------------------------------------------------------------------------

def test_ops_yaml_contract_fails_closed_on_forbidden_trading_ops_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["ops"]["unexpected_pkg2_trading_ops_field"] = True
    _write_yaml(trading_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg2_trading_ops_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_ops_yaml_contract_fails_closed_on_invalid_trading_ops_panic_killswitch_type(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["ops"]["panic_killswitch"] = ["not", "a", "bool"]
    _write_yaml(trading_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "panic_killswitch" in message
    assert "bool" in message.lower()


# ---------------------------------------------------------------------------
# Runtime gate: panic_killswitch blocks CMD:OPEN
# ---------------------------------------------------------------------------

def test_panic_killswitch_runtime_gate_still_blocks_new_open_when_enabled() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    panic_cfg = cfg.ops.model_copy(update={"panic_killswitch": True})
    trading_with_panic = cfg.trading.model_copy(update={
        "ops": cfg.trading.ops.model_copy(update={"panic_killswitch": True})
    })
    cfg = cfg.model_copy(update={
        "ops": panic_cfg,
        "trading": trading_with_panic,
    })

    fsm = OpenFlowFSM(config=cfg)
    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="ops-panic-rid",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "price": "42000.0",
            "order_type": "LIMIT",
            "idempotent_key": "ops-panic-key",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert result.why == "PANIC_KILLSWITCH"
    assert "panic active" in str(result.pld.get("reason", ""))
