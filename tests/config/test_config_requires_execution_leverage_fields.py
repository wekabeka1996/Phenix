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
        import tempfile
        import shutil
        from pathlib import Path
        from apps.reference.config_loader import ConfigLoader

        repo_root = Path(__file__).resolve().parents[2]

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "aurora"
            shutil.copytree(repo_root / "config" / "aurora", config_dir)

            # Break one required execution field for an active symbol.
            import yaml
            inst_path = config_dir / "instruments.yaml"
            payload = yaml.safe_load(inst_path.read_text(encoding="utf-8"))
            instruments = payload.get("instruments") if isinstance(payload, dict) else None
            assert isinstance(instruments, dict)
            btc = instruments.get("BTCUSDT")
            assert isinstance(btc, dict)
            ex = btc.get("execution")
            assert isinstance(ex, dict)
            ex.pop("target_leverage", None)
            inst_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            loader = ConfigLoader(config_dir=config_dir)
            with pytest.raises(ValueError) as exc:
                loader.load_config(is_live_execution=True)

            error_msg = str(exc.value).lower()
            assert "execution" in error_msg or "leverage" in error_msg or "margin" in error_msg

    def test_loader_validates_sizing_margin_pct_for_live_mode(self):
        import tempfile
        import shutil
        from pathlib import Path
        import yaml
        from apps.reference.config_loader import ConfigLoader

        repo_root = Path(__file__).resolve().parents[2]

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "aurora"
            shutil.copytree(repo_root / "config" / "aurora", config_dir)

            # Break sizing SSOT: remove sizing.margin_pct for an active symbol.
            inst_path = config_dir / "instruments.yaml"
            payload = yaml.safe_load(inst_path.read_text(encoding="utf-8"))
            instruments = payload.get("instruments") if isinstance(payload, dict) else None
            assert isinstance(instruments, dict)
            sol = instruments.get("SOLUSDT")
            assert isinstance(sol, dict)
            sizing = sol.get("sizing")
            assert isinstance(sizing, dict)
            sizing.pop("margin_pct", None)
            inst_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            loader = ConfigLoader(config_dir=config_dir)
            with pytest.raises(ValueError) as exc:
                loader.load_config(is_live_execution=True)

            assert "sizing" in str(exc.value).lower() or "margin_pct" in str(exc.value).lower()
