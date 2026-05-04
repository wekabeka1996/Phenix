import pytest
import os
import logging
from pathlib import Path
from apps.reference.domains.execution_position.telemetry.aurora_log_adapter import AuroraLogAdapter

@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "test_trades.log"

@pytest.fixture
def adapter(log_file):
    return AuroraLogAdapter(log_file=str(log_file))

def test_adapter_init(log_file):
    """Verify initialization and file handler setup."""
    adapter = AuroraLogAdapter(log_file=str(log_file))
    assert Path(log_file).exists()
    assert adapter.logger.name == "aurora.trades"
    # Second init shouldn't add another handler
    handler_count = len(adapter.logger.handlers)
    adapter2 = AuroraLogAdapter(log_file=str(log_file))
    assert len(adapter2.logger.handlers) == handler_count

def test_log_trade_intent(adapter, log_file):
    """Verify trade intent logging."""
    adapter.log_trade_intent(
        rid="r1", symbol="BTCUSDT", side="BUY", 
        probability=0.85, size=100.0, price=50000.0, qty=0.002, risk_score=0.1
    )
    content = log_file.read_text()
    assert "EVENT_TRADE_INTENT_PROPOSED - BTCUSDT BUY" in content
    assert "prob=0.850" in content
    assert "size=$100.00" in content

def test_log_trade_decision(adapter, log_file):
    """Verify trade decision logging."""
    adapter.log_trade_decision("r1", "BTCUSDT", "BUY", "ACCEPTED")
    adapter.log_trade_decision("r2", "BTCUSDT", "SELL", "REJECTED", reason="Insufficient funds")
    content = log_file.read_text()
    assert "EVENT_TRADE_DECISION - BTCUSDT BUY ACCEPTED" in content
    assert "EVENT_TRADE_DECISION - BTCUSDT SELL REJECTED (Insufficient funds)" in content

def test_log_trade_execution(adapter, log_file):
    """Verify trade execution logging."""
    adapter.log_trade_execution("r1", "BTCUSDT", "BUY", order_id="e1", status="FILLED", executed_qty=0.002, executed_price=50000.0)
    content = log_file.read_text()
    assert "EVENT_TRADE_EXECUTION - BTCUSDT BUY FILLED" in content
    assert "order_id=e1" in content
    assert "qty=0.002000" in content

def test_log_guard_rejection(adapter, log_file):
    """Verify guard rejection logging."""
    adapter.log_guard_rejection("r1", "BTCUSDT", "BUY", "COOLDOWN", "Position recently closed")
    content = log_file.read_text()
    assert "GUARD_REJECT: COOLDOWN - BTCUSDT BUY (Position recently closed)" in content
