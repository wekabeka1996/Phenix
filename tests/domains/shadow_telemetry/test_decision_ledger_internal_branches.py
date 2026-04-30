from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.ledger.decision_outcome_ledger import (
    DecisionOutcomeLedgerSink,
    _PendingDecision,
    _normalize_action,
    _normalize_authority_mode,
    _now_ms,
    _payload_view,
    _safe_float,
    _safe_int,
    _string_alias,
    _to_jsonable,
)
from apps.reference.telemetry.metrics import generate_latest


class _Event:
    def __init__(self, payload: object) -> None:
        self.pld = payload


class _WaitSequence:
    def __init__(self, responses: list[bool]) -> None:
        self._responses = iter(responses)

    def wait(self, _timeout: float) -> bool:
        return next(self._responses)


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    label_fragments = [f'{key}="{value}"' for key, value in labels.items()]
    pattern = re.compile(r" (-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)$")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(fragment in line for fragment in label_fragments):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        match = pattern.search(line)
        if match is not None:
            return float(match.group(1))
    return 0.0


def _make_sink(path: Path, **kwargs: object) -> DecisionOutcomeLedgerSink:
    sink_kwargs = {
        "queue_maxsize": 8,
        "overflow_policy": "fail_closed",
        "enqueue_timeout_ms": 0,
        "shutdown_timeout_ms": 2000,
    }
    sink_kwargs.update(kwargs)
    return DecisionOutcomeLedgerSink(path=path, **sink_kwargs)


def _make_row(decision_id: str) -> DecisionOutcomeLedgerRow:
    return DecisionOutcomeLedgerRow(
        decision_id=decision_id,
        rid=f"RID-{decision_id}",
        symbol="BTCUSDT",
        authority_mode="gated",
        request_ts_ms=1_700_000_000_000,
        response_ts_ms=1_700_000_000_001,
        apply_result="GATED_ALLOW",
        fallback_reason=None,
        terminal_status=DecisionOutcomeTerminalStatus.VETOED,
        realized_pnl_net=None,
        fees=None,
        stress_metrics={},
        support_quality={},
        dataset_visibility="trainable",
        invalid_reason_code=None,
        causal_state_snapshot={},
        neocortex_action="ALLOW",
        data_quality_flags={},
    )


def _causal_snapshot() -> dict[str, object]:
    return {
        "event_time_source": "aurora_event",
        "event_time_is_causal": True,
        "trainable": True,
        "dataset_visibility": "trainable",
        "state_vector": [0.1],
    }


def _make_entry(
    *,
    decision_id: str = "decision-1",
    rid: str = "RID-1",
    authority_mode: str = "gated",
    apply_result: str | None = "GATED_ALLOW",
    fallback_reason: str | None = None,
    neocortex_action: str = "ALLOW",
    support_quality: dict[str, object] | None = None,
    expires_at_ms: int = 2_000,
    downstream_rid: str | None = None,
    lifecycle_id: str | None = None,
    trade_id: str | None = None,
) -> _PendingDecision:
    return _PendingDecision(
        decision_id=decision_id,
        rid=rid,
        symbol="BTCUSDT",
        authority_mode=authority_mode,
        request_ts_ms=1_700_000_000_000,
        response_ts_ms=1_700_000_000_001,
        apply_result=apply_result,
        fallback_reason=fallback_reason,
        causal_state_snapshot={},
        neocortex_action=neocortex_action,
        data_quality_flags={},
        stress_metrics={},
        support_quality={
            "supports_counterfactual_join": True,
            "snapshot_missing": False,
            "has_nan": False,
            "is_stale": False,
            "explicit_request_ts_present": True,
            "explicit_response_ts_present": True,
            "observation_provenance_present": True,
            "observation_provenance_causal": True,
            "observation_time_is_causal": True,
            "observation_trainable": True,
            "observation_dataset_visibility": "trainable",
            **(support_quality or {}),
        },
        expires_at_ms=expires_at_ms,
        downstream_rid=downstream_rid,
        lifecycle_id=lifecycle_id,
        trade_id=trade_id,
    )


def test_helper_serialization_and_normalizer_branches(tmp_path: Path) -> None:
    class _ModelOk:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"value": Decimal("1.5")}

    class _ModelBad:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            raise ValueError("boom")

    path_obj = tmp_path / "decision_ledger_v1.jsonl"

    assert isinstance(_now_ms(), int)
    assert _payload_view({"payload": {"a": 1}}) == {"a": 1}
    assert _payload_view({"pld": {"a": 2}}) == {"a": 2}
    assert _payload_view({"a": 3}) == {"a": 3}
    assert _payload_view(_Event({"a": 4})) == {"a": 4}
    assert _payload_view(_Event(None)) == {}

    assert _to_jsonable(Decimal("1.25")) == "1.25"
    assert _to_jsonable(path_obj) == str(path_obj)
    assert _to_jsonable({"nested": (1, 2)}) == {"nested": [1, 2]}
    assert _to_jsonable(_ModelOk()) == {"value": "1.5"}
    assert isinstance(_to_jsonable(_ModelBad()), str)
    assert isinstance(_to_jsonable(object()), str)

    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float(object()) is None
    assert _safe_float("bad") is None
    assert _safe_float("nan") is None
    assert _safe_float("1.5") == 1.5

    assert _safe_int(None) is None
    assert _safe_int(True) is None
    assert _safe_int(object()) is None
    assert _safe_int("3") == 3
    assert _safe_int("bad") is None

    assert _normalize_action(None) == "FALLBACK"
    assert _normalize_action("deny") == "BLOCK"
    assert _normalize_action("allow") == "ALLOW"

    assert _normalize_authority_mode("enforce") == "gated"
    assert _normalize_authority_mode("shadow") == "shadow"
    assert _normalize_authority_mode("") == "unknown"

    source = {"a": None, "b": " ", "c": "value"}
    assert _string_alias(source, "missing", "a", "b", "c") == "value"
    assert _string_alias({}, "a") is None


def test_sink_start_stop_and_wait_edge_paths(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")

    sink.start()
    writer_thread = sink._writer_thread
    cleanup_thread = sink._cleanup_thread

    sink.start()
    assert sink._writer_thread is writer_thread
    assert sink._cleanup_thread is cleanup_thread

    sink._write_queue.put({"row": 1})
    assert sink.wait_until_idle(timeout_sec=0.0) is False
    _ = sink._write_queue.get_nowait()
    sink._write_queue.task_done()

    sink.stop()
    sink.stop()


def test_sink_stop_drains_queued_rows_without_shutdown_failure(tmp_path: Path) -> None:
    reset_failure_outcomes()
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = _make_sink(ledger_path)

    sink.start()
    assert sink._enqueue_row(_make_row("decision-drain")) is True
    assert sink.wait_until_idle(timeout_sec=2.0) is True

    sink.stop()

    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[0]["decision_id"] == "decision-drain"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN,
    ) == 0


def test_sink_stop_records_undrained_shutdown_when_rows_remain(tmp_path: Path) -> None:
    reset_failure_outcomes()
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = _make_sink(ledger_path, shutdown_timeout_ms=1)
    metric_before = _metric_value(
        "neocortex_ledger_shutdown_undrained_total",
        reason_code="UNCLEAN_SHUTDOWN",
    )

    assert sink._enqueue_row(_make_row("decision-undrained")) is True

    sink.stop()

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN,
    ) == 1
    assert _metric_value(
        "neocortex_ledger_shutdown_undrained_total",
        reason_code="UNCLEAN_SHUTDOWN",
    ) == metric_before + 1.0


def test_sink_stop_records_async_forced_stop_when_owned_threads_survive(tmp_path: Path) -> None:
    class _AliveThread:
        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    reset_failure_outcomes()
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl",
                      shutdown_timeout_ms=1)
    metric_before = _metric_value(
        "neocortex_async_forced_stop_total",
        component="decision_outcome_ledger",
        reason_code="UNCLEAN_SHUTDOWN",
    )
    sink._writer_thread = _AliveThread()  # type: ignore[assignment]
    sink._cleanup_thread = _AliveThread()  # type: ignore[assignment]

    sink.stop()

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN,
    ) == 1
    assert _metric_value(
        "neocortex_async_forced_stop_total",
        component="decision_outcome_ledger",
        reason_code="UNCLEAN_SHUTDOWN",
    ) == metric_before + 1.0


def test_flush_expired_skips_unexpired_entry_and_pending_lookup_paths(tmp_path: Path) -> None:
    sink = _make_sink(
        tmp_path / "decision_ledger_v1.jsonl",
        clock_ms_fn=lambda: 1_000,
    )
    entry = _make_entry(expires_at_ms=2_000)

    with sink._lock:
        sink._pending_by_decision_id[entry.decision_id] = entry
        sink._register_alias_locked(entry, rid=entry.rid)

    assert sink.flush_expired(now_ms=1_500) == 0
    assert sink._get_pending_by_decision_id("missing") is None
    assert sink._get_pending_by_decision_id(entry.decision_id) is entry


def test_cleanup_loop_records_degraded_observability_on_flush_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_failure_outcomes()
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")

    monkeypatch.setattr(sink, "_stop_event", _WaitSequence([False, True]))
    monkeypatch.setattr(sink, "flush_expired",
                        MagicMock(side_effect=OSError("disk")))

    sink._cleanup_loop()

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.TELEMETRY_FLUSH_FAILED,
    ) == 1


def test_shadow_decision_logged_and_trade_intent_guard_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")

    sink._on_shadow_decision_logged(
        {"decision_id": "decision-missing-symbol", "rid": "RID-MISSING"})
    assert sink._pending_by_decision_id == {}

    sink._on_trade_intent_proposed(
        {
            "authority_context": {"decision_id": "decision-unknown"},
            "lifecycle_id": "LIFE-UNKNOWN",
        }
    )

    entry = _make_entry()
    with sink._lock:
        sink._pending_by_decision_id[entry.decision_id] = entry
        sink._register_alias_locked(entry, rid=entry.rid)

    sink._on_trade_intent_proposed(
        {"rid": entry.rid, "lifecycle_id": "LIFE-1"})
    assert entry.lifecycle_id == "LIFE-1"

    sink._on_trade_intent_proposed(
        {
            "authority_context": {"decision_id": entry.decision_id},
            "lifecycle_id": "LIFE-2",
        }
    )
    assert entry.lifecycle_id == "LIFE-1"

    orphan_entry = _make_entry(decision_id="decision-orphan")
    monkeypatch.setattr(sink, "_find_matching_entry",
                        lambda payload, pop=False: (orphan_entry, None))
    sink._on_trade_intent_proposed({"rid": "RID-ORPHAN"})


def test_execution_enrichment_guard_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")

    sink._on_execution_enrichment("EVT:OTHER", {"rid": "RID-1"})
    sink._on_execution_enrichment("EVT:TRADE_EXECUTED", {"rid": "RID-MISSING"})

    orphan_entry = _make_entry(decision_id="decision-orphan")
    monkeypatch.setattr(sink, "_find_matching_entry",
                        lambda payload, pop=False: (orphan_entry, None))
    sink._on_execution_enrichment("EVT:TRADE_EXECUTED", {"rid": "RID-ORPHAN"})


def test_time_coercion_and_authority_mode_fallback_paths(tmp_path: Path) -> None:
    sink = _make_sink(
        tmp_path / "decision_ledger_v1.jsonl",
        clock_ms_fn=lambda: 777,
    )

    assert sink._coerce_request_ts_ms(
        {"request_ts_ms": "bad", "decision_ts_ms": 5}) == 5
    assert sink._coerce_request_ts_ms({}) == 777

    assert sink._coerce_response_ts_ms(
        {"response_ts_ms": "bad", "decision_ts_ms": 5}, 3) == 5
    assert sink._coerce_response_ts_ms({}, 7) == 7

    assert sink._resolve_authority_mode(
        {"authority_mode": "enforce"}, {}) == "gated"
    assert sink._resolve_authority_mode(
        {}, {"apply_result": "GATED_ALLOW"}) == "gated"
    assert sink._resolve_authority_mode(
        {}, {"apply_result": "ADVISORY_RECORDED"}) == "advisory"
    assert sink._resolve_authority_mode(
        {}, {"apply_result": "SHADOW_ALLOW"}) == "shadow"
    assert sink._resolve_authority_mode(
        {}, {"apply_result": "MANUAL_ALLOW"}) == "unknown"
    assert sink._resolve_authority_mode({}, {}) == "unknown"


def test_classify_terminal_event_extra_paths(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")

    invalid_entry = _make_entry()
    assert sink._classify_terminal_event("EVT:POSITION_CLOSED", {}, invalid_entry) == (
        DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
        "UNJOINABLE_LIFECYCLE",
    )

    fallback_entry = _make_entry(
        apply_result="FALLBACK_BASELINE",
        fallback_reason="BASELINE_UNAVAILABLE",
        neocortex_action="FALLBACK",
    )
    assert sink._classify_terminal_event(
        "EVT:DECISION_BLOCKED",
        {"reason_code": "NOT_VETO"},
        fallback_entry,
    ) == (DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_NO_EXECUTION, None)


def test_extract_terminal_values_and_dataset_visibility_extra_paths(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")
    entry = _make_entry()

    assert sink._extract_terminal_values(
        "EVT:ORDER_REJECTED",
        {},
        entry,
        DecisionOutcomeTerminalStatus.REJECTED_UPSTREAM,
    ) == (None, None)

    assert sink._extract_terminal_values(
        "EVT:POSITION_CLOSED",
        {"fees": 0.5},
        entry,
        DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
    ) == (None, 0.5)

    locked_entry = _make_entry(
        decision_id="decision-locked",
        rid="RID-LOCKED",
        downstream_rid="RID-DOWNSTREAM-LOCKED",
    )
    assert sink._extract_terminal_values(
        "EVT:POSITION_CLOSED",
        {
            "rid": "RID-NEW",
            "lifecycle_id": "LIFE-NEW",
            "trade_id": "TRADE-NEW",
        },
        locked_entry,
        DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
    ) == (None, None)
    assert locked_entry.downstream_rid == "RID-DOWNSTREAM-LOCKED"
    assert locked_entry.lifecycle_id == "LIFE-NEW"
    assert locked_entry.trade_id == "TRADE-NEW"

    assert sink._dataset_visibility(
        entry, DecisionOutcomeTerminalStatus.VETOED, "BAD") == "diagnostics_only"
    assert sink._dataset_visibility(
        _make_entry(authority_mode="unknown"),
        DecisionOutcomeTerminalStatus.VETOED,
        None,
    ) == "diagnostics_only"
    assert sink._dataset_visibility(
        _make_entry(),
        DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
        None,
    ) == "diagnostics_only"
    assert sink._dataset_visibility(
        _make_entry(support_quality={"snapshot_missing": True}),
        DecisionOutcomeTerminalStatus.VETOED,
        None,
    ) == "diagnostics_only"
    assert sink._dataset_visibility(
        _make_entry(support_quality={"has_nan": True}),
        DecisionOutcomeTerminalStatus.VETOED,
        None,
    ) == "diagnostics_only"
    assert sink._dataset_visibility(
        _make_entry(support_quality={"is_stale": True}),
        DecisionOutcomeTerminalStatus.VETOED,
        None,
    ) == "diagnostics_only"


def test_missing_request_timestamp_cannot_yield_trainable_row(tmp_path: Path) -> None:
    sink = _make_sink(
        tmp_path / "decision_ledger_v1.jsonl",
        clock_ms_fn=lambda: 777,
    )
    sink._on_shadow_decision_logged(
        {
            "decision_id": "decision-missing-request",
            "rid": "RID-MISSING-REQUEST",
            "symbol": "BTCUSDT",
            "response_ts_ms": 999,
            "authority_mode": "gated",
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "causal_state_snapshot": _causal_snapshot(),
            "data_quality_flags": {
                "supports_counterfactual_join": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
            },
        }
    )

    entry = sink._get_pending_by_decision_id("decision-missing-request")
    assert entry is not None
    row = sink._build_row(
        entry,
        terminal_status=DecisionOutcomeTerminalStatus.VETOED,
        invalid_reason_code=None,
        realized_pnl_net=None,
        fees=None,
        joined_by="decision_id",
    )

    assert row.request_ts_ms == 999
    assert row.dataset_visibility == "diagnostics_only"
    assert row.invalid_reason_code == FailureReasonCode.MISSING_REQUIRED_STATE.value


def test_missing_response_timestamp_cannot_yield_trainable_row(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")
    sink._on_shadow_decision_logged(
        {
            "decision_id": "decision-missing-response",
            "rid": "RID-MISSING-RESPONSE",
            "symbol": "BTCUSDT",
            "request_ts_ms": 500,
            "authority_mode": "gated",
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "causal_state_snapshot": _causal_snapshot(),
            "data_quality_flags": {
                "supports_counterfactual_join": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
            },
        }
    )

    entry = sink._get_pending_by_decision_id("decision-missing-response")
    assert entry is not None
    row = sink._build_row(
        entry,
        terminal_status=DecisionOutcomeTerminalStatus.VETOED,
        invalid_reason_code=None,
        realized_pnl_net=None,
        fees=None,
        joined_by="decision_id",
    )

    assert row.response_ts_ms == 500
    assert row.dataset_visibility == "diagnostics_only"
    assert row.invalid_reason_code == FailureReasonCode.MISSING_REQUIRED_STATE.value


def test_clock_fallback_is_ordering_only_not_trainable_admission(tmp_path: Path) -> None:
    sink = _make_sink(
        tmp_path / "decision_ledger_v1.jsonl",
        clock_ms_fn=lambda: 777,
    )
    sink._on_shadow_decision_logged(
        {
            "decision_id": "decision-clock-fallback",
            "rid": "RID-CLOCK-FALLBACK",
            "symbol": "BTCUSDT",
            "authority_mode": "gated",
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "causal_state_snapshot": _causal_snapshot(),
            "data_quality_flags": {
                "supports_counterfactual_join": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
            },
        }
    )

    entry = sink._get_pending_by_decision_id("decision-clock-fallback")
    assert entry is not None
    assert entry.request_ts_ms == 777
    row = sink._build_row(
        entry,
        terminal_status=DecisionOutcomeTerminalStatus.VETOED,
        invalid_reason_code=None,
        realized_pnl_net=None,
        fees=None,
        joined_by="decision_id",
    )

    assert row.dataset_visibility == "diagnostics_only"
    assert row.invalid_reason_code == FailureReasonCode.MISSING_REQUIRED_STATE.value


def test_explicit_causal_timestamps_preserve_trainable_row(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")
    sink._on_shadow_decision_logged(
        {
            "decision_id": "decision-explicit-trainable",
            "rid": "RID-EXPLICIT-TRAINABLE",
            "symbol": "BTCUSDT",
            "request_ts_ms": 500,
            "response_ts_ms": 550,
            "authority_mode": "gated",
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "causal_state_snapshot": _causal_snapshot(),
            "data_quality_flags": {
                "supports_counterfactual_join": True,
                "snapshot_missing": False,
                "has_nan": False,
                "is_stale": False,
            },
        }
    )

    entry = sink._get_pending_by_decision_id("decision-explicit-trainable")
    assert entry is not None
    row = sink._build_row(
        entry,
        terminal_status=DecisionOutcomeTerminalStatus.VETOED,
        invalid_reason_code=None,
        realized_pnl_net=None,
        fees=None,
        joined_by="decision_id",
    )

    assert row.dataset_visibility == "trainable"
    assert row.invalid_reason_code is None


def test_find_matching_entry_lifecycle_trade_and_stale_alias_cleanup(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")
    entry = _make_entry(decision_id="decision-match")

    with sink._lock:
        sink._pending_by_decision_id[entry.decision_id] = entry
        sink._decision_id_by_rid["STALE-RID"] = "missing"
        sink._register_alias_locked(
            entry, lifecycle_id="LIFE-1", trade_id="TRADE-1")
        sink._decision_id_by_lifecycle_id["STALE-LIFE"] = "missing"
        sink._decision_id_by_trade_id["STALE-TRADE"] = "missing"

    matched, joined_by = sink._find_matching_entry(
        {"lifecycle_id": "LIFE-1"}, pop=False)
    assert matched is entry
    assert joined_by == "lifecycle_id"

    matched, joined_by = sink._find_matching_entry(
        {"lifecycle_id": "UNKNOWN-LIFE", "trade_id": "TRADE-1"},
        pop=False,
    )
    assert matched is entry
    assert joined_by == "trade_id"

    matched, joined_by = sink._find_matching_entry(
        {"lifecycle_id": "STALE-LIFE"}, pop=False)
    assert matched is None
    assert joined_by is None
    assert "STALE-LIFE" not in sink._decision_id_by_lifecycle_id

    matched, joined_by = sink._find_matching_entry(
        {"rid": "STALE-RID"}, pop=False)
    assert matched is None
    assert joined_by is None
    assert "STALE-RID" not in sink._decision_id_by_rid

    matched, joined_by = sink._find_matching_entry(
        {"trade_id": "STALE-TRADE"}, pop=False)
    assert matched is None
    assert joined_by is None
    assert "STALE-TRADE" not in sink._decision_id_by_trade_id

    assert sink._find_matching_entry({}, pop=False) == (None, None)
    assert sink._find_matching_entry(
        {"trade_id": "UNKNOWN-TRADE"}, pop=False) == (None, None)


def test_pending_lookup_none_decision_id_returns_none(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")
    assert sink._get_pending_by_decision_id(None) is None


def test_register_alias_locked_preserves_existing_identity_fields(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl")
    entry = _make_entry(
        decision_id="decision-existing",
        rid="RID-EXISTING",
        downstream_rid="DOWNSTREAM-ORIG",
        lifecycle_id="LIFE-ORIG",
        trade_id="TRADE-ORIG",
    )

    with sink._lock:
        sink._register_alias_locked(
            entry, rid="RID-NEW", lifecycle_id="LIFE-NEW", trade_id="TRADE-NEW")

    assert entry.downstream_rid == "DOWNSTREAM-ORIG"
    assert entry.lifecycle_id == "LIFE-ORIG"
    assert entry.trade_id == "TRADE-ORIG"
    assert sink._decision_id_by_rid["RID-NEW"] == entry.decision_id
    assert sink._decision_id_by_lifecycle_id["LIFE-NEW"] == entry.decision_id
    assert sink._decision_id_by_trade_id["TRADE-NEW"] == entry.decision_id

    entry_noop = _make_entry(decision_id="decision-noop", rid="RID-NOOP")
    with sink._lock:
        sink._register_alias_locked(entry_noop)
        sink._register_alias_locked(
            entry_noop, rid="", lifecycle_id="", trade_id="")

    assert "" not in sink._decision_id_by_rid
    assert "" not in sink._decision_id_by_lifecycle_id
    assert "" not in sink._decision_id_by_trade_id


def test_sink_queue_is_bounded_by_constructor_contract(tmp_path: Path) -> None:
    sink = _make_sink(tmp_path / "decision_ledger_v1.jsonl", queue_maxsize=7)

    assert sink._write_queue.maxsize == 7


def test_fail_closed_queue_overflow_is_explicit_and_counted(tmp_path: Path) -> None:
    reset_failure_outcomes()
    ledger_path = tmp_path / "decision_ledger_v1.jsonl"
    sink = _make_sink(ledger_path, queue_maxsize=1, enqueue_timeout_ms=0)
    metric_before = _metric_value(
        "neocortex_ledger_queue_dropped_total",
        policy="fail_closed",
        reason_code="TELEMETRY_FLUSH_FAILED",
    )

    assert sink._enqueue_row(_make_row("decision-1")) is True
    assert sink._enqueue_row(_make_row("decision-2")) is False

    assert sink._write_queue.qsize() == 1
    assert _metric_value("neocortex_ledger_queue_depth") == 1.0
    assert _metric_value(
        "neocortex_ledger_queue_dropped_total",
        policy="fail_closed",
        reason_code="TELEMETRY_FLUSH_FAILED",
    ) == metric_before + 1.0
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.TELEMETRY_FLUSH_FAILED,
    ) == 1
    assert not ledger_path.exists()
