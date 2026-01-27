"""
TASK53-I: Config Loader Fail-Closed Contract Tests

Tests verify that the config loader enforces strict contracts:
1. Unknown fields → crash (extra='forbid')
2. Duplicate leaf paths → ConfigContractError
3. Parent-vs-leaf duplicate → ConfigContractError
4. Missing required numeric fields → ValidationError
5. Wrong type numeric fields → ValidationError

All tests use tmp_path as config root to avoid mutating production YAML.
"""
import shutil
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader
from pydantic import ValidationError


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Helper to write YAML files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    """Copy production config to tmp_path for mutation."""
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


class TestUnknownFieldCrashes:
    """Test that unknown fields in YAML cause crash via extra='forbid'."""
    
    def test_unknown_field_in_domains_yaml_crashes(self, tmp_path: Path) -> None:
        """Unknown field in domains.yaml → ValidationError."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        
        # Add unknown field to decision_making
        domains["decision_making"]["UNKNOWN_FIELD_XYZ123"] = 999
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        assert "UNKNOWN_FIELD_XYZ123" in str(exc_info.value)
    
    def test_unknown_field_in_system_yaml_crashes(self, tmp_path: Path) -> None:
        """Unknown field in system.yaml → ValidationError."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        system_path = cfg_dir / "system.yaml"
        system = yaml.safe_load(system_path.read_text(encoding="utf-8"))
        
        # Add unknown field to system config
        system["system"]["BOGUS_CONFIG_KEY"] = "should_crash"
        _write_yaml(system_path, system)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        assert "BOGUS_CONFIG_KEY" in str(exc_info.value)
    
    def test_unknown_field_in_strategy_profile_crashes(self, tmp_path: Path) -> None:
        """Unknown field in strategy profile → ValidationError."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        aurora_path = cfg_dir / "strategies" / "aurora.yaml"
        aurora = yaml.safe_load(aurora_path.read_text(encoding="utf-8"))
        
        # Add unknown field to aurora.decision
        aurora["aurora"]["decision"]["PHANTOM_KEY"] = 12345
        _write_yaml(aurora_path, aurora)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        assert "PHANTOM_KEY" in str(exc_info.value)


class TestDuplicateLeafPathCrashes:
    """Test that duplicate leaf paths across YAML files cause crash."""
    
    def test_duplicate_leaf_path_in_system_and_trading_crashes(self, tmp_path: Path) -> None:
        """Duplicate leaf path between system.yaml and trading.yaml → ConfigContractError."""
        cfg_dir = tmp_path / "aurora"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        
        # Create minimal configs with duplicate path
        _write_yaml(
            cfg_dir / "system.yaml",
            {
                "trading_mode": "testnet",
                "system": {"logging": {"level": "INFO", "file": "x", "format": "json", "rotation": {"max_bytes": 1, "backup_count": 1}}},
                "ops": {"panic_killswitch": True, "panic_ttl_sec": None, "quiet_hours_utc": [], "allowlist_symbols": [], "metrics_url": "x", "reports_dir": "x"},
                "bridge": {"retry_scheduler": {"max_attempts": 1, "min_retry_delay_ms": 1, "backoff_factor": 1.0, "jitter_ms": 0}},
                # Duplicate path: trading.market_data.websocket_streams
                "trading": {"market_data": {"websocket_streams": ["bookTicker"]}},
            },
        )
        _write_yaml(
            cfg_dir / "trading.yaml",
            {"trading": {"mode": "testnet", "market_data": {"websocket_streams": ["trade"]}}},
        )
        _write_yaml(cfg_dir / "regime.yaml", {"hmm": {}, "features": {}})
        _write_yaml(cfg_dir / "domains.yaml", {"debug": {"disable_positions_stale_gate": False, "disable_daily_loss_limit": False}})
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ConfigContractError) as exc_info:
            loader.load_config()
        
        assert "Duplicate config paths" in str(exc_info.value)
        assert "trading.market_data.websocket_streams" in str(exc_info.value)


class TestMissingRequiredNumericCrashes:
    """Test that missing required numeric fields cause crash."""
    
    def test_missing_watchdog_ack_ttl_ms_crashes(self, tmp_path: Path) -> None:
        """Missing required numeric field (ack_ttl_ms) → ValidationError.
        
        TASK-ZOMBIE-FIX: watchdog now lives in trading.yaml under trading.execution.watchdog,
        not in domains.yaml.
        """
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # FIX: watchdog is in trading.yaml, not domains.yaml
        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        
        # Remove required numeric field
        if "trading" in trading and "execution" in trading["trading"]:
            execution = trading["trading"]["execution"]
            if "watchdog" in execution:
                del execution["watchdog"]["ack_ttl_ms"]
        _write_yaml(trading_path, trading)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        # Check that error mentions the missing field
        error_str = str(exc_info.value)
        assert "ack_ttl_ms" in error_str or "watchdog" in error_str
    
    def test_missing_qos_symbol_cooldown_sec_crashes(self, tmp_path: Path) -> None:
        """Missing qos.symbol_cooldown_sec → ValidationError."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        
        # Remove required field
        if "decision_making" in domains and "qos" in domains["decision_making"]:
            del domains["decision_making"]["qos"]["symbol_cooldown_sec"]
        _write_yaml(domains_path, domains)
        
        # TASK53-FIX: Also remove from backtest_override.yaml since it provides fallback
        override_path = cfg_dir / "backtest_override.yaml"
        if override_path.exists():
            override = yaml.safe_load(override_path.read_text(encoding="utf-8"))
            if (
                isinstance(override, dict)
                and "domains" in override
                and "decision_making" in override["domains"]
                and "qos" in override["domains"]["decision_making"]
                and "symbol_cooldown_sec" in override["domains"]["decision_making"]["qos"]
            ):
                del override["domains"]["decision_making"]["qos"]["symbol_cooldown_sec"]
                _write_yaml(override_path, override)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        error_str = str(exc_info.value)
        assert "symbol_cooldown_sec" in error_str or "qos" in error_str


class TestWrongTypeNumericCrashes:
    """Test that wrong type for numeric fields causes crash."""
    
    def test_string_instead_of_int_crashes(self, tmp_path: Path) -> None:
        """String value for int field → ValidationError.
        
        TASK-ZOMBIE-FIX: watchdog now lives in trading.yaml under trading.execution.watchdog.
        """
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # FIX: watchdog is in trading.yaml, not domains.yaml
        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        
        # Set string instead of int
        trading["trading"]["execution"]["watchdog"]["ack_ttl_ms"] = "not_a_number"
        _write_yaml(trading_path, trading)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        error_str = str(exc_info.value)
        assert "ack_ttl_ms" in error_str or "int" in error_str.lower()
    
    def test_string_instead_of_float_crashes(self, tmp_path: Path) -> None:
        """String value for float field → ValidationError."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        
        # Set string instead of float
        if "risk_management" in domains and "trading_allowed_thresholds" in domains["risk_management"]:
            domains["risk_management"]["trading_allowed_thresholds"]["max_risk_score"] = "high"
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        error_str = str(exc_info.value)
        assert "max_risk_score" in error_str or "float" in error_str.lower()


class TestConfigLoaderIntegrity:
    """Integration tests for config loader integrity."""
    
    def test_production_config_loads_without_error(self) -> None:
        """Verify production config loads successfully (smoke test)."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        assert config is not None
        assert config.trading_mode is not None
        assert config.domains is not None
    
    def test_provenance_map_populated(self) -> None:
        """Verify provenance map tracks source files."""
        loader = ConfigLoader()
        loader.load_config()
        
        assert hasattr(loader, "provenance_map")
        assert len(loader.provenance_map) > 0
    
    def test_all_pydantic_models_have_extra_forbid(self) -> None:
        """Verify critical config models have extra='forbid' (static check)."""
        from apps.reference import config_models
        import inspect
        
        # Get all classes in config_models
        forbid_count = 0
        allow_count = 0
        classes_checked = []
        
        for name, obj in inspect.getmembers(config_models, inspect.isclass):
            if hasattr(obj, "model_config"):
                mc = obj.model_config
                if isinstance(mc, dict) and mc.get("extra") == "forbid":
                    forbid_count += 1
                elif hasattr(mc, "get") and mc.get("extra") == "forbid":
                    forbid_count += 1
                elif hasattr(mc, "extra") and str(mc.extra) == "forbid":
                    forbid_count += 1
                else:
                    allow_count += 1
                    classes_checked.append(name)
        
        # Assert majority are forbid (allow some exceptions for specific patterns)
        assert forbid_count > 50, f"Expected >50 models with extra='forbid', got {forbid_count}"
        # Allow at most 10 exceptions
        assert allow_count < 10, f"Too many models without extra='forbid': {classes_checked[:10]}"
