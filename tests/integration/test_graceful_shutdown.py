import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch


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
    import sys
    vfound_pkg_path = repo_root / 'vfoundation'
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(vfound_pkg_path) not in sys.path:
        sys.path.insert(0, str(vfound_pkg_path))

    # Remove potentially conflicting injected modules
    for mod in ['vfoundation', 'vfoundation.core', 'vfoundation.core.protocol']:
        if mod in sys.modules:
            del sys.modules[mod]

    # Inject a mock vfoundation package to ensure FSMCore is available and has necessary API
    import types
    # Remove potentially conflicting injected modules
    for mod in ['vfoundation', 'vfoundation.core', 'vfoundation.core.protocol']:
        if mod in sys.modules:
            del sys.modules[mod]

    vfoundation_pkg = types.ModuleType('vfoundation')
    vfoundation_core = types.ModuleType('vfoundation.core')

    class DummyFSM:
        def __init__(self):
            self.register_domain = MagicMock()
            self.listen = MagicMock()
            self.emit = MagicMock()

    vfoundation_core.FSMCore = DummyFSM

    vfoundation_protocol = types.ModuleType('vfoundation.core.protocol')
    class MessageStub:
        def __init__(self, *args, **kwargs):
            self.rid = 'test-rid'
            self.span_id = 'test-span'
    vfoundation_protocol.Message = MessageStub

    sys.modules['vfoundation'] = vfoundation_pkg
    sys.modules['vfoundation.core'] = vfoundation_core
    sys.modules['vfoundation.core.protocol'] = vfoundation_protocol

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
