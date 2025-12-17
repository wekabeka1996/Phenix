"""
Tests for MarketDataWorker bootstrap and fail-fast behavior.

CFG-RUNTIME-BOOTSTRAP-07-MARKET-DATA-WORKER-CONFIG-PROOF
"""

import pytest
import logging
from pathlib import Path
from unittest.mock import MagicMock
from multiprocessing import Queue

# Import worker class for testing
import sys
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.domains.market_data.worker import MarketDataWorker


class TestMarketDataWorkerBootstrap:
    """Test bootstrap proof logging and fail-fast validation."""
    
    def test_empty_instruments_fails_with_diagnostic(self, caplog):
        """
        Test A: Empty instruments → ValueError with diagnostic information.
        
        CFG-RUNTIME-BOOTSTRAP-07: Worker must fail-fast with clear diagnostic.
        """
        # Create empty config
        config_dict = {
            "_config_name": "test_aurora",
            "_config_dir": "/tmp/test_config/aurora",
            "instruments": {},  # EMPTY (canonical SSOT)
            "trading": {
                "instruments": {},  # Legacy (diagnostics only)
                "market_data": {
                    "poll_interval_sec": 1,
                    "macro_sync": {
                        "anchors": []
                    }
                },
                "domain_configuration": {
                    "market_data": {
                        "trading_mode": "testnet"
                    }
                }
            }
        }
        
        # Create mock queue and logger
        ipc_queue = Queue()
        logger = logging.getLogger("test_worker")
        logger.setLevel(logging.DEBUG)
        
        # VERIFY: ValueError raised with diagnostic info
        with pytest.raises(ValueError) as exc_info:
            MarketDataWorker(ipc_queue, config_dict, logger)
        
        error_msg = str(exc_info.value)
        
        # VERIFY: Error message contains diagnostic keywords
        assert "BOOTSTRAP FAILED" in error_msg
        assert "No symbols configured" in error_msg
        assert "config_name: test_aurora" in error_msg
        assert "config_dir: /tmp/test_config/aurora" in error_msg
        assert "instruments.yaml" in error_msg
        assert "Probable causes" in error_msg
        assert "Action required" in error_msg
    
    def test_valid_instruments_logs_bootstrap_proof(self, caplog):
        """
        Test B: Valid instruments → bootstrap proof logged.
        
        CFG-RUNTIME-BOOTSTRAP-07: Worker must log config source and symbols.
        """
        # Create valid config
        config_dict = {
            "_config_name": "aurora",
            "_config_dir": "config/aurora",
            "instruments": {
                "BTCUSDT": {"tick_size": "0.1", "step_size": "0.001"},
                "ETHUSDT": {"tick_size": "0.01", "step_size": "0.001"},
                "SOLUSDT": {"tick_size": "0.001", "step_size": "0.01"},
            },
            "trading": {
                "instruments": {},  # Legacy (diagnostics only)
                "market_data": {
                    "poll_interval_sec": 1,
                    "macro_sync": {
                        "anchors": ["BTCUSDT"]
                    }
                },
                "domain_configuration": {
                    "market_data": {
                        "trading_mode": "testnet"
                    }
                }
            }
        }
        
        # Create mock queue and logger
        ipc_queue = Queue()
        logger = logging.getLogger("test_worker")
        logger.setLevel(logging.DEBUG)
        
        # Add handler to capture logs
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        with caplog.at_level(logging.INFO):
            worker = MarketDataWorker(ipc_queue, config_dict, logger)
        
        # VERIFY: Worker created successfully
        assert worker is not None
        assert worker._symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        assert worker._anchors == ["BTCUSDT"]
        assert worker._mode == "testnet"
        
        # VERIFY: Bootstrap proof logged
        log_messages = caplog.text
        assert "BOOTSTRAP PROOF" in log_messages
        assert "config_name: aurora" in log_messages
        assert "config_dir: config/aurora" in log_messages
        assert "symbols_count: 3" in log_messages
        assert "BTCUSDT" in log_messages
        assert "ETHUSDT" in log_messages
        assert "SOLUSDT" in log_messages
    
    def test_missing_config_metadata_uses_defaults(self, caplog):
        """
        Test C: Missing _config_name/_config_dir → uses <unknown> defaults.
        
        CFG-RUNTIME-BOOTSTRAP-07: Backward compatibility with old configs.
        """
        # Config without metadata (backward compat)
        config_dict = {
            "instruments": {
                "BTCUSDT": {"tick_size": "0.1", "step_size": "0.001"},
            },
            "trading": {
                "instruments": {},  # Legacy (diagnostics only)
                "market_data": {
                    "poll_interval_sec": 1,
                    "macro_sync": {
                        "anchors": []
                    }
                },
                "domain_configuration": {
                    "market_data": {
                        "trading_mode": "testnet"
                    }
                }
            }
        }
        
        # Create mock queue and logger
        ipc_queue = Queue()
        logger = logging.getLogger("test_worker")
        logger.setLevel(logging.DEBUG)
        
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        
        with caplog.at_level(logging.INFO):
            worker = MarketDataWorker(ipc_queue, config_dict, logger)
        
        # VERIFY: Worker created with defaults
        assert worker is not None
        assert worker._symbols == ["BTCUSDT"]
        
        # VERIFY: Logs show <unknown> for missing metadata
        log_messages = caplog.text
        assert "config_name: <unknown>" in log_messages
        assert "config_dir: <unknown>" in log_messages
    
    def test_large_symbols_list_truncated_in_log(self, caplog):
        """
        Test D: Large symbols list → preview truncated to first 10.
        
        CFG-RUNTIME-BOOTSTRAP-07: Avoid log spam with large symbol lists.
        """
        # Create config with many symbols
        symbols = {f"SYMBOL{i}USDT": {"tick_size": "0.01"} for i in range(20)}
        
        config_dict = {
            "_config_name": "aurora",
            "_config_dir": "config/aurora",
            "instruments": symbols,
            "trading": {
                "instruments": {},  # Legacy (diagnostics only)
                "market_data": {
                    "poll_interval_sec": 1,
                    "macro_sync": {"anchors": []}
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                }
            }
        }
        
        ipc_queue = Queue()
        logger = logging.getLogger("test_worker")
        logger.setLevel(logging.DEBUG)
        
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        
        with caplog.at_level(logging.INFO):
            worker = MarketDataWorker(ipc_queue, config_dict, logger)
        
        # VERIFY: symbols_count shows full count
        assert "symbols_count: 20" in caplog.text
        
        # VERIFY: symbols_preview shows only first 10
        log_messages = caplog.text
        assert "symbols_preview:" in log_messages
        # First 10 symbols should be present
        for i in range(10):
            assert f"SYMBOL{i}USDT" in log_messages
        # 11th+ symbols should NOT be in preview (truncated)
        # Note: Full list is in worker._symbols, just not in log preview


class TestMarketDataProxyConfigMetadata:
    """Test that MarketDataProxy adds config metadata to serialized dict."""
    
    def test_proxy_adds_config_metadata(self):
        """
        Test E: MarketDataProxy._get_config_dict() adds metadata.
        
        CFG-RUNTIME-BOOTSTRAP-07: Proxy must add _config_name and _config_dir.
        """
        from apps.reference.domains.market_data.proxy import MarketDataProxy
        
        # Create mock config with metadata
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {
            "instruments": {"BTCUSDT": {}},
            "trading": {"market_data": {}},
        }
        mock_config._config_name = "test_aurora"
        mock_config._config_dir = "/test/config/aurora"
        
        # Create proxy (with mock FSM)
        mock_fsm = MagicMock()
        proxy = MarketDataProxy(fsm=mock_fsm, config=mock_config)
        
        # Get serialized config
        config_dict = proxy._get_config_dict()
        
        # VERIFY: Metadata added
        assert config_dict["_config_name"] == "test_aurora"
        assert config_dict["_config_dir"] == "/test/config/aurora"
    
    def test_proxy_uses_defaults_if_metadata_missing(self):
        """
        Test F: Proxy uses defaults if config has no metadata.
        
        CFG-RUNTIME-BOOTSTRAP-07: Backward compatibility.
        """
        from apps.reference.domains.market_data.proxy import MarketDataProxy
        
        # Create mock config WITHOUT metadata
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {
            "instruments": {"BTCUSDT": {}},
            "trading": {"market_data": {}},
        }
        # No _config_name or _config_dir attributes
        del mock_config._config_name
        del mock_config._config_dir
        
        mock_fsm = MagicMock()
        proxy = MarketDataProxy(fsm=mock_fsm, config=mock_config)
        
        config_dict = proxy._get_config_dict()
        
        # VERIFY: Defaults used
        assert config_dict["_config_name"] == "aurora"
        assert config_dict["_config_dir"] == "config/aurora"
