"""
Unit tests for Alpha Search Runtime Contracts.

Validates every Pydantic model in
apps/reference/domains/alpha_search/runtime/contracts.py:
  AlphaInputV1, AlphaShadowResultV1, ScenarioSpec,
  RuntimeConfig, HotReloadConfig, InputConfig, ScenarioMatrixConfig.

Covers: required fields, defaults, bounds, extra="forbid",
        literal enforcement, model validators, roundtrip serialization.
"""

import pytest
from pydantic import ValidationError

from apps.reference.domains.alpha_search.runtime.contracts import (
    AlphaInputV1,
    AlphaShadowResultV1,
    ScenarioSpec,
    RuntimeConfig,
    HotReloadConfig,
    InputConfig,
    ScenarioMatrixConfig,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _minimal_alpha_input(**overrides) -> dict:
    """Return a minimal valid AlphaInputV1 dict."""
    base = dict(
        ts_ms=1700000000000,
        symbol="BTCUSDT",
        bar_close_ts=1700000300000,
        price=42000.5,
        features={"obi": 0.12, "delta_price": -0.003},
    )
    base.update(overrides)
    return base


def _minimal_shadow_result(**overrides) -> dict:
    """Return a minimal valid AlphaShadowResultV1 dict."""
    base = dict(
        scenario_id="S01_AURORA",
        strategy_type="aurora",
        ts_ms=1700000000000,
        symbol="BTCUSDT",
        score=0.45,
        confidence=0.8,
        threshold=0.3,
        side="BUY",
        provider_id="aurora_v1",
        model_name="aurora_baseline",
    )
    base.update(overrides)
    return base


def _override_scenario(**overrides) -> dict:
    """Return a valid ScenarioSpec dict in override mode."""
    base = dict(
        scenario_id="S01_AURORA_BASELINE",
        strategy_type="aurora",
        config_mode="override",
        base_refs={"aurora": "config/aurora/strategies/aurora.yaml"},
    )
    base.update(overrides)
    return base


def _full_config_scenario(**overrides) -> dict:
    """Return a valid ScenarioSpec dict in full_config mode."""
    base = dict(
        scenario_id="S02_MR_FULL",
        strategy_type="mean_reversion",
        config_mode="full_config",
        scenario_config_dir="config/alpha_search/scenarios/S02",
    )
    base.update(overrides)
    return base


def _minimal_matrix(**overrides) -> dict:
    """Return a minimal valid ScenarioMatrixConfig dict."""
    base = dict(
        matrix_id="test_matrix_v1",
        input={"stream_path": "data/alpha_input_v1.jsonl"},
        scenarios=[_override_scenario()],
    )
    base.update(overrides)
    return base


# =============================================================================
# AlphaInputV1
# =============================================================================

@pytest.mark.unit
class TestAlphaInputV1:

    def test_valid_minimal(self):
        """Minimal required fields produce a valid model."""
        obj = AlphaInputV1(**_minimal_alpha_input())
        assert obj.symbol == "BTCUSDT"
        assert obj.price == 42000.5

    def test_defaults_applied(self):
        """Optional fields receive correct default values."""
        obj = AlphaInputV1(**_minimal_alpha_input())
        assert obj.tf_sec == 300
        assert obj.regime == "DEFAULT"
        assert obj.warmup_status == {}
        assert obj.source_verb == ""
        assert obj.source_trace_id == ""

    def test_valid_full(self):
        """All fields explicitly set."""
        obj = AlphaInputV1(**_minimal_alpha_input(
            tf_sec=60,
            regime="HIGH_VOLATILITY",
            warmup_status={"obi": True},
            source_verb="bar_close",
            source_trace_id="trace-abc-123",
        ))
        assert obj.tf_sec == 60
        assert obj.regime == "HIGH_VOLATILITY"
        assert obj.warmup_status == {"obi": True}
        assert obj.source_verb == "bar_close"

    def test_extra_field_forbidden(self):
        """Extra fields must be rejected (extra='forbid')."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            AlphaInputV1(**_minimal_alpha_input(unknown_field="bad"))

    def test_missing_required_field(self):
        """Omitting a required field raises ValidationError."""
        data = _minimal_alpha_input()
        del data["price"]
        with pytest.raises(ValidationError, match="price"):
            AlphaInputV1(**data)

    def test_price_must_be_positive(self):
        """price must be > 0."""
        with pytest.raises(ValidationError, match="price"):
            AlphaInputV1(**_minimal_alpha_input(price=0))
        with pytest.raises(ValidationError, match="price"):
            AlphaInputV1(**_minimal_alpha_input(price=-1.0))

    def test_symbol_min_length(self):
        """symbol must have min_length=1 (empty string rejected)."""
        with pytest.raises(ValidationError, match="symbol"):
            AlphaInputV1(**_minimal_alpha_input(symbol=""))

    def test_tf_sec_allows_live_tick_zero(self):
        """tf_sec=0 is valid for live-tick snapshots; negatives are rejected."""
        obj = AlphaInputV1(**_minimal_alpha_input(tf_sec=0))
        assert obj.tf_sec == 0
        with pytest.raises(ValidationError, match="tf_sec"):
            AlphaInputV1(**_minimal_alpha_input(tf_sec=-1))

    def test_roundtrip_serialization(self):
        """model_dump -> model_validate produces identical object."""
        original = AlphaInputV1(**_minimal_alpha_input(
            tf_sec=60, regime="TREND_UP",
        ))
        rebuilt = AlphaInputV1.model_validate(original.model_dump())
        assert rebuilt == original


# =============================================================================
# AlphaShadowResultV1
# =============================================================================

@pytest.mark.unit
class TestAlphaShadowResultV1:

    def test_valid_minimal(self):
        """Minimal construction with all required fields."""
        obj = AlphaShadowResultV1(**_minimal_shadow_result())
        assert obj.scenario_id == "S01_AURORA"
        assert obj.shadow is True

    def test_defaults_applied(self):
        """Check default values for optional fields."""
        obj = AlphaShadowResultV1(**_minimal_shadow_result())
        assert obj.why == []
        assert obj.features_used == []
        assert obj.shadow is True
        assert obj.regime == "DEFAULT"

    def test_extra_field_forbidden(self):
        """Extra fields rejected by extra='forbid'."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            AlphaShadowResultV1(**_minimal_shadow_result(rogue="x"))

    def test_score_out_of_bounds(self):
        """score must be in [-1.0, 1.0]."""
        with pytest.raises(ValidationError, match="score"):
            AlphaShadowResultV1(**_minimal_shadow_result(score=1.5))
        with pytest.raises(ValidationError, match="score"):
            AlphaShadowResultV1(**_minimal_shadow_result(score=-1.1))

    def test_confidence_out_of_bounds(self):
        """confidence must be in [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="confidence"):
            AlphaShadowResultV1(**_minimal_shadow_result(confidence=-0.01))
        with pytest.raises(ValidationError, match="confidence"):
            AlphaShadowResultV1(**_minimal_shadow_result(confidence=1.01))

    def test_roundtrip_serialization(self):
        """model_dump -> model_validate roundtrip."""
        original = AlphaShadowResultV1(**_minimal_shadow_result(
            why=["strong_signal"], features_used=["obi", "delta_price"],
        ))
        rebuilt = AlphaShadowResultV1.model_validate(original.model_dump())
        assert rebuilt == original


# =============================================================================
# ScenarioSpec
# =============================================================================

@pytest.mark.unit
class TestScenarioSpec:

    def test_valid_override_mode(self):
        """Override mode with base_refs is accepted."""
        obj = ScenarioSpec(**_override_scenario())
        assert obj.config_mode == "override"
        assert obj.base_refs is not None

    def test_valid_full_config_mode(self):
        """full_config mode with scenario_config_dir is accepted."""
        obj = ScenarioSpec(**_full_config_scenario())
        assert obj.config_mode == "full_config"
        assert obj.scenario_config_dir is not None

    def test_extra_field_forbidden(self):
        """Extra fields rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            ScenarioSpec(**_override_scenario(bogus=42))

    def test_override_requires_base_refs(self):
        """Override mode without base_refs triggers model_validator error."""
        with pytest.raises(ValidationError, match="override mode requires base_refs"):
            ScenarioSpec(**_override_scenario(base_refs=None))

    def test_full_config_requires_dir(self):
        """full_config mode without scenario_config_dir triggers error."""
        with pytest.raises(
            ValidationError,
            match="full_config mode requires scenario_config_dir",
        ):
            ScenarioSpec(**_full_config_scenario(scenario_config_dir=None))

    def test_invalid_strategy_type_literal(self):
        """strategy_type must be one of the allowed literals."""
        with pytest.raises(ValidationError, match="strategy_type"):
            ScenarioSpec(**_override_scenario(strategy_type="random_forest"))

    def test_scenario_id_min_length(self):
        """scenario_id must not be empty."""
        with pytest.raises(ValidationError, match="scenario_id"):
            ScenarioSpec(**_override_scenario(scenario_id=""))


# =============================================================================
# RuntimeConfig
# =============================================================================

@pytest.mark.unit
class TestRuntimeConfig:

    def test_all_defaults(self):
        """No arguments required; all fields have defaults."""
        obj = RuntimeConfig()
        assert obj.max_scenarios == 20
        assert obj.max_concurrent_scenarios == 20
        assert obj.parallelism == "thread_pool"
        assert obj.max_workers == 4
        assert obj.queue_maxsize == 4000
        assert obj.backpressure_policy == "drop_oldest"
        assert obj.memory_budget_mb_per_scenario == 50
        assert obj.scenario_timeout_sec == 5.0
        assert obj.health_heartbeat_sec == 30.0

    def test_extra_field_forbidden(self):
        """Extra fields rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            RuntimeConfig(gpu_enabled=True)

    def test_max_scenarios_upper_bound(self):
        """max_scenarios must be <= 50."""
        with pytest.raises(ValidationError, match="max_scenarios"):
            RuntimeConfig(max_scenarios=51)

    def test_max_scenarios_lower_bound(self):
        """max_scenarios must be >= 1."""
        with pytest.raises(ValidationError, match="max_scenarios"):
            RuntimeConfig(max_scenarios=0)

    def test_invalid_parallelism_literal(self):
        """parallelism must be 'sequential' or 'thread_pool'."""
        with pytest.raises(ValidationError, match="parallelism"):
            RuntimeConfig(parallelism="multiprocessing")


# =============================================================================
# HotReloadConfig
# =============================================================================

@pytest.mark.unit
class TestHotReloadConfig:

    def test_all_defaults(self):
        """All fields have sensible defaults."""
        obj = HotReloadConfig()
        assert obj.enabled is False
        assert obj.poll_interval_sec == 5.0
        assert obj.debounce_sec == 2.0
        assert obj.rollback_on_error is True

    def test_extra_field_forbidden(self):
        """Extra fields rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            HotReloadConfig(watch_dirs=["/tmp"])

    def test_poll_interval_bounds(self):
        """poll_interval_sec must be in [1.0, 60.0]."""
        with pytest.raises(ValidationError, match="poll_interval_sec"):
            HotReloadConfig(poll_interval_sec=0.5)
        with pytest.raises(ValidationError, match="poll_interval_sec"):
            HotReloadConfig(poll_interval_sec=61.0)


# =============================================================================
# InputConfig
# =============================================================================

@pytest.mark.unit
class TestInputConfig:

    def test_valid_defaults(self):
        """stream_path is required; source_mode defaults to 'replay'."""
        obj = InputConfig(stream_path="data/stream.jsonl")
        assert obj.source_mode == "replay"
        assert obj.stream_path == "data/stream.jsonl"

    def test_extra_field_forbidden(self):
        """Extra fields rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputConfig(stream_path="x.jsonl", batch_size=100)

    def test_invalid_source_mode_literal(self):
        """source_mode must be 'replay' or 'live_tail'."""
        with pytest.raises(ValidationError, match="source_mode"):
            InputConfig(stream_path="x.jsonl", source_mode="kafka")


# =============================================================================
# ScenarioMatrixConfig
# =============================================================================

@pytest.mark.unit
class TestScenarioMatrixConfig:

    def test_valid_minimal(self):
        """Minimal valid matrix config."""
        obj = ScenarioMatrixConfig(**_minimal_matrix())
        assert obj.matrix_id == "test_matrix_v1"
        assert obj.version == 2
        assert len(obj.scenarios) == 1

    def test_extra_field_forbidden(self):
        """Extra fields rejected at root level."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            ScenarioMatrixConfig(**_minimal_matrix(author="test"))

    def test_duplicate_scenario_ids_rejected(self):
        """Duplicate scenario_id values trigger model_validator error."""
        dup = _override_scenario()
        with pytest.raises(ValidationError, match="Duplicate scenario IDs"):
            ScenarioMatrixConfig(**_minimal_matrix(scenarios=[dup, dup]))

    def test_enabled_count_exceeds_max_scenarios(self):
        """More enabled scenarios than max_scenarios raises error."""
        scenarios = [
            _override_scenario(scenario_id=f"S{i:02d}_AURORA")
            for i in range(5)
        ]
        with pytest.raises(ValidationError, match="Enabled scenarios"):
            ScenarioMatrixConfig(**_minimal_matrix(
                runtime={"max_scenarios": 2},
                scenarios=scenarios,
            ))

    def test_scenarios_list_must_not_be_empty(self):
        """scenarios must have min_length=1."""
        with pytest.raises(ValidationError, match="scenarios"):
            ScenarioMatrixConfig(**_minimal_matrix(scenarios=[]))

    def test_roundtrip_serialization(self):
        """Full roundtrip through model_dump / model_validate."""
        original = ScenarioMatrixConfig(**_minimal_matrix(
            runtime={"max_workers": 8, "parallelism": "sequential"},
            hot_reload={"enabled": True, "poll_interval_sec": 10.0},
            scenarios=[
                _override_scenario(scenario_id="S01_A"),
                _full_config_scenario(scenario_id="S02_B"),
            ],
        ))
        rebuilt = ScenarioMatrixConfig.model_validate(original.model_dump())
        assert rebuilt == original
        assert rebuilt.runtime.max_workers == 8
        assert rebuilt.hot_reload.enabled is True
