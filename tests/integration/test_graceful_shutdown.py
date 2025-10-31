import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
import types
import sys

def test_graceful_shutdown_calls_stop_on_managed_components():
    """
    Ensure that the main module attempts to stop managed components when KeyboardInterrupt occurs.
    """
    repo_root = Path(__file__).resolve().parents[2]
    main_path = repo_root / 'apps' / 'reference' / 'main.py'

    # Dynamic import by file path
    spec = importlib.util.spec_from_file_location('apps.reference.main', str(main_path))
    main_app = importlib.util.module_from_spec(spec)

    # Ensure imports that main expects are present
    vfound_pkg_path = repo_root / 'vfoundation'
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(vfound_pkg_path) not in sys.path:
        sys.path.insert(0, str(vfound_pkg_path))

    # Remove potentially conflicting injected modules
    for mod in ['vfoundation', 'vfoundation.core', 'vfoundation.core.protocol', 'vfoundation.adapters', 'vfoundation.dr']:
        if mod in sys.modules:
            del sys.modules[mod]

    # Inject a mock vfoundation package to ensure FSMCore is available and has necessary API
    vfoundation_pkg = types.ModuleType('vfoundation')
    vfoundation_core = types.ModuleType('vfoundation.core')
    vfoundation_adapters = types.ModuleType('vfoundation.adapters')
    vfoundation_adapters_binance = types.ModuleType('vfoundation.adapters.binance_adapter')
    vfoundation_dr = types.ModuleType('vfoundation.dr')

    class DummyFSM:
        def __init__(self):
            self.domains = {
                "market_data": MagicMock(),
                "account_observer": MagicMock(),
                "snapshot_scheduler": MagicMock(),
                "account_balance": MagicMock(),
                "feature_engineering": MagicMock(),
                "risk_management": MagicMock(),
                "position_tracking": MagicMock(),
                "decision_making": MagicMock(),
                "execution_position": MagicMock(),
            }
            self.register_domain = MagicMock()
            self.listen = MagicMock()
            self.emit = MagicMock()

        def get_domain(self, name):
            return self.domains.get(name)
    vfoundation_core.FSMCore = DummyFSM

    vfoundation_protocol = types.ModuleType('vfoundation.core.protocol')
    class MessageStub:
        def __init__(self, *args, **kwargs):
            self.rid = 'test-rid'
            self.span_id = 'test-span'
            self.pld = kwargs.get('pld', {}) # Add pld attribute
    vfoundation_protocol.Message = MessageStub

    # Mock BinanceAdapter
    class MockBinanceAdapter:
        def __init__(self, *args, **kwargs):
            pass
        async def get_account_balance(self):
            return []
        async def get_open_positions(self):
            return []
        async def close_session(self):
            pass
    
    class MockBinanceAPIError(Exception):
        pass
    
    vfoundation_adapters_binance.BinanceAdapter = MockBinanceAdapter
    vfoundation_adapters_binance.BinanceAPIError = MockBinanceAPIError

    # Mock WAL module
    vfoundation_dr.wal = MagicMock()
    vfoundation_dr.wal.append = MagicMock(return_value="mock_hash")

    sys.modules['vfoundation'] = vfoundation_pkg
    sys.modules['vfoundation.core'] = vfoundation_core
    sys.modules['vfoundation.core.protocol'] = vfoundation_protocol
    sys.modules['vfoundation.adapters'] = vfoundation_adapters
    sys.modules['vfoundation.adapters.binance_adapter'] = vfoundation_adapters_binance
    sys.modules['vfoundation.dr'] = vfoundation_dr

    spec.loader.exec_module(main_app)  # type: ignore[attr-defined]

    # Prepare mocks for components - mock all active domains to avoid starting threads
    domain_names = [
        'MarketDataConnector', 'AccountObserver', 'SnapshotScheduler', 'AccountConnector',
        'FeatureEngineering', 'RiskManagement', 'PositionTracking', 'DecisionMaking', 'ExecPosFSM'
    ]
    for dn in domain_names:
        setattr(main_app, dn, MagicMock())

    # Make instances provide stop method and track calls
    market_inst = main_app.MarketDataConnector.return_value
    market_inst.start = MagicMock()
    market_inst.stop = MagicMock()

    acc_obs_inst = main_app.AccountObserver.return_value
    acc_obs_inst.start = MagicMock()
    acc_obs_inst.stop = MagicMock()

    snap_inst = main_app.SnapshotScheduler.return_value
    snap_inst.start = MagicMock()
    snap_inst.stop = MagicMock()

    # Mock the FSM's get_domain method to return our mocked instances
    # The main function gets components via fsm.get_domain(), not via the class constructors
    original_get_domain = vfoundation_core.FSMCore.get_domain
    def mock_get_domain(self, name):
        if name == "market_data":
            return market_inst
        elif name == "account_observer":
            return acc_obs_inst
        elif name == "snapshot_scheduler":
            return snap_inst
        else:
            # For other domains, return a mock that doesn't need stop() called
            mock_comp = MagicMock()
            mock_comp.stop = MagicMock()
            return mock_comp
    
    vfoundation_core.FSMCore.get_domain = mock_get_domain

    # Patch time.sleep to raise KeyboardInterrupt to trigger shutdown flow
    with patch('time.sleep', side_effect=KeyboardInterrupt):
        # Run main; it should call start() then enter loop and be interrupted
        try:
            main_app.main()
        except KeyboardInterrupt:
            # The test environment simulates a Ctrl+C; main() handles KeyboardInterrupt itself
            pass

    # Assert that stop() was called for each mocked managed component
    assert market_inst.stop.called
    assert acc_obs_inst.stop.called
    assert snap_inst.stop.called

    # Clean up injected mock modules to avoid affecting other tests
    modules_to_remove = [
        'vfoundation', 'vfoundation.core', 'vfoundation.core.protocol',
        'vfoundation.adapters', 'vfoundation.adapters.binance_adapter', 'vfoundation.dr'
    ]
    for mod in modules_to_remove:
        if mod in sys.modules:
            del sys.modules[mod]
