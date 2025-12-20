import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from apps.reference.domains.execution_position.order_guardian import OrderGuardian

@pytest.fixture
def mock_adapter():
    return MagicMock()

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    # Mocking standard structure
    cfg.guardian = MagicMock()
    cfg.guardian.unified = True
    cfg.guardian.ledger_db_path = ":memory:"
    return cfg

def test_guardian_init_with_dict_raises_error(mock_adapter):
    """Ensure init with dict config raises TypeError as per logic."""
    with pytest.raises(TypeError, match="OrderGuardian requires typed config object"):
        OrderGuardian(adapter=mock_adapter, config={"some": "dict"})

def test_guardian_init_default_unified(mock_adapter):
    """Test default initialization with unified mode enabled."""
    cfg = MagicMock()
    cfg.guardian = None # Should fallback to unified=True
    guardian = OrderGuardian(adapter=mock_adapter, config=cfg)
    assert guardian._impl is not None

def test_guardian_init_non_unified(mock_adapter):
    """Test initialization with unified mode disabled."""
    cfg = MagicMock()
    cfg.guardian = MagicMock()
    cfg.guardian.unified = False
    guardian = OrderGuardian(adapter=mock_adapter, config=cfg)
    assert guardian._impl is not None

def test_guardian_register_entry_delegation(mock_adapter, mock_config):
    """Test register_entry delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'register_entry') as mock_reg:
        guardian.register_entry(symbol="BTCUSDT", qty=1.0)
        mock_reg.assert_called_once_with(symbol="BTCUSDT", qty=1.0)

def test_guardian_register_brackets_delegation(mock_adapter, mock_config):
    """Test register_brackets delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'register_brackets') as mock_reg:
        guardian.register_brackets(symbol="BTCUSDT", tp=50000.0)
        mock_reg.assert_called_once_with(symbol="BTCUSDT", tp=50000.0)

@pytest.mark.asyncio
async def test_guardian_should_place_brackets_delegation(mock_adapter, mock_config):
    """Test should_place_brackets delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'should_place_brackets', return_value=True) as mock_meth:
        res = await guardian.should_place_brackets("BTCUSDT")
        assert res is True
        mock_meth.assert_called_once_with("BTCUSDT")

@pytest.mark.asyncio
async def test_guardian_cleanup_before_close_delegation(mock_adapter, mock_config):
    """Test cleanup_before_close delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'cleanup_before_close') as mock_meth:
        await guardian.cleanup_before_close("BTCUSDT")
        mock_meth.assert_called_once_with("BTCUSDT")

def test_guardian_update_known_symbols_delegation(mock_adapter, mock_config):
    """Test update_known_symbols delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'update_known_symbols') as mock_meth:
        symbols = {"BTCUSDT", "ETHUSDT"}
        guardian.update_known_symbols(symbols)
        mock_meth.assert_called_once_with(symbols)

def test_guardian_get_metrics_delegation(mock_adapter, mock_config):
    """Test get_metrics delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'get_metrics', return_value={"m1": 1}) as mock_meth:
        metrics = guardian.get_metrics()
        assert metrics == {"m1": 1}
        mock_meth.assert_called_once()

def test_guardian_poll_interval_property(mock_adapter, mock_config):
    """Test poll_interval_ms property."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config, poll_interval_ms=500)
    assert guardian.poll_interval_ms == 500

@pytest.mark.asyncio
async def test_guardian_start_stop_delegation(mock_adapter, mock_config):
    """Test start/stop delegation."""
    guardian = OrderGuardian(adapter=mock_adapter, config=mock_config)
    with patch.object(guardian._impl, 'start') as mock_start, \
         patch.object(guardian._impl, 'stop') as mock_stop:
        await guardian.start()
        await guardian.stop()
        mock_start.assert_called_once()
        mock_stop.assert_called_once()
