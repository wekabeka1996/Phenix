"""
Tests for features.yaml deprecated detection.

CFG-FEATURES-REGIME-SSOT-04-LIVE-OR-DEPRECATE
"""

import pytest
import yaml
import os
from pathlib import Path
import shutil
from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(tmp_path: Path) -> Path:
    """Copy repo canonical config so tests don't depend on model defaults."""
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


class TestFeaturesYamlDeprecated:
    """Test that features.yaml is detected as deprecated/unused"""
    
    def test_features_yaml_exists_strict_mode_crashes(self, tmp_path):
        """
        Test STRICT MODE: features.yaml exists → ValueError.
        
        CFG-FEATURES-REGIME-SSOT-04: features.yaml is orphaned (not loaded),
        strict mode must crash to prevent confusion.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Create orphaned features.yaml
        features_yaml = {
            "feature_engineering": {
                "enable_new_metrics": True
            }
        }
        (config_dir / "features.yaml").write_text(yaml.dump(features_yaml), encoding="utf-8")
        
        # Enable strict mode
        os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
        try:
            loader = ConfigLoader(config_dir=config_dir)
            
            from apps.reference.config_contract import ConfigContractError
            with pytest.raises(ConfigContractError) as exc_info:
                loader.load_config()
            
            # VERIFY: error message mentions deprecated
            error_msg = str(exc_info.value)
            assert "features.yaml" in error_msg.lower()
            assert "deprecated" in error_msg.lower() or "orphaned" in error_msg.lower()
        finally:
            os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    def test_features_yaml_exists_non_strict_still_fails(self, tmp_path):
        """
        Test NON-STRICT MODE: features.yaml exists → still fails (no soft mode).
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Create orphaned features.yaml
        features_yaml = {
            "feature_engineering": {
                "enable_new_metrics": True
            }
        }
        (config_dir / "features.yaml").write_text(yaml.dump(features_yaml), encoding="utf-8")
        
        # Ensure NON-strict mode
        os.environ["STRICT_CONFIG_CONFLICTS"] = "0"
        
        loader = ConfigLoader(config_dir=config_dir)
        from apps.reference.config_contract import ConfigContractError
        with pytest.raises(ConfigContractError):
            loader.load_config()
    
    def test_features_yaml_missing_no_error(self, tmp_path):
        """
        Test NORMAL CASE: features.yaml missing → no error.
        
        CFG-FEATURES-REGIME-SSOT-04: Normal operation without orphaned file.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Load config - should succeed
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded successfully
        assert config is not None
        assert hasattr(config, "trading_mode")
        assert config.trading_mode in {"testnet", "production", "live", "hybrid_live_data_testnet_exec"}
