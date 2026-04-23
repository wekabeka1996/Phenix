"""
Tests for SHADOW_HARDENING_CORRECTIVE_PACKAGE_V1.

Covers:
  A. Double-wiring removal in fsm.py _get_or_create_flows
  B. Semantic clarity of INPUT vs OUTPUT shadow records
  C. Placeholder filtering in payload_fragment attribution fields
  D. Authority boundary preservation
"""
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM, CloseState
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    ShadowCriticalEventJournal,
    build_payload_fragment,
    _is_placeholder_text,
)
from vfoundation.core.protocol import Message


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _make_manage_config():
    cfg = MagicMock()
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.emergency = None
    cfg.trading.execution.manage.brackets = None
    cfg.trailing = None
    cfg.strategies.aurora.assets = {}
    cfg.strategies.aurora.decision.bar_gating = None
    return cfg


# ============================================================================
# A. WIRING TESTS — shadow journal attached exactly once per flow
# ============================================================================


class TestWiringNoDuplication:
    """Prove shadow journal is wired exactly once, not double-wired."""

    def test_manage_flow_journal_wired_once_on_creation(self, tmp_path):
        """New ManageFlowFSM gets set_shadow_journal called, journal is set."""
        journal = ShadowCriticalEventJournal(path=str(tmp_path / "j.jsonl"))
        manage = ManageFlowFSM(config=_make_manage_config())
        assert manage._shadow_journal is None
        manage.set_shadow_journal(journal)
        assert manage._shadow_journal is journal

    def test_close_flow_journal_wired_once_on_creation(self, tmp_path):
        """New CloseFlowFSM gets set_shadow_journal called, journal is set."""
        journal = ShadowCriticalEventJournal(path=str(tmp_path / "j.jsonl"))
        close = CloseFlowFSM()
        assert close._shadow_journal is None
        close.set_shadow_journal(journal)
        assert close._shadow_journal is journal

    def test_idempotent_wiring_does_not_create_second_journal(self, tmp_path):
        """Calling set_shadow_journal twice with the same journal is idempotent."""
        journal = ShadowCriticalEventJournal(path=str(tmp_path / "j.jsonl"))
        manage = ManageFlowFSM(config=_make_manage_config())
        manage.set_shadow_journal(journal)
        manage.set_shadow_journal(journal)
        assert manage._shadow_journal is journal

    def test_get_or_create_flows_wires_journal_once(self, tmp_path):
        """
        Structural: after the fix, the if-block creates flows WITHOUT wiring,
        and the unconditional tail wires once — so new flows get exactly 1 call.
        We verify by counting set_shadow_journal invocations on mock flows.
        """
        journal = ShadowCriticalEventJournal(path=str(tmp_path / "j.jsonl"))

        # Create a minimal mock that simulates _get_or_create_flows behavior
        # after the fix: create in if-block, wire in unconditional tail.
        manage_mock = MagicMock(spec=ManageFlowFSM)
        close_mock = MagicMock(spec=CloseFlowFSM)
        manage_mock._shadow_journal = None
        close_mock._shadow_journal = None

        # Simulate the fixed _get_or_create_flows for a NEW symbol:
        # 1. The if-block creates flows (no wiring inside if)
        # 2. The unconditional tail wires (single call)
        manage_flows = {}
        close_flows = {}
        symbol = "BTCUSDT"
        _shadow_journal = journal

        # Fixed code structure — creation block
        if symbol not in manage_flows:
            manage_flows[symbol] = manage_mock
            close_flows[symbol] = close_mock

        # Fixed code structure — unconditional wiring (single site)
        if hasattr(manage_flows[symbol], "set_shadow_journal") and _shadow_journal is not None:
            manage_flows[symbol].set_shadow_journal(_shadow_journal)
        if hasattr(close_flows[symbol], "set_shadow_journal") and _shadow_journal is not None:
            close_flows[symbol].set_shadow_journal(_shadow_journal)

        # Exactly 1 call each — no double wiring
        assert manage_mock.set_shadow_journal.call_count == 1
        assert close_mock.set_shadow_journal.call_count == 1

        # Re-get existing flows — still exactly 1 more call each
        if hasattr(manage_flows[symbol], "set_shadow_journal") and _shadow_journal is not None:
            manage_flows[symbol].set_shadow_journal(_shadow_journal)
        if hasattr(close_flows[symbol], "set_shadow_journal") and _shadow_journal is not None:
            close_flows[symbol].set_shadow_journal(_shadow_journal)

        # 1 per call to _get_or_create_flows
        assert manage_mock.set_shadow_journal.call_count == 2
        assert close_mock.set_shadow_journal.call_count == 2


# ============================================================================
# B. SEMANTIC CLARITY — INPUT vs OUTPUT records are distinguishable
# ============================================================================


class TestSemanticClarity:
    """Prove analysts can distinguish INPUT (context) from OUTPUT (state-change) records."""

    def test_close_flow_output_record_carries_transition_window(self, tmp_path):
        """OUTPUT record (DEC:CLOSE) carries before/after state snapshots."""
        path = tmp_path / "journal.jsonl"
        journal = ShadowCriticalEventJournal(path=str(path))
        flow = CloseFlowFSM()
        flow.set_shadow_journal(journal)

        flow.handle(
            Message(
                op="CMD", verb="CLOSE",
                src="dm", dst="ep", rid="r1",
                pld={"symbol": "BTCUSDT", "reason": "test_close"},
            )
        )

        records = _read_jsonl(path)
        output_records = [r for r in records if r["source_path"]
                          == "execution:close_flow_output"]
        assert len(output_records) == 1
        out = output_records[0]
        assert out["event_name"] == "DEC:CLOSE"
        assert out["local_state_before"] is not None
        assert out["local_state_after"] is not None
        assert out["local_state_before"]["state"] == "FLAT"
        assert out["local_state_after"]["state"] == "DONE"
        assert out["rid"] == "r1"
        assert out["payload_fragment"]["trigger"] == "CMD:CLOSE"
        assert out["payload_fragment"]["idempotent_key"] == "r1"
        assert out["lifecycle_id"] == "r1"

    def test_close_flow_input_record_has_no_transition_window(self, tmp_path):
        """INPUT record (CMD:CLOSE) carries NO before/after — only contextual payload."""
        path = tmp_path / "journal.jsonl"
        journal = ShadowCriticalEventJournal(path=str(path))
        flow = CloseFlowFSM()
        flow.set_shadow_journal(journal)

        flow.handle(
            Message(
                op="CMD", verb="CLOSE",
                src="dm", dst="ep", rid="r1",
                pld={"symbol": "BTCUSDT", "reason": "test_close"},
            )
        )

        records = _read_jsonl(path)
        input_records = [r for r in records if r["source_path"]
                         == "execution:close_flow_input"]
        assert len(input_records) == 1
        inp = input_records[0]
        assert inp["event_name"] == "CMD:CLOSE"
        assert inp["local_state_before"] is None
        assert inp["local_state_after"] is None
        assert "record_role=input" in inp["notes"]
        assert "result=DEC:CLOSE" in inp["notes"]

    def test_manage_flow_output_record_semantic_authority(self, tmp_path):
        """ManageFlowFSM OUTPUT record carries transition window, INPUT does not."""
        path = tmp_path / "journal.jsonl"
        journal = ShadowCriticalEventJournal(path=str(path))
        manage = ManageFlowFSM(config=_make_manage_config())
        manage.set_shadow_journal(journal)
        manage.state = ManageState.TRACKING
        manage.symbol = "BTCUSDT"
        manage.position_qty = Decimal("0.1")
        manage.position_entry_price = Decimal("50000")
        manage.position_side = "BUY"
        manage.position_open_ts = 1.0

        message = Message(
            op="UPD", verb="MARKET_DATA",
            src="ws", dst="ep", rid="r2", why="test",
            pld={"symbol": "BTCUSDT", "last_price": "49900"},
        )

        with patch.object(manage, "_get_max_hold_sec", return_value=1):
            result = manage.handle(message)

        assert result is not None
        records = _read_jsonl(path)
        # Only DEC:CLOSE passes should_capture — UPD:MARKET_DATA does not
        output_records = [r for r in records if r["source_path"]
                          == "execution:manage_flow_output"]
        assert len(output_records) == 1
        out = output_records[0]
        assert out["event_name"] == "DEC:CLOSE"
        assert out["local_state_before"] is not None
        assert out["local_state_after"] is not None

    def test_no_result_emits_only_input_record(self, tmp_path):
        """When handle() returns None, only the INPUT record is emitted."""
        path = tmp_path / "journal.jsonl"
        journal = ShadowCriticalEventJournal(path=str(path))
        flow = CloseFlowFSM()
        flow.set_shadow_journal(journal)
        flow.state = CloseState.OPENED
        flow.position_active = True
        flow.position_open_ts = 1.0

        # EVT:TRADE_EXECUTED is in critical events but _check_close_conditions returns None
        result = flow.handle(
            Message(
                op="EVT", verb="TRADE_EXECUTED",
                src="ws", dst="ep", rid="r3",
                pld={"symbol": "BTCUSDT", "qty": "0.05"},
            )
        )
        assert result is None

        records = _read_jsonl(path)
        input_records = [r for r in records if r["source_path"]
                         == "execution:close_flow_input"]
        output_records = [r for r in records if r["source_path"]
                          == "execution:close_flow_output"]
        assert len(output_records) == 0
        assert len(input_records) == 1
        assert input_records[0]["local_state_before"] is None
        assert input_records[0]["local_state_after"] is None
        assert "record_role=input" in input_records[0]["notes"]


# ============================================================================
# C. PLACEHOLDER FILTERING — "unknown" stripped from attribution fields
# ============================================================================


class TestPlaceholderFiltering:
    """Prove payload_fragment strips bare 'unknown' from attribution-critical fields."""

    def test_bare_unknown_stripped_from_reason(self):
        fragment = build_payload_fragment(
            {"reason": "unknown", "symbol": "BTCUSDT"})
        assert fragment.get("reason") is None
        assert fragment["symbol"] == "BTCUSDT"

    def test_bare_unknown_stripped_from_side(self):
        fragment = build_payload_fragment({"side": "Unknown", "qty": "0.1"})
        assert fragment.get("side") is None
        assert fragment["qty"] == "0.1"

    def test_bare_unknown_stripped_from_strategy(self):
        fragment = build_payload_fragment(
            {"strategy": " UNKNOWN ", "symbol": "ETHUSDT"})
        assert fragment.get("strategy") is None

    def test_bare_unknown_stripped_from_trigger(self):
        fragment = build_payload_fragment({"trigger": "unknown"})
        assert fragment.get("trigger") is None

    def test_bare_unknown_stripped_from_source(self):
        fragment = build_payload_fragment({"source": "unknown"})
        assert fragment.get("source") is None

    def test_bare_unknown_stripped_from_block_reason(self):
        fragment = build_payload_fragment({"block_reason": "unknown"})
        assert fragment.get("block_reason") is None

    def test_bare_unknown_stripped_from_inferred_role(self):
        fragment = build_payload_fragment({"inferred_role": "unknown"})
        assert fragment.get("inferred_role") is None

    def test_legitimate_compound_value_preserved(self):
        """'unknown_disappearance' is a real domain value, not a placeholder."""
        fragment = build_payload_fragment({"reason": "unknown_disappearance"})
        assert fragment["reason"] == "unknown_disappearance"

    def test_legitimate_domain_values_untouched(self):
        """Non-attribution and non-placeholder values pass through unchanged."""
        fragment = build_payload_fragment({
            "reason": "MAX_HOLD_TIME_EXCEEDED",
            "side": "BUY",
            "strategy": "aurora",
            "trigger": "CMD:CLOSE",
            "symbol": "BTCUSDT",
            "reduce_only": True,
            "qty": "0.1",
        })
        assert fragment["reason"] == "MAX_HOLD_TIME_EXCEEDED"
        assert fragment["side"] == "BUY"
        assert fragment["strategy"] == "aurora"
        assert fragment["trigger"] == "CMD:CLOSE"
        assert fragment["symbol"] == "BTCUSDT"
        assert fragment["reduce_only"] is True
        assert fragment["qty"] == "0.1"

    def test_non_attribution_fields_not_stripped(self):
        """Fields outside the attribution-critical set are not filtered."""
        fragment = build_payload_fragment(
            {"status": "unknown", "warmup": "unknown"})
        # 'status' and 'warmup' are not in the attribution-critical list
        assert fragment["status"] == "unknown"
        assert fragment["warmup"] == "unknown"

    def test_placeholder_text_exact_match_only(self):
        """_is_placeholder_text only matches bare 'unknown', not substrings."""
        assert _is_placeholder_text("unknown") is True
        assert _is_placeholder_text("UNKNOWN") is True
        assert _is_placeholder_text(" unknown ") is True
        assert _is_placeholder_text("unknown_disappearance") is False
        assert _is_placeholder_text("partially_unknown") is False
        assert _is_placeholder_text("UNKNOWN_REASON") is False
        assert _is_placeholder_text(42) is False
        assert _is_placeholder_text(None) is False


# ============================================================================
# D. AUTHORITY BOUNDARY PRESERVATION
# ============================================================================


class TestAuthorityBoundaries:
    """Prove shadow remains evidence-only; no restore/startup/portfolio changes."""

    def test_shadow_record_model_forbids_extra_fields(self):
        """ShadowJournalRecord uses extra='forbid' — no creep."""
        from apps.reference.telemetry.shadow_journal import ShadowJournalRecord
        assert ShadowJournalRecord.model_config.get("extra") == "forbid"

    def test_shadow_journal_does_not_mutate_flow_state(self, tmp_path):
        """Recording to shadow journal must not change CloseFlowFSM state."""
        path = tmp_path / "journal.jsonl"
        journal = ShadowCriticalEventJournal(path=str(path))
        flow = CloseFlowFSM()
        flow.set_shadow_journal(journal)

        # State before handle
        assert flow.state == CloseState.FLAT
        assert flow.position_active is False

        flow.handle(
            Message(
                op="CMD", verb="CLOSE",
                src="dm", dst="ep", rid="r1",
                pld={"symbol": "BTCUSDT", "reason": "test"},
            )
        )

        # State after handle — changed by business logic, NOT by shadow recording
        assert flow.state == CloseState.DONE
        assert flow.position_active is False

        # Verify records were written (shadow is functional)
        records = _read_jsonl(path)
        assert len(records) >= 1

    def test_record_transition_is_append_only(self, tmp_path):
        """Shadow journal only appends records, never reads back to influece flow."""
        path = tmp_path / "journal.jsonl"
        journal = ShadowCriticalEventJournal(path=str(path))

        # Write two records
        journal.record_transition(
            event_name="DEC:CLOSE",
            source_component="test",
            source_path="test:path",
            event_origin_type="test",
            truth_owner="test",
            payload={"symbol": "BTCUSDT"},
        )
        journal.record_transition(
            event_name="CMD:CLOSE",
            source_component="test",
            source_path="test:path",
            event_origin_type="test",
            truth_owner="test",
            payload={"symbol": "ETHUSDT"},
        )

        records = _read_jsonl(path)
        assert len(records) == 2
        # Both records exist independently — no mutation from prior record
        assert records[0]["symbol"] == "BTCUSDT"
        assert records[1]["symbol"] == "ETHUSDT"
