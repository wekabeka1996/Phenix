"""
Tests for config_validator_v2.py
"""

import json
import os
import sys
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock


sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from apps.reference.config_loader import load_config
from apps.reference.config_models import ConfigV2
from tools.config_validator_v2 import validate_config_v2, validate_config_v2_schema
import tools.config_validator_v2 as config_validator


def _configure_valid_domain_mocks(
    mock_exposure,
    mock_brackets,
    mock_risk,
    mock_risk_soft,
    mock_risk_weights,
    mock_risk_thresholds,
    mock_sizing,
    mock_decision,
    mock_symbols,
    mock_profile,
    mock_modes,
    mock_domain_mode,
):
    """Populate resolver patches with valid defaults."""
    exposure = MagicMock()
    exposure.source = "config_v2"
    exposure.caps = SimpleNamespace(
        max_equity_utilization_ratio=200.0,
        max_portfolio_fraction=2.0,
        max_directional_ratio=2.0,
    )
    exposure.reservations = SimpleNamespace(
        pending_ttl_sec=45,
        post_fill_hold_ttl_sec=10,
        positions_stale_ttl_sec=3,
    )
    mock_exposure.return_value = exposure

    brackets = MagicMock()
    brackets.source = "config_v2"
    brackets.tp_bps = 10
    brackets.sl_bps = 5
    mock_brackets.return_value = brackets

    risk = MagicMock()
    risk.cfg.max_realized_loss_usd = 250
    risk.cfg.max_drawdown_pct = 8
    mock_risk.return_value = risk

    risk_soft = SimpleNamespace(
        mode="clip",
        clip_min_notional_usdt=10.0,
        directional_ratio_max=3.0,
        side_exposure_usdt=600.0,
        margin_exposure_usdt=1100.0,
        source="config_v2",
    )
    mock_risk_soft.return_value = risk_soft

    risk_weights = SimpleNamespace(
        delta_price_pct=0.05,
        obi=0.35,
        tfi=0.35,
        absorption_inverse=0.25,
        source="config_v2",
    )
    mock_risk_weights.return_value = risk_weights

    thresholds = SimpleNamespace(
        max_risk_score=0.9,
        overrides={"testnet": 0.87, "production": 0.8},
        source="config_v2",
        for_profile=lambda profile: 0.87 if profile == "testnet" else 0.8,
    )
    mock_risk_thresholds.return_value = thresholds

    sizing = MagicMock()
    sizing.max_risk_pct = 1.0
    sizing.max_risk_usd = 50
    sizing.min_notional_usd = 10
    sizing.max_notional_usd = 10000
    mock_sizing.return_value = sizing

    decision = MagicMock()
    decision.signal_threshold = 0.1
    decision.neutral_threshold = 0.3
    mock_decision.return_value = decision

    mock_symbols.return_value = ["BTCUSDT"]

    profile = MagicMock()
    profile.min_notional = 10
    profile.min_qty = 0.001
    profile.min_price = 0.01
    profile.max_leverage = 20
    mock_profile.return_value = profile

    modes = MagicMock()
    modes.for_domain = MagicMock(return_value="testnet")
    modes.profile = "full_testnet"
    mock_modes.return_value = modes
    mock_domain_mode.return_value = "testnet"


class TestConfigValidatorV2:
    """Test suite for config v2 validator."""

    def test_valid_config(self):
        """Test validation with valid config."""
        # Mock reload_config to return a valid config
        with patch('tools.config_validator_v2.reload_config') as mock_reload:
            mock_cfg = MagicMock()
            # Mock all resolvers to return valid objects
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.resolve_feature_engineering_config') as mock_features, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                # Setup mocks
                mock_reload.return_value = mock_cfg

                # Exposure policy
                exposure = MagicMock()
                exposure.source = "config_v2"
                exposure.caps.max_equity_utilization_ratio = 200.0  # Testnet value
                exposure.caps.max_portfolio_fraction = 2.0  # Allow >1
                exposure.caps.max_directional_ratio = 2.0
                exposure.reservations = SimpleNamespace(
                    pending_ttl_sec=45,
                    post_fill_hold_ttl_sec=10,
                    positions_stale_ttl_sec=3,
                )
                mock_exposure.return_value = exposure

                # Brackets config
                brackets = MagicMock()
                brackets.source = "config_v2"
                brackets.tp_bps = 10
                brackets.sl_bps = 5
                mock_brackets.return_value = brackets

                # Risk resolvers
                risk = MagicMock()
                risk.cfg.max_realized_loss_usd = 250
                risk.cfg.max_drawdown_pct = 8
                mock_risk.return_value = risk

                mock_risk_soft.return_value = SimpleNamespace(
                    mode="clip",
                    clip_min_notional_usdt=10.0,
                    directional_ratio_max=3.0,
                    side_exposure_usdt=600.0,
                    margin_exposure_usdt=1100.0,
                )

                mock_risk_weights.return_value = SimpleNamespace(
                    delta_price_pct=0.05,
                    obi=0.35,
                    tfi=0.35,
                    absorption_inverse=0.25,
                )

                mock_risk_thresholds.return_value = SimpleNamespace(
                    max_risk_score=0.9,
                    overrides=None,
                    for_profile=lambda profile: 0.9,
                )

                # Sizing policy
                sizing = MagicMock()
                sizing.max_risk_pct = 1.0
                sizing.max_risk_usd = 50
                sizing.min_notional_usd = 10
                sizing.max_notional_usd = 10000
                mock_sizing.return_value = sizing

                # Decision policy
                decision = MagicMock()
                decision.signal_threshold = 0.1
                decision.neutral_threshold = 0.3
                mock_decision.return_value = decision

                # Features config
                features_cfg = MagicMock()
                features_cfg.source = "config_v2"
                mock_features.return_value = features_cfg

                # Symbols
                mock_symbols.return_value = ["BTCUSDT", "ETHUSDT"]

                # Instrument profile
                profile = MagicMock()
                profile.min_notional = 10
                profile.min_qty = 0.001
                profile.min_price = 0.01
                profile.max_leverage = 20
                mock_profile.return_value = profile

                # Modes
                modes = MagicMock()
                modes.for_domain = MagicMock(return_value="testnet")
                modes.profile = "full_testnet"
                mock_modes.return_value = modes
                mock_domain_mode.return_value = "testnet"

                result = validate_config_v2()

                assert result["status"] == "ok"
                assert all(domain["status"] ==
                           "ok" for domain in result["domains"].values())

    def test_invariant_violations(self):
        """Test that invariants catch errors."""
        with patch('tools.config_validator_v2.reload_config') as mock_reload:
            mock_cfg = MagicMock()
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                patch('tools.config_validator_v2.resolve_feature_engineering_config') as mock_features, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                mock_reload.return_value = mock_cfg

                # Exposure with invalid max_equity
                exposure = MagicMock()
                exposure.source = "config_v2"
                exposure.caps.max_equity_utilization_ratio = -1  # Invalid
                exposure.caps.max_portfolio_fraction = 0.2
                exposure.caps.max_directional_ratio = 2.0
                exposure.reservations = SimpleNamespace(
                    pending_ttl_sec=45,
                    post_fill_hold_ttl_sec=10,
                    positions_stale_ttl_sec=3,
                )
                mock_exposure.return_value = exposure

                brackets = MagicMock()
                brackets.source = "config_v2"
                brackets.tp_bps = 10
                brackets.sl_bps = 5
                mock_brackets.return_value = brackets

                risk = MagicMock()
                risk.cfg.max_realized_loss_usd = 250
                risk.cfg.max_drawdown_pct = 8
                mock_risk.return_value = risk

                mock_risk_soft.return_value = SimpleNamespace(
                    mode="clip",
                    clip_min_notional_usdt=10.0,
                    directional_ratio_max=3.0,
                    side_exposure_usdt=600.0,
                    margin_exposure_usdt=1100.0,
                )

                mock_risk_weights.return_value = SimpleNamespace(
                    delta_price_pct=0.05,
                    obi=0.35,
                    tfi=0.35,
                    absorption_inverse=0.25,
                )

                mock_risk_thresholds.return_value = SimpleNamespace(
                    max_risk_score=0.9,
                    overrides={"testnet": 0.87},
                    for_profile=lambda profile: 0.87 if profile == "testnet" else 0.9,
                )

                sizing = MagicMock()
                sizing.max_risk_pct = 1.0
                sizing.max_risk_usd = 50
                sizing.min_notional_usd = 10
                sizing.max_notional_usd = 10000
                mock_sizing.return_value = sizing

                decision = MagicMock()
                decision.signal_threshold = 2.0  # Invalid > 1
                decision.neutral_threshold = 0.3
                mock_decision.return_value = decision

                features_cfg = MagicMock()
                features_cfg.source = "config_v2"
                mock_features.return_value = features_cfg

                mock_symbols.return_value = ["BTCUSDT"]
                profile = MagicMock()
                profile.min_notional = 10
                profile.min_qty = 0.001
                profile.min_price = 0.01
                profile.max_leverage = 20
                mock_profile.return_value = profile

                modes = MagicMock()
                modes.for_domain = MagicMock(return_value="testnet")
                modes.profile = "full_testnet"
                mock_modes.return_value = modes
                mock_domain_mode.return_value = "testnet"

                result = validate_config_v2()

                assert result["status"] == "error"
                assert result["domains"]["execution"]["status"] == "error"
                assert "max_equity_utilization_ratio" in str(
                    result["domains"]["execution"]["errors"])
                assert result["domains"]["decision"]["status"] == "error"
                assert "signal_threshold" in str(
                    result["domains"]["decision"]["errors"])

    def test_risk_soft_limits_invalid(self):
        """Risk domain should fail on invalid soft limits."""
        cfg = load_config().model_copy(deep=True)

        with patch('tools.config_validator_v2.reload_config', return_value=cfg):
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                _configure_valid_domain_mocks(
                    mock_exposure,
                    mock_brackets,
                    mock_risk,
                    mock_risk_soft,
                    mock_risk_weights,
                    mock_risk_thresholds,
                    mock_sizing,
                    mock_decision,
                    mock_symbols,
                    mock_profile,
                    mock_modes,
                    mock_domain_mode,
                )

                mock_risk_soft.return_value = SimpleNamespace(
                    mode="clip",
                    clip_min_notional_usdt=-1.0,
                    directional_ratio_max=0.5,
                    side_exposure_usdt=-100.0,
                    margin_exposure_usdt=0.0,
                )

                result = validate_config_v2()

        assert result["status"] == "error"
        assert result["domains"]["risk"]["status"] == "error"
        assert any(
            "soft_limits" in err for err in result["domains"]["risk"]["errors"])

    def test_risk_score_weights_invalid(self):
        """Risk domain should fail when score weights are negative."""
        cfg = load_config().model_copy(deep=True)

        with patch('tools.config_validator_v2.reload_config', return_value=cfg):
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                _configure_valid_domain_mocks(
                    mock_exposure,
                    mock_brackets,
                    mock_risk,
                    mock_risk_soft,
                    mock_risk_weights,
                    mock_risk_thresholds,
                    mock_sizing,
                    mock_decision,
                    mock_symbols,
                    mock_profile,
                    mock_modes,
                    mock_domain_mode,
                )

                mock_risk_weights.return_value = SimpleNamespace(
                    delta_price_pct=-0.1,
                    obi=0.35,
                    tfi=-0.2,
                    absorption_inverse=0.25,
                )

                result = validate_config_v2()

        assert result["status"] == "error"
        assert result["domains"]["risk"]["status"] == "error"
        assert any(
            "score_weights" in err for err in result["domains"]["risk"]["errors"])

    def test_risk_thresholds_invalid(self):
        """Risk domain should fail when trading thresholds are outside [0, 1]."""
        cfg = load_config().model_copy(deep=True)

        with patch('tools.config_validator_v2.reload_config', return_value=cfg):
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                _configure_valid_domain_mocks(
                    mock_exposure,
                    mock_brackets,
                    mock_risk,
                    mock_risk_soft,
                    mock_risk_weights,
                    mock_risk_thresholds,
                    mock_sizing,
                    mock_decision,
                    mock_symbols,
                    mock_profile,
                    mock_modes,
                    mock_domain_mode,
                )

                mock_risk_thresholds.return_value = SimpleNamespace(
                    max_risk_score=1.5,
                    overrides={"testnet": -0.1},
                    for_profile=lambda profile: -0.1,
                )

                result = validate_config_v2()

        assert result["status"] == "error"
        assert result["domains"]["risk"]["status"] == "error"
        assert any(
            "trading_allowed_thresholds" in err for err in result["domains"]["risk"]["errors"])

    def test_modes_invariant_violations(self):
        """Test modes domain invariants."""
        with patch('tools.config_validator_v2.reload_config') as mock_reload:
            mock_cfg = MagicMock()
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                patch('tools.config_validator_v2.resolve_feature_engineering_config') as mock_features, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                mock_reload.return_value = mock_cfg

                # Valid mocks for other domains
                exposure = MagicMock()
                exposure.source = "config_v2"
                exposure.caps.max_equity_utilization_ratio = 200.0
                exposure.caps.max_portfolio_fraction = 2.0
                exposure.caps.max_directional_ratio = 2.0
                exposure.reservations = SimpleNamespace(
                    pending_ttl_sec=45,
                    post_fill_hold_ttl_sec=10,
                    positions_stale_ttl_sec=3,
                )
                mock_exposure.return_value = exposure

                brackets = MagicMock()
                brackets.source = "config_v2"
                brackets.tp_bps = 10
                brackets.sl_bps = 5
                mock_brackets.return_value = brackets

                risk = MagicMock()
                risk.cfg.max_realized_loss_usd = 250
                risk.cfg.max_drawdown_pct = 8
                mock_risk.return_value = risk

                mock_risk_soft.return_value = SimpleNamespace(
                    mode="clip",
                    clip_min_notional_usdt=10.0,
                    directional_ratio_max=3.0,
                    side_exposure_usdt=600.0,
                    margin_exposure_usdt=1100.0,
                )

                mock_risk_weights.return_value = SimpleNamespace(
                    delta_price_pct=0.05,
                    obi=0.35,
                    tfi=0.35,
                    absorption_inverse=0.25,
                )

                mock_risk_thresholds.return_value = SimpleNamespace(
                    max_risk_score=0.9,
                    overrides={"testnet": 0.87},
                    for_profile=lambda profile: 0.87 if profile == "testnet" else 0.9,
                )

                sizing = MagicMock()
                sizing.max_risk_pct = 1.0
                sizing.max_risk_usd = 50
                sizing.min_notional_usd = 10
                sizing.max_notional_usd = 10000
                mock_sizing.return_value = sizing

                decision = MagicMock()
                decision.signal_threshold = 0.1
                decision.neutral_threshold = 0.3
                mock_decision.return_value = decision

                features_cfg = MagicMock()
                features_cfg.source = "config_v2"
                mock_features.return_value = features_cfg

                mock_symbols.return_value = ["BTCUSDT"]
                profile = MagicMock()
                profile.min_notional = 10
                profile.min_qty = 0.001
                profile.min_price = 0.01
                profile.max_leverage = 20
                mock_profile.return_value = profile

                # Invalid modes: invalid domain mode
                modes = MagicMock()
                modes.for_domain = MagicMock(
                    side_effect=lambda domain: "invalid_mode" if domain == "execution_position" else "testnet")
                modes.profile = "full_testnet"
                mock_modes.return_value = modes
                mock_domain_mode.return_value = "invalid_mode"

                result = validate_config_v2()

                assert result["status"] == "error"
                assert result["domains"]["modes"]["status"] == "error"
                assert "not in allowed set" in str(
                    result["domains"]["modes"]["errors"])

    def test_validator_fails_when_features_missing(self):
        """Validator should error when features.yaml is absent."""
        cfg = load_config().model_copy(deep=True)
        cfg.config_v2.domains.pop("features", None)

        with patch('tools.config_validator_v2.reload_config', return_value=cfg):
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                _configure_valid_domain_mocks(
                    mock_exposure,
                    mock_brackets,
                    mock_risk,
                    mock_risk_soft,
                    mock_risk_weights,
                    mock_risk_thresholds,
                    mock_sizing,
                    mock_decision,
                    mock_symbols,
                    mock_profile,
                    mock_modes,
                    mock_domain_mode,
                )

                result = validate_config_v2()

        assert result["status"] == "error"
        assert result["domains"]["features"]["status"] == "error"
        assert result["domains"]["features"]["errors"]

    def test_validator_ok_when_features_present(self):
        """Validator should pass when features config is available."""
        cfg = load_config().model_copy(deep=True)

        with patch('tools.config_validator_v2.reload_config', return_value=cfg):
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                _configure_valid_domain_mocks(
                    mock_exposure,
                    mock_brackets,
                    mock_risk,
                    mock_risk_soft,
                    mock_risk_weights,
                    mock_risk_thresholds,
                    mock_sizing,
                    mock_decision,
                    mock_symbols,
                    mock_profile,
                    mock_modes,
                    mock_domain_mode,
                )

                result = validate_config_v2()

        assert result["status"] == "ok"
        assert result["domains"]["features"]["status"] == "ok"

    def test_overrides_dead_fields_detected(self):
        """Overrides with top-level limits fields should trigger instrument errors."""
        cfg = load_config().model_copy(deep=True)
        assert cfg.config_v2 is not None
        if cfg.config_v2.overrides is None:
            cfg.config_v2.overrides = {}
        overrides = cfg.config_v2.overrides.setdefault("symbols", {})
        symbol_override = overrides.setdefault("SOLUSDT", {})
        symbol_override["max_leverage"] = 250  # invalid placement

        with patch('tools.config_validator_v2.reload_config', return_value=cfg):
            with patch('tools.config_validator_v2.resolve_exposure_policy') as mock_exposure, \
                    patch('tools.config_validator_v2.resolve_brackets_config') as mock_brackets, \
                    patch('tools.config_validator_v2.resolve_daily_risk_state') as mock_risk, \
                    patch('tools.config_validator_v2.resolve_risk_soft_limits') as mock_risk_soft, \
                    patch('tools.config_validator_v2.resolve_risk_score_weights') as mock_risk_weights, \
                    patch('tools.config_validator_v2.resolve_trading_allowed_thresholds') as mock_risk_thresholds, \
                    patch('tools.config_validator_v2.resolve_sizing_policy') as mock_sizing, \
                    patch('tools.config_validator_v2.resolve_decision_policy') as mock_decision, \
                    patch('tools.config_validator_v2.get_trading_symbols') as mock_symbols, \
                    patch('tools.config_validator_v2.resolve_instrument_profile') as mock_profile, \
                    patch('tools.config_validator_v2.compute_effective_trading_modes') as mock_modes, \
                    patch('tools.config_validator_v2.get_domain_mode_from_mapping') as mock_domain_mode:

                _configure_valid_domain_mocks(
                    mock_exposure,
                    mock_brackets,
                    mock_risk,
                    mock_risk_soft,
                    mock_risk_weights,
                    mock_risk_thresholds,
                    mock_sizing,
                    mock_decision,
                    mock_symbols,
                    mock_profile,
                    mock_modes,
                    mock_domain_mode,
                )

                result = validate_config_v2()

        assert result["status"] == "error"
        assert result["domains"]["instruments"]["status"] == "error"
        assert "overrides.symbols.SOLUSDT.max_leverage" in str(
            result["domains"]["instruments"]["errors"])

    def test_cli_exit_codes(self, tmp_path):
        """Test CLI exit codes."""
        from tools.config_validator_v2 import main
        import sys
        from unittest.mock import patch

        # Test with valid config
        with patch('tools.config_validator_v2.validate_config_v2') as mock_validate:
            mock_validate.return_value = {"status": "ok", "domains": {}}

            with patch('sys.argv', ['config_validator_v2.py', '--output', str(tmp_path / "report.json")]):
                with patch('sys.exit') as mock_exit:
                    main()
                mock_exit.assert_not_called()

        # Test with invalid config
        with patch('tools.config_validator_v2.validate_config_v2') as mock_validate:
            mock_validate.return_value = {"status": "error", "domains": {}}

            with patch('sys.argv', ['config_validator_v2.py', '--output', str(tmp_path / "report.json")]):
                with patch('sys.exit') as mock_exit:
                    main()
                mock_exit.assert_called_once_with(1)


def test_config_v2_schema_validation_ok():
    """The JSON Schema for config v2 should accept the repo config."""
    cfg = load_config()
    assert cfg.config_v2 is not None
    errors = validate_config_v2_schema(cfg.config_v2)
    assert errors == []


def test_config_v2_schema_validation_fails_on_missing_domain():
    """Missing a required domain should trigger schema validation failure."""
    cfg = load_config()
    assert cfg.config_v2 is not None
    broken_domains = {
        name: payload
        for name, payload in cfg.config_v2.domains.items()
        if name != "risk"
    }
    broken_config = ConfigV2(
        core=cfg.config_v2.core,
        symbols=cfg.config_v2.symbols,
        instruments=cfg.config_v2.instruments,
        overrides=cfg.config_v2.overrides,
        modes=cfg.config_v2.modes,
        domains=broken_domains,
    )
    errors = validate_config_v2_schema(broken_config)
    assert errors


def test_schema_domain_reports_broken_schema_file(monkeypatch, tmp_path):
    """Schema domain switches to error if the JSON Schema cannot be loaded."""
    cfg = load_config()
    assert cfg.config_v2 is not None
    monkeypatch.setattr(config_validator, "_CONFIG_V2_SCHEMA", None)
    monkeypatch.setattr(
        config_validator,
        "_CONFIG_V2_SCHEMA_PATH",
        tmp_path / "missing_schema.json",
    )

    result = validate_config_v2()
    schema_report = result["domains"].get("schema", {})
    assert schema_report.get("status") == "error"
    assert schema_report.get("errors")
