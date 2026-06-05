from __future__ import annotations

import json
from pathlib import Path

from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (
    to_phase8_calibration_row,
)
from tests.domains.alpha_search.judge.central_brain.test_judge_shadow_calibration_row_contract import (
    valid_shadow_row,
)
from tools.judge.enrich_shadow_calibration_outcomes import (
    enrich_shadow_rows,
    load_shadow_rows,
    main,
)
from tools.judge.label_counterfactual_opportunity_outcomes import MarketBar, build_labels


def unresolved_row(**source_overrides):
    row = valid_shadow_row().model_dump(mode="json")
    row["outcome"] = {
        "outcome_status": "UNRESOLVED",
        "outcome_ts_ms": None,
        "horizon_sec": 300,
        "gross_pnl_usd": None,
        "net_pnl_usd": None,
        "fees_usd": None,
        "slippage_usd": None,
        "max_favorable_usd": None,
        "max_adverse_usd": None,
        "terminal_status": None,
    }
    row["diagnostics"] = {
        "missing_fields": ["outcome.net_pnl_usd"],
        "join_quality": "UNJOINED",
        "reason_codes": ["runtime_shadow_unresolved_outcome"],
    }
    row["source_refs"].update(source_overrides)
    return valid_shadow_row(**row)


def outcome(**overrides):
    payload = {
        "decision_id": "decision-1",
        "rid": "rid-1",
        "lifecycle_id": "life-1",
        "symbol": "BTCUSDT",
        "close_ts_ms": 2000,
        "horizon_sec": 300,
        "gross_pnl_usd": 1.4,
        "net_pnl_usd": 1.1,
        "fees_usd": 0.2,
        "slippage_usd": 0.1,
        "status": "CLOSED",
    }
    payload.update(overrides)
    return payload


def no_side_row(**source_overrides):
    payload = unresolved_row(**source_overrides).model_dump(mode="json")
    payload["side"] = "NONE"
    return valid_shadow_row(**payload)


def test_decision_id_exact_join_resolves_outcome():
    rows, diagnostics = enrich_shadow_rows([unresolved_row()], lifecycle_rows=[outcome()])
    assert diagnostics == []
    assert rows[0].diagnostics.join_quality == "EXACT"
    assert "joined_by_decision_id" in rows[0].diagnostics.reason_codes
    assert rows[0].outcome.outcome_status == "RESOLVED"
    assert rows[0].outcome.net_pnl_usd == 1.1
    assert "joined_to_closed_with_net_pnl" in rows[0].diagnostics.reason_codes


def test_lifecycle_id_exact_join_resolves_outcome():
    row = unresolved_row(decision_id=None, rid=None, lifecycle_id="life-1")
    rows, _ = enrich_shadow_rows(
        [row],
        lifecycle_rows=[outcome(decision_id=None, rid=None)],
    )
    assert rows[0].diagnostics.join_quality == "EXACT"
    assert "joined_by_lifecycle_id" in rows[0].diagnostics.reason_codes


def test_rid_exact_join_marks_rid_exact():
    row = unresolved_row(decision_id=None, lifecycle_id=None, rid="rid-1")
    rows, _ = enrich_shadow_rows(
        [row],
        lifecycle_rows=[outcome(decision_id=None, lifecycle_id=None)],
    )
    assert rows[0].diagnostics.join_quality == "RID_EXACT"
    assert "joined_by_rid" in rows[0].diagnostics.reason_codes


def test_rid_join_prefers_terminal_pnl_over_earlier_intent():
    row = unresolved_row(decision_id=None, lifecycle_id=None, rid="rid-1")
    rows, _ = enrich_shadow_rows(
        [row],
        lifecycle_rows=[
            outcome(decision_id=None, lifecycle_id=None, event_type="ORDER_INTENT", net_pnl_usd=None, close_ts_ms=1500),
            outcome(
                decision_id=None,
                lifecycle_id="rid-1",
                event_type="POSITION_CLOSED",
                realized_pnl_net=-2.5,
                fees_usd=None,
                fees=0.4,
                net_pnl_usd=None,
                close_ts_ms=2500,
            ),
        ],
    )
    assert rows[0].diagnostics.join_quality == "RID_EXACT"
    assert rows[0].outcome.outcome_status == "RESOLVED"
    assert rows[0].outcome.net_pnl_usd == -2.5
    assert rows[0].outcome.fees_usd == 0.4


def test_unjoined_row_stays_unresolved():
    rows, _ = enrich_shadow_rows([unresolved_row()], lifecycle_rows=[])
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert rows[0].diagnostics.join_quality == "UNJOINED"


def test_fuzzy_join_requires_explicit_flag():
    row = unresolved_row(decision_id=None, lifecycle_id=None, rid=None)
    lifecycle = outcome(decision_id=None, lifecycle_id=None, rid=None, close_ts_ms=1100)
    rows, _ = enrich_shadow_rows([row], lifecycle_rows=[lifecycle])
    assert rows[0].diagnostics.join_quality == "UNJOINED"
    rows, _ = enrich_shadow_rows([row], lifecycle_rows=[lifecycle], allow_fuzzy=True)
    assert rows[0].diagnostics.join_quality == "FUZZY"


def test_future_outcome_before_decision_is_rejected():
    rows, diagnostics = enrich_shadow_rows(
        [unresolved_row()],
        lifecycle_rows=[outcome(close_ts_ms=999)],
    )
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert rows[0].diagnostics.join_quality == "UNJOINED"
    assert diagnostics[0]["reason"] == "future_leakage_outcome_before_decision"


def test_missing_net_pnl_keeps_outcome_unresolved():
    rows, _ = enrich_shadow_rows(
        [unresolved_row()],
        lifecycle_rows=[outcome(event_type="POSITION_CLOSED", net_pnl_usd=None, metadata={}, status=None)],
    )
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert rows[0].outcome.net_pnl_usd is None
    assert "joined_to_closed_missing_net_pnl" in rows[0].diagnostics.reason_codes


def test_gross_fallback_is_explicit():
    row = unresolved_row()
    lifecycle = outcome(
        event_type="POSITION_CLOSED",
        net_pnl_usd=None,
        realized_pnl_net=None,
        gross_pnl_usd=3.2,
        metadata={},
    )
    rows, _ = enrich_shadow_rows([row], lifecycle_rows=[lifecycle])
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert rows[0].outcome.net_pnl_usd is None
    assert "gross_pnl_fallback_used" not in rows[0].diagnostics.reason_codes

    rows, _ = enrich_shadow_rows([row], lifecycle_rows=[lifecycle], gross_pnl_fallback=True)
    assert rows[0].outcome.outcome_status == "RESOLVED"
    assert rows[0].outcome.net_pnl_usd == 3.2
    assert "gross_pnl_fallback_used" in rows[0].diagnostics.reason_codes


def test_rejected_no_trade_does_not_get_fake_net_pnl():
    rows, _ = enrich_shadow_rows(
        [unresolved_row()],
        lifecycle_rows=[
            outcome(
                event_type="DECISION_INTENT_REJECTED",
                status="REJECTED",
                net_pnl_usd=None,
                gross_pnl_usd=None,
                close_ts_ms=2001,
                metadata={"alias_of": "TRADE_INTENT_REJECTED"},
            )
        ],
    )
    assert rows[0].outcome.outcome_status == "NOT_APPLICABLE"
    assert rows[0].outcome.net_pnl_usd is None
    assert "outcome.net_pnl_usd" not in rows[0].diagnostics.missing_fields
    assert "joined_to_rejected_no_trade" in rows[0].diagnostics.reason_codes


def test_ordered_open_without_close_economics_remains_unresolved():
    rows, _ = enrich_shadow_rows(
        [unresolved_row()],
        lifecycle_rows=[
            outcome(
                event_type="ORDER_PLACED",
                status="ORDERED",
                net_pnl_usd=None,
                gross_pnl_usd=None,
                metadata={},
            )
        ],
    )
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert "joined_to_ordered_missing_close_economics" in rows[0].diagnostics.reason_codes


def test_entry_fill_realized_pnl_metadata_is_not_net_pnl():
    rows, _ = enrich_shadow_rows(
        [unresolved_row()],
        lifecycle_rows=[
            outcome(
                event_type="ORDER_FILLED",
                status="FILLED",
                net_pnl_usd=None,
                gross_pnl_usd=None,
                metadata={"realized_pnl": 0.0},
            )
        ],
    )
    assert rows[0].outcome.outcome_status == "UNRESOLVED"
    assert rows[0].outcome.net_pnl_usd is None
    assert "joined_to_ordered_missing_close_economics" in rows[0].diagnostics.reason_codes


def test_lifecycle_join_outranks_rid_join():
    row = unresolved_row(decision_id=None, lifecycle_id="life-1", rid="rid-1")
    rows, _ = enrich_shadow_rows(
        [row],
        lifecycle_rows=[
            outcome(decision_id=None, lifecycle_id=None, rid="rid-1", net_pnl_usd=-99.0),
            outcome(decision_id=None, lifecycle_id="life-1", rid="other-rid", net_pnl_usd=4.4),
        ],
    )
    assert rows[0].diagnostics.join_quality == "EXACT"
    assert rows[0].outcome.net_pnl_usd == 4.4


def test_order_id_exact_join_resolves_outcome():
    row = unresolved_row(decision_id=None, lifecycle_id=None, rid=None, order_id="order-1")
    rows, _ = enrich_shadow_rows(
        [row],
        order_rows=[outcome(decision_id=None, lifecycle_id=None, rid=None, order_id="order-1", net_pnl_usd=-1.25)],
    )
    assert rows[0].diagnostics.join_quality == "EXACT"
    assert rows[0].outcome.net_pnl_usd == -1.25


def test_side_recovered_from_critical_journal_strategy_signal_by_rid():
    rows, _ = enrich_shadow_rows(
        [no_side_row(decision_id=None, lifecycle_id=None, rid="rid-1")],
        critical_rows=[
            {
                "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
                "rid": "rid-1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "ts_ms": 1100,
            }
        ],
    )
    assert rows[0].side == "SELL"
    assert "side_source:critical_journal_strategy_signal" in rows[0].diagnostics.reason_codes


def test_side_recovered_from_trade_lifecycle_by_rid_if_critical_absent():
    rows, _ = enrich_shadow_rows(
        [no_side_row(decision_id=None, lifecycle_id=None, rid="rid-1")],
        lifecycle_rows=[{"event_type": "TRADE_LIFECYCLE_ORDERED", "rid": "rid-1", "side": "LONG", "ts_ms": 1100}],
    )
    assert rows[0].side == "BUY"
    assert "side_source:trade_lifecycle" in rows[0].diagnostics.reason_codes


def test_side_recovered_from_order_log_when_explicit():
    rows, _ = enrich_shadow_rows(
        [no_side_row(decision_id=None, lifecycle_id=None, rid="rid-1")],
        order_rows=[{"event_type": "ORDER_INTENT", "rid": "rid-1", "side": "SELL", "timestamp": 1100}],
    )
    assert rows[0].side == "SELL"
    assert "side_source:order_log" in rows[0].diagnostics.reason_codes


def test_side_conflict_keeps_unknown_and_records_reason():
    rows, _ = enrich_shadow_rows(
        [no_side_row(decision_id=None, lifecycle_id=None, rid="rid-1")],
        critical_rows=[
            {"event_name": "EVT:STRATEGY_SIGNAL_PRODUCED", "rid": "rid-1", "side": "BUY"},
            {"event_name": "EVT:STRATEGY_SIGNAL_PRODUCED", "rid": "rid-1", "side": "SELL"},
        ],
    )
    assert rows[0].side == "UNKNOWN"
    assert "side_conflict" in rows[0].diagnostics.reason_codes


def test_side_conflict_across_sources_keeps_unknown_and_records_reason():
    rows, _ = enrich_shadow_rows(
        [no_side_row(decision_id=None, lifecycle_id=None, rid="rid-1")],
        critical_rows=[
            {"event_name": "EVT:STRATEGY_SIGNAL_PRODUCED", "rid": "rid-1", "side": "BUY"},
        ],
        order_rows=[
            {"event_type": "ORDER_INTENT", "rid": "rid-1", "side": "SELL", "timestamp": 1100},
        ],
    )
    assert rows[0].side == "UNKNOWN"
    assert "side_conflict" in rows[0].diagnostics.reason_codes
    assert any(code.startswith("side_conflict_sources:") for code in rows[0].diagnostics.reason_codes)


def test_no_side_inference_from_rid_in_enrichment():
    rows, _ = enrich_shadow_rows([no_side_row(decision_id=None, lifecycle_id=None, rid="rid_SELL_1")])
    assert rows[0].side == "NONE"
    assert "side_unresolved" in rows[0].diagnostics.reason_codes


def test_recovered_side_allows_counterfactual_directional_label():
    rows, _ = enrich_shadow_rows(
        [no_side_row(decision_id=None, lifecycle_id=None, rid="rid-1")],
        critical_rows=[{"event_name": "EVT:STRATEGY_SIGNAL_PRODUCED", "rid": "rid-1", "side": "BUY"}],
    )
    labels = build_labels(
        rows,
        bars_by_symbol={
            "BTCUSDT": [MarketBar(ts_ms=1100, symbol="BTCUSDT", open=100.0, high=105.0, low=99.0, close=104.0, source_path="fixture")]
        },
        horizons_sec=[300],
        created_ts_ms=2000,
        min_move_usd=1.0,
    )
    assert labels[0].candidate_side == "BUY"
    assert labels[0].counterfactual.label == "MISSED_OPPORTUNITY_LONG"


def test_enriched_row_converts_to_phase8_calibration_row():
    rows, _ = enrich_shadow_rows([unresolved_row()], lifecycle_rows=[outcome()])
    converted = to_phase8_calibration_row(rows[0])
    assert converted.outcome.net_pnl_usd == 1.1
    assert converted.source_refs.lifecycle_id == "life-1"


def test_cli_writes_only_requested_outputs_and_keeps_inputs(tmp_path: Path):
    input_path = tmp_path / "shadow.jsonl"
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    output_path = tmp_path / "out" / "enriched.jsonl"
    diagnostics_path = tmp_path / "out" / "diagnostics.json"
    original_input = json.dumps(unresolved_row().model_dump(mode="json"), sort_keys=True) + "\n"
    original_lifecycle = json.dumps(outcome(), sort_keys=True) + "\n"
    input_path.write_text(original_input, encoding="utf-8")
    lifecycle_path.write_text(original_lifecycle, encoding="utf-8")

    assert main(
        [
            "--input-shadow-jsonl",
            str(input_path),
            "--trade-lifecycle-jsonl",
            str(lifecycle_path),
            "--output-jsonl",
            str(output_path),
            "--diagnostics-json",
            str(diagnostics_path),
        ]
    ) == 0

    assert input_path.read_text(encoding="utf-8") == original_input
    assert lifecycle_path.read_text(encoding="utf-8") == original_lifecycle
    assert output_path.exists()
    assert diagnostics_path.exists()
    loaded = load_shadow_rows(output_path)
    assert loaded[0].outcome.outcome_status == "RESOLVED"
