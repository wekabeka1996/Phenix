from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_position.flows.manage.pending_brackets_wal import (
    CriticalStartupError,
    PENDING_BRACKETS_WAL_FILENAME,
    read_pending_brackets_from_wal,
    scan_malformed_wal_rows,
)


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestMalformedWalForensicScanner:
    def test_summary_reports_exact_line_and_byte_offset(self, tmp_path):
        wal_path = tmp_path / "2026-04-30.jsonl"
        good_line = json.dumps({"verb": "BAR_CLOSED", "pld": {"symbol": "BTCUSDT"}})
        malformed_line = (
            '{"verb":"PENDING_BRACKETS_STORED","pld":{"entry_order_id":"order-1",'
            '"symbol":"BTCUSDT" "side":"BUY"}}'
        )
        _write_lines(
            wal_path,
            [
                good_line,
                malformed_line,
                json.dumps({"verb": "BAR_CLOSED", "pld": {"symbol": "ETHUSDT"}}),
            ],
        )

        summary = scan_malformed_wal_rows(wal_path, preview_chars=80, max_rows=8)

        assert summary.wal_path == str(wal_path)
        assert summary.total_lines_scanned == 3
        assert summary.malformed_count == 1
        assert summary.first_malformed_line == 2
        assert summary.last_malformed_line == 2
        assert len(summary.malformed_rows) == 1

        record = summary.malformed_rows[0]
        assert record.line_number == 2
        assert record.error_type == "JSONDecodeError"
        assert "Expecting" in record.error_message or "Extra data" in record.error_message
        assert record.preview == malformed_line[:80]
        assert record.byte_offset == len(f"{good_line}{os.linesep}".encode("utf-8"))

    def test_summary_bounds_retained_rows_and_preview(self, tmp_path):
        wal_path = tmp_path / "2026-04-30.jsonl"
        lines = [json.dumps({"verb": "BAR_CLOSED"})]
        for idx in range(5):
            lines.append(f'{{"verb":"PENDING_BRACKETS_STORED","idx":{idx}')
        lines.append(json.dumps({"verb": "BAR_CLOSED"}))
        _write_lines(wal_path, lines)

        summary = scan_malformed_wal_rows(wal_path, preview_chars=12, max_rows=2)

        assert summary.malformed_count == 5
        assert summary.first_malformed_line == 2
        assert summary.last_malformed_line == 6
        assert summary.truncated is True
        assert summary.max_rows_retained == 2
        assert len(summary.malformed_rows) == 2
        assert [row.line_number for row in summary.malformed_rows] == [2, 3]
        assert all(len(row.preview) <= 12 for row in summary.malformed_rows)

    def test_scanner_does_not_mutate_source_wal(self, tmp_path):
        wal_path = tmp_path / "2026-04-30.jsonl"
        _write_lines(
            wal_path,
            [
                json.dumps({"verb": "BAR_CLOSED"}),
                '{"verb":"PENDING_BRACKETS_STORED","pld":{"entry_order_id":"order-1"',
            ],
        )

        before = wal_path.read_bytes()
        scan_malformed_wal_rows(wal_path)
        after = wal_path.read_bytes()

        assert after == before


class TestMalformedWalFailClosedRestore:
    def test_authoritative_restore_fails_closed_with_forensic_context(self, tmp_path):
        wal_dir = tmp_path
        shared_wal = wal_dir / "2026-04-30.jsonl"
        good_line = json.dumps(
            {
                "verb": "PENDING_BRACKETS_STORED",
                "pld": {
                    "entry_order_id": "order-before",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "sl": 1.0,
                    "tp": 2.0,
                    "qty": 0.5,
                    "rid": "rid-before",
                    "idem_key": "idem-before",
                    "tick_size": 0.1,
                },
            }
        )
        malformed_line = (
            '{"verb":"PENDING_BRACKETS_STORED","pld":{"entry_order_id":"order-bad",'
            '"symbol":"BTCUSDT" "side":"BUY"}}'
        )
        trailing_good = json.dumps(
            {
                "verb": "PENDING_BRACKETS_STORED",
                "pld": {
                    "entry_order_id": "order-after",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "sl": 1.5,
                    "tp": 2.5,
                    "qty": 0.25,
                    "rid": "rid-after",
                    "idem_key": "idem-after",
                    "tick_size": 0.1,
                },
            }
        )
        _write_lines(wal_dir / PENDING_BRACKETS_WAL_FILENAME, [json.dumps({"verb": "BAR_CLOSED"})])
        _write_lines(wal_dir / "2026-04-30.jsonl", [good_line, malformed_line, trailing_good])

        mock_config = MagicMock()
        mock_config.wal_dir = Path(wal_dir)

        with patch("vfoundation.config.config", mock_config):
            with pytest.raises(CriticalStartupError) as excinfo:
                read_pending_brackets_from_wal()

        message = str(excinfo.value)
        assert str(shared_wal) in message
        assert ":2" in message
        assert "preview=" in message
        assert "order-bad" in message
        assert "report=reports/runtime/WAL_MALFORMED_ROW_FORENSIC_HARDENING_REPORT.md" in message
        assert "order-after" not in message
