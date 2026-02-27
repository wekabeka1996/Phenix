"""
Alpha Search Runtime Contracts
==============================

Pydantic strict models for:
- alpha_input_v1 (inbound feature snapshots)
- alpha_shadow_result_v1 (outbound score results)
- ScenarioMatrixConfig (matrix YAML schema v2)
- RuntimeConfig, HotReloadConfig (capacity / operations knobs)

All models use extra="forbid" for fail-closed validation.
"""

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


# =============================================================================
# Input Contract
# =============================================================================

class AlphaInputV1(BaseModel):
    """
    Strict schema for inbound feature snapshots.

    Consumed by IngestGateway from alpha_input_v1.jsonl stream
    (replay or live mirror).

    Required fields match the union of features needed by:
    - Aurora: obi, delta_price, macro_resid
    - MeanReversion: bb_position, bb_width, rsi_14, price_sma_20_deviation, stoch_k, stoch_d
    - Ensemble: union of enabled model required features

    The `features` dict carries all available features; each ScenarioWorker
    validates its own required subset (fail-closed).
    """

    model_config = ConfigDict(extra="forbid")

    ts_ms: int = Field(
        description="Epoch milliseconds when snapshot was created")
    symbol: str = Field(min_length=1, description="Trading pair, e.g. BTCUSDT")
    tf_sec: int = Field(default=300, ge=0,
                        description="Timeframe in seconds (300 = 5m bars, 0 = live tick)")
    bar_close_ts: int = Field(description="Bar close timestamp (epoch ms)")
    price: float = Field(gt=0, description="Current price at snapshot time")
    features: Dict[str, Any] = Field(
        description="Feature dict (strategy-specific subset required)")
    regime: str = Field(
        default="DEFAULT",
        description="Current regime: HIGH_VOLATILITY|LOW_VOLATILITY|MEAN_REVERSION|TREND_UP|TREND_DOWN|UNCERTAIN|DEFAULT",
    )
    warmup_status: Dict[str, bool] = Field(
        default_factory=dict,
        description="Per-feature warmup readiness flags",
    )
    source_verb: str = Field(
        default="", description="Origin event verb for tracing")
    source_trace_id: str = Field(
        default="", description="Trace ID for correlation")


# =============================================================================
# Output Contract
# =============================================================================

class AlphaShadowResultV1(BaseModel):
    """
    Strict schema for shadow scoring results.

    Written to per-scenario scores.jsonl and aggregate reporter.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    strategy_type: str
    ts_ms: int
    symbol: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    threshold: float
    side: str = Field(description="BUY|SELL|NEUTRAL")
    provider_id: str
    model_name: str
    why: List[str] = Field(default_factory=list)
    features_used: List[str] = Field(default_factory=list)
    shadow: bool = Field(
        default=True, description="Always True for shadow results")
    regime: str = Field(default="DEFAULT")


# =============================================================================
# Scenario Specification
# =============================================================================

class ScenarioSpec(BaseModel):
    """
    Single scenario definition in the matrix.

    Supports two config modes:
    - override: start from base_refs, apply dot-path overrides
    - full_config: load full config files from scenario_config_dir
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(
        min_length=1,
        description="Unique ID, e.g. S01_AURORA_BASELINE",
    )
    enabled: bool = True
    strategy_type: Literal["aurora", "mean_reversion", "ensemble"] = Field(
        description="Strategy family for this scenario",
    )
    config_mode: Literal["override", "full_config"] = Field(
        description="override = dot-path deltas; full_config = full YAML files",
    )

    # For full_config mode
    scenario_config_dir: Optional[str] = Field(
        default=None,
        description="Directory with full config files (for full_config mode)",
    )

    # For override mode
    base_refs: Optional[Dict[str, str]] = Field(
        default=None,
        description="Base config file refs keyed by name (for override mode)",
    )
    overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Dot-path -> value overrides (for override mode)",
    )

    @model_validator(mode="after")
    def validate_config_mode_fields(self):
        """Ensure required fields present for each config mode."""
        if self.config_mode == "full_config":
            if not self.scenario_config_dir:
                raise ValueError(
                    f"Scenario {self.scenario_id}: full_config mode requires scenario_config_dir"
                )
        elif self.config_mode == "override":
            if not self.base_refs:
                raise ValueError(
                    f"Scenario {self.scenario_id}: override mode requires base_refs"
                )
        return self


# =============================================================================
# Runtime Configuration
# =============================================================================

class RuntimeConfig(BaseModel):
    """Runtime capacity and parallelism knobs."""

    model_config = ConfigDict(extra="forbid")

    max_scenarios: int = Field(default=20, ge=1, le=50)
    max_concurrent_scenarios: int = Field(default=20, ge=1, le=50)
    parallelism: Literal["sequential", "thread_pool"] = Field(
        default="thread_pool",
        description="sequential for debugging, thread_pool for production",
    )
    max_workers: int = Field(default=4, ge=1, le=32)
    queue_maxsize: int = Field(default=4000, ge=100, le=100_000)
    backpressure_policy: Literal["drop_oldest", "drop_newest", "block"] = Field(
        default="drop_oldest",
        description="Queue overflow policy: drop_oldest (live), block (replay)",
    )
    memory_budget_mb_per_scenario: int = Field(default=50, ge=10, le=500)
    scenario_timeout_sec: float = Field(default=5.0, ge=0.5, le=60.0)
    health_heartbeat_sec: float = Field(default=30.0, ge=5.0, le=300.0)


class HotReloadConfig(BaseModel):
    """Hot reload configuration for live shadow sessions."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False)
    poll_interval_sec: float = Field(default=5.0, ge=1.0, le=60.0)
    debounce_sec: float = Field(default=2.0, ge=0.5, le=30.0)
    rollback_on_error: bool = Field(default=True)


class InputConfig(BaseModel):
    """Input stream configuration."""

    model_config = ConfigDict(extra="forbid")

    source_mode: Literal["replay", "live_tail"] = Field(
        default="replay",
        description="replay = read JSONL file; live_tail = follow growing file",
    )
    stream_path: str = Field(
        description="Path to alpha_input_v1.jsonl stream",
    )


# =============================================================================
# Root Matrix Config
# =============================================================================

class ScenarioMatrixConfig(BaseModel):
    """
    Root schema for config/alpha_search/scenario_matrix.yaml.

    Single Source of Truth for all alpha search shadow scenarios.
    """

    model_config = ConfigDict(extra="forbid")

    matrix_id: str = Field(
        description="Human-readable identifier for this matrix version")
    version: int = Field(default=2, ge=1)

    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    hot_reload: HotReloadConfig = Field(default_factory=HotReloadConfig)
    input: InputConfig = Field(description="Input stream configuration")
    scenarios: List[ScenarioSpec] = Field(
        min_length=1,
        description="List of scenario specifications",
    )

    @model_validator(mode="after")
    def validate_scenario_count(self):
        """Validate scenario count within runtime limits."""
        enabled = [s for s in self.scenarios if s.enabled]
        if len(enabled) > self.runtime.max_scenarios:
            raise ValueError(
                f"Enabled scenarios ({len(enabled)}) exceeds max_scenarios ({self.runtime.max_scenarios})"
            )
        return self

    @model_validator(mode="after")
    def validate_unique_ids(self):
        """Ensure all scenario IDs are unique."""
        ids = [s.scenario_id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            dupes = [sid for sid in ids if ids.count(sid) > 1]
            raise ValueError(f"Duplicate scenario IDs: {set(dupes)}")
        return self
