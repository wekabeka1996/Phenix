import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jsonschema

from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    OrderEventType,
    parse_order_log_line,
)


def _make_sg() -> SimpleNamespace:
    return SimpleNamespace(
        trace_ts_ms=1775300200000,
        intent_side="BUY",
        signal_score=0.82,
        regime="TREND_UP",
        regime_confidence=0.91,
        trend_dir="UP",
        trend_run_length=4,
        delta_price=0.32,
        pm_norm_10s=0.12,
        pm_norm_60s=0.18,
        pm_norm_300s=0.24,
        vol_pct_10s=0.4,
        vol_pct_60s=0.7,
        vol_pct_300s=1.1,
        deny_reason="NRR-026",
        why_short="trend confirmation failed",
    )


def test_safety_deny_logs_decision_intent_rejected_not_runtime_order_rejected():
    dm = DecisionMaking.__new__(DecisionMaking)
    dm.fsm = MagicMock()
    dm.logger = MagicMock()
    dm._record_blocked_intent = MagicMock()

    with patch("apps.reference.domains.decision_making.core.facade.order_logger.write") as write_mock:
        DecisionMaking._handle_safety_deny(
            dm,
            "ETHUSDT",
            "BUY",
            "rid-phase4-alias-cleanup",
            [],
            _make_sg(),
            strategy_id="md_amr",
        )

    logged_entry = write_mock.call_args_list[-1].args[0]
    assert logged_entry["event_type"] == "DECISION_INTENT_REJECTED"
    assert logged_entry["strategy_id"] == "md_amr"
    assert logged_entry["regime"] == "TREND_UP"
    assert logged_entry["origin_class"] == "decision_alias"
    assert logged_entry["metadata"]["alias_of"] == "TRADE_INTENT_REJECTED"
    assert logged_entry["metadata"]["canonical_event_family"] == "TRADE_INTENT_REJECTED"


def test_decision_intent_rejected_order_log_rows_parse_as_non_runtime_reject():
    payload = {
        "rid": "rid-phase4-alias-cleanup",
        "event_type": "DECISION_INTENT_REJECTED",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "origin_class": "decision_alias",
        "nrr_code": "NRR-026",
        "why": "SAFETY_GATES:trend confirmation failed",
        "source_fsm": "DecisionMaking",
        "timestamp": 1775300200000,
    }
    schema = json.loads(
        Path("apps/reference/schemas/order_logger_v1.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(instance=payload, schema=schema)

    line = json.dumps(payload)

    entry = parse_order_log_line(line)
    assert entry is not None
    assert entry.event_type == OrderEventType.UNKNOWN
