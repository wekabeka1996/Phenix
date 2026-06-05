import os
from apps.reference.domains.execution_position.telemetry.aurora_log_adapter import (
    AuroraLogAdapter,
)


def test_aurora_log_adapter_writes(tmp_path):
    log_file = tmp_path / "aurora_test.log"

    # Create adapter
    adapter = AuroraLogAdapter(log_file=str(log_file), level="INFO")

    # Ensure file is created by logging something
    adapter.logger.info("Test log message")

    # Log some messages
    adapter.log_trade_intent(
        "rid1", "ETHUSDT", "BUY", probability=0.55, size=100.0, price=123.45
    )

    # Force flush
    import time
    time.sleep(0.1)
    for handler in adapter.logger.handlers:
        handler.flush()

    # Check file exists and has content
    assert log_file.exists(), f"Log file {log_file} does not exist"

    # Read content and check
    content = log_file.read_text(encoding="utf-8")
    assert len(content) > 0, "Log file is empty"
    assert "EVENT_TRADE_INTENT_PROPOSED" in content or "TRADE_INTENT" in content
