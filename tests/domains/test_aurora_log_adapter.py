import os
from apps.reference.domains.execution_position.aurora_log_adapter import AuroraLogAdapter


def test_aurora_log_adapter_writes(tmp_path):
    log_file = tmp_path / "aurora_test.log"
    adapter = AuroraLogAdapter(log_file=str(log_file), level="INFO")

    adapter.log_trade_intent("rid1", "ETHUSDT", "BUY", probability=0.55, size=100.0, price=123.45)
    adapter.log_trade_decision("rid1", "ETHUSDT", "BUY", "ACCEPTED")
    adapter.log_trade_execution("rid1", "ETHUSDT", "BUY", order_id="ord1", status="FILLED", executed_qty=0.1, executed_price=123.45)
    adapter.log_guard_rejection("rid2", "ETHUSDT", "SELL", "COOLDOWN", "cooldown reason")

    # Ensure file exists and contains lines
    assert log_file.exists()
    text = log_file.read_text(encoding="utf-8")
    assert "EVENT_TRADE_INTENT_PROPOSED" in text or "TRADE_INTENT" in text
