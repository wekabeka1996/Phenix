#!/usr/bin/env python3
"""Dynamic trading config smoke check using AuroraConfig + config v2 resolvers."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.reference.config_decision import resolve_decision_policy
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.config_features import resolve_feature_engineering_config
from apps.reference.config_loader import ConfigLoader
from apps.reference.config_regimes import resolve_regime_detector_config
from apps.reference.config_risk import resolve_daily_risk_state
from apps.reference.config_sizing import resolve_sizing_policy
from apps.reference.config_symbols import get_trading_symbols, resolve_instrument_profile
from tools.config_validator_v2 import format_validation_summary, validate_config_v2


@pytest.fixture(scope="module")
def aurora_cfg():
    """Load AuroraConfig from the config/v2 root and gate it via the validator."""
    project_root = Path(__file__).resolve().parents[1]
    validation_report = validate_config_v2(project_root / "config")
    assert validation_report["status"] == "ok", (
        f"Config v2 validation failed:\n{format_validation_summary(validation_report)}"
    )

    loader = ConfigLoader(config_dir=project_root / "config")
    return loader.load_config()


def _pick_symbol(cfg) -> str:
    symbols = get_trading_symbols()
    if symbols:
        return symbols[0]
    legacy_symbols = ((getattr(cfg.trading, "instruments", {}) or {}))
    if isinstance(legacy_symbols, dict):
        for candidate in legacy_symbols.keys():
            return candidate
    return "BTCUSDT"


def test_dynamic_integration_config_loads(aurora_cfg):
    assert aurora_cfg.trading_mode, "AuroraConfig should expose a trading mode"
    assert aurora_cfg.config_v2 is not None, "config_v2 payload must be attached"


@pytest.mark.integration
def test_dynamic_integration_resolvers_use_config_v2(aurora_cfg):
    symbol = _pick_symbol(aurora_cfg)
    exposure_policy = resolve_exposure_policy(aurora_cfg)
    decision_policy = resolve_decision_policy(aurora_cfg)
    sizing_policy = resolve_sizing_policy(
        aurora_cfg, symbol=symbol, regime="NORMAL"
    )
    instrument_profile = resolve_instrument_profile(aurora_cfg, symbol)
    risk_state = resolve_daily_risk_state(aurora_cfg)
    features_cfg = resolve_feature_engineering_config(aurora_cfg)
    regime_cfg = resolve_regime_detector_config(aurora_cfg)

    assert exposure_policy.source == "config_v2"
    assert decision_policy.source == "config_v2"
    assert sizing_policy.source == "config_v2"
    assert instrument_profile.source == "config_v2"
    assert getattr(risk_state, "source", "config_v2") == "config_v2"
    assert features_cfg.source == "config_v2"
    assert regime_cfg.source == "config_v2"

    # Sanity-check a couple of concrete datapoints to ensure we are not reading defaults
    reservations = getattr(exposure_policy, "reservations", None)
    assert reservations is not None, "Exposure reservations must be populated"
    assert reservations.pending_ttl_sec != 90, "Pending TTL should originate from v2 overrides"
    assert sizing_policy.max_risk_pct > 0
    assert instrument_profile.min_qty > 0


def test_dynamic_integration_supports_domain_imports():
    """Ensure critical domain modules remain importable under config v2."""
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking  # noqa: F401
    from apps.reference.domains.decision_making.decision_making import DecisionMaking  # noqa: F401
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector  # noqa: F401

    # If imports succeed pytest will keep the test green; no runtime side effects needed.
    assert PositionTracking is not None
    assert DecisionMaking is not None
    assert RegimeDetector is not None
