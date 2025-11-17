#!/usr/bin/env python3
"""Tests for dual-mode risk config resolver with config v2 support."""

import pytest
from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.config_risk import (
    resolve_daily_risk_state,
    resolve_risk_soft_limits,
    resolve_risk_score_weights,
    resolve_trading_allowed_thresholds,
)


class TestRiskConfigV2:
    """Test dual-mode risk config resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        # Mock legacy config
        mock_config = {
            "trading": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 300.0,
                        "max_drawdown_pct": 10.0,
                        "reset_time_utc": "02:00",
                    }
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        risk_state = resolve_daily_risk_state(cfg)

        assert risk_state.cfg.max_realized_loss_usd == 300.0
        assert risk_state.cfg.max_drawdown_pct == 10.0
        assert risk_state.cfg.reset_h == 2
        assert risk_state.cfg.reset_m == 0

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 200.0,  # legacy value
                        "max_drawdown_pct": 5.0,  # legacy value
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 400.0,  # v2 value
                        "max_drawdown_pct": 12.0,  # v2 value
                        "reset_time_utc": "03:30",
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        risk_state = resolve_daily_risk_state(cfg)

        assert risk_state.cfg.max_realized_loss_usd == 400.0  # v2 value
        assert risk_state.cfg.max_drawdown_pct == 12.0  # v2 value
        assert risk_state.cfg.reset_h == 3
        assert risk_state.cfg.reset_m == 30

    def test_v2_fallback_on_missing_risk_domain(self):
        """Test fallback to legacy when risk domain not in v2."""
        mock_config = {
            "trading": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 150.0,
                        "max_drawdown_pct": 7.0,
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "execution": {  # Different domain
                    "some": "config"
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        risk_state = resolve_daily_risk_state(cfg)

        assert risk_state.cfg.max_realized_loss_usd == 150.0  # legacy value
        assert risk_state.cfg.max_drawdown_pct == 7.0  # legacy value

    def test_v2_fallback_on_invalid_config(self):
        """Test fallback when v2 config is invalid."""
        mock_config = {
            "trading": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 100.0,
                        "max_drawdown_pct": 6.0,
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": "invalid",  # Invalid type
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        risk_state = resolve_daily_risk_state(cfg)

        # Should fallback to legacy
        assert risk_state.cfg.max_realized_loss_usd == 100.0  # legacy value
        assert risk_state.cfg.max_drawdown_pct == 6.0  # legacy value

    def test_risk_soft_limits_v2_priority(self):
        mock_config = {"trading": {"risk": {"soft_limits": {}}}}
        v2_data = {
            "domains": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 250,
                        "max_drawdown_pct": 5,
                        "reset_time_utc": "00:00",
                    },
                    "soft_limits": {
                        "mode": "clip",
                        "clip_min_notional_usdt": 25.5,
                        "directional_ratio_max": 2.5,
                        "side_exposure_usdt": 321,
                        "margin_exposure_usdt": 654,
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data)
        )
        limits = resolve_risk_soft_limits(cfg)

        assert limits.source == "config_v2"
        assert limits.clip_min_notional_usdt == 25.5
        assert limits.directional_ratio_max == 2.5
        assert limits.side_exposure_usdt == 321
        assert limits.margin_exposure_usdt == 654

    def test_risk_soft_limits_legacy_fallback(self):
        mock_config = {
            "trading": {
                "risk": {
                    "soft_limits": {
                        "mode": "clip",
                        "clip_min_notional_usdt": 11,
                        "directional_ratio_max": 4,
                        "side_exposure_usdt": 900,
                        "margin_exposure_usdt": 1400,
                    }
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        limits = resolve_risk_soft_limits(cfg)

        assert limits.source == "legacy"
        assert limits.clip_min_notional_usdt == 11
        assert limits.directional_ratio_max == 4

    def test_risk_score_weights_v2_priority(self):
        mock_config = {"trading": {"risk": {"score_weights": {}}}}
        v2_data = {
            "domains": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 250,
                        "max_drawdown_pct": 5,
                        "reset_time_utc": "00:00",
                    },
                    "score_weights": {
                        "delta_price_pct": 0.2,
                        "obi": 0.4,
                        "tfi": 0.1,
                        "absorption_inverse": 0.3,
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data)
        )
        weights = resolve_risk_score_weights(cfg)

        assert weights.source == "config_v2"
        assert weights.delta_price_pct == 0.2
        assert weights.obi == 0.4
        assert weights.tfi == 0.1
        assert weights.absorption_inverse == 0.3

    def test_risk_score_weights_legacy_fallback(self):
        mock_config = {
            "trading": {
                "risk": {
                    "score_weights": {
                        "delta_price": 0.08,
                        "obi": 0.2,
                        "tfi": 0.4,
                        "absorption_inverse": 0.32,
                    }
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        weights = resolve_risk_score_weights(cfg)

        assert weights.source == "legacy"
        assert weights.delta_price_pct == 0.08
        assert weights.obi == 0.2
        assert weights.tfi == 0.4
        assert weights.absorption_inverse == 0.32

    def test_trading_allowed_thresholds_v2_priority(self):
        mock_config = {"trading": {"risk": {}}}
        v2_data = {
            "domains": {
                "risk": {
                    "daily_limits": {
                        "max_loss_usd": 250,
                        "max_drawdown_pct": 5,
                        "reset_time_utc": "00:00",
                    },
                    "trading_allowed_thresholds": {
                        "max_risk_score": 0.92,
                        "overrides": {
                            "testnet": 0.95,
                            "production": 0.85,
                        }
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data)
        )
        thresholds = resolve_trading_allowed_thresholds(cfg)

        assert thresholds.source == "config_v2"
        assert thresholds.max_risk_score == 0.92
        assert thresholds.overrides == {"testnet": 0.95, "production": 0.85}

    def test_trading_allowed_thresholds_legacy_fallback(self):
        mock_config = {
            "trading": {
                "risk": {
                    "trading_allowed_thresholds": {"max_risk_score": 0.88},
                    "testnet": {"max_risk_score": 0.9},
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        thresholds = resolve_trading_allowed_thresholds(cfg)

        assert thresholds.source == "legacy"
        assert thresholds.max_risk_score == 0.88
        assert thresholds.overrides == {"testnet": 0.9}
