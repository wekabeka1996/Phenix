import pytest
from unittest.mock import MagicMock, patch
from apps.reference.domains.execution_position.order_guardian import OrderGuardian
from apps.reference.services.order_guardian import OrderGuardian as ServicesGuardian
from apps.reference.services.ledger_store_adapter import LedgerStoreAdapter
from apps.reference.domains.execution_position.manage_config import clear_manage_config_cache

@pytest.fixture(autouse=True)
def clear_cache():
    clear_manage_config_cache()

@pytest.fixture
def mock_adapter():
    return MagicMock()

@pytest.fixture
def mock_config():
    return {
        "guardian": {
            "unified": True,
            "ledger_db_path": ":memory:"
        },
        "trading": {
            "execution": {
                "manage": {
                    "mode": "aggregated_only",
                    "brackets": {
                        "aggregated_oco": {
                            "enabled": True,
                            "aggregated_only_mode": True,
                            "recalc_on_partial_close": True,
                            "ttl_protect_new_bracket_ms": 5000,
                            "allow_unprotected_position": False
                        }
                    }
                }
            }
        }
    }

def test_initialization_unified(mock_adapter, mock_config):
    with patch("apps.reference.domains.execution_position.order_guardian.OrderLedger") as MockLedger:
        guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)

        # Verify Ledger was initialized
        MockLedger.assert_called_once()

        # Verify ServicesGuardian was initialized with store
        assert isinstance(guardian._impl, ServicesGuardian)
        assert isinstance(guardian._impl.store, LedgerStoreAdapter)
        assert guardian._impl.adapter == mock_adapter

def test_initialization_legacy(mock_adapter):
    config = {"guardian": {"unified": False}}

    guardian = OrderGuardian(adapter=mock_adapter, config=config)

    # Verify ServicesGuardian was initialized with store=InMemoryStore (default)
    assert isinstance(guardian._impl, ServicesGuardian)
    assert guardian._impl.store.__class__.__name__ == "InMemoryStore"

def test_delegation(mock_adapter, mock_config):
    with patch("apps.reference.domains.execution_position.order_guardian.OrderLedger"):
        guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)

        # Mock the implementation
        guardian._impl = MagicMock()

        # Test register_entry delegation
        guardian.register_entry(symbol="BTCUSDT", order_id="123")
        guardian._impl.register_entry.assert_called_once_with(symbol="BTCUSDT", order_id="123")

        # Test on_fill delegation
        guardian.on_fill(order_id="123", qty="1.0")
        guardian._impl.on_fill.assert_called_once_with(order_id="123", qty="1.0")

        # Test list_entries delegation
        guardian.list_entries(symbol="BTCUSDT")
        guardian._impl.list_entries.assert_called_once_with(symbol="BTCUSDT")

def test_aggregated_config_resolution(mock_adapter, mock_config):
    with patch("apps.reference.domains.execution_position.order_guardian.OrderLedger"):
        guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)

        agg_cfg = guardian._aggregated_guardian_cfg
        assert agg_cfg.enabled is True
        assert agg_cfg.ttl_protect_new_bracket_ms == 5000
        assert agg_cfg.allow_unprotected_position is False

def test_aggregated_config_resolution_disabled(mock_adapter):
    config = {
        "execution": {
            "manage": {
                "brackets": {
                    "aggregated_oco": {
                        "enabled": False
                    }
                }
            }
        }
    }

    with patch("apps.reference.domains.execution_position.order_guardian.OrderLedger"):
        guardian = OrderGuardian(adapter=mock_adapter, config=config)

        agg_cfg = guardian._aggregated_guardian_cfg
        assert agg_cfg.enabled is False

def test_default_db_path(mock_adapter):
    # Config without db_path
    config = {"guardian": {"unified": True}}

    with patch("apps.reference.domains.execution_position.order_guardian.OrderLedger") as MockLedger:
        guardian = OrderGuardian(adapter=mock_adapter, config=config)

        # Verify it used a temp path
        args, _ = MockLedger.call_args
        assert "order_ledger.db" in args[0]
