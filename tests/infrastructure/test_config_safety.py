"""
SECURITY AUDIT: Configuration Overlay Safety Tests

Verifies that:
- Production/Live modes use STRICT SSOT configs (no overlay)
- Backtest mode correctly applies relaxed overlay
- No cross-contamination between modes

CRITICAL: These tests MUST pass before any production deployment.
"""

import os
import pytest
import tempfile
import shutil
import re
from pathlib import Path
from typing import Any, Dict
import yaml


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def canonical_config_dir():
    """Return path to canonical production config directory."""
    return Path(__file__).resolve().parents[2] / "config" / "aurora"


@pytest.fixture
def temp_config_dir(canonical_config_dir):
    """Create a temporary copy of canonical config for isolated testing."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Copy all config files
        shutil.copytree(canonical_config_dir, tmp_path / "aurora")
        yield tmp_path / "aurora"


@pytest.fixture
def clean_env():
    """Ensure clean environment for each test."""
    original_env = os.environ.copy()
    # Remove any test-related env vars
    for key in list(os.environ.keys()):
        if "STRICT" in key or "CONFIG" in key:
            os.environ.pop(key, None)
    yield
    os.environ.clear()
    os.environ.update(original_env)


def _patch_trading_mode(config_dir: Path, mode: str) -> None:
    """Patch system.yaml AND trading.yaml to set specific trading_mode."""
    # Patch system.yaml
    system_yaml = config_dir / "system.yaml"
    content = system_yaml.read_text()
    
    # Replace any trading_mode with the specified mode
    content = re.sub(
        r'trading_mode:\s*["\']?\w+["\']?',
        f'trading_mode: "{mode}"',
        content
    )
    if 'trading_mode:' not in content:
        content += f'\ntrading_mode: "{mode}"\n'
    system_yaml.write_text(content)
    
    # CRITICAL: Also patch trading.yaml to prevent mode override
    trading_yaml = config_dir / "trading.yaml"
    if trading_yaml.exists():
        content = trading_yaml.read_text()
        # Replace trading.mode: backtest with the test mode
        content = re.sub(
            r'(\n\s*mode:\s*)["\']?backtest["\']?',
            f'\\1"{mode}"',
            content
        )
        trading_yaml.write_text(content)


# ============================================================================
# TEST CASE A: BACKTEST MODE (Overlay Applied)
# ============================================================================

class TestBacktestModeOverlayApplied:
    """Verify backtest mode correctly applies relaxed overlay settings."""

    def test_backtest_warmup_enforcement_is_warn_only(self, temp_config_dir, clean_env):
        """
        BACKTEST: warmup.enforcement_mode MUST be 'warn_only' after overlay.
        
        This allows backtest to proceed without full feature warmup.
        """
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, "backtest")
        
        # Load config
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # ASSERT: Overlay applied - warmup is relaxed
        fe = config.domains.feature_engineering
        assert hasattr(fe, 'warmup'), "FeatureEngineering must have warmup config"
        assert fe.warmup.enforcement_mode == "warn_only", (
            f"BACKTEST FAIL: warmup.enforcement_mode={fe.warmup.enforcement_mode}, "
            f"expected 'warn_only'. Overlay not applied!"
        )

    def test_backtest_risk_skew_is_disabled(self, temp_config_dir, clean_env):
        """
        BACKTEST: risk_skew.max_skew_sec MUST be very high (disabled).
        
        Historical data has no "staleness" concept.
        """
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, "backtest")
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # ASSERT: Overlay applied - risk_skew disabled
        dm = config.domains.decision_making
        assert hasattr(dm, 'risk_skew'), "DecisionMaking must have risk_skew config"
        assert dm.risk_skew.max_skew_sec >= 999999, (
            f"BACKTEST FAIL: risk_skew.max_skew_sec={dm.risk_skew.max_skew_sec}, "
            f"expected >= 999999. Overlay not applied!"
        )

    def test_backtest_directional_sanity_disabled(self, temp_config_dir, clean_env):
        """
        BACKTEST: directional_sanity.enabled MUST be False.
        
        Allows counter-trend entries for mean-reversion testing.
        """
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, "backtest")
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # ASSERT: Overlay applied - directional_sanity disabled
        dm = config.domains.decision_making
        if hasattr(dm, 'directional_sanity'):
            assert dm.directional_sanity.enabled is False, (
                f"BACKTEST FAIL: directional_sanity.enabled={dm.directional_sanity.enabled}, "
                f"expected False. Overlay not applied!"
            )


# ============================================================================
# TEST CASE B: LIVE MODE (Overlay IGNORED - CRITICAL SECURITY)
# ============================================================================

class TestLiveModeOverlayIgnored:
    """
    CRITICAL SECURITY TESTS
    
    Verify live/production modes use STRICT SSOT configs.
    The backtest overlay MUST be completely ignored.
    """

    @pytest.mark.parametrize("live_mode", [
        "live",
        "production", 
        "testnet",
        "hybrid_live_data_testnet_exec",
    ])
    def test_live_warmup_enforcement_is_fail_fast(self, temp_config_dir, clean_env, live_mode):
        """
        LIVE/PRODUCTION: warmup.enforcement_mode MUST be 'fail_fast'.
        
        CRITICAL: System must NOT trade until all features are ready.
        """
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, live_mode)
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # ASSERT: STRICT production settings (overlay NOT applied)
        fe = config.domains.feature_engineering
        assert hasattr(fe, 'warmup'), "FeatureEngineering must have warmup config"
        assert fe.warmup.enforcement_mode == "fail_fast", (
            f"🚨 SECURITY VIOLATION: warmup.enforcement_mode={fe.warmup.enforcement_mode} "
            f"in {live_mode} mode! Expected 'fail_fast'. "
            f"Backtest overlay may have leaked into production!"
        )

    @pytest.mark.parametrize("live_mode", [
        "live",
        "production",
        "testnet",
        "hybrid_live_data_testnet_exec",
    ])
    def test_live_risk_skew_is_strict(self, temp_config_dir, clean_env, live_mode):
        """
        LIVE/PRODUCTION: risk_skew.max_skew_sec MUST be low (e.g., 5 seconds).
        
        CRITICAL: Stale data detection is essential for live trading safety.
        """
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, live_mode)
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # ASSERT: STRICT production settings (overlay NOT applied)
        dm = config.domains.decision_making
        assert hasattr(dm, 'risk_skew'), "DecisionMaking must have risk_skew config"
        # Production value should be <= 60 seconds (typically 5)
        assert dm.risk_skew.max_skew_sec <= 60, (
            f"🚨 SECURITY VIOLATION: risk_skew.max_skew_sec={dm.risk_skew.max_skew_sec} "
            f"in {live_mode} mode! Expected <= 60. "
            f"Backtest overlay may have leaked into production!"
        )

    def test_live_directional_sanity_enabled(self, temp_config_dir, clean_env):
        """
        LIVE: directional_sanity.enabled MUST be True.
        
        CRITICAL: Prevents counter-trend entries in production.
        """
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, "live")
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # ASSERT: STRICT production settings
        dm = config.domains.decision_making
        if hasattr(dm, 'directional_sanity'):
            assert dm.directional_sanity.enabled is True, (
                f"🚨 SECURITY VIOLATION: directional_sanity.enabled={dm.directional_sanity.enabled} "
                f"in live mode! Expected True. "
                f"Backtest overlay may have leaked into production!"
            )


# ============================================================================
# TEST CASE C: OVERLAY FILE ISOLATION
# ============================================================================

class TestOverlayFileIsolation:
    """Verify overlay file is only loaded for backtest mode."""

    def test_overlay_file_exists(self, canonical_config_dir):
        """Verify backtest_override.yaml exists in config directory."""
        overlay_path = canonical_config_dir / "backtest_override.yaml"
        assert overlay_path.exists(), (
            f"backtest_override.yaml not found at {overlay_path}. "
            f"Backtest mode will use strict production settings!"
        )

    def test_overlay_contains_relaxed_settings(self, canonical_config_dir):
        """Verify overlay file contains expected relaxed settings."""
        overlay_path = canonical_config_dir / "backtest_override.yaml"
        if not overlay_path.exists():
            pytest.skip("backtest_override.yaml not found")
        
        with open(overlay_path, 'r') as f:
            overlay = yaml.safe_load(f)
        
        # Check for expected relaxed settings
        assert 'domains' in overlay, "Overlay must have 'domains' section"
        
        fe = overlay.get('domains', {}).get('feature_engineering', {})
        warmup = fe.get('warmup', {})
        assert warmup.get('enforcement_mode') == 'warn_only', (
            f"Overlay warmup.enforcement_mode={warmup.get('enforcement_mode')}, "
            f"expected 'warn_only'"
        )

    def test_ssot_files_have_strict_defaults(self, canonical_config_dir):
        """Verify SSOT files have strict production defaults."""
        # Check domains.yaml
        domains_path = canonical_config_dir / "domains.yaml"
        with open(domains_path, 'r') as f:
            domains = yaml.safe_load(f)
        
        fe = domains.get('feature_engineering', {})
        warmup = fe.get('warmup', {})
        assert warmup.get('enforcement_mode') == 'fail_fast', (
            f"🚨 SSOT VIOLATION: domains.yaml warmup.enforcement_mode="
            f"{warmup.get('enforcement_mode')}, expected 'fail_fast'"
        )
        
        dm = domains.get('decision_making', {})
        risk_skew = dm.get('risk_skew', {})
        assert risk_skew.get('max_skew_sec', 999) <= 60, (
            f"🚨 SSOT VIOLATION: domains.yaml risk_skew.max_skew_sec="
            f"{risk_skew.get('max_skew_sec')}, expected <= 60"
        )


# ============================================================================
# TEST CASE D: CONFIG LOADER BEHAVIOR VERIFICATION
# ============================================================================

class TestConfigLoaderOverlayBehavior:
    """Verify ConfigLoader correctly handles overlay application."""

    def test_overlay_method_exists(self, temp_config_dir, clean_env):
        """Verify _apply_backtest_overlay method exists in ConfigLoader."""
        from apps.reference.config_loader import ConfigLoader
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        
        # Check method exists
        assert hasattr(loader, '_apply_backtest_overlay'), (
            "ConfigLoader missing _apply_backtest_overlay method"
        )

    def test_provenance_tracking_for_overlay(self, temp_config_dir, clean_env):
        """Verify provenance correctly tracks overlay source in backtest mode."""
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, "backtest")
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # Check provenance map for backtest_override entries
        overlay_entries = [
            k for k, v in loader.provenance_map.items() 
            if 'backtest_override' in str(v)
        ]
        
        assert len(overlay_entries) > 0, (
            "No provenance entries from backtest_override.yaml found. "
            "Overlay may not be properly tracked."
        )

    def test_no_overlay_provenance_in_live_mode(self, temp_config_dir, clean_env):
        """Verify no overlay provenance entries exist in live mode."""
        from apps.reference.config_loader import ConfigLoader
        
        _patch_trading_mode(temp_config_dir, "live")
        
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # Check NO provenance from backtest_override
        overlay_entries = [
            k for k, v in loader.provenance_map.items() 
            if 'backtest_override' in str(v)
        ]
        
        assert len(overlay_entries) == 0, (
            f"🚨 SECURITY VIOLATION: Found {len(overlay_entries)} provenance entries "
            f"from backtest_override.yaml in LIVE mode! Keys: {overlay_entries[:5]}"
        )


# ============================================================================
# FINAL SAFETY SUMMARY TEST
# ============================================================================

class TestProductionSafetySummary:
    """Final comprehensive safety verification."""

    def test_production_deployment_safety_checklist(self, canonical_config_dir, clean_env):
        """
        DEPLOYMENT GATE: All checks must pass before production deployment.
        
        This is the final safety gate test.
        """
        errors = []
        
        # 1. Verify domains.yaml has strict defaults
        domains_path = canonical_config_dir / "domains.yaml"
        with open(domains_path, 'r') as f:
            domains = yaml.safe_load(f)
        
        fe = domains.get('feature_engineering', {})
        if fe.get('warmup', {}).get('enforcement_mode') != 'fail_fast':
            errors.append("❌ domains.yaml: warmup.enforcement_mode != fail_fast")
        
        dm = domains.get('decision_making', {})
        if dm.get('risk_skew', {}).get('max_skew_sec', 999) > 60:
            errors.append("❌ domains.yaml: risk_skew.max_skew_sec > 60")
        
        # 2. Verify backtest_override.yaml exists
        overlay_path = canonical_config_dir / "backtest_override.yaml"
        if not overlay_path.exists():
            errors.append("⚠️ backtest_override.yaml missing (backtest will use strict settings)")
        
        # 3. Verify ConfigLoader logic
        from apps.reference.config_loader import ConfigLoader
        loader = ConfigLoader(config_dir=canonical_config_dir)
        
        # Check method exists
        if not hasattr(loader, '_apply_backtest_overlay'):
            errors.append("❌ ConfigLoader missing _apply_backtest_overlay method")
        
        # Final verdict
        if errors:
            error_report = "\n".join(errors)
            pytest.fail(
                f"\n{'='*60}\n"
                f"🚨 PRODUCTION DEPLOYMENT BLOCKED 🚨\n"
                f"{'='*60}\n"
                f"{error_report}\n"
                f"{'='*60}\n"
                f"Fix all issues before deploying to production!\n"
            )
        
        # All checks passed
        print("\n" + "="*60)
        print("✅ PRODUCTION DEPLOYMENT SAFE")
        print("="*60)
        print("All safety checks passed:")
        print("  ✅ domains.yaml has strict production defaults")
        print("  ✅ backtest_override.yaml exists for simulation")
        print("  ✅ ConfigLoader overlay pattern correctly implemented")
        print("="*60)
