from __future__ import annotations

import csv
from pathlib import Path

import pytest

import calibrators.policy_gates.calibrate_low_vol_cost_floor as calibrator


def test_fee_formula_synthetic_example_matches_required_contract() -> None:
    economics = calibrator.calculate_fee_economics(
        notional=5000.0,
        open_fee_bps=4.0,
        close_fee_bps=4.0,
        target_net_fee_multiple=2.0,
        slippage_buffer_bps=0.0,
    )

    assert economics.round_trip_fee_usd == pytest.approx(4.0)
    assert economics.required_net_usd == pytest.approx(8.0)
    assert economics.required_gross_tp_usd == pytest.approx(12.0)
    assert economics.required_gross_tp_bps == pytest.approx(24.0)


def test_fee_resolver_prefers_cli_then_strategy_then_global() -> None:
    cli = calibrator.resolve_fee_contract(
        cli_open_fee_bps=4.0,
        cli_close_fee_bps=5.0,
        strategy_fee_bps=3.0,
        global_fee_bps=2.0,
        strategy_specific=True,
        acceptance_required=True,
    )
    assert cli.fee_source == calibrator.FEE_SOURCE_CLI
    assert cli.open_fee_bps == pytest.approx(4.0)
    assert cli.close_fee_bps == pytest.approx(5.0)

    strategy = calibrator.resolve_fee_contract(
        cli_open_fee_bps=None,
        cli_close_fee_bps=None,
        strategy_fee_bps=3.0,
        global_fee_bps=2.0,
        strategy_specific=True,
        acceptance_required=True,
    )
    assert strategy.fee_source == calibrator.FEE_SOURCE_STRATEGY
    assert strategy.open_fee_bps == pytest.approx(3.0)
    assert strategy.close_fee_bps == pytest.approx(3.0)

    global_fee = calibrator.resolve_fee_contract(
        cli_open_fee_bps=None,
        cli_close_fee_bps=None,
        strategy_fee_bps=None,
        global_fee_bps=2.0,
        strategy_specific=False,
        acceptance_required=True,
    )
    assert global_fee.fee_source == calibrator.FEE_SOURCE_GLOBAL
    assert global_fee.open_fee_bps == pytest.approx(2.0)
    assert global_fee.close_fee_bps == pytest.approx(2.0)


def test_fee_resolver_fails_closed_for_acceptance_when_no_source_exists() -> None:
    resolution = calibrator.resolve_fee_contract(
        cli_open_fee_bps=None,
        cli_close_fee_bps=None,
        strategy_fee_bps=None,
        global_fee_bps=None,
        strategy_specific=False,
        acceptance_required=True,
    )

    assert resolution.fee_source == calibrator.FEE_SOURCE_UNAVAILABLE
    assert resolution.acceptance_blocked is True
    assert resolution.open_fee_bps is None
    assert resolution.close_fee_bps is None


def test_slippage_contract_does_not_confuse_configured_cap_with_realized() -> None:
    configured_cap = calibrator.resolve_slippage_contract(
        cli_override_bps=None,
        realized_slippage_bps=None,
        configured_cap_bps=25.0,
    )
    assert configured_cap.slippage_bps == pytest.approx(25.0)
    assert configured_cap.slippage_source == calibrator.SLIPPAGE_SOURCE_CONFIGURED_CAP

    realized = calibrator.resolve_slippage_contract(
        cli_override_bps=None,
        realized_slippage_bps=1.5,
        configured_cap_bps=25.0,
    )
    assert realized.slippage_source == calibrator.SLIPPAGE_SOURCE_REALIZED
    assert realized.slippage_bps == pytest.approx(1.5)


def test_direction_confidence_never_uses_regime_confidence_as_substitute() -> None:
    resolution = calibrator.resolve_direction_confidence()

    assert resolution.direction_confidence is None
    assert resolution.direction_confidence_source == "unavailable"


def test_same_bar_collision_is_marked_ambiguous() -> None:
    outcome = calibrator.detect_same_bar_collision(
        side="BUY",
        high_price=103.0,
        low_price=97.0,
        tp_price=102.0,
        sl_price=98.0,
    )

    assert outcome.ambiguous_same_bar is True
    assert outcome.pessimistic_outcome == "stop_loss_first"
    assert outcome.optimistic_outcome == "take_profit_first"


def test_sufficiency_becomes_exploratory_only_when_samples_are_insufficient() -> None:
    verdict = calibrator.evaluate_sufficiency(
        closed_samples=4,
        symbol_counts={"BTCUSDT": 4},
        strategy_counts={"UNKNOWN": 4},
        bucket_counts={"0.80+": 4},
        counterfactual_samples=0,
        min_closed_samples=30,
        min_samples_per_symbol=5,
        min_samples_per_strategy=5,
        min_bucket_samples=10,
        min_counterfactual_samples=10,
    )

    assert verdict.accepted is False
    assert verdict.exploratory_only is True
    assert "closed_samples<30" in verdict.reasons


def test_parse_args_help_mentions_required_artifacts(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        calibrator._parse_args(["--help"])

    help_text = capsys.readouterr().out
    assert "low_vol_trade_dataset.csv" in help_text
    assert "--min-samples-per-symbol" in help_text
    assert "--min-counterfactual-samples" in help_text


def test_cohorts_remain_separated_and_outputs_are_created(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    out_dir = tmp_path / "artifacts"
    logs_dir = tmp_path / "logs"
    data_dir = tmp_path / "data"
    recorder_dir = data_dir / "recorder" / "2026-04-28"

    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    recorder_dir.mkdir(parents=True, exist_ok=True)

    for file_name in (
        "order_log_v1.jsonl",
        "trade_lifecycle.jsonl",
        "regime_confidence_audit_v1.jsonl",
    ):
        (logs_dir / file_name).write_text("", encoding="utf-8")

    (reports_dir / "executed_trades_master.csv").write_text(
        "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n"
        "A1,False,BTCUSDT,BUY,LOW_VOLATILITY,5000,2026-04-28T00:00:00+00:00,closed,,,",
        encoding="utf-8",
    )
    with (reports_dir / "executed_trades_master.csv").open("a", encoding="utf-8") as handle:
        handle.write("OID1,2026-04-28T01:00:00+00:00,5100,12,4,True\n")

    (reports_dir / "rejected_attempts_master.csv").write_text(
        "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n"
        "R1,False,BTCUSDT,BUY,LOW_VOLATILITY,5000,2026-04-28T00:05:00+00:00,rejected,,safety_gate,,,0,0,False\n",
        encoding="utf-8",
    )
    (reports_dir / "order_attempts_master.csv").write_text(
        "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n"
        "U1,True,BTCUSDT,BUY,LOW_VOLATILITY,5000,2026-04-28T00:10:00+00:00,timeout_non_fill,unlinked,,,,0,0,False\n",
        encoding="utf-8",
    )
    (recorder_dir / "BTCUSDT_300.csv").write_text(
        "close,datetime,high,low,open,regime,regime_conf,symbol,tf_sec,timestamp,volume\n"
        "5000,2026-04-28T00:00:00,5050,4950,5000,LOW_VOLATILITY,0.85,BTCUSDT,300,1745798400000,10\n",
        encoding="utf-8",
    )

    result = calibrator.run_calibration(
        calibrator._parse_args(
            [
                "--data-dir",
                str(data_dir),
                "--logs-dir",
                str(logs_dir),
                "--reports-dir",
                str(reports_dir),
                "--out-dir",
                str(out_dir),
                "--regime",
                "LOW_VOLATILITY",
                "--open-fee-bps",
                "4",
                "--close-fee-bps",
                "4",
                "--target-net-fee-multiple",
                "2",
                "--slippage-buffer-bps",
                "2",
                "--skip-bad-rows",
            ]
        )
    )

    output_files = result["outputs"]
    for key in ("dataset", "candidate_json", "candidate_yaml", "inventory_report", "calibration_report"):
        assert Path(output_files[key]).exists()

    with Path(output_files["dataset"]).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert {row["cohort"] for row in rows} == {
        calibrator.COHORT_CLOSED_REAL_TRADE,
        calibrator.COHORT_REJECTED_ATTEMPT,
        calibrator.COHORT_ORDER_ATTEMPT_UNFILLED,
    }
    assert all(row["direction_confidence_source"]
               == "unavailable" for row in rows)


def test_run_calibration_does_not_modify_production_yaml(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_files = [
        repo_root / "config" / "aurora" / "domains.yaml",
        repo_root / "config" / "aurora" / "trading.yaml",
        repo_root / "config" / "aurora" / "strategies" / "md_amr.yaml",
    ]
    before = {path: path.read_text(encoding="utf-8") for path in target_files}

    reports_dir = tmp_path / "reports"
    out_dir = tmp_path / "artifacts"
    logs_dir = tmp_path / "logs"
    data_dir = tmp_path / "data"
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    for file_name in (
        "order_log_v1.jsonl",
        "trade_lifecycle.jsonl",
        "regime_confidence_audit_v1.jsonl",
    ):
        (logs_dir / file_name).write_text("", encoding="utf-8")
    for file_name in (
        "executed_trades_master.csv",
        "rejected_attempts_master.csv",
        "order_attempts_master.csv",
    ):
        (reports_dir / file_name).write_text(
            "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n",
            encoding="utf-8",
        )

    calibrator.run_calibration(
        calibrator._parse_args(
            [
                "--data-dir",
                str(data_dir),
                "--logs-dir",
                str(logs_dir),
                "--reports-dir",
                str(reports_dir),
                "--out-dir",
                str(out_dir),
                "--open-fee-bps",
                "4",
                "--close-fee-bps",
                "4",
                "--slippage-buffer-bps",
                "2",
                "--skip-bad-rows",
            ]
        )
    )

    after = {path: path.read_text(encoding="utf-8") for path in target_files}
    assert before == after


def test_order_log_rejected_rows_add_regime_confidence_without_master_join(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    out_dir = tmp_path / "artifacts"
    logs_dir = tmp_path / "logs"
    data_dir = tmp_path / "data"

    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    (logs_dir / "order_log_v1.jsonl").write_text(
        '{"rid":"aurora_BTCUSDT_1","event_type":"DECISION_INTENT_REJECTED","symbol":"BTCUSDT","side":"BUY","regime":"LOW_VOLATILITY","regime_confidence":0.81,"timestamp":1745798400000,"metadata":{"reject_reason":"SAFETY_GATES_DENY","alias_of":"TRADE_INTENT_REJECTED","canonical_event_family":"TRADE_INTENT_REJECTED"}}\n',
        encoding="utf-8",
    )
    for file_name in ("trade_lifecycle.jsonl", "regime_confidence_audit_v1.jsonl"):
        (logs_dir / file_name).write_text("", encoding="utf-8")
    for file_name in (
        "executed_trades_master.csv",
        "rejected_attempts_master.csv",
        "order_attempts_master.csv",
    ):
        (reports_dir / file_name).write_text(
            "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n",
            encoding="utf-8",
        )

    result = calibrator.run_calibration(
        calibrator._parse_args(
            [
                "--data-dir",
                str(data_dir),
                "--logs-dir",
                str(logs_dir),
                "--reports-dir",
                str(reports_dir),
                "--out-dir",
                str(out_dir),
                "--open-fee-bps",
                "4",
                "--close-fee-bps",
                "4",
                "--slippage-buffer-bps",
                "2",
                "--skip-bad-rows",
            ]
        )
    )

    with Path(result["outputs"]["dataset"]).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    raw_rows = [row for row in rows if row["truth_source"]
                == calibrator.TRUTH_ORDER_LOG]
    assert len(raw_rows) == 1
    assert raw_rows[0]["regime_confidence"] == "0.81"
    assert raw_rows[0]["cohort"] == calibrator.COHORT_REJECTED_ATTEMPT
    assert "raw_order_log_event" in raw_rows[0]["quality_flags"]


def test_run_calibration_filters_non_target_regimes_from_master_and_raw_logs(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    out_dir = tmp_path / "artifacts"
    logs_dir = tmp_path / "logs"
    data_dir = tmp_path / "data"

    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    (logs_dir / "order_log_v1.jsonl").write_text(
        '{"rid":"aurora_BTCUSDT_1","event_type":"DECISION_INTENT_REJECTED","symbol":"BTCUSDT","side":"BUY","regime":"LOW_VOLATILITY","regime_confidence":0.81,"timestamp":1745798400000,"metadata":{"alias_of":"TRADE_INTENT_REJECTED","canonical_event_family":"TRADE_INTENT_REJECTED"}}\n'
        '{"rid":"aurora_ETHUSDT_2","event_type":"DECISION_INTENT_REJECTED","symbol":"ETHUSDT","side":"BUY","regime":"MEAN_REVERSION","regime_confidence":0.77,"timestamp":1745798401000,"metadata":{"alias_of":"TRADE_INTENT_REJECTED","canonical_event_family":"TRADE_INTENT_REJECTED"}}\n',
        encoding="utf-8",
    )
    for file_name in ("trade_lifecycle.jsonl", "regime_confidence_audit_v1.jsonl"):
        (logs_dir / file_name).write_text("", encoding="utf-8")

    (reports_dir / "executed_trades_master.csv").write_text(
        "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n"
        "L1,False,BTCUSDT,BUY,LOW_VOLATILITY,5000,2026-04-28T00:00:00+00:00,closed,,,OID1,2026-04-28T01:00:00+00:00,5100,12,4,True\n"
        "M1,False,ETHUSDT,BUY,MEAN_REVERSION,3000,2026-04-28T00:05:00+00:00,closed,,,OID2,2026-04-28T01:05:00+00:00,3010,5,2,True\n",
        encoding="utf-8",
    )
    for file_name in ("rejected_attempts_master.csv", "order_attempts_master.csv"):
        (reports_dir / file_name).write_text(
            "attempt_id,synthetic_id,symbol,side,regime,intent_price,intent_ts,outcome,confidence,reject_reason,order_instance_id,exit_ts,exit_price,realized_pnl,commission,exact_roundtrip\n",
            encoding="utf-8",
        )

    result = calibrator.run_calibration(
        calibrator._parse_args(
            [
                "--data-dir",
                str(data_dir),
                "--logs-dir",
                str(logs_dir),
                "--reports-dir",
                str(reports_dir),
                "--out-dir",
                str(out_dir),
                "--regime",
                "LOW_VOLATILITY",
                "--open-fee-bps",
                "4",
                "--close-fee-bps",
                "4",
                "--slippage-buffer-bps",
                "2",
                "--skip-bad-rows",
            ]
        )
    )

    with Path(result["outputs"]["dataset"]).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert rows
    assert {row["regime"] for row in rows} == {"LOW_VOLATILITY"}
    assert {row["dataset_id"] for row in rows} == {"L1", "aurora_BTCUSDT_1"}
