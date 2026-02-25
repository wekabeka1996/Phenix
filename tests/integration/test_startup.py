import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from apps.reference.bootstrap.domain_builder import build_live_domains

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
