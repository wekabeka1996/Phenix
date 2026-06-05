"""Focused regression tests for LEV-REMOVE-DEFAULTS-2026-05-09.

Proves:
1. ExposureConfig no longer declares `leverage_defaults`
2. Config loads cleanly from YAML without `leverage_defaults`
3. Runtime leverage still resolves from instruments.<SYM>.execution.target_leverage
4. ExposureConfig still accepts a valid dict (extra='forbid' contract intact)
5. ExposureGuard.resolve_symbol_leverage reads only instruments — no regression
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import apps.reference.config_models as cm
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.guards.exposure_guard import ExposureGuard

CONFIG_DIR = Path("config/aurora")


# ---------------------------------------------------------------------------
# Model surface: leverage_defaults is gone
# ---------------------------------------------------------------------------

def test_exposure_config_has_no_leverage_defaults_field() -> None:
    """LEV-REMOVE-DEFAULTS-2026-05-09: leverage_defaults must not exist on ExposureConfig."""
    assert not hasattr(cm.ExposureConfig, "leverage_defaults") or \
        "leverage_defaults" not in cm.ExposureConfig.model_fields, (
        "ExposureConfig still declares leverage_defaults — "
        "LEV-REMOVE-DEFAULTS-2026-05-09 removal failed"
    )


def test_aurora_exposure_config_alias_has_no_leverage_defaults_field() -> None:
    """AuroraExposureConfig alias must also not expose leverage_defaults."""
    assert "leverage_defaults" not in cm.AuroraExposureConfig.model_fields, (
        "AuroraExposureConfig still declares leverage_defaults"
    )


def test_exposure_config_rejects_leverage_defaults_as_unknown_field() -> None:
    """extra='forbid': passing leverage_defaults to ExposureConfig raises ValidationError."""
    valid_kwargs = {
        "max_equity_utilization_pct": 0.30,
        "max_portfolio_fraction": 0.95,
        "max_directional_ratio": 20.0,
        "count_pending_orders": True,
        "exclude_reduce_only": True,
    }
    with pytest.raises(ValidationError) as exc_info:
        cm.ExposureConfig(
            **valid_kwargs, leverage_defaults={"__default__": 20})
    msg = str(exc_info.value)
    assert "leverage_defaults" in msg


def test_exposure_config_valid_without_leverage_defaults() -> None:
    """ExposureConfig constructs cleanly with no leverage_defaults key."""
    config = cm.ExposureConfig(
        max_equity_utilization_pct=0.30,
        max_portfolio_fraction=0.95,
        max_directional_ratio=20.0,
        count_pending_orders=True,
        exclude_reduce_only=True,
    )
    assert config.count_pending_orders is True
    assert config.exclude_reduce_only is True
    assert not hasattr(config, "leverage_defaults")


# ---------------------------------------------------------------------------
# YAML round-trip: config loads without leverage_defaults
# ---------------------------------------------------------------------------

def test_config_loads_without_leverage_defaults() -> None:
    """Config loads successfully from YAML after leverage_defaults removal."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    assert cfg is not None
    assert cfg.trading is not None
    assert cfg.trading.execution is not None
    assert cfg.trading.execution.exposure is not None


def test_exposure_config_loaded_has_no_leverage_defaults() -> None:
    """Loaded config.trading.execution.exposure has no leverage_defaults attribute."""
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    exposure = cfg.trading.execution.exposure
    assert "leverage_defaults" not in exposure.model_fields, (
        "YAML round-trip produced ExposureConfig with leverage_defaults — "
        "field removal incomplete"
    )


# ---------------------------------------------------------------------------
# Runtime leverage resolution: instruments SSOT unaffected
# ---------------------------------------------------------------------------

def test_resolve_symbol_leverage_btcusdt_reads_from_instruments() -> None:
    """ExposureGuard.resolve_symbol_leverage reads instruments.BTCUSDT.execution.target_leverage=25."""
    from unittest.mock import MagicMock
    from decimal import Decimal

    cfg = ConfigLoader(CONFIG_DIR).load_config()
    guard = ExposureGuard(fsm_core=MagicMock(), config=cfg)

    lev = guard.resolve_symbol_leverage("BTCUSDT")
    assert lev == Decimal("25"), (
        f"BTCUSDT leverage resolved to {lev}, expected 25 from instruments.yaml"
    )


def test_resolve_symbol_leverage_dogeusdt_reads_from_instruments() -> None:
    """ExposureGuard.resolve_symbol_leverage reads instruments.DOGEUSDT.execution.target_leverage=10."""
    from unittest.mock import MagicMock
    from decimal import Decimal

    cfg = ConfigLoader(CONFIG_DIR).load_config()
    guard = ExposureGuard(fsm_core=MagicMock(), config=cfg)

    lev = guard.resolve_symbol_leverage("DOGEUSDT")
    assert lev == Decimal("10"), (
        f"DOGEUSDT leverage resolved to {lev}, expected 10 from instruments.yaml"
    )


def test_resolve_symbol_leverage_does_not_use_leverage_defaults() -> None:
    """resolve_symbol_leverage does not read from trading.execution.exposure — only instruments."""
    from unittest.mock import MagicMock
    from decimal import Decimal

    cfg = ConfigLoader(CONFIG_DIR).load_config()
    guard = ExposureGuard(fsm_core=MagicMock(), config=cfg)

    # Prove BTCUSDT returns 25 (instruments.yaml), not 20 (old leverage_defaults value).
    # If leverage_defaults were still the source, it would have returned 20.
    lev = guard.resolve_symbol_leverage("BTCUSDT")
    assert lev != Decimal("20"), (
        "BTCUSDT leverage is 20 — suspect leverage_defaults regression. "
        "Expected 25 from instruments.yaml (target_leverage=25)."
    )
    assert lev == Decimal("25")
