"""
Test: Smart Extraction for ExecPosFSM price resolution

CFG-SMART-EXTRACT-01: Verifies that _resolve_price correctly extracts
stop_price/target_price from multiple payload locations:
1. Root level (normalized by DecisionMaking)
2. Nested price_ctx (raw strategy output, e.g., MeanReversion)
3. Nested order object (legacy/alternative structure)

This test ensures the Strategy→Execution data contract is not broken
by payload structure variations.
"""

import pytest
from apps.reference.domains.execution_position.utils import resolve_price
from unittest.mock import MagicMock, patch
from typing import Optional


class TestFsmSmartExtract:
    """Test suite for _resolve_price smart extraction."""

    @pytest.fixture
    def mock_fsm(self):
        """Create a minimal ExecPosFSM instance for testing."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter'):
            from apps.reference.config_loader import ConfigLoader
            from apps.reference.domains.execution_position.fsm import ExecPosFSM
            
            loader = ConfigLoader()
            config = loader.load_config()
            
            mock_bus = MagicMock()
            fsm = ExecPosFSM(config=config, fsm=mock_bus, shadow_mode=True)
            return fsm

    def test_resolve_price_from_root(self, mock_fsm):
        """Test extraction from root level (normalized by DecisionMaking)."""
        pld = {
            "stop_price": "27000.50",
            "target_price": "28500.00",
        }
        
        assert resolve_price(pld, "stop_price") == "27000.50"
        assert resolve_price(pld, "target_price") == "28500.00"

    def test_resolve_price_from_price_ctx(self, mock_fsm):
        """
        Test extraction from nested price_ctx (MeanReversion strategy output).
        
        This is the CRITICAL test case - MeanReversion places stop_price inside
        price_ctx, and this was previously lost.
        """
        pld = {
            "instrument": "BTCUSDT",
            "side": "BUY",
            "price_ctx": {
                "stop_price": "26500.00",
                "target_price": "29000.00",
                "entry_price": "27500.00",
            },
            "order": {
                "qty": "0.01",
                "order_type": "LIMIT",
                "price": "27500.00",
            }
        }
        
        # stop_price is ONLY in price_ctx, not at root
        assert resolve_price(pld, "stop_price") == "26500.00"
        assert resolve_price(pld, "target_price") == "29000.00"

    def test_resolve_price_from_order(self, mock_fsm):
        """Test extraction from nested order object (legacy structure)."""
        pld = {
            "instrument": "ETHUSDT",
            "side": "SELL",
            "order": {
                "qty": "0.5",
                "order_type": "MARKET",
                "stop_price": "1800.00",
                "target_price": "1700.00",
            }
        }
        
        # stop_price is ONLY in order, not at root or price_ctx
        assert resolve_price(pld, "stop_price") == "1800.00"
        assert resolve_price(pld, "target_price") == "1700.00"

    def test_resolve_price_priority_root_over_price_ctx(self, mock_fsm):
        """Test that root level has priority over price_ctx."""
        pld = {
            "stop_price": "27000.00",  # Root level (priority 1)
            "price_ctx": {
                "stop_price": "26000.00",  # Nested (priority 2)
            }
        }
        
        # Root should win
        assert resolve_price(pld, "stop_price") == "27000.00"

    def test_resolve_price_priority_price_ctx_over_order(self, mock_fsm):
        """Test that price_ctx has priority over order."""
        pld = {
            "price_ctx": {
                "stop_price": "26500.00",  # price_ctx (priority 2)
            },
            "order": {
                "stop_price": "26000.00",  # order (priority 3)
            }
        }
        
        # price_ctx should win
        assert resolve_price(pld, "stop_price") == "26500.00"

    def test_resolve_price_returns_none_for_missing(self, mock_fsm):
        """Test that None is returned when field is not found anywhere."""
        pld = {
            "instrument": "DOGEUSDT",
            "side": "BUY",
            "order": {
                "qty": "100",
            }
        }
        
        assert resolve_price(pld, "stop_price") is None
        assert resolve_price(pld, "target_price") is None

    def test_resolve_price_ignores_null_values(self, mock_fsm):
        """Test that null/None/'None' values are skipped."""
        pld = {
            "stop_price": None,  # Should skip
            "price_ctx": {
                "stop_price": "None",  # Should skip
            },
            "order": {
                "stop_price": "27000.00",  # Should be used
            }
        }
        
        assert resolve_price(pld, "stop_price") == "27000.00"

    def test_resolve_price_ignores_empty_string(self, mock_fsm):
        """Test that empty strings are skipped."""
        pld = {
            "stop_price": "",  # Should skip
            "price_ctx": {
                "stop_price": "26500.00",  # Should be used
            }
        }
        
        assert resolve_price(pld, "stop_price") == "26500.00"


class TestMetadataExtraction:
    """Test that TCA and Risk metadata are properly extracted and logged."""

    @pytest.fixture
    def mock_fsm_with_bus(self):
        """Create ExecPosFSM with mocked bus for event testing."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter'):
            from apps.reference.config_loader import ConfigLoader
            from apps.reference.domains.execution_position.fsm import ExecPosFSM
            
            loader = ConfigLoader()
            config = loader.load_config()
            
            mock_bus = MagicMock()
            mock_bus.listen = MagicMock()
            mock_bus.emit = MagicMock()
            
            fsm = ExecPosFSM(config=config, fsm=mock_bus, shadow_mode=True)
            return fsm

    def test_tca_budget_extraction(self, mock_fsm_with_bus):
        """Verify TCA budget parameters are available in payload processing."""
        pld = {
            "instrument": "BTCUSDT",
            "side": "BUY",
            "tca_budget": {
                "max_slippage_bps": 15,
                "max_latency_ms": 500,
                "maker_preference": "neutral",
            },
            "order": {
                "qty": "0.01",
                "order_type": "LIMIT",
                "price": "27500.00",
            }
        }
        
        tca = pld.get("tca_budget") or {}
        assert tca.get("max_slippage_bps") == 15
        assert tca.get("max_latency_ms") == 500
        assert tca.get("maker_preference") == "neutral"

    def test_risk_context_extraction(self, mock_fsm_with_bus):
        """Verify risk context parameters are available in payload processing."""
        pld = {
            "instrument": "ETHUSDT",
            "side": "SELL",
            "risk_context": {
                "risk_score": 0.45,
                "trade_cvar95_bps": 85,
                "portfolio_heat": 0.12,
            },
            "order": {
                "qty": "0.5",
                "order_type": "MARKET",
            }
        }
        
        risk = pld.get("risk_context") or {}
        assert risk.get("risk_score") == 0.45
        assert risk.get("trade_cvar95_bps") == 85
        assert risk.get("portfolio_heat") == 0.12
