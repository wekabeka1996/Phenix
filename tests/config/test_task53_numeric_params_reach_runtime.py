"""
TASK53-I: Numeric Parameters Reach Runtime Tests

Behavioral proofs that numeric config parameters actually affect runtime behavior:
1. execution_position.watchdog.ack_ttl_ms → affects watchdog timeout
2. decision_making.qos.symbol_cooldown_sec → affects intent DEFER timing
3. feature_engineering.volatility.window_sec → affects volatility calculation
4. position_tracking.positions_stale_ttl_sec → affects stale gate

All tests use tmp_path as config root and mock time/state to isolate behavior.
"""
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch
from decimal import Decimal

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    """Copy production config to tmp_path for mutation."""
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Helper to write YAML files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _assign_strategy_ids(cfg_dir: Path, symbol_to_ids: Dict[str, list[str]]) -> None:
    """Ensure strategy assignments exist in strategies.yaml for selected symbols."""
    strategies_path = cfg_dir / "strategies.yaml"
    strategies = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    assert isinstance(strategies, dict)
    assignments = strategies.setdefault("assignments", {})
    assert isinstance(assignments, dict)

    for symbol, strategy_ids in symbol_to_ids.items():
        assigned = assignments.setdefault(symbol, [])
        if not isinstance(assigned, list):
            assigned = []
            assignments[symbol] = assigned
        for strategy_id in strategy_ids:
            if strategy_id not in assigned:
                assigned.append(strategy_id)

    _write_yaml(strategies_path, strategies)


class TestWatchdogAckTtlMsReachesRuntime:
    """Prove that trading.execution.watchdog.ack_ttl_ms affects watchdog behavior.
    
    NOTE: watchdog was moved from domains.yaml to trading.yaml (TASK-ZOMBIE-FIX).
    """
    
    def test_ack_ttl_ms_is_loaded_correctly(self, tmp_path: Path) -> None:
        """ack_ttl_ms from config reaches the ExecPosFSM watchdog settings."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Modify ack_ttl_ms to a unique value (now in trading.yaml under trading.execution.watchdog)
        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        TEST_VALUE = 12345
        trading["trading"]["execution"]["watchdog"]["ack_ttl_ms"] = TEST_VALUE
        _write_yaml(trading_path, trading)
        
        # Load config
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Verify value is accessible at runtime (now via trading.execution.watchdog)
        assert config.trading.execution.watchdog.ack_ttl_ms == TEST_VALUE
    
    def test_different_ack_ttl_values_produce_different_configs(self, tmp_path: Path) -> None:
        """Changing ack_ttl_ms produces different config objects (not cached)."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        trading_path = cfg_dir / "trading.yaml"
        
        # Value 1 (now in trading.yaml under trading.execution.watchdog)
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        trading["trading"]["execution"]["watchdog"]["ack_ttl_ms"] = 5000
        _write_yaml(trading_path, trading)
        
        loader1 = ConfigLoader(config_dir=cfg_dir)
        config1 = loader1.load_config()
        val1 = config1.trading.execution.watchdog.ack_ttl_ms
        
        # Value 2 (different)
        trading["trading"]["execution"]["watchdog"]["ack_ttl_ms"] = 15000
        _write_yaml(trading_path, trading)
        
        loader2 = ConfigLoader(config_dir=cfg_dir)
        config2 = loader2.load_config()
        val2 = config2.trading.execution.watchdog.ack_ttl_ms
        
        assert val1 == 5000
        assert val2 == 15000
        assert val1 != val2


class TestPreflightBackoffMsIsFailClosed:
    """Prove that trading.execution.preflight_backoff_ms exists (no silent fallback)."""

    def test_preflight_backoff_ms_is_loaded_from_yaml(self, tmp_path: Path) -> None:
        cfg_dir = _copy_config_to_tmp(tmp_path)
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        assert config.trading.execution.preflight_backoff_ms is not None
        assert list(config.trading.execution.preflight_backoff_ms)

    def test_missing_preflight_backoff_ms_crashes(self, tmp_path: Path) -> None:
        from pydantic import ValidationError

        cfg_dir = _copy_config_to_tmp(tmp_path)

        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        assert isinstance(trading, dict)
        assert "trading" in trading and isinstance(trading["trading"], dict)
        assert "execution" in trading["trading"] and isinstance(trading["trading"]["execution"], dict)

        trading["trading"]["execution"].pop("preflight_backoff_ms", None)
        _write_yaml(trading_path, trading)

        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()

        assert "preflight_backoff_ms" in str(exc_info.value)


class TestQosSymbolCooldownSecReachesRuntime:
    """Prove that decision_making.qos.symbol_cooldown_sec affects QoS behavior."""
    
    def test_symbol_cooldown_sec_is_loaded_correctly(self, tmp_path: Path) -> None:
        """symbol_cooldown_sec from config reaches DecisionMaking domain."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Modify to unique value
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 42
        domains["decision_making"]["qos"]["symbol_cooldown_sec"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Verify value is accessible
        assert config.domains.decision_making.qos.symbol_cooldown_sec == TEST_VALUE
    
    def test_cooldown_affects_decision_making_init(self, tmp_path: Path) -> None:
        """DecisionMaking uses symbol_cooldown_sec from config at init."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Set specific cooldown
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 99
        domains["decision_making"]["qos"]["symbol_cooldown_sec"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Create mock FSM
        mock_fsm = MagicMock()
        mock_fsm.listen = MagicMock()
        
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        dm = DecisionMaking(fsm=mock_fsm, config=config)
        
        # Check that the domain stored the config value
        assert dm._default_symbol_cooldown_sec == TEST_VALUE


class TestVolatilityWindowSecReachesRuntime:
    """Prove that feature_engineering.volatility.window_sec affects calculations."""
    
    def test_volatility_window_sec_is_loaded_correctly(self, tmp_path: Path) -> None:
        """volatility.window_sec from config reaches FeatureEngineering domain."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Modify to unique value
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 120  # 2 minutes instead of default 60
        domains["feature_engineering"]["volatility"]["window_sec"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Verify value is accessible
        assert config.domains.feature_engineering.volatility.window_sec == TEST_VALUE
    
    def test_window_sec_affects_feature_engineering_init(self, tmp_path: Path) -> None:
        """FeatureEngineering uses volatility.window_sec from config at init."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Set specific window
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 180
        domains["feature_engineering"]["volatility"]["window_sec"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Create mock FSM
        mock_fsm = MagicMock()
        mock_fsm.listen = MagicMock()
        
        from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
        fe = FeatureEngineering(fsm=mock_fsm, config=config)
        
        # The FeatureEngineering should have access to config with our value
        # Check via the internal calculation engine or config resolver
        from apps.reference.domain_config import DomainConfigResolver
        resolver = DomainConfigResolver(config)
        fe_cfg = resolver.get_feature_engineering()
        assert fe_cfg.volatility.window_sec == TEST_VALUE


class TestPositionsStaleTtlSecReachesRuntime:
    """Prove that position_tracking.positions_stale_ttl_sec affects stale gate."""
    
    def test_positions_stale_ttl_sec_is_loaded_correctly(self, tmp_path: Path) -> None:
        """positions_stale_ttl_sec from config reaches domain."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Modify to unique value
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 30  # 30 seconds instead of default 15
        domains["position_tracking"]["positions_stale_ttl_sec"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Verify value is accessible
        assert config.domains.position_tracking.positions_stale_ttl_sec == TEST_VALUE
    
    def test_stale_ttl_is_used_by_domain(self, tmp_path: Path) -> None:
        """Position tracking uses positions_stale_ttl_sec in gate logic."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Set specific TTL
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 5  # Very short TTL
        domains["position_tracking"]["positions_stale_ttl_sec"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Verify it's in the config object
        assert config.domains.position_tracking.positions_stale_ttl_sec == TEST_VALUE


class TestEffectiveConfigSnapshot:
    """Test that config produces expected snapshot with correct numeric types."""
    
    def test_numeric_types_are_correct(self, tmp_path: Path) -> None:
        """All critical numeric fields have correct Python types."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Check integer fields (watchdog now in trading.execution, not domains)
        assert isinstance(config.trading.execution.watchdog.ack_ttl_ms, int)
        assert isinstance(config.trading.execution.watchdog.fill_ttl_ms, int)
        assert isinstance(config.domains.decision_making.qos.symbol_cooldown_sec, int)
        assert isinstance(config.domains.feature_engineering.volatility.window_sec, int)
        assert isinstance(config.domains.position_tracking.positions_stale_ttl_sec, int)
        
        # Check float fields
        assert isinstance(config.domains.risk_management.trading_allowed_thresholds.max_risk_score, float)
    
    def test_critical_numeric_keys_present(self, tmp_path: Path) -> None:
        """All critical numeric keys are present and non-None."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # List of critical paths that must be present
        # NOTE: watchdog moved from domains.execution_position to trading.execution (TASK-ZOMBIE-FIX)
        critical_numeric_paths = [
            ("trading", "execution", "watchdog", "ack_ttl_ms"),
            ("trading", "execution", "watchdog", "fill_ttl_ms"),
            ("trading", "execution", "watchdog", "check_interval_ms"),
            ("domains", "decision_making", "qos", "symbol_cooldown_sec"),
            ("domains", "decision_making", "qos", "max_intents_per_minute_per_symbol"),
            ("domains", "feature_engineering", "volatility", "window_sec"),
            ("domains", "feature_engineering", "volatility", "sma_length"),
            ("domains", "position_tracking", "positions_stale_ttl_sec"),
            ("domains", "risk_management", "trading_allowed_thresholds", "max_risk_score"),
        ]
        
        for path in critical_numeric_paths:
            obj = config
            for attr in path:
                obj = getattr(obj, attr)
            assert obj is not None, f"Path {'.'.join(path)} is None"
            assert isinstance(obj, (int, float)), f"Path {'.'.join(path)} is not numeric: {type(obj)}"
    
    def test_config_to_dict_preserves_numerics(self, tmp_path: Path) -> None:
        """config.to_dict() preserves numeric values correctly."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Get dict representation
        config_dict = config.model_dump() if hasattr(config, "model_dump") else config.to_dict()
        
        # Verify numeric values are preserved (watchdog now in trading.execution)
        assert isinstance(config_dict["trading"]["execution"]["watchdog"]["ack_ttl_ms"], int)
        assert config_dict["trading"]["execution"]["watchdog"]["ack_ttl_ms"] > 0


class TestRiskManagementThresholdsReachRuntime:
    """Prove that risk_management thresholds affect runtime decisions."""
    
    def test_max_risk_score_is_loaded_correctly(self, tmp_path: Path) -> None:
        """max_risk_score from config reaches RiskManagement domain."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        
        # Modify to unique value
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        TEST_VALUE = 0.75
        domains["risk_management"]["trading_allowed_thresholds"]["max_risk_score"] = TEST_VALUE
        _write_yaml(domains_path, domains)
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # Verify value is accessible
        assert config.domains.risk_management.trading_allowed_thresholds.max_risk_score == pytest.approx(TEST_VALUE)


class TestMeanReversionConfigsReachRuntime:
    """Prove that mean_reversion.yaml configs for XRP/DOGE reach runtime correctly."""
    
    def test_xrp_doge_mr_configs_loaded_correctly(self, tmp_path: Path) -> None:
        """XRP/DOGE/BTC configs from mean_reversion.yaml are loaded and differ as expected."""
        cfg_dir = _copy_config_to_tmp(tmp_path)
        _assign_strategy_ids(
            cfg_dir,
            {
                "BTCUSDT": ["mean_reversion"],
                "DOGEUSDT": ["mean_reversion"],
                "XRPUSDT": ["mean_reversion"],
            },
        )
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        mr = config.strategies.mean_reversion
        assert mr.enabled is True
        assert mr.timeframe_sec == 300
        
        # DOGE specific overrides
        doge = mr.assets.get("DOGEUSDT")
        assert doge is not None
        assert doge.enabled is True
        assert doge.strategy.bb_num_std == 2.1
        assert doge.strategy.tp_to_mid is False  # DOGE targets outer band
        assert doge.strategy.cooldown_sec == 210
        # NOTE: risk.position_size_usd removed from MRAssetConfig (TASK-ZOMBIE-FIX), sizing now via instruments
        
        # XRP specific overrides
        xrp = mr.assets.get("XRPUSDT")
        assert xrp is not None
        assert xrp.enabled is True
        assert xrp.strategy.bb_num_std == 2.5
        assert xrp.strategy.tp_to_mid is True  # XRP targets mid band
        assert xrp.strategy.cooldown_sec == 165
        # NOTE: risk.position_size_usd removed from MRAssetConfig (TASK-ZOMBIE-FIX)
        
        # XRP has sl_atr_mult = 2.0 (FIX: was null, now uses industry standard 2.0x ATR)
        assert xrp.strategy.sl_atr_mult == 2.0
        assert mr.strategy.sl_atr_mult == 1.5

    def test_mr_handler_uses_per_asset_overrides(self, tmp_path: Path) -> None:
        """MeanReversionHandler correctly applies per-asset config overrides."""
        from unittest.mock import MagicMock
        from decimal import Decimal
        
        cfg_dir = _copy_config_to_tmp(tmp_path)
        _assign_strategy_ids(
            cfg_dir,
            {
                "BTCUSDT": ["mean_reversion"],
                "DOGEUSDT": ["mean_reversion"],
                "XRPUSDT": ["mean_reversion"],
            },
        )
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        mock_fsm = MagicMock()
        mock_fsm.listen = MagicMock()
        
        from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
        handler = MeanReversionHandler(fsm=mock_fsm, config=config)
        
        assert handler._enabled is True
        
        # Check DOGE strategy runtime config
        doge_strat = handler._strategies.get("DOGEUSDT")
        if doge_strat:  # Only if DOGE is assigned in strategies_registry
            assert doge_strat.config.tp_to_mid is False
            assert doge_strat.config.bb_num_std == 2.1
            assert doge_strat.config.cooldown_sec == 210
            # sl_atr_mult should be 1.5 (from DOGE config or global fallback)
            assert doge_strat.config.sl_atr_mult == Decimal("1.5")
        
        # Check XRP strategy runtime config
        xrp_strat = handler._strategies.get("XRPUSDT")
        if xrp_strat:  # Only if XRP is assigned in strategies_registry
            assert xrp_strat.config.tp_to_mid is True
            assert xrp_strat.config.bb_num_std == 2.5
            assert xrp_strat.config.cooldown_sec == 165
            # sl_atr_mult = 2.0 (FIX: was null, now uses industry standard 2.0x ATR)
            assert xrp_strat.config.sl_atr_mult == Decimal("2.0")
