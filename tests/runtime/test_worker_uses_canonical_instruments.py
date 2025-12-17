"""
CFG-RUNTIME-INSTRUMENTS-SSOT-ALIGN-10: Test worker reads canonical instruments.

Test Plan:
1. Canonical filled, legacy empty → PASS, symbols_count > 0
2. Canonical empty, legacy filled → FAIL (canonical empty) + diagnostic shows legacy
3. Both empty → FAIL
4. Both filled, different → PASS by canonical + drift warning
5. instruments.yaml exists but load failed → FAIL + actionable
6. BOOTSTRAP PROOF shows canonical preview
"""
import pytest
from unittest.mock import Mock, patch
from apps.reference.domains.market_data.worker import MarketDataWorker


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    return Mock()


@pytest.fixture
def mock_queue():
    """Mock IPC queue."""
    return Mock()


def test_canonical_filled_legacy_empty(mock_queue, mock_logger):
    """T1: Canonical filled, legacy empty → worker PASS, symbols_count > 0."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/fake/config/aurora",
        "instruments": {
            "BTCUSDT": {"tick_size": "0.01"},
            "ETHUSDT": {"tick_size": "0.01"}
        },
        "trading": {
            "instruments": {},  # legacy empty
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": ["BTCUSDT"]}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    worker = MarketDataWorker(mock_queue, config_dict, mock_logger)
    
    # Should succeed, symbols from canonical
    assert worker._symbols == ["BTCUSDT", "ETHUSDT"]
    assert len(worker._symbols) == 2
    
    # Check BOOTSTRAP PROOF logged (first info call)
    assert mock_logger.info.called
    first_log_call = mock_logger.info.call_args_list[0]
    log_msg = first_log_call[0][0]
    assert "📋 BOOTSTRAP PROOF" in log_msg
    assert "symbols_count: 2" in log_msg


def test_canonical_empty_legacy_filled(mock_queue, mock_logger):
    """T2: Canonical empty, legacy filled → worker FAIL (canonical empty) + diagnostic shows legacy."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/fake/config/aurora",
        "instruments": {},  # canonical empty
        "trading": {
            "instruments": {"BTCUSDT": {"tick_size": "0.01"}},  # legacy filled (ignored)
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": []}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    with pytest.raises(ValueError, match="BOOTSTRAP FAILED: No symbols configured"):
        MarketDataWorker(mock_queue, config_dict, mock_logger)
    
    # Check diagnostic shows both canonical (0) and legacy (1)
    assert mock_logger.critical.called
    error_msg = mock_logger.critical.call_args[0][0]
    assert "config.instruments (canonical SSOT): 0 symbols" in error_msg
    assert "config.trading.instruments (legacy): 1 symbols" in error_msg


def test_both_empty(mock_queue, mock_logger):
    """T3: Both empty → FAIL."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/fake/config/aurora",
        "instruments": {},
        "trading": {
            "instruments": {},
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": []}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    with pytest.raises(ValueError, match="BOOTSTRAP FAILED: No symbols configured"):
        MarketDataWorker(mock_queue, config_dict, mock_logger)


def test_both_filled_different(mock_queue, mock_logger):
    """T4: Both filled, different → PASS by canonical + drift warning."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/fake/config/aurora",
        "instruments": {
            "BTCUSDT": {"tick_size": "0.01"},
            "ETHUSDT": {"tick_size": "0.01"}
        },
        "trading": {
            "instruments": {
                "SOLUSDT": {"tick_size": "0.001"}  # different symbol (legacy)
            },
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": ["BTCUSDT"]}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    worker = MarketDataWorker(mock_queue, config_dict, mock_logger)
    
    # Should use canonical (BTC/ETH), not legacy (SOL)
    assert worker._symbols == ["BTCUSDT", "ETHUSDT"]
    
    # Check drift warning logged
    assert mock_logger.warning.called
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "CONFIG DRIFT DETECTED" in warning_msg
    assert "Canonical-only symbols:" in warning_msg
    assert "Legacy-only symbols:" in warning_msg


def test_instruments_yaml_exists_but_canonical_empty(mock_queue, mock_logger):
    """T5: instruments.yaml exists but canonical empty → FAIL + actionable message."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/home/wekabeka/Музыка/Phenix/config/aurora",  # real path
        "instruments": {},  # canonical empty (load failed or empty file)
        "trading": {
            "instruments": {},
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": []}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    with pytest.raises(ValueError, match="BOOTSTRAP FAILED: No symbols configured"):
        MarketDataWorker(mock_queue, config_dict, mock_logger)
    
    # Check actionable message references instruments.yaml
    error_msg = mock_logger.critical.call_args[0][0]
    assert "instruments.yaml exists: True" in error_msg
    assert "c.instruments.keys()" in error_msg  # canonical command, not c.trading.instruments


def test_bootstrap_proof_shows_canonical_preview(mock_queue, mock_logger):
    """T6: BOOTSTRAP PROOF shows canonical symbols preview."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/fake/config/aurora",
        "instruments": {
            f"SYM{i:02d}USDT": {"tick_size": "0.01"} for i in range(15)  # 15 symbols
        },
        "trading": {
            "instruments": {},
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": ["SYM00USDT"]}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    worker = MarketDataWorker(mock_queue, config_dict, mock_logger)
    
    # Check BOOTSTRAP PROOF preview (first 10 of 15)
    first_log_call = mock_logger.info.call_args_list[0]
    log_msg = first_log_call[0][0]
    assert "symbols_count: 15" in log_msg
    assert "SYM00USDT" in log_msg  # first symbol in preview
    assert "SYM09USDT" in log_msg  # 10th symbol (0-indexed)
    assert "SYM14USDT" not in log_msg  # beyond preview limit (11th+)


def test_actionable_command_references_canonical(mock_queue, mock_logger):
    """T7: Error message references canonical c.instruments, not c.trading.instruments."""
    config_dict = {
        "_config_name": "test_aurora",
        "_config_dir": "/fake/config",
        "instruments": {},
        "trading": {
            "instruments": {},
            "market_data": {"poll_interval_sec": 1, "macro_sync": {"anchors": []}},
            "domain_configuration": {"market_data": {"trading_mode": "testnet"}}
        }
    }
    
    with pytest.raises(ValueError):
        MarketDataWorker(mock_queue, config_dict, mock_logger)
    
    error_msg = mock_logger.critical.call_args[0][0]
    
    # Should reference canonical command
    assert "c.instruments.keys()" in error_msg
    
    # Should NOT reference legacy command
    assert "c.trading.instruments" not in error_msg
    
    # Should reference SSOT docs
    assert "CFG_FREEZE_SSOT_MAP.md" in error_msg
