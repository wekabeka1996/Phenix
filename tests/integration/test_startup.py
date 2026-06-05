import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from apps.reference.bootstrap.domain_builder import build_live_domains
from vfoundation.core import FSMCore


def _valid_bar_closed_pld():
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 1700000000000,
        "tf_sec": 300,
        "bar_close_ts": 1700000300000,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1700000000000,
            "end_ts_ms": 1700000300000,
            "open": "42000.00",
            "high": "42100.00",
            "low": "41900.00",
            "close": "42050.00",
            "volume": "1.5",
        },
    }


def test_config_loader_smoke():
    """Verify that ConfigLoader can load the system configuration without error."""
    # Use real config files
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    if not config_dir.exists():
        pytest.skip(f"Config directory not found at {config_dir}")

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()

    assert config is not None
    assert config.trading is not None
    assert len(config.instruments) > 0


def test_domain_builder_smoke():
    """Verify that all domain components can be initialized via DomainBuilder."""
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    if not config_dir.exists():
        pytest.skip("Config directory not found")

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()

    # Mock FSM and Logger
    mock_fsm = MagicMock()
    mock_logger = MagicMock()

    # Mock external connectors that might try to open network sockets
    with patch("apps.reference.bootstrap.domain_builder.MarketDataConnector"), \
            patch("apps.reference.bootstrap.domain_builder.AccountConnector"), \
            patch("apps.reference.bootstrap.domain_builder.ExecPosFSM"), \
            patch("apps.reference.bootstrap.domain_builder.CsvRecorder"):

        domains = build_live_domains(
            config=config,
            fsm=mock_fsm,
            logger=mock_logger
        )

        assert domains.feature_engineering is not None
        assert domains.risk_management is not None
        assert domains.decision_making is not None
        assert domains.position_tracking is not None


def test_domain_builder_skips_ta_features_when_config_absent():
    """ta_features must not bootstrap when config.domains.ta_features is absent."""
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    if not config_dir.exists():
        pytest.skip("Config directory not found")

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config().model_copy(deep=True)
    config.domains.ta_features = None

    mock_fsm = MagicMock()
    mock_logger = MagicMock()

    with patch("apps.reference.bootstrap.domain_builder.MarketDataConnector"), \
            patch("apps.reference.bootstrap.domain_builder.AccountConnector"), \
            patch("apps.reference.bootstrap.domain_builder.ExecPosFSM"), \
            patch("apps.reference.bootstrap.domain_builder.CsvRecorder"), \
            patch("apps.reference.bootstrap.domain_builder.TAFeaturesEngine") as ta_engine:

        domains = build_live_domains(
            config=config,
            fsm=mock_fsm,
            logger=mock_logger,
        )

        ta_engine.assert_not_called()
        assert domains.ta_features_engine is None


def test_domain_builder_bootstraps_ta_features_from_canonical_config():
    """ta_features must bootstrap from config.domains.ta_features, not a side-loaded YAML."""
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    if not config_dir.exists():
        pytest.skip("Config directory not found")

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()

    mock_fsm = MagicMock()
    mock_logger = MagicMock()

    with patch("apps.reference.bootstrap.domain_builder.MarketDataConnector"), \
            patch("apps.reference.bootstrap.domain_builder.AccountConnector"), \
            patch("apps.reference.bootstrap.domain_builder.ExecPosFSM"), \
            patch("apps.reference.bootstrap.domain_builder.CsvRecorder"), \
            patch("apps.reference.bootstrap.domain_builder.TAFeaturesEngine") as ta_engine:

        build_live_domains(
            config=config,
            fsm=mock_fsm,
            logger=mock_logger,
        )

        ta_engine.assert_called_once()
        assert ta_engine.call_args.kwargs["config"] == config.domains.ta_features


def test_domain_builder_registers_ta_features_bar_closed_listener_before_feature_engineering():
    """Keep same-bar TA delivery ahead of FE-triggered decision flow."""
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    if not config_dir.exists():
        pytest.skip("Config directory not found")

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()
    if config.domains.ta_features is None or not config.domains.ta_features.enabled:
        pytest.skip("ta_features not enabled in current config")

    listener_order: list[str] = []

    class _NoopDomain:
        def __init__(self, *args, **kwargs):
            pass

    class _NoopBarAggregator(_NoopDomain):
        def on_market_tick(self, event):
            return None

    class _FeatureEngineeringProbe:
        def __init__(self, fsm, config):
            fsm.listen("EVT:BAR_CLOSED", self.on_bar_closed)

        def on_bar_closed(self, event):
            listener_order.append("feature_engineering")

    class _TAFeaturesProbe:
        def __init__(self, *, fsm, config):
            fsm.listen("EVT:BAR_CLOSED", self.on_bar_closed)

        def on_bar_closed(self, event):
            listener_order.append("ta_features")

    with patch("apps.reference.bootstrap.domain_builder.AccountConnector", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.MarketDataConnector", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.MarketDataProxy", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.TAFeaturesEngine", _TAFeaturesProbe), \
            patch("apps.reference.bootstrap.domain_builder.FeatureEngineering", _FeatureEngineeringProbe), \
            patch("apps.reference.bootstrap.domain_builder.BarAggregator", _NoopBarAggregator), \
            patch("apps.reference.bootstrap.domain_builder.RiskManagement", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.ExecPosFSM", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.PositionTracking", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.DecisionMaking", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.RegimeDetector", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.CsvRecorder", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.SystemStressOverlay", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.ObjectiveEngineRuntime", _NoopDomain):

        fsm = FSMCore()
        build_live_domains(
            config=config,
            fsm=fsm,
            logger=MagicMock(),
        )

    fsm.emit(
        "EVT:BAR_CLOSED",
        _valid_bar_closed_pld(),
        why="test_bar_listener_order",
    )

    assert listener_order[:2] == ["ta_features", "feature_engineering"]


def test_domain_builder_registers_execpos_trade_executed_listener_before_position_tracking():
    """Lock runtime listener order so local lifecycle activation precedes portfolio truth updates."""
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    if not config_dir.exists():
        pytest.skip("Config directory not found")

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()
    listener_order: list[str] = []

    class _NoopDomain:
        def __init__(self, *args, **kwargs):
            pass

    class _NoopBarAggregator(_NoopDomain):
        def on_market_tick(self, event):
            return None

    class _ExecPosProbe:
        def __init__(self, config, fsm):
            fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)

        def on_trade_executed(self, event):
            listener_order.append("execution")

    class _PositionTrackingProbe:
        def __init__(self, fsm, config):
            fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)

        def on_trade_executed(self, event):
            listener_order.append("position")

    with patch("apps.reference.bootstrap.domain_builder.AccountConnector", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.MarketDataConnector", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.MarketDataProxy", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.FeatureEngineering", _NoopDomain), \
            patch("apps.reference.bootstrap.domain_builder.BarAggregator", _NoopBarAggregator), \
        patch("apps.reference.bootstrap.domain_builder.RiskManagement", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.ExecPosFSM", _ExecPosProbe), \
        patch("apps.reference.bootstrap.domain_builder.PositionTracking", _PositionTrackingProbe), \
        patch("apps.reference.bootstrap.domain_builder.DecisionMaking", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.RegimeDetector", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.CsvRecorder", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.SystemStressOverlay", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.ObjectiveEngineRuntime", _NoopDomain), \
        patch("apps.reference.bootstrap.domain_builder.TAFeaturesEngine", _NoopDomain):

        fsm = FSMCore()
        build_live_domains(
            config=config,
            fsm=fsm,
            logger=MagicMock(),
        )

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "orderId": "order-1",
            "clientOrderId": "ENTRY-1",
            "quantity": "0.01",
            "price": "100.0",
            "rid": "rid-1",
        },
        why="test_listener_order",
    )

    assert listener_order[:2] == ["execution", "position"]
