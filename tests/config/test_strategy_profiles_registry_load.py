"""
Tests for registry-driven strategy profile loading.

CFG-STRATEGIES-SSOT-03-REGISTRY-DRIVEN-LOADING-AND-ONE-CONFIG-TRUTH
"""

import pytest
import yaml
import shutil
from pathlib import Path
from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(dst_config_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    shutil.copytree(src, dst_config_dir)


def _write_strategies_yaml(config_dir: Path, *, assignments: dict[str, list[str]]) -> None:
    priorities: dict[str, int] = {}
    priority_counter = 1
    strategy_ids: list[str] = []
    for _, strat_list in assignments.items():
        for sid in strat_list:
            if sid not in priorities:
                priorities[sid] = priority_counter
                priority_counter += 1
            if sid not in strategy_ids:
                strategy_ids.append(sid)

    strategies_yaml = {
        "version": "1.0.0",
        "assignments": assignments,
        "arbitration": {
            "mode": "priority",
            "priority": priorities,
            "logging": {"rejected_why_prefix": "ARBITRATION_REJECT", "log_level": "INFO"},
        },
    }
    (config_dir / "strategies.yaml").write_text(yaml.dump(strategies_yaml), encoding="utf-8")


def create_test_config(config_dir: Path, with_mr_assignment=True, with_mr_profile=True, with_aurora=False):
    """Create config based on canonical SSOT, then toggle assignments/profile presence."""
    config_dir.parent.mkdir(parents=True, exist_ok=True)
    _copy_canonical_config_dir(config_dir)

    assignments: dict[str, list[str]] = {}
    strategy_list: list[str] = []
    if with_aurora:
        strategy_list.append("aurora")
    if with_mr_assignment:
        strategy_list.append("mean_reversion_1m")
    if strategy_list:
        assignments["BTCUSDT"] = strategy_list

    _write_strategies_yaml(config_dir, assignments=assignments)

    strategies_dir = config_dir / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)

    if not with_mr_profile:
        mr_path = strategies_dir / "mean_reversion_1m.yaml"
        if mr_path.exists():
            mr_path.unlink()

    if not with_aurora:
        aurora_path = strategies_dir / "aurora.yaml"
        if aurora_path.exists():
            aurora_path.unlink()


class TestRegistryDrivenLoading:
    """Test that ConfigLoader loads strategy profiles ONLY from strategies_registry.assignments"""
    
    def test_registry_driven_load_mean_reversion(self, tmp_path):
        """
        Test that MR profile is loaded via registry assignments (not hardcoded).
        
        CFG-STRATEGIES-SSOT-03: ConfigLoader reads strategies.yaml assignments,
        then loads corresponding profiles from strategies/{id}.yaml
        """
        config_dir = tmp_path / "config" / "aurora"
        create_test_config(config_dir, with_mr_assignment=True, with_mr_profile=True)
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: mean_reversion_1m config loaded from profile (not hardcoded)
        assert hasattr(config, "mean_reversion_1m")
        assert config.mean_reversion_1m is not None
        assert config.mean_reversion_1m.enabled is True
        assert config.mean_reversion_1m.timeframe_sec == 60
    
    def test_assigned_strategy_missing_profile_fails(self, tmp_path):
        """
        Test FAIL-CLOSED: strategy assigned in registry but profile missing → ValueError.
        
        CFG-STRATEGIES-SSOT-03: Strict mode - missing profile for assigned strategy must crash.
        """
        config_dir = tmp_path / "config" / "aurora"
        # Create config WITHOUT MR profile (but WITH assignment)
        create_test_config(config_dir, with_mr_assignment=True, with_mr_profile=False)
        
        # Load config - MUST FAIL
        loader = ConfigLoader(config_dir=config_dir)
        with pytest.raises(ValueError) as exc_info:
            config = loader.load_config()
        
        # VERIFY: error message mentions missing profile
        error_msg = str(exc_info.value)
        assert "mean_reversion_1m" in error_msg
        assert "profile missing" in error_msg.lower() or "missing" in error_msg.lower()
    
    def test_unassigned_strategy_profile_not_loaded(self, tmp_path):
        """
        Test that strategy profile present but NOT in assignments → not loaded.
        
        CFG-STRATEGIES-SSOT-03: Only load profiles for strategies actually assigned.
        """
        config_dir = tmp_path / "config" / "aurora"
        # Create config WITH aurora assignment and profile, but MR profile without assignment
        create_test_config(config_dir, with_mr_assignment=False, with_mr_profile=True, with_aurora=True)
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: mean_reversion_1m NOT loaded (not in assignments)
        assert config.mean_reversion_1m is None
    
    def test_multiple_strategies_assigned_all_loaded(self, tmp_path):
        """
        Test that multiple strategies assigned → all profiles loaded.
        
        CFG-STRATEGIES-SSOT-03: BTC hybrid (aurora + MR) → both profiles loaded.
        """
        config_dir = tmp_path / "config" / "aurora"
        create_test_config(config_dir, with_mr_assignment=True, with_mr_profile=True, with_aurora=True)
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: BOTH profiles loaded
        assert hasattr(config, "mean_reversion_1m")
        assert config.mean_reversion_1m is not None
        assert config.mean_reversion_1m.enabled is True
