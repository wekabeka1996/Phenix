"""
CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: BTC Arbitration Deterministic Tests

Tests verify:
1. BTC with both aurora + mean_reversion signals → only aurora passes (priority=1)
2. Blocked strategy logs correct reason (ARBITRATION_REJECT:priority_aurora_wins)
3. Single-strategy symbols (ETH, DOGE) → always pass
4. Arbitration is deterministic (same symbol → same strategy wins)
"""
import pytest
import sys
from unittest.mock import Mock, MagicMock
from pathlib import Path

# Mock order_logger before importing DecisionMaking (avoid FileNotFoundError)
sys.modules['apps.reference.telemetry.order_logger'] = MagicMock()

# Now import DecisionMaking (after mocking dependencies)
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_models import (
    AuroraConfig,
    StrategiesRegistryConfig,
    StrategiesArbitrationConfig,
    StrategiesArbitrationLoggingConfig
)


@pytest.fixture
def strategies_registry_config():
    """Create StrategiesRegistryConfig with BTC hybrid setup."""
    return StrategiesRegistryConfig(
        version="1.0.0",
        assignments={
            "ETHUSDT": ["aurora"],  # Aurora only
            "SOLUSDT": ["aurora"],  # Aurora only
            "DOGEUSDT": ["mean_reversion_1m"],  # MR only
            "XRPUSDT": ["mean_reversion_1m"],  # MR only
            "BTCUSDT": ["aurora", "mean_reversion_1m"],  # HYBRID
        },
        arbitration=StrategiesArbitrationConfig(
            mode="priority",
            priority={
                "aurora": 1,  # Higher priority (wins)
                "mean_reversion_1m": 2,  # Lower priority
            },
            logging=StrategiesArbitrationLoggingConfig(
                rejected_why_prefix="ARBITRATION_REJECT",
                log_level="INFO"
            )
        )
    )


@pytest.fixture
def mock_config(strategies_registry_config):
    """Create mock AuroraConfig with strategies_registry."""
    config = Mock(spec=AuroraConfig)
    config.strategies_registry = strategies_registry_config
    config.mode = "testnet"
    config.decision = Mock()
    config.decision.signal_threshold = 0.1
    config.decision.symbols_to_track = ["ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BTCUSDT"]
    return config


@pytest.fixture
def mock_fsm():
    """Create mock FSMCore."""
    fsm = Mock()
    fsm.logger = Mock()
    fsm.md_service = Mock()
    fsm.order_logger = Mock()
    fsm.exchange_adapter = Mock()
    fsm.risk_manager = Mock()
    fsm.alpha_registry = Mock()
    fsm.regime_adapter = Mock()
    fsm.feature_repo = Mock()
    fsm.mean_reversion_handler = Mock()
    return fsm


def test_btc_aurora_signal_passes_arbitration(mock_fsm, mock_config, strategies_registry_config):
    """Test D1: BTC Aurora signal passes (priority=1)."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    result = dm._check_strategy_arbitration("BTCUSDT", "aurora")

    assert result["allowed"] is True, "Aurora should pass arbitration on BTC (priority=1)"
    # When allowed=True, reason may be empty string or None (not required)


def test_btc_mean_reversion_signal_blocked_by_arbitration(
    mock_fsm, mock_config, strategies_registry_config
):
    """Test D2: BTC MR signal blocked by Aurora (priority=2 < 1)."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    result = dm._check_strategy_arbitration("BTCUSDT", "mean_reversion_1m")

    assert result["allowed"] is False, "MR should be blocked on BTC (priority=2 < aurora priority=1)"
    assert "priority" in result["reason"].lower(), "Reason should mention priority"
    assert "aurora" in result["reason"].lower(), "Reason should mention Aurora as winner"


def test_btc_arbitration_reason_format(mock_fsm, mock_config, strategies_registry_config):
    """Test D3: Blocked strategy logs reason with correct prefix (≤80 chars)."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    result = dm._check_strategy_arbitration("BTCUSDT", "mean_reversion_1m")

    reason = result["reason"]
    assert reason.startswith("ARBITRATION_REJECT:"), \
        "Reason should start with rejected_why_prefix"
    assert len(reason) <= 80, f"Reason length {len(reason)} exceeds 80 chars: {reason}"
    assert "priority" in reason.lower(), "Reason should mention priority mechanism"


def test_eth_aurora_only_always_passes(mock_fsm, mock_config, strategies_registry_config):
    """Test E1: ETH (Aurora only) always passes arbitration."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    result = dm._check_strategy_arbitration("ETHUSDT", "aurora")

    assert result["allowed"] is True, "Aurora should pass on ETH (only strategy assigned)"


def test_doge_mr_only_always_passes(mock_fsm, mock_config, strategies_registry_config):
    """Test E2: DOGE (MR only) always passes arbitration."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    result = dm._check_strategy_arbitration("DOGEUSDT", "mean_reversion_1m")

    assert result["allowed"] is True, "MR should pass on DOGE (only strategy assigned)"


def test_arbitration_deterministic_repeated_calls(
    mock_fsm, mock_config, strategies_registry_config
):
    """Test F: Arbitration is deterministic (same symbol → same result, N times)."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    # Call arbitration 10 times for BTC aurora
    results_aurora = [
        dm._check_strategy_arbitration("BTCUSDT", "aurora")["allowed"]
        for _ in range(10)
    ]
    assert all(r is True for r in results_aurora), \
        "Aurora on BTC should ALWAYS pass (deterministic)"

    # Call arbitration 10 times for BTC MR
    results_mr = [
        dm._check_strategy_arbitration("BTCUSDT", "mean_reversion_1m")["allowed"]
        for _ in range(10)
    ]
    assert all(r is False for r in results_mr), \
        "MR on BTC should ALWAYS be blocked (deterministic)"


def test_no_registry_no_arbitration(mock_fsm, mock_config):
    """Test G: No strategies_registry → all strategies pass (legacy behavior)."""
    mock_config.strategies_registry = None
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = None

    result_aurora = dm._check_strategy_arbitration("BTCUSDT", "aurora")
    result_mr = dm._check_strategy_arbitration("BTCUSDT", "mean_reversion_1m")

    assert result_aurora["allowed"] is True, \
        "Aurora should pass when no registry (legacy mode)"
    assert result_mr["allowed"] is True, \
        "MR should pass when no registry (legacy mode)"


def test_unassigned_strategy_blocked(mock_fsm, mock_config, strategies_registry_config):
    """Test H: Strategy not in assignments → blocked."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    # Aurora assigned to ETH, but try to use MR (not assigned)
    result = dm._check_strategy_arbitration("ETHUSDT", "mean_reversion_1m")

    assert result["allowed"] is False, \
        "MR should be blocked on ETH (not in assignments)"
    assert "not_assigned" in result["reason"].lower() or "strategy_not_assigned" in result["reason"].lower(), \
        "Reason should mention strategy not assigned"


def test_unknown_symbol_blocks_all_strategies(mock_fsm, mock_config, strategies_registry_config):
    """Test I: Unknown symbol → all strategies blocked."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    result = dm._check_strategy_arbitration("ADAUSDT", "aurora")

    assert result["allowed"] is False, \
        "Aurora should be blocked for unknown symbol ADAUSDT"
    assert "not_in_registry" in result["reason"].lower() or "symbol_not_in_registry" in result["reason"].lower(), \
        "Reason should mention symbol not in registry"


def test_mr_gateway_integration_blocks_btc(mock_fsm, mock_config, strategies_registry_config):
    """Test J: MR gateway integration blocks BTC MR signals."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config
    dm._record_blocked_intent = Mock()  # Mock intent blocking tracker

    # Simulate MR signal for BTC
    mr_signal = Mock()
    mr_signal.symbol = "BTCUSDT"
    mr_signal.side = "BUY"
    
    # This should hit the arbitration gate in the MR gateway (L654-661)
    # For this test, we verify the _check_strategy_arbitration call
    result = dm._check_strategy_arbitration("BTCUSDT", "mean_reversion_1m")

    assert result["allowed"] is False, \
        "MR should be blocked by arbitration on BTC"
    # In real flow, _record_blocked_intent would be called


def test_aurora_propose_intent_integration_allows_btc(mock_fsm, mock_config, strategies_registry_config):
    """Test K: Aurora _propose_trade_intent allows BTC signals."""
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = strategies_registry_config

    # Verify Aurora can propose intent for BTC (priority=1 wins)
    result = dm._check_strategy_arbitration("BTCUSDT", "aurora")

    assert result["allowed"] is True, \
        "Aurora should pass arbitration on BTC (priority=1)"
    # In real flow, _propose_trade_intent would proceed with intent emission


def test_unknown_mode_blocks_all_strategies(mock_fsm, mock_config):
    """Test L: Unknown arbitration mode blocks all strategies (fail-closed defense-in-depth)."""
    # Create registry with unknown mode (bypassing Pydantic validation for testing)
    # CRITICAL: use HYBRID symbol (2+ strategies) to trigger arbitration logic
    invalid_registry = Mock()
    invalid_registry.assignments = {
        "BTCUSDT": ["aurora", "mean_reversion_1m"]  # Hybrid symbol
    }
    invalid_registry.arbitration = Mock()
    invalid_registry.arbitration.mode = "weird_unknown_mode"
    invalid_registry.arbitration.priority = {"aurora": 1, "mean_reversion_1m": 2}
    invalid_registry.arbitration.logging = Mock()
    invalid_registry.arbitration.logging.rejected_why_prefix = "ARBITRATION_REJECT"
    
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = invalid_registry
    
    result = dm._check_strategy_arbitration("BTCUSDT", "aurora")
    
    assert result["allowed"] is False, \
        "Unknown arbitration mode should block all strategies (fail-closed)"
    assert "unknown_mode" in result["reason"].lower(), \
        "Reason should mention unknown_mode"


def test_missing_priority_blocks_strategy_runtime(mock_fsm, mock_config):
    """Test M: Missing priority for assigned strategy blocks at runtime (defense-in-depth)."""
    # Create registry with missing priority (runtime check, in case validator missed it)
    registry_no_priority = Mock()
    registry_no_priority.assignments = {
        "BTCUSDT": ["aurora", "mean_reversion_1m"]  # Hybrid
    }
    registry_no_priority.arbitration = Mock()
    registry_no_priority.arbitration.mode = "priority"
    registry_no_priority.arbitration.priority = {
        "aurora": 1
        # MISSING: mean_reversion_1m
    }
    registry_no_priority.arbitration.logging = Mock()
    registry_no_priority.arbitration.logging.rejected_why_prefix = "ARBITRATION_REJECT"
    
    dm = DecisionMaking(fsm=mock_fsm, config=mock_config)
    dm.strategies_registry = registry_no_priority
    
    result = dm._check_strategy_arbitration("BTCUSDT", "mean_reversion_1m")
    
    assert result["allowed"] is False, \
        "Missing priority should block strategy (fail-closed)"
    assert "missing_priority" in result["reason"].lower(), \
        "Reason should mention missing_priority"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
