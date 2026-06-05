import enum
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.domains.execution_position as domain_ep
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")
ARTIFACT = (
    Path(__file__).resolve().parent
    / "_artifacts"
    / "execution_position_contract.generated.json"
)


@pytest.fixture(scope="module")
def frozen_manifest() -> dict[str, Any]:
    assert ARTIFACT.exists(), (
        f"Frozen execution_position contract not found at {ARTIFACT}. "
        "Regenerate only when the roadmap explicitly authorizes a package contract update."
    )
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _serialize_default(field_info: Any) -> str:
    if field_info.is_required():
        return repr("<required>")

    default = field_info.default
    if isinstance(default, list):
        return "list"
    if isinstance(default, dict):
        return "dict"
    if isinstance(default, set):
        return type(default).__name__
    return repr(default)


def _serialize_default_factory(field_info: Any) -> str | None:
    if field_info.default_factory is None:
        return None
    return field_info.default_factory.__name__


def _assert_model_contract(model_cls: type, snapshot: dict[str, Any]) -> None:
    fields = model_cls.model_fields

    assert model_cls.model_config.get("extra") == snapshot["extra"]
    assert set(fields) == set(snapshot["fields"])

    for field_name, expected in snapshot["fields"].items():
        field_info = fields[field_name]
        assert field_info.is_required() is expected["required"], (
            f"{model_cls.__name__}.{field_name} required drift"
        )
        assert _serialize_default(field_info) == expected["default"], (
            f"{model_cls.__name__}.{field_name} default drift"
        )
        assert _serialize_default_factory(field_info) == expected["default_factory"], (
            f"{model_cls.__name__}.{field_name} default_factory drift"
        )


def _assert_enum_contract(enum_cls: type[enum.Enum], snapshot: dict[str, Any]) -> None:
    current = [{"name": member.name, "value": member.value}
               for member in enum_cls]
    assert current == snapshot["members"]


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _load_execution_position_with_guardian_mutation(
    tmp_path: Path,
    mutator,
) -> cm.ExecutionPositionDomainConfig:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    guardian = domains["execution_position"]["guardian"]
    mutator(guardian)
    _write_yaml(domains_path, domains)
    return ConfigLoader(config_dir=cfg_dir).load_config().domains.execution_position


def test_execution_position_facade_reexports_are_exact_identity(
    frozen_manifest: dict[str, Any],
) -> None:
    for name in set(frozen_manifest["models"]) | set(frozen_manifest["enums"]):
        assert getattr(cm, name) is getattr(domain_ep, name)


def test_execution_position_extraction_preserves_model_contract(
    frozen_manifest: dict[str, Any],
) -> None:
    for name, snapshot in frozen_manifest["models"].items():
        _assert_model_contract(getattr(cm, name), snapshot)


def test_execution_position_extraction_preserves_enum_contract(
    frozen_manifest: dict[str, Any],
) -> None:
    for name, snapshot in frozen_manifest["enums"].items():
        _assert_enum_contract(getattr(cm, name), snapshot)


def test_current_aurora_config_loads_execution_position_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    domains = yaml.safe_load(
        (CONFIG_DIR / "domains.yaml").read_text(encoding="utf-8"))
    expected_portfolio_max_age_ms = domains["execution_position"][
        "position_policy_sidecar"]["freshness"]["portfolio_max_age_ms"]

    ep = cfg.domains.execution_position
    assert type(ep) is cm.ExecutionPositionDomainConfig
    assert type(ep.fallback) is cm.FallbackConfig
    assert ep.fallback.policy == "fail_closed"

    assert ep.exposure_guard.pending_ttl_sec == 90
    assert ep.exposure_guard.post_fill_ttl_sec == 5
    assert ep.exposure_guard.stale_ttl_sec == 60
    assert ep.exposure_guard.max_equity_utilization_pct == 150.0

    assert ep.fsm_open.idempotency_window_sec == 60
    assert ep.order_index.ttl_sec == 3600
    assert ep.inflight_reconcile.inflight_ttl_sec == 60
    assert ep.inflight_reconcile.max_ttl_sec == 120
    assert ep.inflight_reconcile.reconcile_interval_sec == 10
    assert ep.inflight_reconcile.verbose_logging is True
    assert ep.metrics_collector.window_size_minutes == 60
    assert ep.metrics_collector.recent_rejections_minutes == 5
    assert ep.idempotent_cancel.max_retries == 2
    assert ep.utils.client_order_id_max_length == 32
    assert ep.utils.basis_points_base == 10000.0

    assert ep.event_dedup is not None
    assert type(ep.event_dedup) is cm.EventDedupConfig
    assert ep.event_dedup.max_size == 100000
    assert ep.event_dedup.ttl_ms == 86400000
    assert type(ep.event_dedup.warm_state) is cm.EventDedupWarmStateConfig
    assert ep.event_dedup.warm_state.enabled is True
    assert ep.event_dedup.warm_state.storage_path == "logs/execution_terminal_identity_cache_v1.json"
    assert ep.event_dedup.warm_state.max_entries == 2000

    assert ep.restore_artifact.mode is cm.ExecutionPositionRestoreArtifactMode.AUTHORITATIVE
    assert ep.restore_artifact.storage_path == "ops/restore/execution_position_restore_envelope_v1.json"
    assert ep.restore_artifact.flush_interval_ms == 30000
    assert ep.restore_artifact.dark_read_max_artifact_age_ms == 300000

    assert ep.startup_truth_artifact.mode is cm.ExecutionPositionStartupTruthArtifactMode.WRITER_ONLY
    assert ep.startup_truth_artifact.storage_path == "ops/restore/execution_position_startup_truth_v1.jsonl"

    assert ep.pending_entry_ttl.enabled is True
    assert ep.pending_entry_ttl.ttl_by_tf_sec == {
        180: 600, 300: 1200, 900: 1800}
    assert ep.pending_entry_ttl.reject_unknown_tf is True
    assert ep.pending_entry_ttl.cancel_on_regime_change is True
    assert ep.pending_entry_ttl.regime_change_cancel_mode == "let_ttl_expire"
    assert ep.pending_entry_ttl.cancel_on_supersede is True
    assert ep.pending_entry_ttl.cancel_on_panic is True
    assert ep.pending_entry_ttl.supersede_cancel_timeout_sec == 5.0
    assert ep.pending_entry_ttl.supersede_reprice_guard is not None
    assert ep.pending_entry_ttl.supersede_reprice_guard.enabled is True
    assert ep.pending_entry_ttl.supersede_reprice_guard.enforce is True
    assert ep.pending_entry_ttl.supersede_reprice_guard.min_price_improvement_bps == 5.0
    assert ep.pending_entry_ttl.supersede_reprice_guard.min_price_improvement_atr_mult == 0.10
    assert ep.pending_entry_ttl.advanced_stale_cancel is not None
    assert ep.pending_entry_ttl.advanced_stale_cancel.enabled is True
    assert ep.pending_entry_ttl.advanced_stale_cancel.min_age_before_cancel_sec == 300
    assert ep.pending_entry_ttl.advanced_stale_cancel.drift_away.mode == "atr"
    assert ep.pending_entry_ttl.advanced_stale_cancel.drift_away.atr_mult == 0.5
    assert ep.pending_entry_ttl.advanced_stale_cancel.may_cancel_regimes == {
        "BUY": ["TREND_DOWN"],
        "SELL": ["TREND_UP"],
    }
    assert ep.pending_entry_ttl.advanced_stale_cancel.never_cancel_regimes == [
        "UNCERTAIN",
        "MEAN_REVERSION",
        "LOW_VOLATILITY",
    ]

    assert ep.maker_only_entry.enabled is False
    assert ep.order_capabilities.supported_order_types == ["LIMIT", "MARKET"]
    assert ep.order_capabilities.supported_tif == ["GTC", "GTX", "IOC", "FOK"]
    assert ep.bracket_placement.tp_widen_first_bps == 25
    assert ep.bracket_placement.tp_widen_second_bps == 60
    assert ep.bracket_placement.retry_backoff_ms == [200, 400]
    assert ep.bracket_health_check is not None
    assert ep.bracket_health_check.enabled is True
    assert ep.bracket_health_check.interval_sec == 45
    assert ep.bracket_health_check.grace_period_ms == 15000
    assert ep.bracket_health_check.max_placements_per_cycle == 2
    assert ep.order_lifecycle.fill_settlement_delay_ms == 500
    assert ep.order_lifecycle.position_close_cleanup_delay_ms == 2000

    assert ep.shadow_check.enabled is True
    assert ep.shadow_check.check_every_n_requests == 10
    assert ep.shadow_check.tolerance_pct == 1.0
    assert ep.shadow_check.absolute_threshold_usd == 5000.0
    assert ep.shadow_check.use_absolute_for_large_portfolios is True
    assert ep.shadow_check.large_portfolio_threshold_usd == 1000000.0

    assert ep.guardian.poll_interval_ms == 500
    assert ep.guardian.unified is True
    assert ep.guardian.emit_tidy_event is True
    assert ep.guardian.emit_tidy_monitoring_event is True
    assert ep.guardian.cleanup_ttl_ms == 6000
    assert ep.guardian.symbol_cooldown_ms == 4000
    assert ep.intent_boundary_audit.enabled is True
    assert ep.intent_boundary_audit.route_ttl_ms == 2000
    assert ep.intent_boundary_audit.downstream_ttl_ms == 5000

    assert type(ep.position_policy_sidecar) is cm.PositionPolicySidecarConfig
    assert ep.position_policy_sidecar.mode is cm.PositionPolicySidecarMode.ENABLE
    assert ep.position_policy_sidecar.freshness.portfolio_max_age_ms == expected_portfolio_max_age_ms
    assert ep.position_policy_sidecar.freshness.features_max_age_ms == 15000
    assert ep.position_policy_sidecar.freshness.regime_max_age_ms == 30000
    assert ep.position_policy_sidecar.freshness.order_state_max_age_ms == 15000
    assert ep.position_policy_sidecar.startup_grace.startup_grace_ms == 30000
    assert ep.position_policy_sidecar.startup_grace.post_fill_grace_ms == 15000
    assert ep.position_policy_sidecar.startup_grace.min_portfolio_updates == 1
    assert ep.position_policy_sidecar.startup_grace.min_feature_updates == 1
    assert ep.position_policy_sidecar.startup_grace.min_regime_updates == 1
    assert ep.position_policy_sidecar.profitability_guard.enabled is True
    assert ep.position_policy_sidecar.profitability_guard.min_unrealized_pnl_pct == 0.25
    assert ep.position_policy_sidecar.profitability_guard.min_unrealized_pnl_usdt == 0.0
    assert ep.position_policy_sidecar.scoring.weights.microstructure_adverse_pressure == 0.30
    assert ep.position_policy_sidecar.scoring.weights.regime_exhaustion_hint == 0.30
    assert ep.position_policy_sidecar.scoring.weights.conviction_decay == 0.15
    assert ep.position_policy_sidecar.scoring.weights.unrealized_loss_pressure == 0.25
    assert ep.position_policy_sidecar.scoring.caps.microstructure_adverse_pressure == 1.0
    assert ep.position_policy_sidecar.scoring.caps.regime_exhaustion_hint == 1.0
    assert ep.position_policy_sidecar.scoring.caps.conviction_decay == 1.0
    assert ep.position_policy_sidecar.scoring.caps.unrealized_loss_pressure == 1.0
    assert ep.position_policy_sidecar.thresholds.recommend_soft_close_at == 0.30
    assert ep.position_policy_sidecar.thresholds.loss_bps_full_pressure == 50.0
    assert ep.position_policy_sidecar.thresholds.adverse_price_distance_bps_full_pressure == 25.0
    assert ep.position_policy_sidecar.thresholds.book_imbalance_full_pressure == 0.35
    assert ep.position_policy_sidecar.thresholds.regime_confidence_floor == 0.55
    assert ep.position_policy_sidecar.thresholds.signal_score_floor == 0.0
    assert ep.position_policy_sidecar.thresholds.adverse_regimes_long == [
        "TREND_DOWN"]
    assert ep.position_policy_sidecar.thresholds.adverse_regimes_short == [
        "TREND_UP"]
    assert ep.position_policy_sidecar.logging.emit_internal_bus_events is True
    assert ep.position_policy_sidecar.logging.write_trade_lifecycle_jsonl is True
    assert ep.position_policy_sidecar.logging.trade_lifecycle_log_path == "logs/trade_lifecycle.jsonl"
    assert ep.position_policy_sidecar.logging.include_score_payloads is True
    assert ep.position_policy_sidecar.allowed_actions.soft_close_symbol_current_net_only is True
    assert ep.position_policy_sidecar.allowed_actions.partial_reduce is False
    assert ep.position_policy_sidecar.allowed_actions.bracket_mutation is False
    assert ep.position_policy_sidecar.allowed_actions.exact_targeting is False
    assert ep.position_policy_sidecar.shadow_percent_notional_arm.enabled is True
    assert ep.position_policy_sidecar.shadow_percent_notional_arm.candidate_pcts == [
        0.02,
        0.05,
        0.07,
    ]
    assert ep.position_policy_sidecar.shadow_fee_aware_arm.enabled is True
    assert [source.value for source in ep.position_policy_sidecar.shadow_fee_aware_arm.fee_source_priority] == [
        "realized_lifecycle_fee",
        "order_log_fee",
        "configured_fee_model",
    ]
    assert ep.position_policy_sidecar.shadow_fee_aware_arm.candidate_fee_multiples == [
        1.0,
        1.5,
        2.0,
    ]
    assert ep.position_policy_sidecar.shadow_fee_aware_arm.optional_pct_notional_floor.candidate_pcts == [
        0.02,
        0.05,
    ]


def test_guardian_legacy_emit_tidy_event_only_maps_to_monitoring_flag(
    tmp_path: Path,
) -> None:
    def _mutate(guardian: dict[str, Any]) -> None:
        guardian.pop("emit_tidy_monitoring_event", None)
        guardian["emit_tidy_event"] = False

    ep = _load_execution_position_with_guardian_mutation(tmp_path, _mutate)

    assert ep.guardian.emit_tidy_event is False
    assert ep.guardian.emit_tidy_monitoring_event is False


def test_guardian_new_emit_tidy_monitoring_event_only_loads(
    tmp_path: Path,
) -> None:
    def _mutate(guardian: dict[str, Any]) -> None:
        guardian.pop("emit_tidy_event", None)
        guardian["emit_tidy_monitoring_event"] = False

    ep = _load_execution_position_with_guardian_mutation(tmp_path, _mutate)

    assert ep.guardian.emit_tidy_event is False
    assert ep.guardian.emit_tidy_monitoring_event is False


def test_guardian_legacy_and_monitoring_flags_equal_load(
    tmp_path: Path,
) -> None:
    def _mutate(guardian: dict[str, Any]) -> None:
        guardian["emit_tidy_event"] = False
        guardian["emit_tidy_monitoring_event"] = False

    ep = _load_execution_position_with_guardian_mutation(tmp_path, _mutate)

    assert ep.guardian.emit_tidy_event is False
    assert ep.guardian.emit_tidy_monitoring_event is False


def test_guardian_legacy_and_monitoring_flags_differ_fail_fast(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    guardian = domains["execution_position"]["guardian"]
    guardian["emit_tidy_event"] = False
    guardian["emit_tidy_monitoring_event"] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "emit_tidy_event" in message
    assert "emit_tidy_monitoring_event" in message
    assert "differ" in message


def test_execution_position_yaml_contract_fails_closed_on_forbidden_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["unexpected_pkg8_field"] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg8_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_execution_position_yaml_contract_fails_closed_on_invalid_sidecar_regime_label(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["thresholds"][
        "adverse_regimes_long"
    ] = ["FLAT_UP"]
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "adverse_regimes_long" in message
    assert "FLAT_UP" in message
    assert "unsupported sidecar regime label" in message


def test_execution_position_yaml_contract_fails_closed_on_invalid_pending_entry_ttl_map(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["pending_entry_ttl"]["ttl_by_tf_sec"] = {
        30: 600}
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "pending_entry_ttl" in message
    assert "tf_sec must be >= 60" in message


def test_execution_position_yaml_contract_fails_closed_on_disallowed_sidecar_action(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["position_policy_sidecar"]["allowed_actions"][
        "partial_reduce"
    ] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "position_policy_sidecar" in message
    assert "partial_reduce" in message
    assert "forbids partial_reduce" in message
