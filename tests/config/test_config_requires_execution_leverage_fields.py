"""
TASK47c-A: Config Contract Tests for Leverage/Margin Execution Fields.

TDD approach: Write failing tests first, then implement config models.
Validates fail-closed behavior for LIVE execution mode.
"""
import pytest
from pydantic import ValidationError


class TestConfigRequiresExecutionLeverageFields:
    """Tests for mandatory execution fields in LIVE mode."""

    def test_config_requires_execution_leverage_fields_in_live_mode(self):
        """
        LIVE mode MUST fail if any instrument is missing:
        - margin_mode
        - target_leverage  
        - leverage_policy
        - max_notional_utilization
        """
        from apps.reference.config_models import InstrumentExecutionConfig
        
        # All fields present → should pass
        valid = InstrumentExecutionConfig(
            margin_mode="isolated",
            target_leverage=20,
            leverage_policy="verify_only",
            max_notional_utilization=0.8,
        )
        assert valid.margin_mode == "isolated"
        assert valid.target_leverage == 20
        assert valid.leverage_policy == "verify_only"
        assert valid.max_notional_utilization == 0.8
        
    def test_config_fails_when_margin_mode_missing(self):
        """Missing margin_mode → ValidationError."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                # margin_mode missing
                target_leverage=20,
                leverage_policy="verify_only",
                max_notional_utilization=0.8,
            )
        assert "margin_mode" in str(exc.value)
        
    def test_config_fails_when_target_leverage_missing(self):
        """Missing target_leverage → ValidationError."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                # target_leverage missing
                leverage_policy="verify_only",
                max_notional_utilization=0.8,
            )
        assert "target_leverage" in str(exc.value)
        
    def test_config_fails_when_leverage_policy_missing(self):
        """Missing leverage_policy → ValidationError."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=20,
                # leverage_policy missing
                max_notional_utilization=0.8,
            )
        assert "leverage_policy" in str(exc.value)

    def test_config_fails_when_max_notional_utilization_missing(self):
        """Missing max_notional_utilization → ValidationError."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=20,
                leverage_policy="verify_only",
                # max_notional_utilization missing
            )
        assert "max_notional_utilization" in str(exc.value)


class TestConfigRejectsInvalidValues:
    """Tests for invalid enum/value rejections."""
    
    def test_config_rejects_invalid_margin_mode(self):
        """Only 'isolated' and 'cross' are valid margin modes."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="invalid_mode",  # not isolated/cross
                target_leverage=20,
                leverage_policy="verify_only",
                max_notional_utilization=0.8,
            )
        assert "margin_mode" in str(exc.value)
        
    def test_config_rejects_invalid_leverage_policy(self):
        """Only 'verify_only' and 'set_and_verify' are valid policies."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=20,
                leverage_policy="auto_set",  # not verify_only/set_and_verify
                max_notional_utilization=0.8,
            )
        assert "leverage_policy" in str(exc.value)
        
    def test_config_rejects_leverage_below_minimum(self):
        """target_leverage must be >= 1."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=0,  # below 1
                leverage_policy="verify_only",
                max_notional_utilization=0.8,
            )
        assert "target_leverage" in str(exc.value) or "greater than" in str(exc.value).lower()
        
    def test_config_rejects_leverage_above_maximum(self):
        """target_leverage must be <= 125 (Binance limit)."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=150,  # above 125
                leverage_policy="verify_only",
                max_notional_utilization=0.8,
            )
        assert "target_leverage" in str(exc.value) or "less than" in str(exc.value).lower()
        
    def test_config_rejects_utilization_above_one(self):
        """max_notional_utilization must be <= 1.0."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=20,
                leverage_policy="verify_only",
                max_notional_utilization=1.5,  # above 1.0
            )
        assert "max_notional_utilization" in str(exc.value) or "less than" in str(exc.value).lower()
        
    def test_config_rejects_utilization_below_zero(self):
        """max_notional_utilization must be >= 0.0."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=20,
                leverage_policy="verify_only",
                max_notional_utilization=-0.1,  # below 0.0
            )
        assert "max_notional_utilization" in str(exc.value) or "greater than" in str(exc.value).lower()


class TestConfigStrictNoExtraFields:
    """Tests that extra fields are forbidden (extra='forbid')."""
    
    def test_config_rejects_extra_fields(self):
        """Extra fields should be rejected (strict validation)."""
        from apps.reference.config_models import InstrumentExecutionConfig
        
        with pytest.raises(ValidationError) as exc:
            InstrumentExecutionConfig(
                margin_mode="isolated",
                target_leverage=20,
                leverage_policy="verify_only",
                max_notional_utilization=0.8,
                unknown_field="should_fail",  # extra field
            )
        assert "extra" in str(exc.value).lower() or "unknown_field" in str(exc.value)


class TestLiveExecutionFailClosed:
    """Tests for LIVE mode startup crash on missing fields."""
    
    def test_loader_validates_execution_fields_for_live_mode(self):
        """
        When is_live_execution=True, loader should fail if any active instrument
        is missing execution config (margin_mode/target_leverage/etc).
        """
        from apps.reference.config_loader import ConfigLoader
        from pathlib import Path
        import tempfile
        import yaml
        
        # Create minimal config with LIVE mode but missing execution fields
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create required YAML files
            system_yaml = {
                "mode": "LIVE",
                "api_mode": "mainnet",
                "trading_mode": "hybrid_live_data_testnet_exec",
            }
            trading_yaml = {
                "binance_api": {
                    "use_testnet": False,
                    "live": {"api_key": "test", "api_secret": "secret"},
                    "testnet": {"api_key": "testnet", "api_secret": "secret"},
                },
                "trading": {
                    "mode": "LIVE",
                    "decision": {"signal_threshold": 0.0, "symbols_to_track": ["BTCUSDT"]},
                },
            }
            domains_yaml = {
                "decision_making": {
                    "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 1000},
                    "qos": {"symbol_cooldown_sec": 60, "mode": "block", "enforce": True, 
                            "exposure_block_cooldown_sec": 30, "max_intents_per_minute_per_symbol": 5,
                            "max_exposure_events_per_minute": 10},
                    "features": {"ttl_sec": 60},
                    "bar_gating": {"enable": False, "bar_ms": 1000},
                    "behavior_fsm": {"enable": False, "high_vol_multiplier": 1.0, "low_vol_multiplier": 1.0},
                    "signals": {"normalize": True, "enable_new_metrics": False},
                    "risk_skew": {"max_skew_sec": 5, "max_defer_count": 3, "defer_cooldown_sec": 1},
                    "arming": {"require_regime_warmup": False, "retry_backoff_ms": 100, "max_attempts": 3},
                },
            }
            regime_yaml = {
                "regime": {"window_size": 100},
            }
            strategies_yaml = {
                "assignments": {},  # No strategies assigned for this test
            }
            aurora_instruments_yaml = {}  # Empty for this test
            # Instruments WITHOUT execution config (should cause fail in LIVE)
            instruments_yaml = {
                "BTCUSDT": {
                    "tick_size": 0.1,
                    "step_size": 0.001,
                    # NO execution config → should fail in LIVE
                }
            }
            
            # Write files to config directory (ConfigLoader expects direct files, not aurora subdir)
            with open(config_dir / "system.yaml", "w") as f:
                yaml.dump(system_yaml, f)
            with open(config_dir / "trading.yaml", "w") as f:
                yaml.dump(trading_yaml, f)
            with open(config_dir / "domains.yaml", "w") as f:
                yaml.dump(domains_yaml, f)
            with open(config_dir / "instruments.yaml", "w") as f:
                yaml.dump(instruments_yaml, f)
            with open(config_dir / "regime.yaml", "w") as f:
                yaml.dump(regime_yaml, f)
            with open(config_dir / "strategies.yaml", "w") as f:
                yaml.dump(strategies_yaml, f)
            with open(config_dir / "aurora_instruments.yaml", "w") as f:
                yaml.dump(aurora_instruments_yaml, f)
            
            # Attempt to load - should fail for LIVE mode due to missing execution config
            # Disable strict mode for non-execution checks (aurora_instruments empty is ok for this test)
            import os
            old_strict = os.environ.get("STRICT_CONFIG_CONFLICTS")
            os.environ["STRICT_CONFIG_CONFLICTS"] = "0"
            try:
                loader = ConfigLoader(config_dir=config_dir)
                with pytest.raises(ValueError) as exc:
                    loader.load_config(is_live_execution=True)
            finally:
                if old_strict is not None:
                    os.environ["STRICT_CONFIG_CONFLICTS"] = old_strict
                else:
                    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
            
            # Verify error mentions missing execution config
            error_msg = str(exc.value).lower()
            assert "execution" in error_msg or "leverage" in error_msg or "margin" in error_msg

