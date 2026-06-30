"""Tests for vfoundation.dr.replay — Phase 1.11."""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any, Dict, List

import pytest

from vfoundation.dr import wal, replay


@pytest.fixture()
def tmp_wal(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Redirect WAL_DIR and replay's WAL_DIR reference to a temp directory."""
    wal_dir = tmp_path / "wal"
    wal_dir.mkdir()
    wal.set_wal_dir(wal_dir)
    monkeypatch.setattr(replay.wal, "WAL_DIR", wal_dir)
    return wal_dir


def _write_chained_records(
    wal_dir: pathlib.Path, records: List[Dict[str, Any]]
) -> None:
    """Write records with proper hash-chain to a JSONL file."""
    today = time.strftime("%Y-%m-%d")
    path = wal_dir / f"{today}.jsonl"
    prev_hash = "0" * 64
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            payload = {**rec, "_prev": prev_hash}
            record_json = json.dumps(
                payload, sort_keys=True, ensure_ascii=False)
            import hashlib
            record_hash = hashlib.sha256(
                record_json.encode("utf-8")).hexdigest()
            payload["_hash"] = record_hash
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            prev_hash = record_hash


def _valid_order_state_changed_record() -> Dict[str, Any]:
    return {
        "op": "EVT",
        "verb": "ORDER_STATE_CHANGED",
        "ts": 3000,
        "src": "execution_position",
        "dst": "monitoring",
        "pld": {
            "symbol": "BTCUSDT",
            "event_ts_ms": 3000,
            "status": "CANCELED",
            "canonical_identity_key": (
                "evt:order_state_changed:symbol=BTCUSDT:order_id=oid-2:terminal_state=CANCELED"
            ),
            "order_id": "oid-2",
        },
    }


# ─── replay_for_rid ──────────────────────────────────────────────────

def _valid_order_rejected_record() -> Dict[str, Any]:
    return {
        "op": "EVT",
        "verb": "ORDER_REJECTED",
        "ts": 4000,
        "src": "execution_position",
        "dst": "observability",
        "rid": "reject-rid-1",
        "pld": {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "event_ts_ms": 4000,
            "reason_code": "ADAPTER_ERROR",
            "reason_text": "adapter rejected before durable order id",
            "origin_class": "execution_adapter",
            "identity_quality": "order_identity_weak",
            "canonical_identity_key": (
                "evt:order_rejected:symbol=BTCUSDT:rid=reject-rid-1:"
                "terminal_state=REJECTED:reject_reason=ADAPTER_ERROR"
            ),
            "terminal_non_fill": True,
            "terminal_state_kind": "REJECTED",
            "compatibility_aliases_retained": True,
        },
    }


class TestReplayForRid:
    def test_returns_events_for_matching_rid(self, tmp_wal: pathlib.Path) -> None:
        records = [
            {"rid": "r1", "op": "CMD", "verb": "OPEN", "ts": 1000},
            {"rid": "r2", "op": "EVT", "verb": "FILLED", "ts": 2000},
            {"rid": "r1", "op": "EVT", "verb": "PLACED", "ts": 3000},
        ]
        _write_chained_records(tmp_wal, records)

        collected: List[Dict[str, Any]] = []
        result = replay.replay_for_rid("r1", lambda e: collected.append(e))
        assert len(result) == 2
        assert all(e["rid"] == "r1" for e in result)
        assert len(collected) == 2

    def test_returns_empty_for_unknown_rid(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(
            tmp_wal, [{"rid": "x", "op": "EVT", "verb": "OK", "ts": 1}])
        result = replay.replay_for_rid("missing", lambda e: None)
        assert result == []

    def test_returns_empty_when_no_wal_dir(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        no_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(replay.wal, "WAL_DIR", no_dir)
        result = replay.replay_for_rid("r1", lambda e: None)
        assert result == []


# ─── replay_for_rid_with_integrity ───────────────────────────────────

class TestReplayWithIntegrity:
    def test_valid_chain_returns_true(self, tmp_wal: pathlib.Path) -> None:
        records = [
            {"rid": "r1", "op": "CMD", "verb": "OPEN", "ts": 1},
            {"rid": "r1", "op": "EVT", "verb": "ACK", "ts": 2},
        ]
        _write_chained_records(tmp_wal, records)
        events, ok, merkle = replay.replay_for_rid_with_integrity(
            "r1", lambda e: None)
        assert ok is True
        assert len(events) == 2
        assert len(merkle) == 64  # sha256 hex

    def test_tampered_hash_returns_false(self, tmp_wal: pathlib.Path) -> None:
        records = [
            {"rid": "r1", "op": "CMD", "verb": "OPEN", "ts": 1},
            {"rid": "r1", "op": "EVT", "verb": "ACK", "ts": 2},
        ]
        _write_chained_records(tmp_wal, records)

        # Tamper with the hash of the second record
        today = time.strftime("%Y-%m-%d")
        path = tmp_wal / f"{today}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        obj = json.loads(lines[1])
        obj["_hash"] = "f" * 64  # corrupt
        lines[1] = json.dumps(obj, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _, ok, _ = replay.replay_for_rid_with_integrity("r1", lambda e: None)
        assert ok is False

    def test_empty_wal_is_valid(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        empty = tmp_path / "empty_wal"
        empty.mkdir()
        monkeypatch.setattr(replay.wal, "WAL_DIR", empty)
        events, ok, merkle = replay.replay_for_rid_with_integrity(
            "any", lambda e: None)
        assert events == []
        assert ok is True
        assert merkle == "0" * 64


# ─── bounded startup replay subset ───────────────────────────────────

class TestReplayW5BoundedStartupSubset:
    def test_filters_to_w5_subset_and_symbol_scope(self, tmp_wal: pathlib.Path) -> None:
        order_state_changed = _valid_order_state_changed_record()
        _write_chained_records(
            tmp_wal,
            [
                {
                    "rid": "r1",
                    "op": "EVT",
                    "verb": "ORDER_PLACED",
                    "ts": 1000,
                    "symbol": "BTCUSDT",
                    "client_order_id": "cid-1",
                    "order_id": "oid-1",
                },
                {
                    "rid": "r2",
                    "op": "EVT",
                    "verb": "EXECUTION_CLOSE_RECONCILED",
                    "ts": 2000,
                    "symbol": "BTCUSDT",
                    "source": "bus",
                    "why": "close",
                },
                order_state_changed,
                {
                    "rid": "r4",
                    "op": "EVT",
                    "verb": "TRADE_EXECUTED",
                    "ts": 4000,
                    "symbol": "ETHUSDT",
                    "client_order_id": "cid-3",
                    "order_id": "oid-3",
                    "side": "BUY",
                    "quantity": "1.0",
                    "price": "10.0",
                },
            ],
        )

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.attempted is True
        assert summary.completed is True
        assert summary.scan_state == "completed"
        assert summary.symbols_considered == ["BTCUSDT"]
        assert summary.records_seen == 3
        assert summary.records_accepted == 2
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 0
        assert summary.records_ignored_by_boundary == 2
        assert summary.event_counts == {
            "EVT:ORDER_PLACED": 1,
            "EVT:ORDER_STATE_CHANGED": 1,
        }
        assert len(summary.symbol_records) == 1
        assert summary.symbol_records[0].symbol == "BTCUSDT"
        assert summary.symbol_records[0].accepted_records == 2
        assert order_state_changed["pld"]["canonical_identity_key"] in summary.symbol_records[0].identity_keys

    @pytest.mark.parametrize("identity_kind", ["order_id", "client_order_id", "rid"])
    def test_accepts_valid_order_state_changed_with_supported_identity_fields(
        self,
        tmp_wal: pathlib.Path,
        identity_kind: str,
    ) -> None:
        record = _valid_order_state_changed_record()
        payload = record["pld"]

        payload.pop("order_id", None)
        payload.pop("client_order_id", None)
        payload.pop("clientOrderId", None)
        record.pop("rid", None)

        if identity_kind == "order_id":
            payload["order_id"] = "oid-2"
        elif identity_kind == "client_order_id":
            payload["client_order_id"] = "cid-2"
        elif identity_kind == "rid":
            record["rid"] = "rid-2"
        else:
            raise AssertionError(f"Unexpected identity_kind: {identity_kind}")

        _write_chained_records(tmp_wal, [record])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 1
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:ORDER_STATE_CHANGED": 1}
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].identity_keys == [
            record["pld"]["canonical_identity_key"]
        ]

    def test_order_state_changed_uses_canonical_identity_key_for_dedupe(self, tmp_wal: pathlib.Path) -> None:
        first = _valid_order_state_changed_record()
        first["rid"] = "rid-1"
        second = _valid_order_state_changed_record()
        second["rid"] = "rid-2"

        _write_chained_records(tmp_wal, [first, second])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 2
        assert summary.records_accepted == 1
        assert summary.records_duplicate == 1
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:ORDER_STATE_CHANGED": 1}
        assert summary.symbol_records[0].identity_keys == [
            first["pld"]["canonical_identity_key"]
        ]

    def test_order_state_changed_fails_closed_on_missing_symbol(self, tmp_wal: pathlib.Path) -> None:
        record = _valid_order_state_changed_record()
        record["pld"].pop("symbol")

        _write_chained_records(tmp_wal, [record])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 0
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 1
        assert summary.event_counts == {}
        assert summary.unresolved_reasons == [
            "EVT:ORDER_STATE_CHANGED:missing_symbol"]
        assert summary.symbol_records == []

    @pytest.mark.parametrize(
        ("failure_case", "expected_reason"),
        [
            (
                "missing_canonical_identity_key",
                "EVT:ORDER_STATE_CHANGED:missing_canonical_identity_key",
            ),
            (
                "empty_canonical_identity_key",
                "EVT:ORDER_STATE_CHANGED:missing_canonical_identity_key",
            ),
            ("missing_status", "EVT:ORDER_STATE_CHANGED:missing_status"),
            ("missing_event_ts_ms", "EVT:ORDER_STATE_CHANGED:missing_event_ts_ms"),
            (
                "missing_all_identity",
                "EVT:ORDER_STATE_CHANGED:missing_order_id_or_client_order_id_or_rid",
            ),
        ],
    )
    def test_order_state_changed_fails_closed_when_required_contract_fields_are_missing(
        self,
        tmp_wal: pathlib.Path,
        failure_case: str,
        expected_reason: str,
    ) -> None:
        record = _valid_order_state_changed_record()
        payload = record["pld"]

        if failure_case == "missing_canonical_identity_key":
            payload.pop("canonical_identity_key")
        elif failure_case == "empty_canonical_identity_key":
            payload["canonical_identity_key"] = "   "
        elif failure_case == "missing_status":
            payload.pop("status")
        elif failure_case == "missing_event_ts_ms":
            payload.pop("event_ts_ms")
        elif failure_case == "missing_all_identity":
            payload.pop("order_id", None)
            payload.pop("orderId", None)
            payload.pop("client_order_id", None)
            payload.pop("clientOrderId", None)
            payload.pop("rid", None)
            record.pop("rid", None)
        else:
            raise AssertionError(f"Unexpected failure_case: {failure_case}")

        _write_chained_records(tmp_wal, [record])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 0
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 1
        assert summary.event_counts == {}
        assert summary.unresolved_reasons == [expected_reason]
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].unresolved_reasons == [
            expected_reason]

    @pytest.mark.parametrize(
        ("identity_field", "identity_value"),
        [
            ("order_id", "oid-reject-1"),
            ("orderId", "oid-reject-1"),
            ("exchange_order_id", "ex-reject-1"),
            ("exchangeOrderId", "ex-reject-1"),
            ("client_order_id", "cid-reject-1"),
            ("clientOrderId", "cid-reject-1"),
            ("corr_id", "corr-reject-1"),
            ("corrId", "corr-reject-1"),
        ],
    )
    def test_accepts_order_rejected_with_strong_identity(
        self,
        tmp_wal: pathlib.Path,
        identity_field: str,
        identity_value: str,
    ) -> None:
        record = _valid_order_rejected_record()
        record["pld"][identity_field] = identity_value

        _write_chained_records(tmp_wal, [record])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 1
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:ORDER_REJECTED": 1}
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].identity_keys == [
            f"EVT:ORDER_REJECTED|BTCUSDT|reject-rid-1|{identity_field}|{identity_value}"
        ]

    def test_accepts_order_rejected_with_weak_canonical_identity(self, tmp_wal: pathlib.Path) -> None:
        record = _valid_order_rejected_record()

        _write_chained_records(tmp_wal, [record])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 1
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:ORDER_REJECTED": 1}
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].identity_keys == [
            record["pld"]["canonical_identity_key"]
        ]

    def test_order_rejected_weak_canonical_identity_dedupes(self, tmp_wal: pathlib.Path) -> None:
        first = _valid_order_rejected_record()
        second = _valid_order_rejected_record()
        second["rid"] = "reject-rid-2"
        second["pld"]["rid"] = "reject-rid-2"

        _write_chained_records(tmp_wal, [first, second])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 2
        assert summary.records_accepted == 1
        assert summary.records_duplicate == 1
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:ORDER_REJECTED": 1}
        assert summary.symbol_records[0].identity_keys == [
            first["pld"]["canonical_identity_key"]
        ]

    @pytest.mark.parametrize(
        ("failure_case", "expected_reason"),
        [
            (
                "missing_canonical_identity_key",
                "EVT:ORDER_REJECTED:missing_identity:canonical_identity_key",
            ),
            (
                "empty_canonical_identity_key",
                "EVT:ORDER_REJECTED:missing_identity:canonical_identity_key",
            ),
            ("missing_rid", "EVT:ORDER_REJECTED:missing_identity:rid"),
            (
                "missing_terminal_non_fill",
                "EVT:ORDER_REJECTED:missing_identity:terminal_non_fill",
            ),
            (
                "false_terminal_non_fill",
                "EVT:ORDER_REJECTED:missing_identity:terminal_non_fill",
            ),
            (
                "missing_terminal_state_kind",
                "EVT:ORDER_REJECTED:missing_identity:terminal_state_kind",
            ),
            (
                "wrong_terminal_state_kind",
                "EVT:ORDER_REJECTED:missing_identity:terminal_state_kind",
            ),
            ("missing_event_ts_ms", "EVT:ORDER_REJECTED:missing_identity:event_ts_ms"),
            (
                "missing_identity_quality",
                "EVT:ORDER_REJECTED:missing_identity:identity_quality",
            ),
            (
                "invalid_identity_quality",
                "EVT:ORDER_REJECTED:missing_identity:identity_quality",
            ),
            (
                "missing_origin_class",
                "EVT:ORDER_REJECTED:missing_identity:origin_class",
            ),
            (
                "missing_compatibility_aliases_retained",
                "EVT:ORDER_REJECTED:missing_identity:compatibility_aliases_retained",
            ),
            (
                "false_compatibility_aliases_retained",
                "EVT:ORDER_REJECTED:missing_identity:compatibility_aliases_retained",
            ),
        ],
    )
    def test_order_rejected_weak_identity_fails_closed_when_guardrails_are_missing(
        self,
        tmp_wal: pathlib.Path,
        failure_case: str,
        expected_reason: str,
    ) -> None:
        record = _valid_order_rejected_record()
        payload = record["pld"]

        if failure_case == "missing_canonical_identity_key":
            payload.pop("canonical_identity_key")
        elif failure_case == "empty_canonical_identity_key":
            payload["canonical_identity_key"] = "   "
        elif failure_case == "missing_rid":
            record.pop("rid", None)
            payload.pop("rid", None)
        elif failure_case == "missing_terminal_non_fill":
            payload.pop("terminal_non_fill")
        elif failure_case == "false_terminal_non_fill":
            payload["terminal_non_fill"] = False
        elif failure_case == "missing_terminal_state_kind":
            payload.pop("terminal_state_kind")
        elif failure_case == "wrong_terminal_state_kind":
            payload["terminal_state_kind"] = "CANCELED"
        elif failure_case == "missing_event_ts_ms":
            payload.pop("event_ts_ms")
            payload.pop("ts_ms", None)
            record.pop("ts", None)
        elif failure_case == "missing_identity_quality":
            payload.pop("identity_quality")
        elif failure_case == "invalid_identity_quality":
            payload["identity_quality"] = "not_valid"
        elif failure_case == "missing_origin_class":
            payload.pop("origin_class")
        elif failure_case == "missing_compatibility_aliases_retained":
            payload.pop("compatibility_aliases_retained")
        elif failure_case == "false_compatibility_aliases_retained":
            payload["compatibility_aliases_retained"] = False
        else:
            raise AssertionError(f"Unexpected failure_case: {failure_case}")

        _write_chained_records(tmp_wal, [record])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 0
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 1
        assert summary.event_counts == {}
        assert summary.unresolved_reasons == [expected_reason]
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].unresolved_reasons == [
            expected_reason]

    def test_order_rejected_has_no_timestamp_only_or_rid_only_fallback(self, tmp_wal: pathlib.Path) -> None:
        timestamp_only = {
            "op": "EVT",
            "verb": "ORDER_REJECTED",
            "ts": 4000,
            "pld": {
                "symbol": "BTCUSDT",
                "event_ts_ms": 4000,
            },
        }
        rid_only = {
            "op": "EVT",
            "verb": "ORDER_REJECTED",
            "ts": 5000,
            "rid": "reject-rid-only",
            "pld": {
                "symbol": "BTCUSDT",
                "event_ts_ms": 5000,
                "rid": "reject-rid-only",
            },
        }

        _write_chained_records(tmp_wal, [timestamp_only, rid_only])

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 2
        assert summary.records_accepted == 0
        assert summary.records_duplicate == 0
        assert summary.records_unresolved == 2
        assert summary.event_counts == {}
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert any(
            "missing_identity:canonical_identity_key" in reason
            for reason in summary.unresolved_reasons
        )
        assert any(
            "missing_identity:rid" in reason
            for reason in summary.unresolved_reasons
        )

    def test_is_idempotent_for_duplicate_identity(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(
            tmp_wal,
            [
                {
                    "rid": "r1",
                    "op": "EVT",
                    "verb": "ORDER_PLACED",
                    "ts": 1000,
                    "symbol": "BTCUSDT",
                    "client_order_id": "cid-1",
                    "order_id": "oid-1",
                },
                {
                    "rid": "r1",
                    "op": "EVT",
                    "verb": "ORDER_PLACED",
                    "ts": 2000,
                    "symbol": "BTCUSDT",
                    "client_order_id": "cid-1",
                    "order_id": "oid-1",
                },
            ],
        )

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 2
        assert summary.records_accepted == 1
        assert summary.records_duplicate == 1
        assert summary.records_unresolved == 0
        assert summary.symbol_records[0].identity_keys == [
            "EVT:ORDER_PLACED|BTCUSDT|r1|order_id|oid-1"
        ]

    def test_missing_identity_fails_closed(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(
            tmp_wal,
            [
                {
                    "rid": "r1",
                    "op": "EVT",
                    "verb": "PENDING_BRACKETS_STORED",
                    "ts": 1000,
                    "symbol": "BTCUSDT",
                    "qty": 1,
                }
            ],
        )

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 0
        assert summary.records_unresolved == 1
        assert summary.records_duplicate == 0
        assert summary.unresolved_reasons == [
            "EVT:PENDING_BRACKETS_STORED:missing_identity:entry_order_id"]
        assert summary.symbol_records[0].unresolved_records == 1

    def test_accepts_pending_brackets_stored_from_daily_wal(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(
            tmp_wal,
            [
                {
                    "rid": "r-stored-1",
                    "op": "EVT",
                    "verb": "PENDING_BRACKETS_STORED",
                    "ts": 1000,
                    "src": "execution_position",
                    "dst": "observability",
                    "pld": {
                        "ts_ms": 1000,
                        "entry_order_id": "entry-1",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "sl": 99.5,
                        "tp": 101.0,
                        "qty": 1.0,
                        "rid": "r-stored-1",
                        "idem_key": "idem-entry-1",
                        "tick_size": 0.1,
                    },
                }
            ],
        )

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 1
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:PENDING_BRACKETS_STORED": 1}
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].identity_keys == [
            "EVT:PENDING_BRACKETS_STORED|BTCUSDT|r-stored-1|entry_order_id|entry-1"
        ]

    def test_accepts_pending_brackets_cleared_from_daily_wal(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(
            tmp_wal,
            [
                {
                    "rid": "r-cleared-1",
                    "op": "EVT",
                    "verb": "PENDING_BRACKETS_CLEARED",
                    "ts": 2000,
                    "src": "execution_position",
                    "dst": "observability",
                    "pld": {
                        "ts_ms": 2000,
                        "entry_order_id": "entry-1",
                        "symbol": "BTCUSDT",
                        "reason": "filled",
                    },
                }
            ],
        )

        summary = replay.replay_w5_bounded_startup_subset(
            symbols_considered=["BTCUSDT"],
        )

        assert summary.records_seen == 1
        assert summary.records_accepted == 1
        assert summary.records_unresolved == 0
        assert summary.event_counts == {"EVT:PENDING_BRACKETS_CLEARED": 1}
        assert summary.restore_boundary_separation == "report_only"
        assert summary.authoritative_mutation_attempted is False
        assert summary.symbol_records[0].identity_keys == [
            "EVT:PENDING_BRACKETS_CLEARED|BTCUSDT|r-cleared-1|entry_order_id|entry-1"
        ]


# ─── replay_from_wal ────────────────────────────────────────────────

class TestReplayFromWal:
    def test_replays_all_events(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(tmp_wal, [
            {"rid": "a", "op": "EVT", "verb": "X", "ts": 100},
            {"rid": "b", "op": "EVT", "verb": "Y", "ts": 200},
        ])
        collected: List[Dict[str, Any]] = []
        replay.replay_from_wal(lambda e: collected.append(e))
        assert len(collected) == 2

    def test_from_ts_filter(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(tmp_wal, [
            {"rid": "a", "op": "EVT", "verb": "X", "ts": 100},
            {"rid": "b", "op": "EVT", "verb": "Y", "ts": 200},
            {"rid": "c", "op": "EVT", "verb": "Z", "ts": 300},
        ])
        collected: List[Dict[str, Any]] = []
        replay.replay_from_wal(lambda e: collected.append(e), from_ts=200)
        assert len(collected) == 2
        assert all(e["ts"] >= 200 for e in collected)

    def test_no_wal_dir_does_nothing(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(replay.wal, "WAL_DIR", tmp_path / "nope")
        collected: List[Dict[str, Any]] = []
        replay.replay_from_wal(lambda e: collected.append(e))
        assert collected == []
