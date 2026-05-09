from __future__ import annotations

import json
from pathlib import Path

import SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION as poc04


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _make_atom(*, atom_id: str, ts_ms: int, outcome_code: str, post_move_bps: float) -> dict:
    return {
        "atom_id": atom_id,
        "atom_kind": "REJECTED",
        "context": {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "strategy_id": "aurora",
            "regime": "LOW_VOLATILITY",
            "confidence_bucket": "0.25..0.50",
        },
        "outcome_code": outcome_code,
        "net_score": -abs(post_move_bps) if outcome_code == "REJECT_MISSED_POSITIVE" else abs(post_move_bps),
        "reward_bps": 0.0 if outcome_code == "REJECT_MISSED_POSITIVE" else abs(post_move_bps),
        "threat_bps": abs(post_move_bps) if outcome_code == "REJECT_MISSED_POSITIVE" else 0.0,
        "surprise": abs(post_move_bps),
        "importance": abs(post_move_bps),
        "outcome_snapshot": {
            "post_move_bps": post_move_bps,
            "post_move_horizons": {
                "T+30m": {
                    "future_price": 101.0,
                    "future_ts_ms": ts_ms + 1800000,
                    "post_move_bps": post_move_bps,
                }
            },
        },
        "raw_contract": {
            "event_ts_ms": ts_ms,
            "reference_price": 100.0,
            "entry_price": 100.0,
            "contract_id": atom_id,
            "reject_reason": "LOW_VOL_COST_FLOOR_DENY",
        },
    }


def _write_manifest(path: Path) -> None:
    manifest = {
        "READY_FOR_COUNTERFACTUAL_SIM": [
            {
                "context_id": "BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50",
                "verdict": "POLICY_TOO_STRICT_CANDIDATE",
                "validation_result": "CONFIRMED",
                "train_count": 10,
                "validation_count": 11,
                "train_net_score": -16.0,
                "validation_net_score": -11.0,
                "train_outcomes": {"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 8},
                "validation_outcomes": {"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 8},
            }
        ],
        "PROMISING_LOW_SUPPORT": [],
        "REJECTED_FALSE_POSITIVE": [],
        "INCONCLUSIVE_LOW_POWER": [],
        "CONFIRMED_BUT_UNSTABLE": [],
        "CONFIRMED_BUT_UNCLASSIFIED": [],
        "UNKNOWN": [],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_simulate_policy_too_strict_candidate_returns_positive_net_when_gain_dominates(tmp_path: Path) -> None:
    saf_path = tmp_path / "aurora_real_logs_v02.saf.jsonl"
    manifest_path = tmp_path / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    _write_manifest(manifest_path)
    rows = [
        _make_atom(atom_id="a1", ts_ms=1, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=18.0),
        _make_atom(atom_id="a2", ts_ms=2, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=22.0),
        _make_atom(atom_id="a3", ts_ms=3, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=16.0),
        _make_atom(atom_id="a4", ts_ms=4, outcome_code="REJECT_CORRECT_BLOCK", post_move_bps=-5.0),
        _make_atom(atom_id="a5", ts_ms=5, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=30.0),
        _make_atom(atom_id="a6", ts_ms=6, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=35.0),
    ]
    _write_jsonl(saf_path, rows)
    validation_by_context = poc04._load_validation_atoms_by_context(saf_path)
    ctx = json.loads(manifest_path.read_text(encoding="utf-8"))["READY_FOR_COUNTERFACTUAL_SIM"][0]
    result = poc04.simulate_policy_too_strict_candidate(
        context_record=ctx,
        validation_atoms=validation_by_context[("BTCUSDT", "BUY", "aurora", "LOW_VOLATILITY", "0.25..0.50")],
        saf_path=saf_path,
    )
    assert result is not None
    assert result.policy_too_strict_count >= 2
    assert result.policy_protected_count >= 1
    assert result.opportunity_gain_raw_bps > result.added_loss_risk_raw_bps


def test_run_generates_report(tmp_path: Path) -> None:
    saf_path = tmp_path / "aurora_real_logs_v02.saf.jsonl"
    manifest_path = tmp_path / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    poc03_report = tmp_path / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
    poc02_report = tmp_path / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
    output_report = tmp_path / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md"
    _write_manifest(manifest_path)
    _write_jsonl(
        saf_path,
        [
            _make_atom(atom_id="a1", ts_ms=1, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=18.0),
            _make_atom(atom_id="a2", ts_ms=2, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=22.0),
            _make_atom(atom_id="a3", ts_ms=3, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=16.0),
            _make_atom(atom_id="a4", ts_ms=4, outcome_code="REJECT_CORRECT_BLOCK", post_move_bps=-5.0),
            _make_atom(atom_id="a5", ts_ms=5, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=30.0),
            _make_atom(atom_id="a6", ts_ms=6, outcome_code="REJECT_MISSED_POSITIVE", post_move_bps=35.0),
        ],
    )
    poc03_report.write_text("report", encoding="utf-8")
    poc02_report.write_text("report", encoding="utf-8")
    result = poc04.run(
        manifest_path=manifest_path,
        saf_path=saf_path,
        poc03_report_path=poc03_report,
        poc02_report_path=poc02_report,
        output_report_path=output_report,
    )
    assert result["verdict"] in {
        "COUNTERFACTUAL_POSITIVE_BUT_LOW_POWER",
        "COUNTERFACTUAL_NEGATIVE",
        "COUNTERFACTUAL_INCONCLUSIVE",
    }
    text = output_report.read_text(encoding="utf-8")
    assert "## Candidate Manifest Summary" in text
    assert "## Conservative Net Impact" in text
