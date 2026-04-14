from __future__ import annotations

import json
from pathlib import Path

from tools.forensics.phase6_package1_open_intake_proof_harness import (
    generate_phase6_package1_open_intake_harness_proof,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generate_phase6_package1_open_intake_harness_proof(tmp_path: Path) -> None:
    result = generate_phase6_package1_open_intake_harness_proof(tmp_path)

    summary = result["summary"]
    assert summary["evidence_grade"] == "harness-grade"
    assert summary["success_cmd_open_count"] == 1
    assert summary["reject_event_count"] == 1
    assert summary["reject_reason_code"] == "NRR-INTENT-OPEN-INTAKE-INVALID"
    assert summary["reject_stage"] == "typed_open_intake"

    success_cmd_open = _read_json(tmp_path / "success_cmd_open.json")
    success_metadata = success_cmd_open["pld"]["metadata"]
    assert success_metadata["execution_intake_contract"] == "trade_intent_open_intake_v1"
    assert success_metadata["execution_intake_path"] == "EVT:TRADE_INTENT_PROPOSED->CMD:OPEN"
    assert "tf_sec" not in success_metadata

    reject_event = _read_json(tmp_path / "reject_event.json")
    assert reject_event["details"]["execution_intake_contract"] == "trade_intent_open_intake_v1"
    assert reject_event["details"]["execution_intake_stage"] == "typed_open_intake"

    provenance = _read_json(tmp_path / "provenance.json")
    assert provenance["schema_validation_active"] is True
    assert provenance["evidence_grade"] == "harness-grade"
    assert provenance["reject_case"]["input_contract"] == "schema-compatible"
