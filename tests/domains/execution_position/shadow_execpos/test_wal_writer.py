"""
Unit tests for ExecPosWALWriter
================================

Tests WAL writer with mocked WAL append function to verify:
- EXEC_TRADE records are written correctly
- EXEC_ORDER records are written correctly  
- EXEC_POSITION records are written correctly
- Fail-closed behavior (write failures don't crash)
"""
import pytest
from typing import Any, Dict, List, Optional

from apps.reference.domains.execution_position.shadow_execpos.wal_writer import ExecPosWALWriter


class MockWALAppend:
    """Mock WAL append function that collects records instead of writing to disk."""
    
    def __init__(self):
        self.records: List[Dict[str, Any]] = []
        self.should_fail = False
    
    def __call__(self, record: Dict[str, Any]) -> Optional[str]:
        if self.should_fail:
            raise RuntimeError("Simulated WAL write failure")
        self.records.append(record)
        return "mock_hash_123"


def test_write_trade_wal_entry_fill():
    """Test writing EXEC_TRADE record for entry fill."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    trade = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "1.5",
        "quantity": "1.5",
        "price": "50000.0",
        "trade_id": "T123",
        "orderId": "O456",
        "source": "binance",
    }
    
    position_ctx = {
        "position_id": "P789",
        "is_new_position": True,
        "realized_pnl": 0,
        "fee": 2.5,
    }
    
    result = writer.write_trade_wal(trade, position_ctx)
    
    assert result is True
    assert len(mock_wal.records) == 1
    
    record = mock_wal.records[0]
    assert record["event_type"] == "EXEC_TRADE"
    assert record["domain"] == "execution_position"
    assert record["runtime"] == "v2"
    assert record["symbol"] == "BTCUSDT"
    assert record["side"] == "BUY"
    assert record["qty"] == "1.5"
    assert record["price"] == "50000.0"
    assert record["order_id"] == "O456"
    assert record["role"] == "ENTRY"  # Inferred from is_new_position
    assert record["position_id"] == "P789"
    assert record["realized_pnl"] == "0"
    assert record["fee"] == "2.5"
    assert "ts" in record


def test_write_trade_wal_sl_fill():
    """Test writing EXEC_TRADE record for SL fill."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    trade = {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "quantity": "10.0",
        "price": "3000.0",
        "order_id": "SL123",
        "type": "STOP_MARKET",
        "reduceOnly": True,
    }
    
    result = writer.write_trade_wal(trade)
    
    assert result is True
    record = mock_wal.records[0]
    assert record["role"] == "SL"  # Inferred from STOP order type


def test_write_trade_wal_tp_fill():
    """Test writing EXEC_TRADE record for TP fill."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    trade = {
        "symbol": "SOLUSDT",
        "side": "SELL",
        "quantity": "100.0",
        "price": "150.0",
        "order_id": "TP456",
        "order_type":" TAKE_PROFIT_MARKET",
        "reduceOnly": True,
    }
    
    result = writer.write_trade_wal(trade)
    
    assert result is True
    record = mock_wal.records[0]
    assert record["role"] == "TP"  # Inferred from TAKE_PROFIT order type


def test_write_order_wal_placed():
    """Test writing EXEC_ORDER record for order placement."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    order_event = {
        "symbol": "BTCUSDT",
        "order_id": "O123",
        "clientOrderId": "CLIENT456",
        "side": "BUY",
        "type": "LIMIT",
        "status": "NEW",
        "quantity": "1.0",
        "price": "50000.0",
        "role": "ENTRY",
        "reason": "user_order",
    }
    
    result = writer.write_order_wal(order_event)
    
    assert result is True
    assert len(mock_wal.records) == 1
    
    record = mock_wal.records[0]
    assert record["event_type"] == "EXEC_ORDER"
    assert record["domain"] == "execution_position"
    assert record["runtime"] == "v2"
    assert record["symbol"] == "BTCUSDT"
    assert record["order_id"] == "O123"
    assert record["client_order_id"] == "CLIENT456"
    assert record["status"] == "NEW"
    assert record["role"] == "ENTRY"


def test_write_order_wal_cancelled():
    """Test writing EXEC_ORDER record for order cancellation."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    order_event = {
        "symbol": "ETHUSDT",
        "orderId": "O789",
        "status": "CANCELED",
        "reason": "user_cancel",
    }
    
    result = writer.write_order_wal(order_event)
    
    assert result is True
    record = mock_wal.records[0]
    assert record["status"] == "CANCELED"
    assert record["reason"] == "user_cancel"


def test_write_position_wal_open():
    """Test writing EXEC_POSITION record for position open."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    position = {
        "symbol": "BTCUSDT",
        "position_size": "2.5",
        "entry_price": "50000.0",
        "direction": "LONG",
        "realized_pnl": "0",
        "unrealized_pnl": "500.0",
        "exposure_usdt": "125000.0",
        "leverage": 2,
    }
    
    result = writer.write_position_wal(position)
    
    assert result is True
    assert len(mock_wal.records) == 1
    
    record = mock_wal.records[0]
    assert record["event_type"] == "EXEC_POSITION"
    assert record["domain"] == "execution_position"
    assert record["runtime"] == "v2"
    assert record["symbol"] == "BTCUSDT"
    assert record["position_size"] == "2.5"
    assert record["entry_price"] == "50000.0"
    assert record["direction"] == "LONG"
    assert record["leverage"] == 2


def test_write_position_wal_close():
    """Test writing EXEC_POSITION record for position close."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    position = {
        "symbol": "ETHUSDT",
        "qty": "0",
        "position_size": "0",
        "avg_price": "0",
        "side": "FLAT",
        "realized_pnl": "150.0",
    }
    
    result = writer.write_position_wal(position)
    
    assert result is True
    record = mock_wal.records[0]
    assert record["position_size"] == "0"
    assert record["direction"] == "FLAT"


def test_wal_write_failure_logged():
    """Test that WAL write failure is logged and doesn't raise."""
    mock_wal = MockWALAppend()
    mock_wal.should_fail = True
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    trade = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "1.0",
        "price": "50000.0",
    }
    
    # Should not raise, just log and return False
    result = writer.write_trade_wal(trade)
    
    assert result is False
    assert len(mock_wal.records) == 0  # No record written
    assert writer.get_metrics()["write_errors"] == 1


def test_wal_writer_metrics():
    """Test WAL writer metrics tracking."""
    mock_wal = MockWALAppend()
    writer = ExecPosWALWriter(wal_append_fn=mock_wal)
    
    # Write 2 trades, 1 order, 1 position
    writer.write_trade_wal({"symbol": "BTC", "side": "BUY", "quantity": "1", "price": "50000"})
    writer.write_trade_wal({"symbol": "ETH", "side": "SELL", "quantity": "10", "price": "3000"})
    writer.write_order_wal({"symbol": "SOL", "order_id": "O1", "status": "NEW"})
    writer.write_position_wal({"symbol": "BTC", "position_size": "1"})
    
    metrics = writer.get_metrics()
    assert metrics["trades_written"] == 2
    assert metrics["orders_written"] == 1
    assert metrics["positions_written"] == 1
    assert metrics["write_errors"] == 0
