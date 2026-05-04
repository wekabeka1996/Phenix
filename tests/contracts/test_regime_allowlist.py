"""
Tests for Regime Allowlist Contract.

TASK51-B: TDD tests for regime allowlist validation.
"""

import pytest
from typing import Dict, List, Any
from pathlib import Path

import yaml

from apps.reference.domains.regime_allowlist.contract import (
    RegimeAllowlistContract,
    RegimeAllowlistError,
    StrategyRegimeConfig,
    AllowlistViolation,
    validate_strategy_regime_config,
    MR_COMPATIBLE_REGIMES,
    ALL_REGIMES,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


def make_assignments(symbol_strategies: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Create mock strategies.yaml assignments."""
    return symbol_strategies


def make_aurora_assets(symbol_configs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Create mock strategies/aurora.yaml::aurora.assets."""
    return symbol_configs


# ==============================================================================
# Contract Tests
# ==============================================================================


class TestStrategyRegimeConfig:
    """Test StrategyRegimeConfig extraction and properties."""
    
    def test_allows_mr_regimes_with_flat(self):
        """Config with FLAT regimes should allow MR."""
        config = StrategyRegimeConfig(
            symbol="DOGEUSDT",
            strategy="mean_reversion",
            allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
            has_mr_assignment=True,
            has_aurora_assignment=False,
        )
        assert config.allows_mr_regimes is True
    
    def test_blocks_mr_regimes_with_trend_only(self):
        """Config with only TREND regimes should not allow MR."""
        config = StrategyRegimeConfig(
            symbol="ETHUSDT",
            strategy="aurora",
            allowed_regimes=["TREND_UP", "TREND_DOWN"],
            has_mr_assignment=True,
            has_aurora_assignment=True,
        )
        assert config.allows_mr_regimes is False
    
    def test_null_allowed_regimes_blocks_all(self):
        """STRICT: None allowed_regimes means allow nothing (fail-closed)."""
        config = StrategyRegimeConfig(
            symbol="BTCUSDT",
            strategy="aurora",
            allowed_regimes=None,
            has_mr_assignment=False,
            has_aurora_assignment=True,
        )
        assert config.allows_mr_regimes is False
        assert config.allows_aurora_regimes is False
    
    def test_is_mr_enabled_but_blocked(self):
        """Detect when MR is assigned but blocked by regimes."""
        config = StrategyRegimeConfig(
            symbol="TESTUSDT",
            strategy="mean_reversion",
            allowed_regimes=["TREND_UP", "TREND_DOWN"],  # No FLAT regimes!
            has_mr_assignment=True,
            has_aurora_assignment=False,
        )
        assert config.is_mr_enabled_but_blocked is True


class TestRegimeAllowlistContract:
    """Test RegimeAllowlistContract validation logic."""
    
    def test_extract_strategy_config(self):
        """Should extract config from assignments and strategies/aurora.yaml::aurora.assets."""
        assignments = {"DOGEUSDT": ["mean_reversion"]}
        aurora_assets = {
            "DOGEUSDT": {
                "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL"],
            }
        }
        
        config = RegimeAllowlistContract.extract_strategy_config(
            "DOGEUSDT",
            assignments,
            aurora_assets,
        )
        
        assert config.symbol == "DOGEUSDT"
        assert config.has_mr_assignment is True
        assert config.allowed_regimes == ["FLAT_LOW", "FLAT_NORMAL"]
    
    def test_validate_symbol_mr_ok(self):
        """MR with FLAT regimes should pass validation."""
        config = StrategyRegimeConfig(
            symbol="DOGEUSDT",
            strategy="mean_reversion",
            allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "LOW_VOLATILITY"],
            has_mr_assignment=True,
            has_aurora_assignment=False,
        )
        
        violations = RegimeAllowlistContract.validate_symbol(config)
        
        assert len(violations) == 0
    
    def test_validate_symbol_mr_blocked_is_critical(self):
        """MR assigned but no FLAT regimes should be CRITICAL."""
        config = StrategyRegimeConfig(
            symbol="ETHUSDT",
            strategy="mean_reversion",
            allowed_regimes=["TREND_UP", "TREND_DOWN"],
            has_mr_assignment=True,
            has_aurora_assignment=False,
        )
        
        violations = RegimeAllowlistContract.validate_symbol(config)
        
        assert len(violations) == 1
        assert violations[0].severity == "CRITICAL"
        assert "MR strategy assigned but no MR-compatible regimes" in violations[0].message
    
    def test_validate_symbol_unknown_regimes_warning(self):
        """Unknown regimes should produce WARNING."""
        config = StrategyRegimeConfig(
            symbol="TESTUSDT",
            strategy="aurora",
            allowed_regimes=["TREND_UP", "INVALID_REGIME"],
            has_mr_assignment=False,
            has_aurora_assignment=True,
        )
        
        violations = RegimeAllowlistContract.validate_symbol(config)
        
        assert len(violations) == 1
        assert violations[0].severity == "WARNING"
        assert "Unknown regimes" in violations[0].message


# ==============================================================================
# TASK51-B Required Tests
# ==============================================================================


class TestMRBlockingExplainable:
    """TASK51-B: Test MR blocking is explainable and config-driven."""
    
    def test_mr_blocking_is_explainable_and_config_driven(self):
        """
        TASK51-B Test 1: MR blocking should be explainable.
        
        When a regime blocks MR trading, the reason must be:
        1. Traceable to strategies/aurora.yaml::aurora.assets
        2. Include the blocked regime and allowed list
        """
        explanation = RegimeAllowlistContract.explain_blocking(
            symbol="ETHUSDT",
            current_regime="MEAN_REVERSION",
            allowed_regimes=["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY"],
        )
        
        # Must include symbol
        assert "ETHUSDT" in explanation
        # Must indicate blocking
        assert "BLOCKED" in explanation
        # Must show current regime
        assert "MEAN_REVERSION" in explanation
        # Must reference config source
        assert "strategies/aurora.yaml" in explanation
    
    def test_mr_enabled_when_allowlisted(self):
        """
        TASK51-B Test 2: MR should be enabled when properly allowlisted.
        
        When FLAT regimes are in allowed_regimes, MR should work.
        """
        assignments = {"DOGEUSDT": ["mean_reversion"]}
        aurora_assets = {
            "DOGEUSDT": {
                "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
            }
        }
        
        # Should not raise
        RegimeAllowlistContract.validate_all(
            assignments,
            aurora_assets,
            fail_on_critical=True,
        )
        
        # Verify the config allows MR
        config = RegimeAllowlistContract.extract_strategy_config(
            "DOGEUSDT",
            assignments,
            aurora_assets,
        )
        assert config.allows_mr_regimes is True
        assert config.is_mr_enabled_but_blocked is False


class TestConfigValidation:
    """Test full config validation scenarios."""
    
    def test_valid_config_passes(self):
        """Valid configuration should pass without exception."""
        assignments = {
            "DOGEUSDT": ["mean_reversion"],
            "XRPUSDT": ["mean_reversion"],
            "BTCUSDT": ["aurora", "mean_reversion"],
            "ETHUSDT": ["aurora"],
        }
        aurora_instruments = {
            "DOGEUSDT": {
                "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL"],
            },
            "XRPUSDT": {
                "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "LOW_VOLATILITY"],
            },
            "BTCUSDT": {
                "allowed_regimes": ["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY", "MEAN_REVERSION", "FLAT_LOW"],
            },
            "ETHUSDT": {
                "allowed_regimes": ["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY"],
            },
        }
        
        # Should not raise
        violations = RegimeAllowlistContract.validate_all(
            assignments,
            aurora_instruments,
            fail_on_critical=True,
        )
        
        assert len(violations) == 0


# ==============================================================================
# STRICT YAML-DRIVEN POLICY (SSOT): per-symbol allowlist membership
# ==============================================================================


def _load_yaml(path: str) -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    p = (repo_root / path).resolve()
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _extract_assets_and_allowlist_from_strategy_yaml(strategy_name: str) -> Dict[str, List[str] | None]:
    """Return symbol -> allowed_regimes from the strategy SSOT YAML."""
    if strategy_name == "aurora":
        data = _load_yaml("config/aurora/strategies/aurora.yaml")
        assets = ((data.get("aurora") or {}).get("assets") or {})
    elif strategy_name == "mean_reversion":
        data = _load_yaml("config/aurora/strategies/mean_reversion.yaml")
        assets = ((data.get("mean_reversion") or {}).get("assets") or {})
    else:
        raise ValueError(f"Unknown strategy_name={strategy_name}")

    out: Dict[str, List[str] | None] = {}
    for symbol, cfg in (assets or {}).items():
        if not isinstance(cfg, dict):
            continue
        out[str(symbol)] = cfg.get("allowed_regimes")
    return out


@pytest.mark.parametrize("strategy_name", ["aurora", "mean_reversion"])
def test_each_symbol_defines_non_empty_allowed_regimes(strategy_name: str):
    """Архитектурный контракт: управление режимами только через YAML allowlist (fail-closed)."""
    allowlists = _extract_assets_and_allowlist_from_strategy_yaml(strategy_name)
    assert allowlists, f"No assets found in strategy YAML for {strategy_name}"

    for symbol, allowed in allowlists.items():
        assert allowed is not None, f"{strategy_name}.{symbol}: allowed_regimes must be set (not null)"
        assert isinstance(allowed, list), f"{strategy_name}.{symbol}: allowed_regimes must be a list"
        assert len(allowed) > 0, f"{strategy_name}.{symbol}: allowed_regimes must be non-empty"


def _params_from_yaml_allowlists(strategy_name: str):
    allowlists = _extract_assets_and_allowlist_from_strategy_yaml(strategy_name)
    params = []
    for symbol, allowed in allowlists.items():
        for regime in sorted(ALL_REGIMES):
            expected = bool(allowed) and (regime in allowed)
            params.append((strategy_name, symbol, regime, expected, allowed))
    return params


@pytest.mark.parametrize(
    "strategy_name,symbol,regime,expected,allowed_regimes",
    _params_from_yaml_allowlists("aurora") + _params_from_yaml_allowlists("mean_reversion"),
)
def test_allowlist_membership_controls_trading(strategy_name: str, symbol: str, regime: str, expected: bool, allowed_regimes):
    """Если режим есть в YAML allowlist — разрешён; если нет — запрещён."""
    allowed = RegimeAllowlistContract.is_regime_allowed(
        current_regime=regime,
        allowed_regimes=list(allowed_regimes) if allowed_regimes is not None else None,
    )
    assert allowed is expected, (
        f"{strategy_name}.{symbol}: regime={regime} expected={expected} allowed_regimes={allowed_regimes}"
    )


class TestConfigValidationStrict:
    """Additional strict-mode validation tests."""

    def test_invalid_config_raises(self):
        """Invalid configuration should raise RegimeAllowlistError."""
        assignments = {
            "DOGEUSDT": ["mean_reversion"],  # MR assigned
        }
        aurora_instruments = {
            "DOGEUSDT": {
                # WRONG: Only trend regimes, no FLAT for MR!
                "allowed_regimes": ["TREND_UP", "TREND_DOWN"],
            },
        }

        with pytest.raises(RegimeAllowlistError) as exc_info:
            RegimeAllowlistContract.validate_all(
                assignments,
                aurora_instruments,
                fail_on_critical=True,
            )

        assert len(exc_info.value.violations) == 1
        assert exc_info.value.violations[0].symbol == "DOGEUSDT"
        assert "MR strategy assigned" in exc_info.value.violations[0].message


class TestStartupHook:
    """Test validate_strategy_regime_config startup hook."""
    
    def test_validates_strategies_yaml_format(self):
        """Should handle strategies.yaml format correctly."""
        strategies_yaml = {
            "version": "1.0.0",
            "assignments": {
                "BTCUSDT": ["aurora", "mean_reversion"],
            },
        }
        aurora_assets_yaml = {
            "BTCUSDT": {
                "allowed_regimes": ["FLAT_LOW", "MEAN_REVERSION", "TREND_UP"],
            },
        }
        
        # Should not raise
        validate_strategy_regime_config(
            strategies_yaml,
            aurora_assets_yaml,
            mode="live",
        )
    
    def test_empty_assignments_skips_validation(self):
        """Empty assignments should skip validation gracefully."""
        # Should not raise
        validate_strategy_regime_config(
            {},
            {},
            mode="live",
        )


class TestExplainBlocking:
    """Test regime blocking explanation."""
    
    def test_explain_allowed_regime(self):
        """Should explain when regime is allowed."""
        explanation = RegimeAllowlistContract.explain_blocking(
            symbol="BTCUSDT",
            current_regime="TREND_UP",
            allowed_regimes=["TREND_UP", "TREND_DOWN"],
        )
        
        assert "ALLOWED" in explanation
    
    def test_explain_missing_allowlist_is_fail_closed(self):
        """STRICT: Missing allowlist should be explainable and fail-closed."""
        explanation = RegimeAllowlistContract.explain_blocking(
            symbol="BTCUSDT",
            current_regime="TREND_UP",
            allowed_regimes=None,
        )

        assert "BLOCKED" in explanation
        assert "missing/empty" in explanation


class TestRealConfigScenarios:
    """Test with realistic config scenarios from project."""
    
    def test_eth_config_aurora_only(self):
        """ETH with Aurora-only should validate correctly."""
        assignments = {"ETHUSDT": ["aurora"]}
        aurora_instruments = {
            "ETHUSDT": {
                "allowed_regimes": ["TREND_UP", "TREND_DOWN", "FLAT_LOW", "FLAT_NORMAL", "LOW_VOLATILITY"],
            },
        }
        
        violations = RegimeAllowlistContract.validate_all(
            assignments,
            aurora_instruments,
            fail_on_critical=True,
        )
        
        assert len(violations) == 0
    
    def test_doge_config_mr_with_flat(self):
        """DOGE with MR and FLAT regimes should validate."""
        assignments = {"DOGEUSDT": ["mean_reversion"]}
        aurora_instruments = {
            "DOGEUSDT": {
                "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "LOW_VOLATILITY"],
            },
        }
        
        violations = RegimeAllowlistContract.validate_all(
            assignments,
            aurora_instruments,
            fail_on_critical=True,
        )
        
        assert len(violations) == 0
    
    def test_btc_hybrid_config(self):
        """BTC with hybrid (aurora + MR) should validate."""
        assignments = {"BTCUSDT": ["aurora", "mean_reversion"]}
        aurora_instruments = {
            "BTCUSDT": {
                "allowed_regimes": [
                    "TREND_UP", "TREND_DOWN", "LOW_VOLATILITY",
                    "MEAN_REVERSION", "FLAT_LOW", "FLAT_NORMAL"
                ],
            },
        }
        
        violations = RegimeAllowlistContract.validate_all(
            assignments,
            aurora_instruments,
            fail_on_critical=True,
        )
        
        assert len(violations) == 0


class TestMRCompatibleRegimes:
    """Test MR_COMPATIBLE_REGIMES constant."""
    
    def test_flat_regimes_are_mr_compatible(self):
        """All FLAT regimes should be MR-compatible."""
        assert "FLAT_LOW" in MR_COMPATIBLE_REGIMES
        assert "FLAT_NORMAL" in MR_COMPATIBLE_REGIMES
        assert "FLAT_HIGH" in MR_COMPATIBLE_REGIMES
    
    def test_low_volatility_is_mr_compatible(self):
        """LOW_VOLATILITY should be MR-compatible."""
        assert "LOW_VOLATILITY" in MR_COMPATIBLE_REGIMES
    
    def test_trend_regimes_not_mr_compatible(self):
        """TREND regimes should NOT be MR-compatible."""
        assert "TREND_UP" not in MR_COMPATIBLE_REGIMES
        assert "TREND_DOWN" not in MR_COMPATIBLE_REGIMES
    
    def test_all_regimes_constant(self):
        """ALL_REGIMES should contain all known regimes."""
        expected = {
            "TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY",
            "MEAN_REVERSION", "UNCERTAIN", "FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH",
        }
        assert ALL_REGIMES == expected
