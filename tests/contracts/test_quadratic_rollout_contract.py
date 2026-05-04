from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from apps.reference.contracts.quadratic_rollout import (
    QuadraticRolloutMode,
    QuadraticShadowEvaluationState,
    apply_live_quadratic_permission_gate,
    build_startup_quadratic_rollout_report,
    build_quadratic_rollout_snapshot,
    evaluate_quadratic_shadow,
    resolve_requested_quadratic_rollout,
)
from apps.reference.contracts.runtime_readiness import (
    cold_status,
    make_permissions,
    ready_status,
)


def _compute_kwargs(*, pillar_sum: float | None) -> dict[str, object]:
    features = {"price": "100.0"}
    if pillar_sum is not None:
        features["pillar_sum"] = pillar_sum
    return {
        "symbol": "BTCUSDT",
        "features": features,
        "warmup_readiness": {},
        "price": Decimal("100.0"),
        "signal_weights": {},
        "feature_neutrals": {},
        "essential_features": [],
        "base_threshold": Decimal("0.1"),
        "regime_name": "TREND_UP",
        "regime_thresholds": {"TREND_UP": 1.0, "DEFAULT": 1.0},
        "side_bias_state": None,
        "direction_strength_cfg": {},
        "delta_price_cap_pct": Decimal("0.01"),
        "normalize_mode": "signed_v2",
        "neutral_threshold": Decimal("0.05"),
        "current_side": "",
    }


def test_shadow_evaluation_works_when_quadratic_live() -> None:
    """Shadow evaluation still functional when quadratic is the sole live path."""
    decision_cfg = SimpleNamespace(
        scoring_version="quadratic",
        quadratic_rollout=SimpleNamespace(
            shadow_enabled=True,
            rollback_armed=False,
            rollback_reason_chain=[],
        ),
    )
    requested = resolve_requested_quadratic_rollout(decision_cfg)

    shadow = evaluate_quadratic_shadow(
        requested_rollout=requested,
        compute_kwargs=_compute_kwargs(pillar_sum=0.6),
        score_multiplier=1.0,
    )
    rollout = build_quadratic_rollout_snapshot(
        requested_rollout=requested,
        quadratic_readiness=ready_status(
            why=["pillar_sum_present"],
            updated_at=1_700_000_000_000,
            source="test",
            evidence_ref="pillar:test",
        ),
        runtime_permissions=make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=True,
        ),
        shadow_evaluation=shadow,
    )

    assert requested.effective_live_scoring_version == "quadratic"
    assert rollout.mode == QuadraticRolloutMode.QUADRATIC_LIVE
    assert shadow.state == QuadraticShadowEvaluationState.READY
    assert shadow.side == "BUY"
    assert rollout.quadratic_can_open_new_risk is True


def test_live_quadratic_open_new_risk_is_gated_by_explicit_quadratic_readiness() -> None:
    decision_cfg = SimpleNamespace(
        scoring_version="quadratic",
        quadratic_rollout=SimpleNamespace(
            shadow_enabled=False,
            rollback_armed=False,
            rollback_reason_chain=[],
        ),
    )
    requested = resolve_requested_quadratic_rollout(decision_cfg)
    initial_permissions = make_permissions(
        can_manage_existing_risk=True,
        can_open_new_risk=True,
    )

    rollout = build_quadratic_rollout_snapshot(
        requested_rollout=requested,
        quadratic_readiness=cold_status(
            why=["pillar_sum_missing"],
            updated_at=1_700_000_000_000,
            source="test",
            evidence_ref="pillar:test",
        ),
        runtime_permissions=initial_permissions,
    )
    gated_permissions = apply_live_quadratic_permission_gate(
        initial_permissions,
        rollout,
    )

    assert requested.effective_live_scoring_version == "quadratic"
    assert rollout.mode == QuadraticRolloutMode.QUADRATIC_LIVE
    assert rollout.quadratic_can_open_new_risk is False
    assert "quadratic_htf_not_ready" in rollout.quadratic_blocking_reason_chain
    assert gated_permissions.can_manage_existing_risk is True
    assert gated_permissions.can_open_new_risk is False


def test_rollback_armed_is_non_operational_post_phase9_cleanup() -> None:
    """rollback_armed=True in config is ignored — v2 kernel is deleted.
    Effective live version stays quadratic, rollback_armed is forced to False."""
    decision_cfg = SimpleNamespace(
        scoring_version="quadratic",
        quadratic_rollout=SimpleNamespace(
            shadow_enabled=False,
            rollback_armed=True,
            rollback_reason_chain=["operator_triggered"],
        ),
    )
    requested = resolve_requested_quadratic_rollout(decision_cfg)
    initial_permissions = make_permissions(
        can_manage_existing_risk=True,
        can_open_new_risk=True,
    )
    rollout = build_quadratic_rollout_snapshot(
        requested_rollout=requested,
        quadratic_readiness=ready_status(
            why=["pillar_sum_present"],
            updated_at=1_700_000_000_000,
            source="test",
            evidence_ref="pillar:test",
        ),
        runtime_permissions=initial_permissions,
    )
    gated_permissions = apply_live_quadratic_permission_gate(
        initial_permissions,
        rollout,
    )

    # Key: effective stays quadratic, rollback_armed is disarmed
    assert requested.effective_live_scoring_version == "quadratic"
    assert requested.rollback_armed is False
    assert rollout.mode == QuadraticRolloutMode.QUADRATIC_LIVE
    assert rollout.quadratic_can_open_new_risk is True
    assert gated_permissions.can_manage_existing_risk is True
    assert gated_permissions.can_open_new_risk is True


def test_startup_quadratic_rollout_report_is_operator_visible() -> None:
    config = SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    scoring_version="quadratic",
                    quadratic_rollout=SimpleNamespace(
                        shadow_enabled=False,
                        rollback_armed=False,
                        rollback_reason_chain=[],
                    ),
                )
            )
        )
    )

    report = build_startup_quadratic_rollout_report(
        config=config,
        updated_at=1_700_000_000_000,
        source="test:startup_rollout",
    )

    assert report["strategy_id"] == "aurora"
    assert report["mode"] == "quadratic_live"
    assert report["rollback_armed_status"] == "DISARMED"
    assert report["effective_live_scoring_version"] == "quadratic"


def test_unrecognized_scoring_version_forces_quadratic(caplog) -> None:
    """Unrecognized scoring_version forces quadratic (v2 kernel deleted)."""
    decision_cfg = SimpleNamespace(
        scoring_version="typo",
        quadratic_rollout=SimpleNamespace(
            shadow_enabled=False,
            rollback_armed=False,
            rollback_reason_chain=[],
        ),
    )

    with caplog.at_level("CRITICAL", logger="quadratic_rollout"):
        requested = resolve_requested_quadratic_rollout(decision_cfg)

    assert requested.requested_scoring_version == "quadratic"
    assert requested.effective_live_scoring_version == "quadratic"
    assert "forcing 'quadratic'" in caplog.text


def test_v2_scoring_version_forced_to_quadratic(caplog) -> None:
    """scoring_version='v2' is no longer valid — forced to quadratic."""
    decision_cfg = SimpleNamespace(
        scoring_version="v2",
        quadratic_rollout=SimpleNamespace(
            shadow_enabled=False,
            rollback_armed=False,
            rollback_reason_chain=[],
        ),
    )

    with caplog.at_level("CRITICAL", logger="quadratic_rollout"):
        requested = resolve_requested_quadratic_rollout(decision_cfg)

    assert requested.requested_scoring_version == "quadratic"
    assert requested.effective_live_scoring_version == "quadratic"
