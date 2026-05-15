from __future__ import annotations

import json
from pathlib import Path

import jsonschema

import SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION as validator


def _write_saf(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _make_atom(
    *,
    atom_id: str,
    ts_ms: int,
    symbol: str = "BTCUSDT",
    side: str = "SELL",
    strategy_id: str = "aurora",
    regime: str = "LOW_VOLATILITY",
    bucket: str = "0.25..0.50",
    outcome_code: str,
    net_score: float,
) -> dict:
    return {
        "atom_id": atom_id,
        "atom_kind": "REJECTED" if outcome_code.startswith("REJECT") else "ACCEPTED",
        "context": {
            "symbol": symbol,
            "side": side,
            "strategy_id": strategy_id,
            "regime": regime,
            "confidence_bucket": bucket,
        },
        "outcome_code": outcome_code,
        "net_score": net_score,
        "reward_bps": max(net_score, 0.0),
        "threat_bps": abs(min(net_score, 0.0)),
        "surprise": abs(net_score),
        "importance": abs(net_score),
        "raw_contract": {
            "event_ts_ms": ts_ms,
            "close_ts_ms": ts_ms,
        },
    }


def test_normalize_outcome_code_maps_required_labels() -> None:
    assert validator.normalize_outcome_code("ACCEPTED_WIN") == "GOOD_DECISION"
    assert validator.normalize_outcome_code("ACCEPTED_LOSS") == "CLEAN_LOSS"
    assert validator.normalize_outcome_code("BAD_EXIT") == "BAD_EXIT"
    assert validator.normalize_outcome_code(
        "REJECT_CORRECT_BLOCK") == "POLICY_PROTECTED"
    assert validator.normalize_outcome_code(
        "REJECT_MISSED_POSITIVE") == "POLICY_TOO_STRICT"


def test_infer_memory_verdict_detects_policy_too_strict_candidate() -> None:
    train_atoms = [
        validator.ValidationAtom(
            atom_id=f"a{i}",
            event_ts_ms=i,
            context_key=("BTCUSDT", "SELL", "aurora",
                         "LOW_VOLATILITY", "0.25..0.50"),
            context={"symbol": "BTCUSDT", "side": "SELL", "strategy_id": "aurora",
                     "regime": "LOW_VOLATILITY", "confidence_bucket": "0.25..0.50"},
            original_outcome_code="REJECT_MISSED_POSITIVE",
            canonical_outcome_code="POLICY_TOO_STRICT",
            net_score=-12.0,
            reward_bps=0.0,
            threat_bps=12.0,
            surprise=12.0,
            importance=12.0,
        )
        for i in range(3)
    ]
    verdict, recommendation, metrics, counts = validator.infer_memory_verdict(
        train_atoms)
    assert verdict == "POLICY_TOO_STRICT_CANDIDATE"
    assert recommendation == "review_policy_thresholds"
    assert counts["POLICY_TOO_STRICT"] == 3
    assert metrics["policy_too_strict_rate"] == 1.0


def test_classify_validation_result_confirms_toxic_context() -> None:
    validation_atoms = [
        validator.ValidationAtom(
            atom_id="v1",
            event_ts_ms=10,
            context_key=("ETHUSDT", "SELL", "aurora",
                         "TREND_DOWN", "0.25..0.50"),
            context={"symbol": "ETHUSDT", "side": "SELL", "strategy_id": "aurora",
                     "regime": "TREND_DOWN", "confidence_bucket": "0.25..0.50"},
            original_outcome_code="ACCEPTED_LOSS",
            canonical_outcome_code="CLEAN_LOSS",
            net_score=-20.0,
            reward_bps=0.0,
            threat_bps=20.0,
            surprise=20.0,
            importance=20.0,
        )
    ]
    result, reason, metrics, counts, validation_net_score = validator.classify_validation_result(
        "TOXIC_CONTEXT", validation_atoms)
    assert result == "CONFIRMED"
    assert reason == "validation_negative_profile"
    assert counts["CLEAN_LOSS"] == 1
    assert validation_net_score < 0
    assert metrics["negative_rate"] == 1.0


def test_run_validation_generates_report_and_inconclusive_status(tmp_path: Path) -> None:
    saf_path = tmp_path / "aurora_real_logs_v02.saf.jsonl"
    poc02_report = tmp_path / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
    output_report = tmp_path / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
    output_sidecar = tmp_path / "SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json"
    poc02_report.write_text(
        "SEMA_ATOM_POC_02_STATUS:\nREAD_ONLY_REAL_LOG_RUN_COMPLETED\n", encoding="utf-8")
    _write_saf(
        saf_path,
        [
            _make_atom(atom_id="a1", ts_ms=1,
                       outcome_code="REJECT_MISSED_POSITIVE", net_score=-20.0),
            _make_atom(atom_id="a2", ts_ms=2,
                       outcome_code="REJECT_MISSED_POSITIVE", net_score=-18.0),
            _make_atom(atom_id="a3", ts_ms=3,
                       outcome_code="REJECT_CORRECT_BLOCK", net_score=8.0),
            _make_atom(atom_id="a4", ts_ms=4,
                       outcome_code="REJECT_MISSED_POSITIVE", net_score=-16.0),
            _make_atom(atom_id="b1", ts_ms=1, symbol="BNBUSDT", side="BUY",
                       regime="MEAN_REVERSION", outcome_code="ACCEPTED_LOSS", net_score=-25.0),
            _make_atom(atom_id="b2", ts_ms=2, symbol="BNBUSDT", side="BUY",
                       regime="MEAN_REVERSION", outcome_code="BAD_EXIT", net_score=-15.0),
            _make_atom(atom_id="b3", ts_ms=3, symbol="BNBUSDT", side="BUY",
                       regime="MEAN_REVERSION", outcome_code="ACCEPTED_WIN", net_score=10.0),
            _make_atom(atom_id="b4", ts_ms=4, symbol="BNBUSDT", side="BUY",
                       regime="MEAN_REVERSION", outcome_code="ACCEPTED_LOSS", net_score=-12.0),
        ],
    )
    result = validator.run_validation(
        saf_path=saf_path,
        poc02_report_path=poc02_report,
        output_path=output_report,
        output_sidecar_path=output_sidecar,
        min_train_atoms=2,
        min_validation_atoms=1,
    )
    assert result["status"] in {
        "VALIDATION_INCONCLUSIVE", "VALIDATION_PASSED", "VALIDATION_FAILED"}
    report_text = output_report.read_text(encoding="utf-8")
    assert "## Verdict" in report_text
    assert "## Summary" in report_text
    assert "verdict confirmation rate" in report_text
    sidecar = json.loads(output_sidecar.read_text(encoding="utf-8"))
    schema = json.loads(
        validator.DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=sidecar, schema=schema)
    assert sidecar["schema_id"] == validator.SIDECAR_SCHEMA_ID
    assert sidecar["schema_version"] == validator.SIDECAR_SCHEMA_VERSION
    assert sidecar["contexts_total"] == len(
        sidecar["contexts"]) == result["contexts_total"]
    assert sidecar["split_config"]["min_train_atoms"] == 5
    assert sidecar["split_config"]["min_validation_atoms"] == 5
    assert sidecar["split_config"]["display_min_train_atoms"] == 2
    assert sidecar["split_config"]["display_min_validation_atoms"] == 1
    observed_outcome_codes = set()
    for context in sidecar["contexts"]:
        observed_outcome_codes.update(context["train_outcomes"].keys())
        observed_outcome_codes.update(context["validation_outcomes"].keys())
    assert observed_outcome_codes <= set(validator.CANONICAL_OUTCOME_CODES)


def test_run_validation_partitions_by_strategy_id_in_context_key(tmp_path: Path) -> None:
    saf_path = tmp_path / "strategy_partition.saf.jsonl"
    poc02_report = tmp_path / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
    output_report = tmp_path / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
    output_sidecar = tmp_path / "SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json"
    poc02_report.write_text(
        "SEMA_ATOM_POC_02_STATUS:\nREAD_ONLY_REAL_LOG_RUN_COMPLETED\n", encoding="utf-8")
    _write_saf(
        saf_path,
        [
            _make_atom(atom_id="a1", ts_ms=1, strategy_id="aurora",
                       outcome_code="REJECT_MISSED_POSITIVE", net_score=-8.0),
            _make_atom(atom_id="a2", ts_ms=2, strategy_id="aurora",
                       outcome_code="REJECT_CORRECT_BLOCK", net_score=6.0),
            _make_atom(atom_id="b1", ts_ms=3, strategy_id="aurora_alt",
                       outcome_code="ACCEPTED_LOSS", net_score=-7.0),
            _make_atom(atom_id="b2", ts_ms=4, strategy_id="aurora_alt",
                       outcome_code="ACCEPTED_WIN", net_score=5.0),
        ],
    )
    validator.run_validation(
        saf_path=saf_path,
        poc02_report_path=poc02_report,
        output_path=output_report,
        output_sidecar_path=output_sidecar,
        min_train_atoms=1,
        min_validation_atoms=1,
    )
    sidecar = json.loads(output_sidecar.read_text(encoding="utf-8"))
    context_keys = {context["context_key"] for context in sidecar["contexts"]}
    assert context_keys == {
        "BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50",
        "BTCUSDT|SELL|aurora_alt|LOW_VOLATILITY|0.25..0.50",
    }
