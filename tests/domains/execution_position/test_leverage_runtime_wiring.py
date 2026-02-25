"""
TASK47c-P3: Runtime Leverage Wiring Guard Tests

These tests verify the integration of leverage bootstrap into the startup flow:
1. ExecPosFSM accepts leverage_service and is_live_execution parameters
2. OpenFlowFSM receives leverage_service from ExecPosFSM
3. LeverageBootstrapper is called at startup
4. Failed symbols are tracked and can be blocked

Contract: Active Leverage Management
SSOT: apps/reference/domains/execution_position/fsm.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


# ─────────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_config():
    """Create a minimal mock AuroraConfig for testing."""
    config = MagicMock()
    config.model_dump.return_value = {}
    
    # Mock domains.execution_position for IdempotentCancelHelper
    config.domains.execution_position.idempotent_cancel.max_retries = 3
    config.domains.execution_position.fsm_open.idempotency_window_sec = 60
    config.domains.execution_position.dedup.max_size = 1000
    config.domains.execution_position.dedup.ttl_ms = 5000
    
    # Mock ExposureGuard config (required by ExecPosFSM)
    config.domains.execution_position.exposure_guard.max_equity_utilization_pct = 80.0
    config.domains.execution_position.exposure_guard.max_position_size_usd = 10000.0
    config.domains.execution_position.exposure_guard.min_available_equity_usd = 100.0
    
    # Mock trading.execution for cooldown
    config.trading.execution.cooldown_after_close_ms = 1000
    config.trading.execution.cooldown_ms = 1000
    config.trading.execution.guard_enabled = True
    config.trading.mode = "testnet"
    
    # Mock binance_api
    config.binance_api.testnet.api_key = "test_key"
    config.binance_api.testnet.api_secret = "test_secret"
    config.binance_api.testnet.rest_url = "https://testnet.binancefuture.com"
    
    # Mock strategies_registry (SSOT for symbol assignments)
    config.strategies_registry.assignments = {
        "BTCUSDT": ["aurora"],
        "ETHUSDT": ["aurora"],
        "DOGEUSDT": ["mean_reversion"],
    }
    
    # Mock Aurora strategy config
    aurora = MagicMock()
    aurora.assets = {}
    btc_asset = MagicMock()
    btc_asset.leverage = MagicMock()
    btc_asset.leverage.target = 20
    btc_asset.leverage.mode = "ISOLATED"
    aurora.assets["BTCUSDT"] = btc_asset
    
    eth_asset = MagicMock()
    eth_asset.leverage = None  # No leverage config
    aurora.assets["ETHUSDT"] = eth_asset
    config.strategies.aurora = aurora
    
    # Mock MeanReversion strategy config
    mr = MagicMock()
    mr.assets = {}
    doge_asset = MagicMock()
    doge_asset.leverage = MagicMock()
    doge_asset.leverage.target = 10
    doge_asset.leverage.mode = "ISOLATED"
    mr.assets["DOGEUSDT"] = doge_asset
    config.strategies.mean_reversion = mr
    
    # LEVERAGE-SSOT-FIX-01: Mock instruments (SSOT for leverage)
    # New logic reads from instruments.yaml, not strategy configs
    def make_instrument_spec(symbol: str, target_leverage: int, margin_mode: str = "isolated"):
        spec = MagicMock()
        spec.symbol = symbol
        spec.execution = MagicMock()
        spec.execution.target_leverage = target_leverage
        spec.execution.margin_mode = margin_mode
        spec.execution.leverage_policy = "set_and_verify"
        spec.sizing = MagicMock()
        spec.sizing.margin_pct = 0.10
        return spec
    
    config.instruments = {
        "BTCUSDT": make_instrument_spec("BTCUSDT", 20),
        "ETHUSDT": make_instrument_spec("ETHUSDT", 20),
        "DOGEUSDT": make_instrument_spec("DOGEUSDT", 10),
    }
    
    return config


@pytest.fixture
def mock_fsm():
    """Create a mock FSMCore."""
    fsm = MagicMock()
    fsm.get_open_orders.return_value = []
    fsm.get_positions.return_value = {}
    return fsm


# ─────────────────────────────────────────────────────────────────────────────────
# Test: ExecPosFSM Signature
# ─────────────────────────────────────────────────────────────────────────────────


def test_exec_pos_fsm_accepts_leverage_service_parameter():
    """ExecPosFSM.__init__ must accept leverage_service parameter."""
    import inspect
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    sig = inspect.signature(ExecPosFSM.__init__)
    param_names = list(sig.parameters.keys())
    
    assert "leverage_service" in param_names, (
        "ExecPosFSM.__init__ must accept leverage_service parameter"
    )
    assert "is_live_execution" in param_names, (
        "ExecPosFSM.__init__ must accept is_live_execution parameter"
    )


def test_exec_pos_fsm_stores_leverage_service(mock_config, mock_fsm):
    """ExecPosFSM must store leverage_service for use by OpenFlowFSM."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    mock_leverage_service = MagicMock()
    
    # Patch both _initialize_adapter and ExposureGuard to avoid complex config setup
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(
            config=mock_config,
            fsm=mock_fsm,
            shadow_mode=True,
            leverage_service=mock_leverage_service,
            is_live_execution=False,
        )
    
    assert fsm.leverage_service is mock_leverage_service
    assert fsm.is_live_execution is False


def test_exec_pos_fsm_has_run_leverage_bootstrap_method():
    """ExecPosFSM must have run_leverage_bootstrap async method."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    import asyncio
    
    assert hasattr(ExecPosFSM, 'run_leverage_bootstrap'), (
        "ExecPosFSM must have run_leverage_bootstrap method"
    )
    
    # Verify it's an async method
    method = getattr(ExecPosFSM, 'run_leverage_bootstrap')
    assert asyncio.iscoroutinefunction(method), (
        "run_leverage_bootstrap must be an async method"
    )


def test_exec_pos_fsm_has_collect_leverage_configs_method():
    """ExecPosFSM must have _collect_leverage_configs method."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    assert hasattr(ExecPosFSM, '_collect_leverage_configs'), (
        "ExecPosFSM must have _collect_leverage_configs method"
    )


# ─────────────────────────────────────────────────────────────────────────────────
# Test: OpenFlowFSM Live Mode Validation
# ─────────────────────────────────────────────────────────────────────────────────


def test_open_flow_fsm_requires_leverage_service_in_live_mode():
    """OpenFlowFSM must raise RuntimeError if is_live_execution=True without leverage_service."""
    from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
    
    mock_config = MagicMock()
    mock_config.domains.execution_position.fsm_open.idempotency_window_sec = 60
    
    with pytest.raises(RuntimeError, match="LeverageService is required for LIVE"):
        OpenFlowFSM(
            config=mock_config,
            is_live_execution=True,
            leverage_service=None,  # Missing!
        )


def test_open_flow_fsm_accepts_no_leverage_service_in_shadow_mode():
    """OpenFlowFSM should allow no leverage_service when is_live_execution=False."""
    from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
    
    mock_config = MagicMock()
    mock_config.domains.execution_position.fsm_open.idempotency_window_sec = 60
    
    # Should not raise
    fsm = OpenFlowFSM(
        config=mock_config,
        is_live_execution=False,
        leverage_service=None,
    )
    
    assert fsm.leverage_service is None
    assert fsm.is_live_execution is False


def test_open_flow_fsm_stores_leverage_service():
    """OpenFlowFSM must store leverage_service for verification before DEC:OPEN."""
    from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
    
    mock_config = MagicMock()
    mock_config.domains.execution_position.fsm_open.idempotency_window_sec = 60
    mock_leverage_service = MagicMock()
    
    fsm = OpenFlowFSM(
        config=mock_config,
        is_live_execution=True,
        leverage_service=mock_leverage_service,
    )
    
    assert fsm.leverage_service is mock_leverage_service


# ─────────────────────────────────────────────────────────────────────────────────
# Test: Leverage Config Collection
# ─────────────────────────────────────────────────────────────────────────────────


def test_collect_leverage_configs_from_instruments_ssot(mock_config, mock_fsm):
    """LEVERAGE-SSOT-FIX-01: _collect_leverage_configs reads from instruments.yaml SSOT."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(config=mock_config, fsm=mock_fsm, shadow_mode=True)
    
    configs = fsm._collect_leverage_configs()
    
    # Should find BTCUSDT from instruments.yaml (not strategy config)
    assert "BTCUSDT" in configs
    assert configs["BTCUSDT"].target == 20  # From instruments
    assert configs["BTCUSDT"].mode == "ISOLATED"
    
    # ETHUSDT also has instruments config
    assert "ETHUSDT" in configs
    assert configs["ETHUSDT"].target == 20


def test_collect_leverage_configs_from_instruments_for_mr_symbols(mock_config, mock_fsm):
    """LEVERAGE-SSOT-FIX-01: MR symbols also read leverage from instruments.yaml."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(config=mock_config, fsm=mock_fsm, shadow_mode=True)
    
    configs = fsm._collect_leverage_configs()
    
    # Should find DOGEUSDT from instruments.yaml (SSOT, not MR strategy config)
    assert "DOGEUSDT" in configs
    assert configs["DOGEUSDT"].target == 10  # From instruments


def test_collect_leverage_configs_returns_empty_without_registry(mock_fsm):
    """_collect_leverage_configs should return empty dict if no strategies_registry."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    config = MagicMock()
    config.strategies_registry = None
    config.domains.execution_position.idempotent_cancel.max_retries = 3
    config.domains.execution_position.fsm_open.idempotency_window_sec = 60
    config.domains.execution_position.dedup.max_size = 1000
    config.domains.execution_position.dedup.ttl_ms = 5000
    config.trading.execution.cooldown_after_close_ms = 1000
    
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(config=config, fsm=mock_fsm, shadow_mode=True)
    
    configs = fsm._collect_leverage_configs()
    
    assert configs == {}


# ─────────────────────────────────────────────────────────────────────────────────
# Test: Leverage Bootstrap Execution
# ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_leverage_bootstrap_skipped_in_shadow_mode(mock_config, mock_fsm):
    """run_leverage_bootstrap should skip and return empty set in shadow mode."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(config=mock_config, fsm=mock_fsm, shadow_mode=True)
    
    blocked = await fsm.run_leverage_bootstrap()
    
    assert blocked == set()


@pytest.mark.asyncio
async def test_run_leverage_bootstrap_calls_bootstrapper(mock_config, mock_fsm):
    """run_leverage_bootstrap should call LeverageBootstrapper.run() with collected configs."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    from apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper import (
        BootstrapResults,
        BootstrapResult,
        LeverageBootstrapper,
    )
    
    mock_adapter = MagicMock()
    mock_results = BootstrapResults()
    mock_results.add_success("BTCUSDT", BootstrapResult(symbol="BTCUSDT", success=True))
    mock_results.add_success("ETHUSDT", BootstrapResult(symbol="ETHUSDT", success=True))
    mock_results.add_success("DOGEUSDT", BootstrapResult(symbol="DOGEUSDT", success=True))
    
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(config=mock_config, fsm=mock_fsm, shadow_mode=False)
        fsm.adapter = mock_adapter  # Set adapter manually
    
    # Patch LeverageBootstrapper class itself
    with patch.object(LeverageBootstrapper, 'run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_results
        
        blocked = await fsm.run_leverage_bootstrap()
    
    # Bootstrapper.run should be called
    mock_run.assert_awaited_once()
    
    # No failures, empty set
    assert blocked == set()


@pytest.mark.asyncio
async def test_run_leverage_bootstrap_returns_failed_symbols(mock_config, mock_fsm):
    """run_leverage_bootstrap should return failed symbols from bootstrapper."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    from apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper import (
        BootstrapResults,
        BootstrapResult,
        LeverageBootstrapper,
    )
    
    mock_adapter = MagicMock()
    mock_results = BootstrapResults()
    mock_results.add_success("BTCUSDT", BootstrapResult(symbol="BTCUSDT", success=True))
    mock_results.add_success("ETHUSDT", BootstrapResult(symbol="ETHUSDT", success=True))
    mock_results.add_failure("DOGEUSDT", BootstrapResult(
        symbol="DOGEUSDT",
        success=False,
        error_code=-4047,
        error_msg="Cannot change margin type with open positions"
    ))
    
    with patch.object(ExecPosFSM, '_initialize_adapter'), \
         patch.object(ExecPosFSM, '_schedule_guardian_start'), \
         patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'), \
         patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog.start'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
        fsm = ExecPosFSM(config=mock_config, fsm=mock_fsm, shadow_mode=False)
        fsm.adapter = mock_adapter
    
    # Patch LeverageBootstrapper.run
    with patch.object(LeverageBootstrapper, 'run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_results
        
        blocked = await fsm.run_leverage_bootstrap()
    
    # Should return failed symbols
    assert "DOGEUSDT" in blocked
    assert "BTCUSDT" not in blocked
