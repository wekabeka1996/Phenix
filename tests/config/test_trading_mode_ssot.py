"""
T-TMODE-SSOT-2026-05-09 focused tests.

Canonical source: system.yaml:trading_mode (root)
Mirror removed: trading.yaml:trading.mode

These tests prove:
1. YAML structure is correct (system.yaml has it, trading.yaml does not)
2. Config loads correctly with single canonical source
3. trading.mode in trading.yaml is rejected fail-closed
4. trading_mode absent from system.yaml fails closed
5. cfg.trading.mode is injected correctly from the canonical source
6. The consistency validator rejects direct-construction mismatches
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader, ConfigContractError
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")


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
# YAML structural checks
# ---------------------------------------------------------------------------

def test_system_yaml_has_root_trading_mode() -> None:
    """Canonical source (system.yaml:trading_mode) must be present."""
    payload = _load_yaml(CONFIG_DIR / "system.yaml")
    assert "trading_mode" in payload, "system.yaml must have root-level trading_mode"
    mode = payload["trading_mode"]
    assert isinstance(
        mode, str) and mode, "trading_mode must be a non-empty string"


def test_trading_yaml_has_no_mode_field() -> None:
    """T-TMODE-SSOT: trading.mode must NOT be declared in trading.yaml."""
    payload = _load_yaml(CONFIG_DIR / "trading.yaml")
    trading_block = payload.get("trading", {})
    assert "mode" not in trading_block, (
        "trading.yaml must not have trading.mode — "
        "canonical source is system.yaml:trading_mode (T-TMODE-SSOT-2026-05-09)"
    )


# ---------------------------------------------------------------------------
# Normal load: injection correctness
# ---------------------------------------------------------------------------

def test_config_loads_with_single_canonical_trading_mode() -> None:
    """Config loads cleanly; trading_mode from system.yaml propagates to cfg.trading.mode."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert isinstance(cfg.trading_mode, str)
    assert cfg.trading_mode == "hybrid_live_data_testnet_exec"


def test_cfg_trading_mode_injected_into_trading_block() -> None:
    """After load, cfg.trading.mode must equal cfg.trading_mode (injected by loader)."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.trading.mode == cfg.trading_mode, (
        f"cfg.trading.mode ({cfg.trading.mode!r}) must equal cfg.trading_mode ({cfg.trading_mode!r}). "
        "Loader must inject trading.mode from system.yaml:trading_mode."
    )


# ---------------------------------------------------------------------------
# Fail-closed: guard rejects trading.mode in trading.yaml
# ---------------------------------------------------------------------------

def test_trading_mode_split_brain_rejected_if_trading_yaml_has_mode(
    tmp_path: Path,
) -> None:
    """If mode: is added to trading.yaml, config load must fail with the SSOT guard."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["mode"] = "hybrid_live_data_testnet_exec"
    _write_yaml(trading_path, payload)

    with pytest.raises(ConfigContractError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "trading.mode" in message
    assert "T-TMODE-SSOT" in message or "trading.yaml" in message


def test_trading_mode_split_brain_rejected_even_when_values_match(
    tmp_path: Path,
) -> None:
    """Guard fires even when both values are identical — no silent redundancy allowed."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    system_path = cfg_dir / "system.yaml"

    system = _load_yaml(system_path)
    canonical_mode = system["trading_mode"]

    trading = _load_yaml(trading_path)
    # Exactly matching — still rejected
    trading["trading"]["mode"] = canonical_mode
    _write_yaml(trading_path, trading)

    with pytest.raises(ConfigContractError):
        ConfigLoader(config_dir=cfg_dir).load_config()


# ---------------------------------------------------------------------------
# Fail-closed: missing canonical source
# ---------------------------------------------------------------------------

def test_trading_mode_missing_from_system_yaml_fails_closed(
    tmp_path: Path,
) -> None:
    """Removing trading_mode from system.yaml causes a validation failure at startup."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    del payload["trading_mode"]
    _write_yaml(system_path, payload)

    with pytest.raises((ValidationError, ConfigContractError)):
        ConfigLoader(config_dir=cfg_dir).load_config()


def test_trading_mode_invalid_value_fails_closed(tmp_path: Path) -> None:
    """An invalid trading_mode value in system.yaml fails at Pydantic validation."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    payload["trading_mode"] = "not_a_valid_mode"
    _write_yaml(system_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "trading_mode" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Fail-closed: consistency validator on direct model construction
# ---------------------------------------------------------------------------

def test_consistency_validator_fails_on_mismatch_in_direct_construction(
    tmp_path: Path,
) -> None:
    """Pydantic validator rejects trading.mode != trading_mode even without the loader."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    # Build a TradingConfig with a deliberately mismatched mode
    trading_dict = cfg.trading.model_dump()
    trading_dict["mode"] = "testnet"  # Differs from cfg.trading_mode

    root_dict = cfg.model_dump()
    root_dict["trading"] = trading_dict
    # trading_mode remains "hybrid_live_data_testnet_exec"

    with pytest.raises(ValidationError) as exc_info:
        cm.AuroraConfig.model_validate(root_dict)

    message = str(exc_info.value)
    assert "diverges from trading_mode" in message or "trading.mode" in message.lower()


# ---------------------------------------------------------------------------
# Different valid modes load correctly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["testnet", "hybrid_live_data_testnet_exec", "backtest"])
def test_valid_trading_modes_load_correctly(tmp_path: Path, mode: str) -> None:
    """system.yaml:trading_mode accepts all valid mode values."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    payload["trading_mode"] = mode
    _write_yaml(system_path, payload)

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()
    assert cfg.trading_mode == mode
    assert cfg.trading.mode == mode
