#!/usr/bin/env python3
"""Tests for dual-mode instrument profile resolver with config v2 support."""

import pytest

from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2, InstrumentProfile
from apps.reference.config_symbols import (
    resolve_instrument_profile,
    _build_instrument_profile_from_v2,
    _build_instrument_profile_from_legacy,
)


class TestInstrumentProfileV2:
    """Test dual-mode instrument profile resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        # Mock legacy config
        mock_config = {
            "trading": {
                "instruments": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "exchange": "binance",
                        "base_asset": "BTC",
                        "quote_asset": "USDT",
                        "precision_quantity": 3,
                        "precision_price": 2,
                        "min_notional": "10.0",
                        "min_qty": "0.001",
                        "min_price": "0.01",
                        "step_size": "0.001",
                        "tick_size": "0.01",
                        "max_position_size": 5.0,
                        "max_leverage": 20,
                        "default_tp_bps": 50,
                        "default_sl_bps": 25,
                    }
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        profile = resolve_instrument_profile(cfg, "BTCUSDT")

        assert isinstance(profile, InstrumentProfile)
        assert profile.source == "legacy"
        assert profile.symbol == "BTCUSDT"
        assert profile.exchange == "binance"
        assert profile.precision_quantity == 3
        assert profile.max_leverage == 20  # default value since not in legacy

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "instruments": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "max_leverage": 10,  # legacy value
                        "default_tp_bps": 30,  # legacy value
                        "step_size": "0.001",
                        "tick_size": "0.01",
                        "min_qty": "0.001",
                        "min_notional": "10.0",
                    }
                }
            }
        }

        v2_data = {
            "instruments": {
                "BTCUSDT": {
                    "exchange": "binance",
                    "base_asset": "BTC",
                    "quote_asset": "USDT",
                    "precision": {
                        "quantity": 3,
                        "price": 2,
                    },
                    "limits": {
                        "min_notional": 10.0,
                        "min_qty": 0.001,
                        "min_price": 0.01,
                        "max_position_size": 5.0,
                        "max_leverage": 25,  # v2 value
                    },
                    "tp_sl": {
                        "default_tp_bps": 60,  # v2 value
                        "default_sl_bps": 30,
                    },
                }
            },
            "overrides": {
                "symbols": {
                    "BTCUSDT": {
                        "limits": {
                            "max_leverage": 30,  # override value
                        }
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(
                instruments={"instruments": v2_data["instruments"]},
                overrides={"symbols": v2_data["overrides"]["symbols"]}
            ))
        profile = resolve_instrument_profile(cfg, "BTCUSDT")

        assert profile.source == "config_v2"
        assert profile.max_leverage == 30  # override applied
        assert profile.default_tp_bps == 60  # v2 value

    def test_v2_instrument_leverage_overrides_limits(self):
        """Overrides must update nested limits like max_leverage."""
        base_v2 = {
            "SOLUSDT": {
                "exchange": "binance",
                "base_asset": "SOL",
                "quote_asset": "USDT",
                "precision": {"quantity": 2, "price": 2},
                "limits": {
                    "min_notional": 10.0,
                    "min_qty": 0.01,
                    "min_price": 0.01,
                    "max_position_size": 5.0,
                    "max_leverage": 20,
                },
            }
        }
        overrides = {
            "SOLUSDT": {
                "limits": {
                    "max_leverage": 125,
                    "max_position_size": 15.0,
                }
            }
        }

        cfg = AuroraConfig(
            trading={"instruments": {}},
            config_v2=ConfigV2(
                instruments={"instruments": base_v2},
                overrides={"symbols": overrides},
            ),
        )

        profile = resolve_instrument_profile(cfg, "SOLUSDT")

        assert profile.source == "config_v2"
        assert profile.max_leverage == 125
        assert profile.max_position_size == 15.0

    def test_v2_instrument_limits_from_base_without_overrides(self):
        """When no overrides exist, base limits should be honored."""
        base_v2 = {
            "BNBUSDT": {
                "exchange": "binance",
                "base_asset": "BNB",
                "quote_asset": "USDT",
                "precision": {"quantity": 2, "price": 2},
                "limits": {
                    "min_notional": 25.0,
                    "min_qty": 0.05,
                    "min_price": 0.01,
                    "max_position_size": 2.5,
                    "max_leverage": 33,
                },
            }
        }

        cfg = AuroraConfig(
            trading={"instruments": {}},
            config_v2=ConfigV2(
                instruments={"instruments": base_v2},
                overrides={"symbols": {}},
            ),
        )

        profile = resolve_instrument_profile(cfg, "BNBUSDT")

        assert profile.source == "config_v2"
        assert profile.max_leverage == 33
        assert profile.max_position_size == 2.5
        assert profile.min_notional == 25.0
        assert profile.min_qty == pytest.approx(0.05)

    def test_v2_instrument_legacy_not_used_when_v2_present(self):
        """Legacy values must not leak when a v2 profile exists."""
        legacy = {
            "instruments": {
                "ETHUSDT": {
                    "symbol": "ETHUSDT",
                    "max_leverage": 999,
                    "min_notional": "1.0",
                    "min_qty": "0.0001",
                    "step_size": "0.0001",
                    "tick_size": "0.01",
                }
            }
        }

        base_v2 = {
            "ETHUSDT": {
                "precision": {"quantity": 3, "price": 2},
                "limits": {
                    "min_notional": 12.0,
                    "min_qty": 0.002,
                    "min_price": 0.05,
                    "max_position_size": 4.0,
                    "max_leverage": 42,
                },
            }
        }

        cfg = AuroraConfig(
            trading=legacy,
            config_v2=ConfigV2(
                instruments={"instruments": base_v2},
                overrides={"symbols": {}},
            ),
        )

        profile = resolve_instrument_profile(cfg, "ETHUSDT")

        assert profile.source == "config_v2"
        assert profile.max_leverage == 42
        assert profile.min_notional == 12.0
        # Ensure legacy values did not bleed in
        assert profile.min_qty == pytest.approx(0.002)

    def test_v2_fallback_on_missing_symbol(self):
        """Test fallback to legacy when symbol not in v2."""
        mock_config = {
            "trading": {
                "instruments": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "max_leverage": 15,
                        "step_size": "0.001",
                        "tick_size": "0.01",
                        "min_qty": "0.001",
                        "min_notional": "10.0",
                    }
                }
            }
        }

        v2_data = {
            "instruments": {
                "ETHUSDT": {  # Different symbol
                    "limits": {
                        "max_leverage": 25,
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(
                instruments={"instruments": v2_data["instruments"]}
            ))
        profile = resolve_instrument_profile(cfg, "BTCUSDT")

        assert profile.source == "legacy"
        assert profile.max_leverage == 20  # legacy value (default)

    def test_v2_fallback_on_invalid_config(self):
        """Test fallback when v2 config is invalid."""
        mock_config = {
            "trading": {
                "instruments": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "max_leverage": 15,
                        "step_size": "0.001",
                        "tick_size": "0.01",
                        "min_qty": "0.001",
                        "min_notional": "10.0",
                    }
                }
            }
        }

        v2_data = {
            "instruments": {
                "BTCUSDT": {
                    "precision": "invalid",  # Invalid type
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(
                instruments={"instruments": v2_data["instruments"]}
            ))
        profile = resolve_instrument_profile(cfg, "BTCUSDT")

        assert profile.source == "legacy"  # fallback
        assert profile.max_leverage == 20  # legacy value
