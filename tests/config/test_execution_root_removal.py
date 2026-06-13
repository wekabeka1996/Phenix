"""
EX-REMOVE-ROOT-2026-05-09 focused tests.

Canonical source: trading.yaml -> trading.execution.*
Mirror removed: system.yaml:execution.*

These tests prove:
1. system.yaml has no root execution block
2. trading.yaml has the canonical execution block
3. Config loads correctly — cfg.execution is cfg.trading.execution (same object)
4. Loader guard rejects reintroduction of root execution in system.yaml
5. Model validator rejects root execution even when constructed directly
6. fsm_periodic_cleanup_enabled resolves only from trading.execution
7. allow_trade_with_guardian_tidy_only consumer path still works correctly
8. trading.execution missing fails closed
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

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

def test_system_yaml_has_no_root_execution_block() -> None:
    """system.yaml must not have an 'execution:' key at root (EX-REMOVE-ROOT-2026-05-09)."""
    payload = _load_yaml(CONFIG_DIR / "system.yaml")
    assert "execution" not in payload, (
        "system.yaml must not have root-level 'execution:' — "
        "canonical source is trading.yaml -> trading.execution.* (EX-REMOVE-ROOT-2026-05-09)"
    )


def test_trading_yaml_has_execution_block() -> None:
    """trading.yaml must have trading.execution.* (canonical source)."""
    payload = _load_yaml(CONFIG_DIR / "trading.yaml")
    trading_block = payload.get("trading", {})
    assert "execution" in trading_block, (
        "trading.yaml must declare trading.execution — "
        "this is the canonical source (EX-REMOVE-ROOT-2026-05-09)"
    )
    execution = trading_block["execution"]
    assert isinstance(execution, dict)
    # Spot-check essential fields are present
    assert "fsm_periodic_cleanup_enabled" in execution
    assert "order_guardian" in execution
    assert "allow_trade_with_guardian_tidy_only" in execution


# ---------------------------------------------------------------------------
# Normal load: alias correctness
# ---------------------------------------------------------------------------

def test_config_loads_from_trading_execution_as_sole_source() -> None:
    """Config loads cleanly; execution config comes from trading.execution."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.execution is not None
    assert cfg.trading.execution is not None


def test_cfg_execution_is_same_object_as_trading_execution() -> None:
    """cfg.execution IS cfg.trading.execution — same object, not a copy."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.execution is cfg.trading.execution, (
        "cfg.execution must be the same object as cfg.trading.execution — "
        "alias must not create a copy (EX-REMOVE-ROOT-2026-05-09)"
    )


def test_cfg_execution_fsm_cleanup_flag_matches_trading_execution() -> None:
    """cfg.execution.fsm_periodic_cleanup_enabled reads from trading.execution."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg.execution.fsm_periodic_cleanup_enabled == cfg.trading.execution.fsm_periodic_cleanup_enabled


# ---------------------------------------------------------------------------
# Fail-closed: loader guard rejects root execution block
# ---------------------------------------------------------------------------

def test_loader_guard_rejects_root_execution_in_system_yaml(
    tmp_path: Path,
) -> None:
    """If execution: is added back to system.yaml, config load must fail with the SSOT guard."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    # Re-introduce root execution block
    payload["execution"] = {
        "fsm_periodic_cleanup_enabled": False,
        "cooldown_after_close_ms": 60000,
        "anti_race_close_ms": 800,
        "fallback": None,
        "limit_orders": None,
        "orders": None,
        "allow_trade_with_guardian_tidy_only": False,
        "order_guardian": {"unified": True, "ledger_db_path": "data/order_ledger.db"},
        "manage": {"auto": True},
    }
    _write_yaml(system_path, payload)

    with pytest.raises(ConfigContractError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "execution" in message
    assert "EX-REMOVE-ROOT" in message or "trading.yaml" in message or "trading.execution" in message


def test_loader_guard_fires_even_when_root_execution_matches_trading_execution(
    tmp_path: Path,
) -> None:
    """Guard fires even when root execution values match trading.execution — no silent redundancy."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    trading_path = cfg_dir / "trading.yaml"

    # Read canonical trading.execution and copy it verbatim to system.yaml root
    trading = _load_yaml(trading_path)
    canonical_execution = trading["trading"]["execution"]

    system = _load_yaml(system_path)
    system["execution"] = canonical_execution
    _write_yaml(system_path, system)

    with pytest.raises(ConfigContractError):
        ConfigLoader(config_dir=cfg_dir).load_config()


# ---------------------------------------------------------------------------
# Fail-closed: missing canonical source
# ---------------------------------------------------------------------------

def test_trading_execution_missing_fails_closed(tmp_path: Path) -> None:
    """Removing trading.execution causes startup failure — fail-closed."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    del payload["trading"]["execution"]
    _write_yaml(trading_path, payload)

    with pytest.raises((ValidationError, Exception)):
        ConfigLoader(config_dir=cfg_dir).load_config()


def test_model_validator_rejects_root_execution_in_direct_construction() -> None:
    """Pydantic validator rejects execution != None at root, even without the loader."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    root_dict = cfg.model_dump(exclude_none=True)
    # Inject a non-None execution at root — should trigger the fail-closed guard
    root_dict["execution"] = cfg.trading.model_dump().get("execution")

    with pytest.raises(ValidationError) as exc_info:
        cm.AuroraConfig.model_validate(root_dict)

    message = str(exc_info.value)
    assert "split-brain" in message or "EX-REMOVE-ROOT" in message or "execution" in message.lower()


# ---------------------------------------------------------------------------
# config_resolver: fsm_periodic_cleanup_enabled from trading.execution only
# ---------------------------------------------------------------------------

def test_fsm_periodic_cleanup_enabled_resolves_from_trading_execution(
    tmp_path: Path,
) -> None:
    """fsm_periodic_cleanup_enabled resolves exclusively from trading.execution."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    # Explicitly set a distinct value to prove it's read from the right place
    payload["trading"]["execution"]["fsm_periodic_cleanup_enabled"] = True
    _write_yaml(trading_path, payload)

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()
    assert cfg.trading.execution.fsm_periodic_cleanup_enabled is True
    assert cfg.execution.fsm_periodic_cleanup_enabled is True

    from apps.reference.domains.execution_position.adapters.config_resolver import (
        ConfigResolverMixin,
    )

    class _Resolver(ConfigResolverMixin):
        def __init__(self, config: Any) -> None:
            self.config = config

    resolver = _Resolver(cfg)
    assert resolver._resolve_fsm_periodic_cleanup_enabled() is True


def test_fsm_cleanup_resolver_uses_only_trading_execution_not_root(
    tmp_path: Path,
) -> None:
    """Resolver reads trading.execution, ignoring any hypothetical root execution."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    from apps.reference.domains.execution_position.adapters.config_resolver import (
        ConfigResolverMixin,
    )

    class _Resolver(ConfigResolverMixin):
        def __init__(self, config: Any) -> None:
            self.config = config

    resolver = _Resolver(cfg)
    # The resolver should succeed and return the trading.execution value
    result = resolver._resolve_fsm_periodic_cleanup_enabled()
    assert isinstance(result, bool)
    assert result == cfg.trading.execution.fsm_periodic_cleanup_enabled


# ---------------------------------------------------------------------------
# event_handlers: allow_trade_with_guardian_tidy_only via trading.execution
# ---------------------------------------------------------------------------

def test_entry_tidy_gate_reads_allow_trade_flag_from_trading_execution(
    tmp_path: Path,
) -> None:
    """entry_tidy_gate_allow reads allow_trade_with_guardian_tidy_only from trading.execution."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    # Disable the flag (gate should return True — entries allowed by default)
    payload["trading"]["execution"]["allow_trade_with_guardian_tidy_only"] = False
    _write_yaml(trading_path, payload)

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()

    from apps.reference.domains.execution_position.orchestration.event_handlers import (
        EPEventHandlers,
    )

    mock_fsm = MagicMock()
    mock_fsm.config = cfg
    mock_fsm._symbol_last_tidy_ts = {}
    mock_fsm._last_entry_block_ts = {}
    mock_fsm._gate_metrics = {
        "gate_entry_allowed_tidy": 0, "gate_entry_blocked_tidy": 0}
    mock_fsm._guardian_cfg = {
        "cleanup_ttl_ms": 6000, "symbol_cooldown_ms": 4000}

    handlers = EPEventHandlers(mock_fsm)
    # allow_trade_with_guardian_tidy_only=False → gate is disabled → always allow
    assert handlers.entry_tidy_gate_allow("BTCUSDT") is True


def test_entry_tidy_gate_allow_trade_flag_enabled_blocks_without_tidy(
    tmp_path: Path,
) -> None:
    """With allow_trade_with_guardian_tidy_only=True and no tidy event, entry is blocked."""
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["execution"]["allow_trade_with_guardian_tidy_only"] = True
    _write_yaml(trading_path, payload)

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()
    assert cfg.trading.execution.allow_trade_with_guardian_tidy_only is True

    from apps.reference.domains.execution_position.orchestration.event_handlers import (
        EPEventHandlers,
    )

    mock_fsm = MagicMock()
    mock_fsm.config = cfg
    mock_fsm._symbol_last_tidy_ts = {}
    mock_fsm._last_entry_block_ts = {}
    mock_fsm._gate_metrics = {
        "gate_entry_allowed_tidy": 0, "gate_entry_blocked_tidy": 0}
    mock_fsm._guardian_cfg = {
        "cleanup_ttl_ms": 6000, "symbol_cooldown_ms": 4000}

    handlers = EPEventHandlers(mock_fsm)
    # No tidy event → last_tidy=0 → not fresh → no prior block → blocked
    assert handlers.entry_tidy_gate_allow("BTCUSDT") is False
