from __future__ import annotations

import json
from pathlib import Path

from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (
    to_phase8_calibration_row,
)
from tools.judge.build_testnet_shadow_calibration_dataset import (
    build_shadow_calibration_rows,
    load_jsonl,
    write_rows,
)


def verdict(**overrides):
    payload = {
        "verdict_id": "verdict-1",
        "envelope_id": "env-1",
        "decision_id": "decision-1",
        "rid": "rid-1",
        "lifecycle_id": "life-1",
        "created_ts_ms": 1000,
        "decision_ts_ms": 1000,
        "symbol": "BTCUSDT",
        "verdict": "OPEN_LONG",
        "confidence": 0.82,
        "authority_status": "shadow_only",
        "applied": False,
        "regime_label": "TREND_UP",
        "regime_confidence": 0.8,
    }
    payload.update(overrides)
    return payload


def envelope(**overrides):
    payload = {
        "envelope_id": "env-1",
        "symbol": "BTCUSDT",
        "regime_label": "TREND_UP",
        "regime_confidence": 0.8,
    }
    payload.update(overrides)
    return payload


def bridge(**overrides):
    payload = {
        "bridge_decision_id": "bridge-1",
        "source_verdict_id": "verdict-1",
        "decision_id": "decision-1",
        "rid": "rid-1",
        "authority_mode": "shadow",
        "bridge_action": "record_only",
        "applied": False,
        "no_effect": True,
    }
    payload.update(overrides)
    return payload


def outcome(**overrides):
    payload = {
        "decision_id": "decision-1",
        "rid": "rid-1",
        "lifecycle_id": "life-1",
        "symbol": "BTCUSDT",
        "outcome_ts_ms": 2000,
        "horizon_sec": 300,
        "gross_pnl_usd": 1.3,
        "net_pnl_usd": 1.0,
        "fees_usd": 0.2,
        "slippage_usd": 0.1,
        "terminal_status": "closed",
    }
    payload.update(overrides)
    return payload


def build(**kwargs):
    return build_shadow_calibration_rows(
        verdict_rows=kwargs.get("verdict_rows", [verdict()]),
        envelope_rows=kwargs.get("envelope_rows", [envelope()]),
        bridge_rows=kwargs.get("bridge_rows", [bridge()]),
        lifecycle_rows=kwargs.get("lifecycle_rows", [outcome()]),
        source_kind="replay",
        horizon_sec=300,
        join_mode=kwargs.get("join_mode", "exact"),
        allow_unresolved=kwargs.get("allow_unresolved", False),
    )


def test_exact_decision_id_join_builds_resolved_row():
    rows, diagnostics = build()
    assert diagnostics == []
    assert rows[0].diagnostics.join_quality == "EXACT"
    assert rows[0].outcome.outcome_status == "RESOLVED"


def test_rid_join_builds_resolved_row():
    rows, _ = build(
        verdict_rows=[verdict(decision_id=None, lifecycle_id=None)],
        lifecycle_rows=[outcome(decision_id=None, lifecycle_id=None)],
    )
    assert rows[0].source_refs.rid == "rid-1"
    assert rows[0].diagnostics.join_quality == "RID_EXACT"
    assert rows[0].outcome.net_pnl_usd == 1.0


def test_lifecycle_id_join_builds_resolved_row():
    rows, _ = build(
        verdict_rows=[verdict(decision_id=None, rid=None)],
        lifecycle_rows=[outcome(decision_id=None, rid=None)],
    )
    assert rows[0].source_refs.lifecycle_id == "life-1"
    assert rows[0].outcome.outcome_status == "RESOLVED"


def test_unmatched_with_allow_unresolved_creates_unresolved_row():
    rows, diagnostics = build(lifecycle_rows=[], allow_unresolved=True)
    assert diagnostics == []
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert rows[0].diagnostics.join_quality == "UNJOINED"


def test_unmatched_without_allow_unresolved_is_reported_and_dropped():
    rows, diagnostics = build(lifecycle_rows=[])
    assert rows == []
    assert diagnostics[0]["reason"] == "unjoined_outcome_dropped"


def test_fuzzy_join_requires_explicit_mode():
    v = verdict(decision_id=None, rid=None, lifecycle_id=None, decision_ts_ms=1000)
    o = outcome(decision_id=None, rid=None, lifecycle_id=None, outcome_ts_ms=1500)
    rows, diagnostics = build(verdict_rows=[v], lifecycle_rows=[o], allow_unresolved=False)
    assert rows == []
    assert diagnostics
    rows, _ = build(verdict_rows=[v], lifecycle_rows=[o], join_mode="fuzzy")
    assert rows[0].diagnostics.join_quality == "FUZZY"
    assert "joined_by_fuzzy_window" in rows[0].diagnostics.reason_codes


def test_no_future_outcome_before_decision_ts():
    rows, diagnostics = build(lifecycle_rows=[outcome(outcome_ts_ms=999)])
    assert rows == []
    assert diagnostics[0]["reason"] == "future_leakage_outcome_before_decision"


def test_unresolved_economics_excluded_from_calibration_conversion():
    rows, _ = build(lifecycle_rows=[outcome(net_pnl_usd=None)], allow_unresolved=True)
    converted = to_phase8_calibration_row(rows[0])
    assert converted.outcome.net_pnl_usd is None


def test_deterministic_output_order(tmp_path: Path):
    rows, _ = build(
        verdict_rows=[
            verdict(verdict_id="b", decision_id="b", rid="b"),
            verdict(verdict_id="a", decision_id="a", rid="a"),
        ],
        lifecycle_rows=[
            outcome(decision_id="a", rid="a", net_pnl_usd=1.0),
            outcome(decision_id="b", rid="b", net_pnl_usd=2.0),
        ],
    )
    assert [row.verdict.verdict_id for row in rows] == ["a", "b"]
    out = tmp_path / "rows.jsonl"
    write_rows(rows, out)
    loaded = load_jsonl([out])
    assert [item["verdict"]["verdict_id"] for item in loaded] == ["a", "b"]


def test_jsonl_loader_reads_objects(tmp_path: Path):
    path = tmp_path / "verdicts.jsonl"
    path.write_text(json.dumps(verdict()) + "\n", encoding="utf-8")
    assert load_jsonl([path])[0]["verdict_id"] == "verdict-1"


def test_jsonl_loader_unwraps_event_payloads(tmp_path: Path):
    path = tmp_path / "verdicts.jsonl"
    path.write_text(
        json.dumps({"event_name": "EVT:JUDGE_POLICY_VERDICT_EMITTED_V2", "payload": verdict()}) + "\n",
        encoding="utf-8",
    )
    assert load_jsonl([path])[0]["verdict_id"] == "verdict-1"
