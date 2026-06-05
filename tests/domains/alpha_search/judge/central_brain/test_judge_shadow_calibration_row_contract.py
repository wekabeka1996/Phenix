from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (
    JudgeShadowCalibrationRowV1,
    to_phase8_calibration_row,
)


SCHEMA_PATH = Path("apps/reference/domains/alpha_search/judge/schemas/judge_shadow_calibration_row_v1.json")


def valid_shadow_row(**overrides) -> JudgeShadowCalibrationRowV1:
    payload = {
        "row_id": "shadow-row-1",
        "source_kind": "replay",
        "created_ts_ms": 1000,
        "decision_ts_ms": 1000,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "regime_label": "TREND_UP",
        "regime_confidence": 0.8,
        "envelope": {
            "envelope_id": "env-1",
            "present": True,
            "missing_reason": None,
        },
        "verdict": {
            "verdict_id": "verdict-1",
            "verdict": "OPEN_LONG",
            "confidence": 0.82,
            "authority_status": "shadow_only",
            "applied": False,
        },
        "bridge": {
            "bridge_decision_id": "bridge-1",
            "authority_mode": "shadow",
            "bridge_action": "record_only",
            "applied": False,
            "no_effect": True,
        },
        "outcome": {
            "outcome_status": "RESOLVED",
            "outcome_ts_ms": 2000,
            "horizon_sec": 300,
            "gross_pnl_usd": 1.3,
            "net_pnl_usd": 1.0,
            "fees_usd": 0.2,
            "slippage_usd": 0.1,
            "max_favorable_usd": 2.0,
            "max_adverse_usd": -0.5,
            "terminal_status": "closed",
        },
        "source_refs": {
            "decision_id": "decision-1",
            "rid": "rid-1",
            "lifecycle_id": "life-1",
            "order_id": "order-1",
            "trace_id": "trace-1",
            "input_paths": ["verdicts.jsonl"],
        },
        "diagnostics": {
            "missing_fields": [],
            "join_quality": "EXACT",
            "reason_codes": ["joined_by_decision_id"],
        },
    }
    payload.update(overrides)
    return JudgeShadowCalibrationRowV1.model_validate(payload)


def test_valid_row_validates():
    row = valid_shadow_row()
    assert row.schema_version == "1.0.0"
    assert row.bridge.no_effect is True


def test_extra_unknown_field_rejected():
    payload = valid_shadow_row().model_dump()
    payload["extra"] = "no"
    with pytest.raises(ValidationError):
        JudgeShadowCalibrationRowV1.model_validate(payload)


def test_applied_true_rejected_for_generated_row():
    payload = valid_shadow_row().model_dump()
    payload["verdict"]["applied"] = True
    with pytest.raises(ValidationError):
        JudgeShadowCalibrationRowV1.model_validate(payload)


def test_bridge_no_effect_false_rejected_when_present():
    payload = valid_shadow_row().model_dump()
    payload["bridge"]["no_effect"] = False
    with pytest.raises(ValidationError):
        JudgeShadowCalibrationRowV1.model_validate(payload)


def test_missing_net_pnl_requires_unresolved_status():
    payload = valid_shadow_row().model_dump()
    payload["outcome"]["net_pnl_usd"] = None
    with pytest.raises(ValidationError):
        JudgeShadowCalibrationRowV1.model_validate(payload)
    payload["outcome"]["outcome_status"] = "UNRESOLVED"
    assert JudgeShadowCalibrationRowV1.model_validate(payload).outcome.outcome_status == "UNRESOLVED"


def test_row_converts_to_phase8_calibration_row():
    converted = to_phase8_calibration_row(valid_shadow_row())
    assert converted.row_id == "shadow-row-1"
    assert converted.verdict == "OPEN_LONG"
    assert converted.judge_confidence == pytest.approx(0.82)
    assert converted.outcome.net_pnl_usd == pytest.approx(1.0)


def test_fuzzy_join_quality_cannot_be_marked_exact():
    payload = valid_shadow_row().model_dump()
    payload["diagnostics"]["reason_codes"] = ["joined_by_fuzzy_window"]
    with pytest.raises(ValidationError):
        JudgeShadowCalibrationRowV1.model_validate(payload)


def test_rid_exact_join_quality_validates():
    payload = valid_shadow_row().model_dump()
    payload["diagnostics"]["join_quality"] = "RID_EXACT"
    payload["diagnostics"]["reason_codes"] = ["joined_by_rid"]
    assert JudgeShadowCalibrationRowV1.model_validate(payload).diagnostics.join_quality == "RID_EXACT"


def test_schema_json_parses():
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        assert json.load(handle)["title"] == "Judge Shadow Calibration Row V1"
