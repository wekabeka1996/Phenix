from __future__ import annotations

import json
from pathlib import Path

import yaml

from apps.reference.config.domains.decision_making import DecisionMakingDomainConfig
from apps.reference.domains.alpha_search.judge.central_brain.runtime_capture import (
    build_shadow_capture_paths,
    runtime_shadow_capture_enabled,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_capture_writer import (
    JudgeShadowCaptureWriter,
)
from tests.domains.alpha_search.judge.central_brain.test_judge_runtime_shadow_pipeline import (
    build,
)


def current_config():
    data = yaml.safe_load(open("config/aurora/domains.yaml", encoding="utf-8"))
    return DecisionMakingDomainConfig.model_validate(data["decision_making"]).judge_bridge


def test_domains_config_enables_shadow_capture_only():
    cfg = current_config()
    assert cfg.enabled is True
    assert cfg.authority_mode == "shadow"
    assert cfg.shadow_capture.enabled is True
    assert "production" in cfg.forbidden_runtime_modes
    assert "live" in cfg.forbidden_runtime_modes
    assert cfg.calibration_guard.auto_apply is False


def test_telemetry_output_paths_are_explicit():
    paths = build_shadow_capture_paths(current_config())
    assert paths.output_dir == "logs/shadow_telemetry"
    assert paths.evidence_envelope_file.endswith(".jsonl")
    assert paths.policy_verdict_file.endswith(".jsonl")
    assert paths.bridge_decision_file.endswith(".jsonl")
    assert paths.calibration_row_file.endswith(".jsonl")


def test_preflight_sample_capture_writes_all_expected_files(tmp_path):
    cfg = current_config()
    assert runtime_shadow_capture_enabled(cfg) is True
    paths = build_shadow_capture_paths(cfg).model_copy(update={"output_dir": str(tmp_path)})
    writer = JudgeShadowCaptureWriter(enabled=True, paths=paths)
    artifacts = build()
    result = writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    assert len(result.paths) == 4
    for written_path in result.paths.values():
        row = json.loads(Path(written_path).read_text(encoding="utf-8").splitlines()[0])
        assert row["payload"]


def test_runtime_launch_checklist_inputs_are_available():
    cfg = current_config()
    assert cfg.enabled is True
    assert cfg.authority_mode == "shadow"
    assert cfg.shadow_capture.output_dir == "logs/shadow_telemetry"
