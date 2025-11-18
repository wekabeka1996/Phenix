"""Tests for execution.manage.mode validations (OCO-11.12.A)."""

from __future__ import annotations

import pytest
from vfoundation.errors import ConfigError

from apps.reference.domains.execution_position.manage_config import (
    clear_manage_config_cache,
    resolve_execution_manage_config,
)


@pytest.fixture(autouse=True)
def _clear_manage_cache() -> None:
    clear_manage_config_cache()
    yield
    clear_manage_config_cache()


def _base_cfg() -> dict:
    return {
        "config_v2": {
            "domains": {
                "execution": {
                    "manage": {
                        "auto": True,
                    }
                }
            }
        }
    }


def _manage_node(cfg: dict) -> dict:
    return cfg["config_v2"]["domains"]["execution"]["manage"]


def _aggregated_brackets(**agg_overrides: object) -> dict:
    aggregated = {
        "enable": True,
        "aggregated_oco": {
            "enabled": True,
            "aggregated_only_mode": True,
            "recalc_on_scale_in": True,
            "recalc_on_partial_close": True,
            "allow_unprotected_position": False,
        },
    }
    aggregated["aggregated_oco"].update(agg_overrides)
    aggregated.setdefault("sl", {"fixed_bps": 50})
    aggregated.setdefault("tp", {"fixed_bps": 100})
    return aggregated


def test_mode_aggregated_only_valid() -> None:
    cfg = _base_cfg()
    manage = _manage_node(cfg)
    manage["mode"] = "aggregated_only"
    manage["brackets"] = _aggregated_brackets()

    resolved = resolve_execution_manage_config(cfg)

    assert resolved.mode == "aggregated_only"
    assert resolved.brackets.aggregated_oco.enabled is True


def test_mode_legacy_valid_without_aggregated_oco() -> None:
    cfg = _base_cfg()
    manage = _manage_node(cfg)
    manage["mode"] = "legacy"
    manage["brackets"] = {"enable": True}

    resolved = resolve_execution_manage_config(cfg)

    assert resolved.mode == "legacy"
    assert resolved.brackets.aggregated_oco.enabled is False


def test_mode_inferred_as_aggregated_only_when_not_set() -> None:
    cfg = _base_cfg()
    manage = _manage_node(cfg)
    manage["brackets"] = _aggregated_brackets()

    resolved = resolve_execution_manage_config(cfg)

    assert resolved.mode == "aggregated_only"
    assert resolved.brackets.aggregated_oco.enabled is True


def test_aggregated_only_rejects_allow_unprotected_position() -> None:
    cfg = _base_cfg()
    manage = _manage_node(cfg)
    manage["mode"] = "aggregated_only"
    manage["brackets"] = _aggregated_brackets(allow_unprotected_position=True)

    with pytest.raises(ConfigError):
        resolve_execution_manage_config(cfg)


def test_legacy_mode_rejects_aggregated_oco_enabled() -> None:
    cfg = _base_cfg()
    manage = _manage_node(cfg)
    manage["mode"] = "legacy"
    manage["brackets"] = _aggregated_brackets()

    with pytest.raises(ConfigError):
        resolve_execution_manage_config(cfg)


def test_aggregated_only_requires_recalc_on_partial_close() -> None:
    cfg = _base_cfg()
    manage = _manage_node(cfg)
    manage["mode"] = "aggregated_only"
    manage["brackets"] = _aggregated_brackets(recalc_on_partial_close=False)

    with pytest.raises(ConfigError):
        resolve_execution_manage_config(cfg)
