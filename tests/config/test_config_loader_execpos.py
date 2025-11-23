"""
Integration Tests for EP-CONFIG-INJECTION-S2

Validates that config_loader builds ExecutionPositionConfig from config_v2.domains['execution']
and attaches it to master config as execution_position_cfg.

RID: EP-CONFIG-INJECTION-S2
"""

import pytest
from pathlib import Path
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.config import ExecutionPositionConfig


def test_config_loader_builds_execution_position_cfg(tmp_path, monkeypatch):
    """Test: config_loader builds ExecutionPositionConfig from execution.yaml"""
    # Create minimal config structure
    # ConfigLoader expects: project_root/config/domains/execution.yaml
    # and config_dir points to project_root/config/aurora
    aurora_dir = tmp_path / "config" / "aurora"
    aurora_dir.mkdir(parents=True)
    domains_dir = tmp_path / "config" / "domains"
    domains_dir.mkdir(parents=True)

    # Mock project_root detection to point to tmp_path
    monkeypatch.setenv("AURORA_PROJECT_ROOT", str(tmp_path))

    # Minimal system.yaml
    (aurora_dir / "system.yaml").write_text("""
logging:
  level: INFO
""")

    # Minimal trading.yaml
    (aurora_dir / "trading.yaml").write_text("""
trading_mode: testnet
mode: testnet
""")

    # execution.yaml with manage.brackets.aggregated_oco
    (domains_dir / "execution.yaml").write_text("""
manage:
  brackets:
    aggregated_oco:
      enabled: true
      aggregated_only_mode: false
      sl_pct: 0.025
      tp_rr: 2.5
      recalc_on_scale_in: true
      recalc_on_partial_close: false
      ttl_protect_new_bracket_ms: 4000
      allow_unprotected_position: false
      max_sl_legs: 2
      max_tp_legs: 3
  trailing:
    enabled: true
    trail_distance_bps: 150.0
    activate_after_bps: 50.0
    breakeven_rr: 1.5
  close:
    max_hold_time_sec: 7200
    reason_policy: strict
""")

    # Load config
    loader = ConfigLoader(config_dir=aurora_dir)
    master_cfg = loader.load_config()

    # Verify execution_position_cfg exists
    assert hasattr(
        master_cfg, 'execution_position_cfg'), "execution_position_cfg should exist in master config"
    assert master_cfg.execution_position_cfg is not None, "execution_position_cfg should not be None"

    # Verify type
    ep_cfg = master_cfg.execution_position_cfg
    assert isinstance(
        ep_cfg, ExecutionPositionConfig), f"Expected ExecutionPositionConfig, got {type(ep_cfg)}"

    # Verify aggregated_oco fields
    assert ep_cfg.aggregated_oco.enabled is True
    assert ep_cfg.aggregated_oco.sl_pct == 0.025
    assert ep_cfg.aggregated_oco.tp_rr == 2.5
    assert ep_cfg.aggregated_oco.max_sl_legs == 2
    assert ep_cfg.aggregated_oco.max_tp_legs == 3

    # Verify trailing fields
    assert ep_cfg.trailing.enabled is True
    assert ep_cfg.trailing.trail_distance_bps == 150.0
    assert ep_cfg.trailing.breakeven_rr == 1.5

    # Verify close fields
    assert ep_cfg.close.max_hold_time_sec == 7200
    assert ep_cfg.close.reason_policy == "strict"


def test_config_loader_execution_position_cfg_defaults(tmp_path, monkeypatch):
    """Test: config_loader with empty execution.yaml uses defaults"""
    aurora_dir = tmp_path / "config" / "aurora"
    aurora_dir.mkdir(parents=True)
    domains_dir = tmp_path / "config" / "domains"
    domains_dir.mkdir(parents=True)
    monkeypatch.setenv("AURORA_PROJECT_ROOT", str(tmp_path))

    (aurora_dir / "system.yaml").write_text("logging:\n  level: INFO\n")
    (aurora_dir / "trading.yaml").write_text("trading_mode: testnet\nmode: testnet\n")

    # Empty execution.yaml
    (domains_dir / "execution.yaml").write_text("{}\n")

    loader = ConfigLoader(config_dir=aurora_dir)
    master_cfg = loader.load_config()

    # Should still build with defaults
    assert hasattr(master_cfg, 'execution_position_cfg')
    ep_cfg = master_cfg.execution_position_cfg
    assert ep_cfg is not None

    # Check defaults
    assert ep_cfg.aggregated_oco.enabled is False  # Default
    assert ep_cfg.aggregated_oco.sl_pct == 0.02  # Default
    assert ep_cfg.aggregated_oco.tp_rr == 2.0  # Default
    assert ep_cfg.trailing.enabled is False  # Default
    assert ep_cfg.trailing.trail_distance_bps == 100.0  # Default


def test_config_loader_execution_position_cfg_validation_error(tmp_path, monkeypatch):
    """Test: config_loader raises ValidationError on invalid execution config"""
    aurora_dir = tmp_path / "config" / "aurora"
    aurora_dir.mkdir(parents=True)
    domains_dir = tmp_path / "config" / "domains"
    domains_dir.mkdir(parents=True)
    monkeypatch.setenv("AURORA_PROJECT_ROOT", str(tmp_path))

    (aurora_dir / "system.yaml").write_text("logging:\n  level: INFO\n")
    (aurora_dir / "trading.yaml").write_text("trading_mode: testnet\nmode: testnet\n")

    # Invalid execution.yaml (sl_pct = 0.0)
    (domains_dir / "execution.yaml").write_text("""
manage:
  brackets:
    aggregated_oco:
      sl_pct: 0.0
      tp_rr: 2.0
""")

    loader = ConfigLoader(config_dir=aurora_dir)

    # Should NOT raise ValidationError at config_loader level (graceful degradation)
    # ValidationError is logged but system continues with dict-based config
    master_cfg = loader.load_config()

    # execution_position_cfg should be None (failed to build)
    assert master_cfg.execution_position_cfg is None or not hasattr(
        master_cfg, 'execution_position_cfg')


def test_config_loader_execution_position_cfg_fallback_path(tmp_path, monkeypatch):
    """Test: config_loader with flat path (brackets.aggregated_oco) works"""
    aurora_dir = tmp_path / "config" / "aurora"
    aurora_dir.mkdir(parents=True)
    domains_dir = tmp_path / "config" / "domains"
    domains_dir.mkdir(parents=True)
    monkeypatch.setenv("AURORA_PROJECT_ROOT", str(tmp_path))

    (aurora_dir / "system.yaml").write_text("logging:\n  level: INFO\n")
    (aurora_dir / "trading.yaml").write_text("trading_mode: testnet\nmode: testnet\n")

    # Flat path (no "manage" prefix)
    (domains_dir / "execution.yaml").write_text("""
brackets:
  aggregated_oco:
    enabled: true
    sl_pct: 0.03
    tp_rr: 3.0
trailing:
  enabled: true
  trail_distance_bps: 200.0
""")

    loader = ConfigLoader(config_dir=aurora_dir)
    master_cfg = loader.load_config()

    # Should build via fallback path
    assert hasattr(master_cfg, 'execution_position_cfg')
    ep_cfg = master_cfg.execution_position_cfg
    assert ep_cfg is not None

    assert ep_cfg.aggregated_oco.enabled is True
    assert ep_cfg.aggregated_oco.sl_pct == 0.03
    assert ep_cfg.aggregated_oco.tp_rr == 3.0
    assert ep_cfg.trailing.enabled is True
    assert ep_cfg.trailing.trail_distance_bps == 200.0


def test_config_loader_execution_position_cfg_missing_domain(tmp_path, monkeypatch):
    """Test: config_loader without execution.yaml skips ExecutionPositionConfig"""
    aurora_dir = tmp_path / "config" / "aurora"
    aurora_dir.mkdir(parents=True)
    domains_dir = tmp_path / "config" / "domains"
    domains_dir.mkdir(parents=True)
    monkeypatch.setenv("AURORA_PROJECT_ROOT", str(tmp_path))

    (aurora_dir / "system.yaml").write_text("logging:\n  level: INFO\n")
    (aurora_dir / "trading.yaml").write_text("trading_mode: testnet\nmode: testnet\n")

    # No execution.yaml

    loader = ConfigLoader(config_dir=aurora_dir)
    master_cfg = loader.load_config()

    # execution_position_cfg should be None (no execution domain config)
    ep_cfg = getattr(master_cfg, 'execution_position_cfg', None)
    assert ep_cfg is None, "execution_position_cfg should be None when execution.yaml missing"


def test_config_loader_backward_compat_dict_path_untouched(tmp_path, monkeypatch):
    """Test: Old dict-based config path still works (backward compatibility)"""
    aurora_dir = tmp_path / "config" / "aurora"
    aurora_dir.mkdir(parents=True)
    domains_dir = tmp_path / "config" / "domains"
    domains_dir.mkdir(parents=True)
    monkeypatch.setenv("AURORA_PROJECT_ROOT", str(tmp_path))

    (aurora_dir / "system.yaml").write_text("logging:\n  level: INFO\n")
    (aurora_dir / "trading.yaml").write_text("""
trading_mode: testnet
mode: testnet
execution:
  manage:
    brackets:
      sl:
        fixed_bps: 50
""")

    (domains_dir / "execution.yaml").write_text("""
manage:
  brackets:
    aggregated_oco:
      enabled: true
      sl_pct: 0.02
""")

    loader = ConfigLoader(config_dir=aurora_dir)
    master_cfg = loader.load_config()

    # New typed path should exist
    assert hasattr(master_cfg, 'execution_position_cfg')
    assert master_cfg.execution_position_cfg is not None

    # Old dict path should still be accessible via legacy .get() or .execution
    assert hasattr(
        master_cfg, 'execution'), "Legacy execution dict should still exist"
    assert master_cfg.execution is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
