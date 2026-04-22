"""Contract tests for decision-making TRADE_INTENT_REJECTED WAL writes."""

from __future__ import annotations

from unittest.mock import patch

from apps.reference.domains.decision_making.normalized_reject_reasons import (
    build_trade_intent_rejected_message,
    normalize_trade_intent_rejected_payload,
)
from apps.reference.domains.decision_making.trade_intent_reject_wal import (
    write_trade_intent_rejected,
)


def test_write_trade_intent_rejected_normalizes_payload_before_wal_append() -> None:
    written: list[dict] = []

    def _append(record: dict) -> bool:
        written.append(record)
        return True

    with patch(
        "apps.reference.domains.decision_making.trade_intent_reject_wal.wal.append",
        side_effect=_append,
    ):
        write_trade_intent_rejected(
            symbol="BTCUSDT",
            reason_code="NRR-046",
            stage="execution",
            why="W" * 300,
            src="unit_test",
            strategy_id="aurora",
            side="BUY",
            context="unit_test",
            why_chain=["first", "", "second"],
            details={"origin": "test"},
            tf_sec=300,
            bar_close_ts=1_700_000_000_000,
            entry_plan={"kind": "limit"},
            ts_ms=1_700_000_000_123,
            rid="RID-WAL-1",
        )

    assert len(written) == 1
    record = written[0]
    payload = record["pld"]
    expected_payload = normalize_trade_intent_rejected_payload(
        {
            "ts_ms": 1_700_000_000_123,
            "symbol": "BTCUSDT",
            "reason_code": "NRR-046",
            "stage": "execution",
            "why": "W" * 300,
            "strategy_id": "aurora",
            "side": "BUY",
            "rid": "RID-WAL-1",
            "context": "unit_test",
            "why_chain": ["first", "", "second"],
            "details": {"origin": "test"},
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "entry_plan": {"kind": "limit"},
        },
        fallback_rid="RID-WAL-1",
        fallback_ts_ms=1_700_000_000_123,
        fallback_symbol="BTCUSDT",
        fallback_reason_code="NRR-046",
        fallback_stage="execution",
        fallback_why="W" * 300,
    )
    expected_record = build_trade_intent_rejected_message(
        expected_payload,
        src="unit_test",
        rid="RID-WAL-1",
    ).model_dump()

    assert record["verb"] == "TRADE_INTENT_REJECTED"
    assert record["rid"] == "RID-WAL-1"
    assert record["op"] == expected_record["op"]
    assert record["src"] == expected_record["src"]
    assert record["dst"] == expected_record["dst"]
    assert record["ts"] == expected_record["ts"]
    assert record["why"] == expected_record["why"]
    assert payload["ts_ms"] == 1_700_000_000_123
    assert payload["symbol"] == "BTCUSDT"
    assert payload["reason_code"] == "NRR-046"
    assert payload["stage"] == "EXECUTION"
    assert payload["why"] == "W" * 240
    assert payload["strategy_id"] == "aurora"
    assert payload["side"] == "buy"
    assert payload["context"] == "unit_test"
    assert payload["why_chain"] == ["first", "second"]
    assert payload["details"] == {"origin": "test"}
    assert payload["tf_sec"] == 300
    assert payload["bar_close_ts"] == 1_700_000_000_000
    assert payload["entry_plan"] == {"kind": "limit"}
    assert payload == expected_payload