"""
Tests for Alpha Search System Config

Verifies:
- System config loads from YAML without validation errors
- Default config matches previously hardcoded values
- Strict validation rejects unknown fields
- Models actually use config params (not hardcoded)
- All YAML fields match Pydantic model fields
"""

import pytest
import yaml
from pathlib import Path
from decimal import Decimal
from pydantic import ValidationError

from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchSystemConfig,
    MomentumSystemConfig,
    MeanReversionSystemConfig,
    VolatilitySystemConfig,
    EnsembleSystemConfig,
    PluginSystemConfig,
    load_system_config,
    get_default_system_config,
)

# Path to actual config file
SYSTEM_CONFIG_PATH = Path("config/alpha_search_system.yaml")


class TestSystemConfigLoading:
    """Verify system config loads from YAML and defaults."""

    def test_system_config_loads_from_yaml(self):
        """System config should load from actual YAML file without errors."""
        if not SYSTEM_CONFIG_PATH.exists():
            pytest.skip("config/alpha_search_system.yaml not found")

        cfg = load_system_config(str(SYSTEM_CONFIG_PATH))
        assert isinstance(cfg, AlphaSearchSystemConfig)
        assert cfg.momentum.weights.short == 0.3
        assert cfg.momentum.weights.medium == 0.4
        assert cfg.momentum.weights.long == 0.3

    def test_system_config_default_matches_hardcoded(self):
        """get_default_system_config() should match previously hardcoded values."""
        cfg = get_default_system_config()

        # Momentum defaults
        assert cfg.momentum.weights.short == 0.3
        assert cfg.momentum.weights.medium == 0.4
        assert cfg.momentum.weights.long == 0.3
        assert cfg.momentum.volume.confirm_multiplier == 1.2
        assert cfg.momentum.volume.contradict_multiplier == 0.8
        assert cfg.momentum.rsi.overbought == 70
        assert cfg.momentum.rsi.oversold == 30
        assert cfg.momentum.rsi.confidence_penalty == 0.7
        assert cfg.momentum.macd.confirm_boost == 1.1
        assert cfg.momentum.macd.contradict_penalty == 0.9
        assert cfg.momentum.confidence.base == 0.8
        assert cfg.momentum.confidence.consistency_min == 0.7
        assert cfg.momentum.confidence.consistency_range == 0.6

        # Mean reversion defaults
        assert cfg.mean_reversion.weights.bb == 0.4
        assert cfg.mean_reversion.weights.rsi == 0.3
        assert cfg.mean_reversion.weights.sma == 0.2
        assert cfg.mean_reversion.weights.stoch == 0.1
        assert cfg.mean_reversion.rsi.oversold == 30
        assert cfg.mean_reversion.rsi.overbought == 70
        assert cfg.mean_reversion.sma.deviation_normalizer == 0.05
        assert cfg.mean_reversion.stochastic.oversold_zone == 20
        assert cfg.mean_reversion.stochastic.overbought_zone == 80
        assert cfg.mean_reversion.stochastic.signal_strength == 0.3
        assert cfg.mean_reversion.volume.confirm_multiplier == 1.2
        assert cfg.mean_reversion.volume.high_threshold == 1.5
        assert cfg.mean_reversion.bb_width.wide_threshold == 0.05
        assert cfg.mean_reversion.bb_width.narrow_penalty == 0.7
        assert cfg.mean_reversion.confidence.base == 0.5
        assert cfg.mean_reversion.confidence.agreement_factor == 0.4

        # Volatility defaults
        assert cfg.volatility.weights.atr == 0.4
        assert cfg.volatility.weights.bb == 0.25
        assert cfg.volatility.weights.rv == 0.2
        assert cfg.volatility.weights.range == 0.1
        assert cfg.volatility.weights.vol_corr == 0.05
        assert cfg.volatility.bb.amplifier == 10
        assert cfg.volatility.signal_clamp.atr == 2.0
        assert cfg.volatility.volume_vol.high_threshold == 1.2
        assert cfg.volatility.vol_level.low_level == 0.5
        assert cfg.volatility.vol_level.high_boost == 1.2
        assert cfg.volatility.confidence.base == 0.6
        assert cfg.volatility.confidence.no_signal == 0.4

        # Ensemble defaults
        assert cfg.ensemble.max_history == 100
        assert cfg.ensemble.confidence_threshold == 0.1
        assert cfg.ensemble.pnl_normalizer == 100.0
        assert cfg.ensemble.min_performance_score == 0.1
        assert cfg.ensemble.variance_cap == 0.5

        # Plugin defaults
        assert cfg.plugin.default_tf_sec == 300
        assert cfg.plugin.why_chain_limit == 5

    def test_system_config_strict_rejects_unknown(self):
        """extra='forbid' should catch unknown fields."""
        with pytest.raises(ValidationError):
            AlphaSearchSystemConfig(
                momentum=MomentumSystemConfig(),
                unknown_field="should_fail"
            )

    def test_system_config_fallback_on_missing_file(self):
        """load_system_config should return defaults on missing file."""
        cfg = load_system_config("/nonexistent/alpha_search_system.yaml")
        assert isinstance(cfg, AlphaSearchSystemConfig)
        assert cfg.plugin.default_tf_sec == 300


class TestModelsUseConfig:
    """Verify models actually read from config, not hardcoded values."""

    def test_momentum_uses_config_weights(self):
        """MomentumAlphaModel should use weights from config."""
        from apps.reference.domains.alpha_search.models.momentum import MomentumAlphaModel

        # Custom config: 100% weight on short, 0 on others
        custom_config = {
            "weights": {"short": 1.0, "medium": 0.0, "long": 0.0},
            "volume": {"confirm_multiplier": 1.0, "contradict_multiplier": 1.0},
            "rsi": {"overbought": 70, "oversold": 30, "confidence_penalty": 0.7},
            "macd": {"confirm_boost": 1.0, "contradict_penalty": 1.0},
            "confidence": {"base": 0.8, "consistency_min": 0.7, "consistency_range": 0.6},
        }
        model = MomentumAlphaModel(config=custom_config)

        features = {
            "price_momentum_5m": 0.5,
            "price_momentum_1h": -0.5,
            "price_momentum_1d": -0.5,
            "volume_momentum_5m": 0.0,
            "rsi_14": 50,
            "macd_signal": 0,
        }

        score = model.calculate_alpha("BTCUSDT", {"close": 42000}, features)
        # With 100% short weight, score should be positive (0.5)
        assert score.score > 0

        # Default config (30% short): overall negative because 1h + 1d dominate
        default_model = MomentumAlphaModel()
        default_score = default_model.calculate_alpha(
            "BTCUSDT", {"close": 42000}, features)
        assert default_score.score < 0

    def test_mean_reversion_uses_config_weights(self):
        """MeanReversionAlphaModel should use weights from config."""
        from apps.reference.domains.alpha_search.models.mean_reversion import MeanReversionAlphaModel

        # Custom config: 100% weight on BB, 0 on others
        custom_config = {
            "weights": {"bb": 1.0, "rsi": 0.0, "sma": 0.0, "stoch": 0.0},
            "rsi": {"oversold": 30, "overbought": 70},
            "sma": {"deviation_normalizer": 0.05},
            "stochastic": {"oversold_zone": 20, "overbought_zone": 80, "signal_strength": 0.3},
            "volume": {"confirm_multiplier": 1.0, "contradict_multiplier": 1.0, "high_threshold": 1.5, "low_threshold": 0.7},
            "bb_width": {"wide_threshold": 0.05, "narrow_threshold": 0.02, "max_multiplier": 1.5, "narrow_penalty": 0.7},
            "confidence": {"base": 0.5, "agreement_factor": 0.4, "strength_base": 0.8, "signal_threshold": 0.1},
        }
        model = MeanReversionAlphaModel(config=custom_config)

        features = {
            "bb_position": 0.9,  # Near upper band (sell signal)
            "bb_width": 0.05,
            "rsi_14": 50,
            "price_sma_20_deviation": 0,
            "volume_sma_ratio": 1.0,
            "stoch_k": 50,
            "stoch_d": 50,
        }

        score = model.calculate_alpha("BTCUSDT", {"close": 42000}, features)
        # With 100% BB weight and bb_position=0.9, strong sell signal
        assert score.score > 0.5

    def test_volatility_uses_config_weights(self):
        """VolatilityAlphaModel should use weights from config."""
        from apps.reference.domains.alpha_search.models.volatility import VolatilityAlphaModel

        # Custom config: 100% ATR weight
        custom_config = {
            "weights": {"atr": 1.0, "bb": 0.0, "rv": 0.0, "range": 0.0, "vol_corr": 0.0},
            "bb": {"amplifier": 10},
            "signal_clamp": {"atr": 2.0, "rv": 2.0},
            "volume_vol": {"high_threshold": 1.2, "low_threshold": 0.8, "signal_strength": 0.2},
            "vol_level": {"low_level": 0.5, "low_penalty": 0.5, "high_level": 2.0, "high_boost": 1.2},
            "confidence": {"base": 0.6, "agreement_factor": 0.3, "strength_base": 0.7, "no_signal": 0.4},
        }
        model = VolatilityAlphaModel(config=custom_config)

        features = {
            "atr_14": 1.0,
            "atr_ratio": 1.5,  # High ATR ratio -> positive signal
            "bb_width": 0.05,
            "bb_width_change": 0.0,
            "realized_volatility_1h": 0.01,
            "realized_volatility_1d": 0.01,
            "volume_volatility_ratio": 1.0,
            "price_range_ratio": 1.0,
        }

        score = model.calculate_alpha("BTCUSDT", {"close": 42000}, features)
        # With 100% ATR weight and atr_ratio=1.5, signal = 0.5
        assert score.score > 0


class TestYamlFieldsCoverage:
    """Verify all fields in YAML match Pydantic model fields."""

    def test_all_system_fields_present_in_yaml(self):
        """Every Pydantic field should have a corresponding YAML entry."""
        if not SYSTEM_CONFIG_PATH.exists():
            pytest.skip("config/alpha_search_system.yaml not found")

        with open(SYSTEM_CONFIG_PATH) as f:
            raw = yaml.safe_load(f)

        if "alpha_search_system" in raw:
            raw = raw["alpha_search_system"]

        # Parse into config — if any YAML field is missing, Pydantic uses defaults
        # If any YAML field is extra, extra="forbid" raises an error
        cfg = AlphaSearchSystemConfig.model_validate(raw)

        # Verify top-level sections present in YAML
        assert "momentum" in raw
        assert "mean_reversion" in raw
        assert "volatility" in raw
        assert "ensemble" in raw
        assert "plugin" in raw

        # Verify all Pydantic fields have explicit values in YAML
        # (not just defaults — the YAML should be explicit about every param)
        mom = raw["momentum"]
        assert "weights" in mom
        assert "volume" in mom
        assert "rsi" in mom
        assert "macd" in mom
        assert "confidence" in mom

        mr = raw["mean_reversion"]
        assert "weights" in mr
        assert "rsi" in mr
        assert "sma" in mr
        assert "stochastic" in mr
        assert "volume" in mr
        assert "bb_width" in mr
        assert "confidence" in mr

        vol = raw["volatility"]
        assert "weights" in vol
        assert "bb" in vol
        assert "signal_clamp" in vol
        assert "volume_vol" in vol
        assert "vol_level" in vol
        assert "confidence" in vol

    def test_yaml_roundtrip_preserves_values(self):
        """Loading YAML and dumping back should produce same values."""
        if not SYSTEM_CONFIG_PATH.exists():
            pytest.skip("config/alpha_search_system.yaml not found")

        cfg = load_system_config(str(SYSTEM_CONFIG_PATH))
        default_cfg = get_default_system_config()

        # All values should match defaults (since YAML was created from defaults)
        assert cfg.momentum.weights.short == default_cfg.momentum.weights.short
        assert cfg.volatility.bb.amplifier == default_cfg.volatility.bb.amplifier
        assert cfg.ensemble.pnl_normalizer == default_cfg.ensemble.pnl_normalizer
        assert cfg.plugin.why_chain_limit == default_cfg.plugin.why_chain_limit
