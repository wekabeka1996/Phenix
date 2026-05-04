"""Tests for DecisionLedger."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.decision_ledger import DecisionLedger


def test_add_decision(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    rec = ledger.add_decision(
        decision="Use strategy X for regime detection",
        scope="aurora",
        confidence=0.95,
    )
    assert rec.decision_id
    assert rec.status == "active"
    assert rec.confidence == 0.95
    assert rec.schema_version == 1


def test_decision_persists(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    rec = ledger.add_decision(decision="Use 301 bars for warmup")
    loaded = ledger.get_decision(rec.decision_id)
    assert loaded.decision == "Use 301 bars for warmup"
    assert loaded.status == "active"


def test_deprecate_decision(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    rec = ledger.add_decision(decision="Old approach A")
    deprecated = ledger.deprecate(rec.decision_id)
    assert deprecated.status == "deprecated"
    assert deprecated.deprecated_at is not None


def test_supersede_decision(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    old_rec = ledger.add_decision(decision="Old decision")
    new_rec = ledger.add_decision(decision="New decision")
    superseded = ledger.supersede(
        old_rec.decision_id, new_decision_id=new_rec.decision_id)
    assert superseded.status == "superseded"
    assert superseded.superseded_by == new_rec.decision_id


def test_list_active_only(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    r1 = ledger.add_decision(decision="Active decision 1")
    r2 = ledger.add_decision(decision="Active decision 2")
    r3 = ledger.add_decision(decision="Will be deprecated")
    ledger.deprecate(r3.decision_id)

    active = ledger.list_decisions(active_only=True)
    active_ids = [r.decision_id for r in active]
    assert r1.decision_id in active_ids
    assert r2.decision_id in active_ids
    assert r3.decision_id not in active_ids


def test_list_all_decisions(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    ledger.add_decision(decision="D1")
    ledger.add_decision(decision="D2")
    all_decisions = ledger.list_decisions()
    assert len(all_decisions) == 2


def test_decision_not_found(tmp_path):
    ledger = DecisionLedger(root_dir=tmp_path)
    with pytest.raises(KeyError):
        ledger.get_decision("nonexistent")


def test_decision_persists_after_reload(tmp_path):
    ledger1 = DecisionLedger(root_dir=tmp_path)
    rec = ledger1.add_decision(
        decision="Important decision", source_report_ids=["r1"])

    ledger2 = DecisionLedger(root_dir=tmp_path)
    loaded = ledger2.get_decision(rec.decision_id)
    assert loaded.source_report_ids == ["r1"]
