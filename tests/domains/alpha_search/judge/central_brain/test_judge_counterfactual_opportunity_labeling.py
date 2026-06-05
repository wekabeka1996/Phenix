from __future__ import annotations

import json
from pathlib import Path

from tests.domains.alpha_search.judge.central_brain.test_judge_shadow_calibration_row_contract import (
    valid_shadow_row,
)
from tools.judge.label_counterfactual_opportunity_outcomes import (
    MarketBar,
    build_labels,
    load_shadow_rows,
    main,
)


def row(**overrides):
    payload = valid_shadow_row().model_dump(mode="json")
    payload["decision_ts_ms"] = 1000
    payload["created_ts_ms"] = 1000
    payload["symbol"] = "BTCUSDT"
    payload["verdict"]["verdict"] = "NO_ENTRY"
    payload["verdict"]["confidence"] = 0.4
    payload["outcome"] = {
        "outcome_status": "NOT_APPLICABLE",
        "outcome_ts_ms": 1100,
        "horizon_sec": 300,
        "gross_pnl_usd": None,
        "net_pnl_usd": None,
        "fees_usd": None,
        "slippage_usd": None,
        "max_favorable_usd": None,
        "max_adverse_usd": None,
        "terminal_status": "DECISION_INTENT_REJECTED",
    }
    payload.update(overrides)
    return valid_shadow_row(**payload)


def bar(ts_ms: int, *, open=100.0, high=101.0, low=99.0, close=100.5, symbol="BTCUSDT"):
    return MarketBar(ts_ms=ts_ms, symbol=symbol, open=open, high=high, low=low, close=close, source_path="fixture.csv")


def first_label(shadow_row, bars, **kwargs):
    labels = build_labels(
        [shadow_row],
        bars_by_symbol={shadow_row.symbol: bars},
        horizons_sec=[300],
        created_ts_ms=2000,
        min_move_usd=kwargs.pop("min_move_usd", 1.0),
        min_move_bps=kwargs.pop("min_move_bps", 0.0),
        **kwargs,
    )
    return labels[0]


def test_buy_missed_opportunity_from_forward_high():
    label = first_label(row(side="BUY"), [bar(1100, high=105.0, low=99.5, close=104.0)])
    assert label.counterfactual.label == "MISSED_OPPORTUNITY_LONG"
    assert label.counterfactual.max_favorable_usd == 5.0


def test_sell_missed_opportunity_from_forward_low():
    label = first_label(row(side="SELL"), [bar(1100, high=100.5, low=95.0, close=96.0)])
    assert label.counterfactual.label == "MISSED_OPPORTUNITY_SHORT"
    assert label.counterfactual.max_favorable_usd == 5.0


def test_buy_avoided_loss_from_adverse_move():
    label = first_label(row(side="BUY"), [bar(1100, high=100.4, low=95.0, close=96.0)])
    assert label.counterfactual.label == "AVOIDED_LOSS_LONG"
    assert label.counterfactual.max_adverse_usd == -5.0


def test_sell_avoided_loss_from_adverse_move():
    label = first_label(row(side="SELL"), [bar(1100, high=105.0, low=99.8, close=104.0)])
    assert label.counterfactual.label == "AVOIDED_LOSS_SHORT"
    assert label.counterfactual.max_adverse_usd == -5.0


def test_neutral_when_move_below_threshold():
    label = first_label(row(side="BUY"), [bar(1100, high=100.5, low=99.8, close=100.1)])
    assert label.counterfactual.label == "NEUTRAL_NO_OPPORTUNITY"


def test_side_unknown_produces_side_unknown_and_no_fake_label():
    label = first_label(row(side="NONE"), [bar(1100, high=105.0, low=95.0)])
    assert label.candidate_side == "UNKNOWN"
    assert label.counterfactual.label == "SIDE_UNKNOWN"
    assert label.counterfactual.net_opportunity_usd is None


def test_missing_market_data_produces_market_data_missing():
    labels = build_labels([row(side="BUY")], bars_by_symbol={}, horizons_sec=[300], created_ts_ms=2000)
    assert labels[0].counterfactual.label == "MARKET_DATA_MISSING"


def test_insufficient_horizon_produces_insufficient_forward_data():
    shadow_row = row(side="BUY")
    labels = build_labels([shadow_row], bars_by_symbol={shadow_row.symbol: [bar(2001)]}, horizons_sec=[1], created_ts_ms=2000)
    assert labels[0].counterfactual.label == "INSUFFICIENT_FORWARD_DATA"


def test_future_bars_before_decision_timestamp_are_ignored():
    label = first_label(row(side="BUY"), [bar(900), bar(1100, high=105.0)])
    assert label.market_data.first_bar_ts_ms == 1100
    assert label.counterfactual.label == "MISSED_OPPORTUNITY_LONG"


def test_reference_price_source_is_explicit():
    label = first_label(row(side="BUY"), [bar(1100, open=100.0, close=101.0, high=104.0)], reference_price_policy="first_bar_close")
    assert label.counterfactual.reference_price == 101.0
    assert label.counterfactual.reference_price_source == "first_bar_close"


def test_fee_slippage_omitted_stays_null_with_reason_code():
    label = first_label(row(side="BUY"), [bar(1100, high=105.0)])
    assert label.counterfactual.estimated_fee_usd is None
    assert label.counterfactual.estimated_slippage_usd is None
    assert "fee_slippage_not_estimated" in label.reason_codes


def test_fee_slippage_explicit_affects_net_opportunity_but_is_diagnostic():
    label = first_label(row(side="BUY"), [bar(1100, high=105.0)], fee_bps=10.0, slippage_bps=5.0)
    assert label.counterfactual.estimated_fee_usd == 0.1
    assert label.counterfactual.estimated_slippage_usd == 0.05
    assert label.counterfactual.net_opportunity_usd == 4.85
    assert label.counterfactual.calculation_basis == "diagnostic_counterfactual_not_realized_pnl"


def test_no_output_field_named_net_pnl_usd():
    label = first_label(row(side="BUY"), [bar(1100, high=105.0)])
    serialized = json.dumps(label.model_dump(mode="json"))
    assert "net_pnl_usd" not in serialized


def test_promotion_allowed_is_always_false():
    label = first_label(row(side="BUY"), [bar(1100, high=105.0)])
    assert label.promotion_allowed is False


def test_input_rows_are_not_mutated():
    shadow_row = row(side="BUY")
    before = shadow_row.model_dump(mode="json")
    first_label(shadow_row, [bar(1100, high=105.0)])
    assert shadow_row.model_dump(mode="json") == before


def test_side_source_reason_code_is_preserved_in_label_diagnostics():
    shadow_row = row(
        side="BUY",
        diagnostics={
            "missing_fields": ["outcome.net_pnl_usd"],
            "join_quality": "RID_EXACT",
            "reason_codes": ["runtime_shadow_unresolved_outcome", "candidate_side_source:strategy_payload.side"],
        },
    )
    label = first_label(shadow_row, [bar(1100, high=105.0)])
    assert label.candidate_side == "BUY"
    assert "candidate_side_source:strategy_payload.side" in label.reason_codes


def test_deterministic_output():
    shadow_row = row(side="BUY")
    labels_a = build_labels([shadow_row], bars_by_symbol={shadow_row.symbol: [bar(1100, high=105.0)]}, horizons_sec=[300], created_ts_ms=2000)
    labels_b = build_labels([shadow_row], bars_by_symbol={shadow_row.symbol: [bar(1100, high=105.0)]}, horizons_sec=[300], created_ts_ms=2000)
    assert [label.model_dump(mode="json") for label in labels_a] == [label.model_dump(mode="json") for label in labels_b]


def test_cli_writes_requested_outputs_only(tmp_path: Path):
    input_path = tmp_path / "rows.jsonl"
    recorder_dir = tmp_path / "recorder" / "2026-01-01"
    recorder_dir.mkdir(parents=True)
    output_path = tmp_path / "out" / "labels.jsonl"
    diagnostics_path = tmp_path / "out" / "summary.json"
    input_path.write_text(json.dumps(row(side="BUY").model_dump(mode="json")) + "\n", encoding="utf-8")
    (recorder_dir / "BTCUSDT_300.csv").write_text(
        "timestamp,datetime,symbol,tf_sec,open,high,low,close\n"
        "1100,fixture,BTCUSDT,300,100,105,99,104\n",
        encoding="utf-8",
    )

    assert main(
        [
            "--input-enriched-jsonl",
            str(input_path),
            "--recorder-root",
            str(tmp_path / "recorder"),
            "--output-jsonl",
            str(output_path),
            "--diagnostics-json",
            str(diagnostics_path),
            "--horizons-sec",
            "300",
            "--min-move-usd",
            "1",
        ]
    ) == 0

    loaded = load_shadow_rows(input_path)
    assert loaded[0].row_id == "shadow-row-1"
    assert output_path.exists()
    assert diagnostics_path.exists()
    assert diagnostics_path.with_suffix(".md").exists()
