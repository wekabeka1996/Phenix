from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from apps.reference.config.domains.decision_making import (
    JudgeBridgeConfig,
)
from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    JudgeMetaScoringConfig,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_capture_writer import (
    JudgeShadowCaptureWriter,
    ShadowCapturePaths,
    ShadowCaptureWriteResult,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_pipeline import (
    RuntimeShadowArtifacts,
    build_runtime_shadow_artifacts,
)


class RuntimeShadowCaptureDisabled(RuntimeError):
    pass


def build_shadow_capture_paths(config: JudgeBridgeConfig) -> ShadowCapturePaths:
    capture = config.shadow_capture
    return ShadowCapturePaths(
        output_dir=capture.output_dir,
        evidence_envelope_file=capture.evidence_envelope_file,
        policy_verdict_file=capture.policy_verdict_file,
        bridge_decision_file=capture.bridge_decision_file,
        calibration_row_file=capture.calibration_row_file,
    )


def build_runtime_meta_config(config: JudgeBridgeConfig) -> JudgeMetaScoringConfig:
    return JudgeMetaScoringConfig.model_validate(
        config.shadow_capture.meta_scoring.model_dump(mode="json")
    )


def runtime_shadow_capture_enabled(config: JudgeBridgeConfig) -> bool:
    return (
        bool(config.enabled)
        and config.authority_mode == "shadow"
        and bool(config.shadow_capture.enabled)
    )


def build_runtime_shadow_writer(config: JudgeBridgeConfig) -> JudgeShadowCaptureWriter:
    return JudgeShadowCaptureWriter(
        enabled=runtime_shadow_capture_enabled(config),
        paths=build_shadow_capture_paths(config),
    )


def capture_runtime_shadow(
    *,
    strategy_payload: Mapping[str, Any],
    regime_payload: Mapping[str, Any] | None,
    bridge_config: JudgeBridgeConfig,
    runtime_mode: str,
    candidate_context: Mapping[str, Any],
    market_context: Mapping[str, Any] | None = None,
    risk_context: Mapping[str, Any] | None = None,
    portfolio_context: Mapping[str, Any] | None = None,
    execution_readiness: Mapping[str, Any] | None = None,
    writer: JudgeShadowCaptureWriter | None = None,
    now_ms: int | None = None,
) -> tuple[RuntimeShadowArtifacts, ShadowCaptureWriteResult]:
    if not runtime_shadow_capture_enabled(bridge_config):
        raise RuntimeShadowCaptureDisabled("runtime shadow capture is disabled")
    payload_copy = deepcopy(dict(strategy_payload))
    candidate_copy = deepcopy(dict(candidate_context))
    artifacts = build_runtime_shadow_artifacts(
        strategy_payload=payload_copy,
        regime_payload=deepcopy(dict(regime_payload or {})) if regime_payload else None,
        meta_config=build_runtime_meta_config(bridge_config),
        bridge_config=bridge_config,
        runtime_mode=runtime_mode,
        candidate_context=candidate_copy,
        market_context=deepcopy(dict(market_context or {})) if market_context else None,
        risk_context=deepcopy(dict(risk_context or {})) if risk_context else None,
        portfolio_context=(
            deepcopy(dict(portfolio_context or {})) if portfolio_context else None
        ),
        execution_readiness=(
            deepcopy(dict(execution_readiness or {})) if execution_readiness else None
        ),
        now_ms=now_ms,
    )
    active_writer = writer or build_runtime_shadow_writer(bridge_config)
    result = active_writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    return artifacts, result
