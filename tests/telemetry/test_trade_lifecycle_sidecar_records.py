import json
from pathlib import Path

from apps.reference.telemetry.trade_lifecycle_logger import (
    append_trade_lifecycle_record,
    EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND,
    iter_trade_lifecycle_records,
)


def test_iter_trade_lifecycle_records_skips_policy_rows_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "trade_lifecycle.jsonl"
    append_trade_lifecycle_record(
        {"rid": "trade-1", "symbol": "BTCUSDT"}, log_file=str(log_path))
    append_trade_lifecycle_record(
        {
            "record_kind": "position_policy_sidecar",
            "event_type": "POSITION_POLICY_SIDECAR_SUPPRESSED",
            "symbol": "BTCUSDT",
        },
        log_file=str(log_path),
    )

    records = list(iter_trade_lifecycle_records(log_file=str(log_path)))
    assert records == [{"rid": "trade-1", "symbol": "BTCUSDT"}]


def test_iter_trade_lifecycle_records_can_include_policy_rows(tmp_path: Path) -> None:
    log_path = tmp_path / "trade_lifecycle.jsonl"
    append_trade_lifecycle_record(
        {"rid": "trade-1", "symbol": "BTCUSDT"}, log_file=str(log_path))
    append_trade_lifecycle_record(
        {
            "record_kind": "position_policy_sidecar",
            "event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
            "trace_id": "pps:BTCUSDT:1:1",
            "symbol": "BTCUSDT",
            "score_snapshot": {"soft_close_pressure": 0.9},
        },
        log_file=str(log_path),
    )

    records = list(iter_trade_lifecycle_records(
        log_file=str(log_path), include_policy_records=True))
    assert len(records) == 2
    assert records[1]["record_kind"] == "position_policy_sidecar"

    raw = [json.loads(line) for line in log_path.read_text(
        encoding="utf-8").splitlines()]
    assert raw[1]["event_type"] == "POSITION_POLICY_SIDECAR_RECOMMENDED"


def test_iter_trade_lifecycle_records_skips_execution_fill_ingress_rows_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "trade_lifecycle.jsonl"
    append_trade_lifecycle_record(
        {"rid": "trade-1", "symbol": "BTCUSDT"}, log_file=str(log_path))
    append_trade_lifecycle_record(
        {
            "record_kind": "execution_fill_ingress",
            "event_type": "EXECUTION_FILL_INGRESS",
            "rid": "trade-1",
            "symbol": "BTCUSDT",
            "fill_source": "trade_executed",
        },
        log_file=str(log_path),
    )

    records = list(iter_trade_lifecycle_records(log_file=str(log_path)))
    assert records == [{"rid": "trade-1", "symbol": "BTCUSDT"}]

    with_auxiliary = list(
        iter_trade_lifecycle_records(log_file=str(
            log_path), include_policy_records=True)
    )
    assert len(with_auxiliary) == 2
    assert with_auxiliary[1]["record_kind"] == "execution_fill_ingress"


def test_iter_trade_lifecycle_records_skips_bracket_ownership_rows_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "trade_lifecycle.jsonl"
    append_trade_lifecycle_record(
        {"rid": "trade-1", "symbol": "BTCUSDT"}, log_file=str(log_path))
    append_trade_lifecycle_record(
        {
            "record_kind": EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND,
            "event_type": "EXECUTION_BRACKET_RECOVERY_PLACED",
            "symbol": "BTCUSDT",
            "placement_path": "recovery",
            "strategy_id": "aurora",
        },
        log_file=str(log_path),
    )

    records = list(iter_trade_lifecycle_records(log_file=str(log_path)))
    assert records == [{"rid": "trade-1", "symbol": "BTCUSDT"}]

    with_auxiliary = list(
        iter_trade_lifecycle_records(log_file=str(
            log_path), include_policy_records=True)
    )
    assert len(with_auxiliary) == 2
    assert with_auxiliary[1]["record_kind"] == EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND
