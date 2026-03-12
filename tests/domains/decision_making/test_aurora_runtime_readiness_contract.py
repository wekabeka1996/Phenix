from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.bootstrap.startup_warmup import (
    activate_startup_warmup_gate,
    release_startup_warmup_gate,
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    build_canonical_bar_identity,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    cold_restore_status,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.quadratic_rollout import (
    evaluate_quadratic_shadow,
    resolve_requested_quadratic_rollout,
)
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


def test_aurora_emit_signal_adds_runtime_readiness_and_permissions() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(strategies=SimpleNamespace(aurora=SimpleNamespace()), instruments=None)

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {
            "regime_used": "LOW_VOLATILITY",
            "mode": "pct_mult",
            "sl_pct_eff": 0.01,
            "tp_rr_eff": 2.0,
            "rr_post": 2.0,
        },
    }

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    handler._emit_signal(
        "BTCUSDT",
        result,
        {"price": "100.0", "volatility": {"atr_14": 1.0, "atr_ready": True}, "liquidity": {"obi_close": "0.1"}},
        {
            "bar_close_ts": identity.bar_end_ts_ms,
            "source_mode": "live",
            "bar_identity": identity.to_payload(),
            "replay_identity": identity.to_replay_identity().to_payload(),
            "replay_generation": 0,
        },
    )

    assert len(emitted) == 1
    event_name, payload = emitted[0]
    assert event_name == "EVT:STRATEGY_SIGNAL_PRODUCED"
    assert payload["readiness"] == {"warmup_ok": True}
    assert payload["runtime_permissions"]["can_manage_existing_risk"] is True
    assert payload["runtime_permissions"]["can_open_new_risk"] is True
    assert payload["runtime_permissions"]["mode"] == "OPEN_AND_MANAGE"
    assert payload["runtime_readiness"]["scopes"]["strategy_ready_per_symbol"]["state"] == "READY"
    assert payload["runtime_readiness"]["scopes"]["quadratic_htf_ready"]["state"] == "COLD"
    assert payload["bar_close_ts"] == identity.bar_end_ts_ms
    assert payload["source_mode"] == "live"
    assert payload["bar_identity"]["close_boundary_ts_ms"] == identity.close_boundary_ts_ms
    assert payload["replay_identity"]["replay_generation"] == 0
    assert payload["rollout_mode"] == "v2_live"
    assert payload["rollback_armed_status"] == "DISARMED"
    assert payload["quadratic_rollout"]["effective_live_scoring_version"] == "v2"
    assert payload["quadratic_rollout"]["quadratic_can_open_new_risk"] is False
    assert payload["quadratic_rollout"]["shadow_evaluation"]["state"] == "NOT_REQUESTED"


def test_aurora_live_quadratic_requires_explicit_quadratic_readiness_for_new_entries() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

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
        ),
        instruments=None,
    )

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {"mode": "pct_mult"},
    }

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    handler._emit_signal(
        "BTCUSDT",
        result,
        {"price": "100.0", "volatility": {"atr_14": 1.0, "atr_ready": True}, "liquidity": {"obi_close": "0.1"}},
        {
            "bar_close_ts": identity.bar_end_ts_ms,
            "source_mode": "live",
            "bar_identity": identity.to_payload(),
            "replay_identity": identity.to_replay_identity().to_payload(),
            "replay_generation": 0,
        },
    )

    _, payload = emitted[0]
    assert payload["rollout_mode"] == "quadratic_live"
    assert payload["runtime_permissions"]["can_manage_existing_risk"] is True
    assert payload["runtime_permissions"]["can_open_new_risk"] is False
    assert payload["runtime_permissions"]["mode"] == "PROTECT_ONLY"
    assert payload["quadratic_rollout"]["quadratic_can_open_new_risk"] is False
    assert "quadratic_htf_not_ready" in payload["quadratic_rollout"]["quadratic_blocking_reason_chain"]


def test_aurora_rollback_arm_keeps_v2_live_and_reports_shadow_state() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    decision_cfg = SimpleNamespace(
        scoring_version="quadratic",
        quadratic_rollout=SimpleNamespace(
            shadow_enabled=False,
            rollback_armed=True,
            rollback_reason_chain=["operator_triggered"],
        ),
    )
    config = SimpleNamespace(
        strategies=SimpleNamespace(aurora=SimpleNamespace(decision=decision_cfg)),
        instruments=None,
    )

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {"mode": "pct_mult"},
    }

    requested_rollout = resolve_requested_quadratic_rollout(decision_cfg)
    shadow_eval = evaluate_quadratic_shadow(
        requested_rollout=requested_rollout,
        compute_kwargs={
            "symbol": "BTCUSDT",
            "features": {"pillar_sum": 0.5, "price": "100.0"},
            "warmup_readiness": {},
            "price": Decimal("100.0"),
            "signal_weights": {},
            "feature_neutrals": {},
            "essential_features": [],
            "base_threshold": Decimal("0.1"),
            "regime_name": "LOW_VOLATILITY",
            "regime_thresholds": {"LOW_VOLATILITY": 1.0, "DEFAULT": 1.0},
            "side_bias_state": None,
            "direction_strength_cfg": {},
            "delta_price_cap_pct": Decimal("0.01"),
            "normalize_mode": "signed_v2",
            "neutral_threshold": Decimal("0.05"),
            "current_side": "",
        },
        score_multiplier=1.0,
    )

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    handler._emit_signal(
        "BTCUSDT",
        result,
        {
            "price": "100.0",
            "pillar_sum": 0.5,
            "volatility": {"atr_14": 1.0, "atr_ready": True},
            "liquidity": {"obi_close": "0.1"},
        },
        {
            "bar_close_ts": identity.bar_end_ts_ms,
            "source_mode": "live",
            "bar_identity": identity.to_payload(),
            "replay_identity": identity.to_replay_identity().to_payload(),
            "replay_generation": 0,
        },
        quadratic_shadow_evaluation=shadow_eval,
    )

    _, payload = emitted[0]
    assert payload["rollout_mode"] == "v2_rollback"
    assert payload["rollback_armed_status"] == "ARMED"
    assert payload["runtime_permissions"]["can_open_new_risk"] is True
    assert payload["quadratic_rollout"]["quadratic_can_open_new_risk"] is False
    assert payload["quadratic_rollout"]["shadow_evaluation"]["state"] == "READY"
    assert "operator_triggered" in payload["quadratic_rollout"]["rollback_reason_chain"]


def test_aurora_gap_signal_is_protect_only_and_marks_basis_invalidated() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(strategies=SimpleNamespace(aurora=SimpleNamespace()), instruments=None)

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {
            "regime_used": "LOW_VOLATILITY",
            "mode": "pct_mult",
            "sl_pct_eff": 0.01,
            "tp_rr_eff": 2.0,
            "rr_post": 2.0,
        },
    }

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    handler._emit_signal(
        "BTCUSDT",
        result,
        {"price": "100.0", "volatility": {"atr_14": 1.0, "atr_ready": True}, "liquidity": {"obi_close": "0.1"}},
        {
            "bar_close_ts": identity.bar_end_ts_ms,
            "source_mode": "live",
            "bar_identity": identity.to_payload(),
            "replay_identity": identity.to_replay_identity().to_payload(),
            "replay_generation": 0,
            "gap_state": "GAP_DETECTED",
            "gap_policy_action": "DEGRADE_TO_NON_TRADING",
            "gap_bars_skipped": 2,
            "is_gap_bar": True,
        },
    )

    assert len(emitted) == 1
    _, payload = emitted[0]
    assert payload["runtime_permissions"]["can_manage_existing_risk"] is True
    assert payload["runtime_permissions"]["can_open_new_risk"] is False
    assert payload["runtime_permissions"]["mode"] == "PROTECT_ONLY"
    assert payload["runtime_readiness"]["scopes"]["basis_bar_ready"]["state"] == "INVALIDATED_GAP"
    assert payload["runtime_readiness"]["scopes"]["trading_ready"]["state"] == "BLOCKED"
    assert "basis_bar_gap" in payload["runtime_readiness"]["blocking_reason_chain"]
    assert payload["gap_state"] == "GAP_DETECTED"
    assert payload["gap_policy_action"] == "DEGRADE_TO_NON_TRADING"


def test_aurora_live_warmup_overrides_cold_restore_snapshot() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(strategies=SimpleNamespace(aurora=SimpleNamespace()), instruments=None)

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {
            "regime_used": "LOW_VOLATILITY",
            "mode": "pct_mult",
            "sl_pct_eff": 0.01,
            "tp_rr_eff": 2.0,
            "rr_post": 2.0,
        },
    }

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    restore_snapshot = make_strategy_restore_snapshot(
        strategy_id="aurora",
        symbol="BTCUSDT",
        updated_at=1_700_000_000_000,
        scopes={
            RuntimeAnalyticsRestoreScope.EXECUTION_STATE.value: restored_restore_status(
                why=["execution_snapshot_loaded"],
                updated_at=1_700_000_000_000,
                source="execution_position:startup_restore",
                evidence_ref="execution:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.BARS.value: cold_restore_status(
                why=["bars_restore_missing"],
                updated_at=1_700_000_000_000,
                source="market_data:startup_restore",
                evidence_ref="bars:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.PARTIAL_BAR.value: cold_restore_status(
                why=["partial_bar_restore_missing"],
                updated_at=1_700_000_000_000,
                source="market_data:startup_restore",
                evidence_ref="partial_bar:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_LAST_BAR.value: cold_restore_status(
                why=["fe_last_bar_restore_missing"],
                updated_at=1_700_000_000_000,
                source="feature_engineering:startup_restore",
                evidence_ref="fe_last_bar:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE.value: cold_restore_status(
                why=["fe_cache_restore_missing"],
                updated_at=1_700_000_000_000,
                source="feature_engineering:startup_restore",
                evidence_ref="fe_cache:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE.value: cold_restore_status(
                why=["regime_restore_missing"],
                updated_at=1_700_000_000_000,
                source="regime_detector:startup_restore",
                evidence_ref="regime:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.PILLAR_STATE.value: cold_restore_status(
                why=["pillar_restore_missing"],
                updated_at=1_700_000_000_000,
                source="feature_engineering:startup_restore",
                evidence_ref="pillars:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.DECISION_CACHE.value: cold_restore_status(
                why=["decision_cache_restore_missing"],
                updated_at=1_700_000_000_000,
                source="decision_making:startup_restore",
                evidence_ref="decision_cache:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value: cold_restore_status(
                why=["strategy_local_restore_missing"],
                updated_at=1_700_000_000_000,
                source="decision_making:startup_restore",
                evidence_ref="strategy_local:BTCUSDT:1700000000000",
            ),
        },
        source="startup:test",
        has_open_position=True,
    )
    handler.apply_runtime_analytics_restore_snapshot(restore_snapshot)

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    handler._emit_signal(
        "BTCUSDT",
        result,
        {"price": "100.0", "volatility": {"atr_14": 1.0, "atr_ready": True}, "liquidity": {"obi_close": "0.1"}},
        {
            "bar_close_ts": identity.bar_end_ts_ms,
            "source_mode": "live",
            "bar_identity": identity.to_payload(),
            "replay_identity": identity.to_replay_identity().to_payload(),
            "replay_generation": 0,
        },
    )

    assert len(emitted) == 1
    _, payload = emitted[0]
    assert payload["runtime_permissions"]["can_open_new_risk"] is True
    assert payload["runtime_permissions"]["mode"] == "OPEN_AND_MANAGE"
    assert payload["analytics_restore"]["rollup_state"] == "PARTIAL"
    assert payload["runtime_readiness"]["scopes"]["execution_context_ready"]["state"] == "READY"
    assert payload["runtime_readiness"]["scopes"]["microstructure_ready"]["state"] == "READY"


def test_aurora_startup_warmup_gate_blocks_new_risk_until_boot_finishes() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(strategies=SimpleNamespace(aurora=SimpleNamespace()), instruments=None)

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {"mode": "pct_mult"},
    }

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    activate_startup_warmup_gate(
        updated_at=1_700_000_000_000,
        source="startup:test",
    )
    try:
        handler._emit_signal(
            "BTCUSDT",
            result,
            {"price": "100.0", "volatility": {"atr_14": 1.0, "atr_ready": True}, "liquidity": {"obi_close": "0.1"}},
            {
                "bar_close_ts": identity.bar_end_ts_ms,
                "source_mode": "live",
                "bar_identity": identity.to_payload(),
                "replay_identity": identity.to_replay_identity().to_payload(),
                "replay_generation": 0,
            },
        )
    finally:
        release_startup_warmup_gate()

    _, payload = emitted[0]
    assert payload["runtime_permissions"]["can_manage_existing_risk"] is True
    assert payload["runtime_permissions"]["can_open_new_risk"] is False
    assert "startup_warmup_in_progress" in payload["runtime_readiness"]["blocking_reason_chain"]


def test_aurora_live_gap_precedence_beats_restored_snapshot() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(strategies=SimpleNamespace(aurora=SimpleNamespace()), instruments=None)

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda symbol: None
    handler._compute_regime_tpsl = lambda **kwargs: {
        "stop_price": Decimal("99"),
        "target_price": Decimal("101"),
        "tpsl_ctx": {"mode": "pct_mult"},
    }

    state = handler._symbol_states["BTCUSDT"]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    restore_snapshot = make_strategy_restore_snapshot(
        strategy_id="aurora",
        symbol="BTCUSDT",
        updated_at=1_700_000_000_000,
        scopes={
            scope.value: restored_restore_status(
                why=[f"{scope.value}_restored"],
                updated_at=1_700_000_000_000,
                source="startup:test",
                evidence_ref=f"{scope.value}:BTCUSDT:1700000000000",
            )
            for scope in RuntimeAnalyticsRestoreScope
        },
        source="startup:test",
        has_open_position=False,
    )
    handler.apply_runtime_analytics_restore_snapshot(restore_snapshot)

    result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    handler._emit_signal(
        "BTCUSDT",
        result,
        {"price": "100.0", "volatility": {"atr_14": 1.0, "atr_ready": True}, "liquidity": {"obi_close": "0.1"}},
        {
            "bar_close_ts": identity.bar_end_ts_ms,
            "source_mode": "live",
            "bar_identity": identity.to_payload(),
            "replay_identity": identity.to_replay_identity().to_payload(),
            "replay_generation": 0,
            "gap_state": "GAP_DETECTED",
            "gap_policy_action": "DEGRADE_TO_NON_TRADING",
            "gap_bars_skipped": 2,
            "is_gap_bar": True,
        },
    )

    _, payload = emitted[0]
    assert payload["runtime_permissions"]["can_open_new_risk"] is False
    assert payload["runtime_readiness"]["scopes"]["basis_bar_ready"]["state"] == "INVALIDATED_GAP"
    assert payload["runtime_readiness"]["scopes"]["trading_ready"]["state"] == "BLOCKED"


def test_aurora_process_decision_blocks_cold_start_until_basis_bars_seen() -> None:
    blocked: list[dict] = []

    with (
        patch.object(AuroraHandler, "_load_config", lambda self: None),
        patch("apps.reference.domains.decision_making.aurora_decision.write_trade_intent_rejected") as rejected_wal,
    ):
        handler = AuroraHandler(
            config=SimpleNamespace(
                strategies=SimpleNamespace(
                    aurora=SimpleNamespace(
                        decision=SimpleNamespace(scoring_version="v2"),
                    )
                ),
                instruments=None,
            ),
            emit_fn=lambda *_args, **_kwargs: None,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

        handler._is_symbol_enabled = lambda symbol: True
        handler._get_instrument_config = lambda symbol: SimpleNamespace(
            allowed_regimes=["LOW_VOLATILITY"]
        )
        handler._check_regime_liveness = lambda symbol, state: None
        handler._emit_strategy_blocked = lambda **kwargs: blocked.append(kwargs)
        handler._basis_required_bars_override = 5
        handler._bars_seen_since_restart["BTCUSDT"] = 1

        state = handler._symbol_states["BTCUSDT"]
        state.regime = "LOW_VOLATILITY"
        state.regime_ts_ms = 1_700_000_000_000

        handler._process_decision(
            "BTCUSDT",
            {
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1_700_000_000_000,
                "rid": "bars-required-test",
                "warmup": {"full_ready": True, "ready": {}},
                "features": {"price": "100.0"},
            },
        )

    assert len(blocked) == 1
    assert blocked[0]["reason_code"] == "BARS_REQUIRED_COLD_START"
    assert blocked[0]["details"] == {"bars_seen": 1, "basis_required_bars": 5}
    rejected_wal.assert_called_once()


def test_aurora_objective_missing_exposure_summary_blocks_explicitly() -> None:
    blocked: list[dict] = []
    emitted: list[tuple[str, dict]] = []

    def emit_fn(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(scoring_version="v2"),
                objective=SimpleNamespace(enabled=True),
            )
        ),
        domains=SimpleNamespace(
            objective_engine=SimpleNamespace(
                enabled=True,
                components={
                    "cost": SimpleNamespace(
                        enabled=True,
                        parameters={
                            "base_fee_bps": 1.0,
                            "slippage_from_spread_ratio": 0.5,
                        },
                    ),
                    "behavior": SimpleNamespace(
                        enabled=True,
                        parameters={"window_sec": 60.0},
                    ),
                },
            )
        ),
        regime_shift_inception=None,
        instruments=None,
    )

    scoring_result = SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        deferred=False,
        defer_reason=None,
        shield_multiplier=1.0,
    )
    scoring_kernel_cls = type(
        "StubAuroraKernel",
        (),
        {"compute": staticmethod(lambda **_kwargs: scoring_result)},
    )

    with (
        patch.object(AuroraHandler, "_load_config", lambda self: None),
        patch(
            "apps.reference.domains.decision_making.aurora_decision.evaluate_quadratic_shadow",
            return_value=SimpleNamespace(state="NOT_REQUESTED"),
        ),
    ):
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._basis_required_bars_override = 0
    handler._is_symbol_enabled = lambda symbol: True
    handler._check_regime_liveness = lambda symbol, state: None
    handler._get_instrument_config = lambda symbol: SimpleNamespace(
        allowed_regimes=["LOW_VOLATILITY"],
        tick_size=None,
        volatility_entry_logic=None,
    )
    handler._get_signal_weights = lambda symbol, instr_cfg: {}
    handler._get_feature_neutrals = lambda symbol, instr_cfg: {}
    handler._get_essential_features = lambda symbol, instr_cfg: []
    handler._get_side_bias_state = lambda symbol: None
    handler._get_regime_thresholds = lambda symbol, instr_cfg: {
        "LOW_VOLATILITY": 1.0,
        "DEFAULT": 1.0,
    }
    handler._apply_vol_adj_gates = lambda *args, **kwargs: False
    handler._should_suppress_soft_exit = lambda *args, **kwargs: False
    handler._get_reentry_cooldown_sec = lambda symbol: 0.0
    handler._emit_strategy_blocked = lambda **kwargs: blocked.append(kwargs)
    handler.scoring_kernel_cls = scoring_kernel_cls
    handler.signal_threshold = Decimal("0.1")
    handler.neutral_threshold = Decimal("0.05")
    handler.direction_strength_cfg = {}
    handler.delta_price_cap_pct = Decimal("0.01")
    handler.normalize_signals_mode = "signed_v2"
    handler.score_multiplier = 1.0
    handler._quadratic_shadow_shield_fn = None
    handler._regime_smoother = None
    handler.execution_gate = object()
    handler.exit_manager = SimpleNamespace(
        check_exit=lambda **_kwargs: (False, None, None)
    )
    handler.entry_plan_calculator = SimpleNamespace(
        compute=lambda **_kwargs: SimpleNamespace(
            entry_price=Decimal("100.0"),
            stop_loss_price=Decimal("99.0"),
            take_profit_price=Decimal("101.0"),
        )
    )
    handler._latest_portfolio = {}
    handler._latest_exposure_summary = None

    state = handler._symbol_states["BTCUSDT"]
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42

    handler._process_decision(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "warmup": {"full_ready": True, "ready": {}},
            "features": {
                "price": "100.0",
                "atr": 1.0,
                "obi": 0.1,
            },
        },
    )

    assert not emitted
    assert len(blocked) == 1
    assert blocked[0]["reason_code"] == "OBJECTIVE_PRECONDITION_NOT_MET"
    assert blocked[0]["details"]["precondition"] == "OBJECTIVE_EXPOSURE_SUMMARY_MISSING"
