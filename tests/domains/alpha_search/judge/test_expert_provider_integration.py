"""
LLM Judge Phase 2 — DEFECT-P2-01 Expert Provider Integration Tests

End-to-end tests proving:
1. Judge expert providers go through bridge → EVT:JUDGE_EXPERT_PRODUCED_V1
2. Judge expert providers do NOT emit EVT:ALPHA_SCORE_CALCULATED
3. JSONL shadow log is written when enabled
4. Non-judge providers still emit EVT:ALPHA_SCORE_CALCULATED unchanged
5. No regression to existing provider behavior
"""

import json
import os
import tempfile
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.alpha_search.alpha_model import AlphaModel, AlphaScore
from apps.reference.domains.alpha_search.backtest_plugin import (
    AlphaSearchBacktestPlugin,
    FeatureCacheEntry,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    JudgeExpertProviderConfig,
    ProviderConfig,
    TriggersConfig,
    CacheConfig,
    VirtualTraderConfig,
    load_alpha_search_config,
)
from apps.reference.domains.alpha_search.judge.config_models import (
    ChamberConfig,
    ConfidenceLadderTier,
    JudgeCortexConfig,
    JudgeExpertsConfig,
    JudgeShadowLogConfig,
    ShadowPlanConfig,
    SignalWeightsExpertConfig,
    FeatureNeutralsExpertConfig,
    VerdictConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    ShadowEntryPlan,
    JudgeVerdict,
)
from apps.reference.domains.alpha_search.judge.chamber import ChamberAggregator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_WEIGHTS = {
    "obi": 0.42,
    "delta_price": 0.15,
    "ema_bias": 0.15,
}

MINIMAL_NEUTRALS = {
    "obi": 0.0,
    "delta_price": 0.0,
    "ema_bias": 0.5,
}

FEATURES_BULLISH = {
    "obi": 0.6,
    "tfi": 0.2,
    "delta_price": 0.3,
    "ema_bias": 0.9,
    "macro_resid": 0.2,
    "volume_spike": 0.1,
    "volatility_state": 0.1,
    "close": 50000.0,
}


class StubEventBus:
    """Minimal event bus that records emitted events."""

    def __init__(self):
        self.emitted: list = []
        self._listeners: dict = {}

    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append(
            {"event": event_name, "payload": payload, "why": why})

    def listen(self, event_name: str, handler):
        self._listeners.setdefault(event_name, []).append(handler)


def _make_signal_weights_expert_config(*, enabled=True):
    return SignalWeightsExpertConfig(
        enabled=enabled,
        expert_id="judge.signal_weights_v1",
        expert_version="1.0.0",
        signal_threshold=0.162,
        min_active_features=1,
        signal_weights=MINIMAL_WEIGHTS,
        feature_neutrals=MINIMAL_NEUTRALS,
        essential_features=[],
    )


def _make_feature_neutrals_expert_config(*, enabled=True):
    return FeatureNeutralsExpertConfig(
        enabled=enabled,
        expert_id="judge.feature_neutrals_v1",
        expert_version="1.0.0",
        signal_threshold=0.162,
        min_active_directional_features=1,
        signal_weights=MINIMAL_WEIGHTS,
        feature_neutrals=MINIMAL_NEUTRALS,
        essential_features=[],
        directional_features=["obi", "delta_price", "ema_bias"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
    )


def _make_shadow_plan_config() -> ShadowPlanConfig:
    return ShadowPlanConfig(
        enabled=True,
        confidence_ladder=[
            ConfidenceLadderTier(
                name="low",
                min_confidence=0.20,
                limit_offset_bps=0,
                tp_offset_pct=0.010,
                sl_offset_pct=0.006,
            ),
            ConfidenceLadderTier(
                name="medium",
                min_confidence=0.35,
                limit_offset_bps=3,
                tp_offset_pct=0.015,
                sl_offset_pct=0.008,
            ),
            ConfidenceLadderTier(
                name="high",
                min_confidence=0.50,
                limit_offset_bps=5,
                tp_offset_pct=0.020,
                sl_offset_pct=0.010,
            ),
        ],
    )


def _make_config(
    *,
    judge_mode="shadow",
    judge_enabled=False,
    shadow_log_enabled=True,
    shadow_log_dir="logs/judge_experts",
    include_aurora=False,
    sw_enabled=True,
    fn_enabled=False,
    chamber=None,
    verdict=None,
):
    """Build an AlphaSearchConfig with judge expert providers.

    chamber: None → no chamber block; pass ChamberConfig() for defaults.
    verdict: None → no verdict block; pass VerdictConfig() for defaults.
    """
    providers = {}

    if sw_enabled:
        providers["judge_sw"] = ProviderConfig(
            enabled=True,
            threshold=0.162,
            judge_expert=JudgeExpertProviderConfig(
                expert_type="signal_weights"),
        )

    if fn_enabled:
        providers["judge_fn"] = ProviderConfig(
            enabled=True,
            threshold=0.162,
            judge_expert=JudgeExpertProviderConfig(
                expert_type="feature_neutrals"),
        )

    if include_aurora:
        # Minimal aurora adapter stub — uses default adapter config
        providers["aurora"] = ProviderConfig(
            enabled=True,
            threshold=0.2,
            adapter={"scoring_version": "quadratic"},
        )

    judge_cfg = JudgeCortexConfig(
        enabled=judge_enabled,
        mode=judge_mode,
        experts=JudgeExpertsConfig(
            signal_weights=_make_signal_weights_expert_config(
                enabled=sw_enabled),
            feature_neutrals=_make_feature_neutrals_expert_config(
                enabled=fn_enabled),
        ),
        shadow_log=JudgeShadowLogConfig(
            enabled=shadow_log_enabled,
            log_dir=shadow_log_dir,
        ),
        chamber=chamber,
        verdict=verdict,
    )

    return AlphaSearchConfig(
        enabled=True,
        shadow_mode=True,
        triggers=TriggersConfig(),
        cache=CacheConfig(),
        providers=providers,
        virtual_trader=VirtualTraderConfig(enabled=False),
        judge=judge_cfg,
    )


def _load_repo_shadow_config(
    *,
    judge_enabled=True,
    judge_mode="shadow",
    sw_enabled=True,
    fn_enabled=True,
    shadow_log_enabled=False,
    shadow_log_dir="logs/judge_experts",
):
    cfg = load_alpha_search_config("config/alpha_search.yaml")
    raw = cfg.model_dump()
    raw["virtual_trader"]["enabled"] = False
    raw["judge"]["enabled"] = judge_enabled
    raw["judge"]["mode"] = judge_mode
    raw["judge"]["shadow_log"]["enabled"] = shadow_log_enabled
    raw["judge"]["shadow_log"]["log_dir"] = shadow_log_dir
    raw["judge"]["experts"]["signal_weights"]["enabled"] = sw_enabled
    raw["judge"]["experts"]["feature_neutrals"]["enabled"] = fn_enabled
    return AlphaSearchConfig.model_validate(raw)


def _inject_cache_entry(plugin, symbol="BTCUSDT", tf_sec=300, bar_close_ts=1700000000000):
    """Inject a cache entry with bullish features."""
    key = (symbol, tf_sec, bar_close_ts)
    plugin._feature_cache[key] = FeatureCacheEntry(
        symbol=symbol,
        tf_sec=tf_sec,
        bar_close_ts=bar_close_ts,
        features=dict(FEATURES_BULLISH),
        ts=bar_close_ts,
        price=50000.0,
    )
    return key


def _inject_custom_cache_entry(
    plugin,
    *,
    features,
    symbol="BTCUSDT",
    tf_sec=300,
    bar_close_ts=1700000000000,
    price=50000.0,
):
    """Inject a cache entry with explicit feature payload."""
    key = (symbol, tf_sec, bar_close_ts)
    plugin._feature_cache[key] = FeatureCacheEntry(
        symbol=symbol,
        tf_sec=tf_sec,
        bar_close_ts=bar_close_ts,
        features=dict(features),
        ts=bar_close_ts,
        price=price,
    )
    return key


def _fire_decision(plugin, symbol="BTCUSDT", tf_sec=300, bar_close_ts=1700000000000):
    """Simulate CMD:PROCESS_STRATEGY by calling the decision handler directly."""
    event = {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
    }
    plugin._on_decision_score(event)


# ---------------------------------------------------------------------------
# Test: Judge expert emits EVT:JUDGE_EXPERT_PRODUCED_V1
# ---------------------------------------------------------------------------


class TestJudgeExpertEmitsCorrectEvent:
    def test_signal_weights_emits_judge_event(self):
        """signal_weights provider emits EVT:JUDGE_EXPERT_PRODUCED_V1."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow", sw_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        judge_events = [e for e in bus.emitted if e["event"]
                        == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
        assert len(
            judge_events) == 1, f"Expected 1 judge event, got {len(judge_events)}"

        payload = judge_events[0]["payload"]
        assert payload["expert_id"] == "judge.signal_weights_v1"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["schema_version"] == "1"

    def test_feature_neutrals_emits_judge_event(self):
        """feature_neutrals provider emits EVT:JUDGE_EXPERT_PRODUCED_V1."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow",
                           sw_enabled=False, fn_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        judge_events = [e for e in bus.emitted if e["event"]
                        == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
        assert len(judge_events) == 1
        assert judge_events[0]["payload"]["expert_id"] == "judge.feature_neutrals_v1"


# ---------------------------------------------------------------------------
# Test: Judge expert does NOT emit EVT:ALPHA_SCORE_CALCULATED
# ---------------------------------------------------------------------------


class TestJudgeExpertSuppressesAlphaScore:
    def test_signal_weights_no_alpha_score_event(self):
        """signal_weights provider must NOT emit EVT:ALPHA_SCORE_CALCULATED."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow", sw_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        alpha_events = [e for e in bus.emitted if e["event"]
                        == "EVT:ALPHA_SCORE_CALCULATED"]
        assert len(alpha_events) == 0, (
            f"Judge expert leaked into ALPHA_SCORE_CALCULATED: {alpha_events}"
        )

    def test_feature_neutrals_no_alpha_score_event(self):
        """feature_neutrals provider must NOT emit EVT:ALPHA_SCORE_CALCULATED."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow",
                           sw_enabled=False, fn_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        alpha_events = [e for e in bus.emitted if e["event"]
                        == "EVT:ALPHA_SCORE_CALCULATED"]
        assert len(alpha_events) == 0


# ---------------------------------------------------------------------------
# Test: Bridge produces valid ExpertOutput payload
# ---------------------------------------------------------------------------


class TestBridgeProducesValidExpertOutput:
    def test_judge_event_payload_is_valid_expert_output(self):
        """EVT:JUDGE_EXPERT_PRODUCED_V1 payload deserializes to ExpertOutput."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow", sw_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        judge_events = [e for e in bus.emitted if e["event"]
                        == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
        assert len(judge_events) == 1
        payload = judge_events[0]["payload"]
        # Must deserialize without error
        eo = ExpertOutput(**payload)
        assert eo.expert_id == "judge.signal_weights_v1"
        assert eo.expert_version == "1.0.0"
        assert eo.entry_verdict in (
            "OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "UNKNOWN")
        assert eo.cycle_key == "ENTRY:BTCUSDT:300:1700000000000"
        assert eo.schema_version == "1"


class TestEntryEdgeBranchRuntimeProof:
    def test_entry_unknown_runtime_branch_from_deferred_essential_feature(self):
        """Entry expert emits UNKNOWN when an essential feature is present-but-None."""
        bus = StubEventBus()
        cfg = AlphaSearchConfig(
            enabled=True,
            shadow_mode=True,
            triggers=TriggersConfig(),
            cache=CacheConfig(),
            providers={
                "judge_sw": ProviderConfig(
                    enabled=True,
                    threshold=0.162,
                    judge_expert=JudgeExpertProviderConfig(
                        expert_type="signal_weights"
                    ),
                ),
            },
            virtual_trader=VirtualTraderConfig(enabled=False),
            judge=JudgeCortexConfig(
                enabled=True,
                mode="shadow",
                experts=JudgeExpertsConfig(
                    signal_weights=SignalWeightsExpertConfig(
                        enabled=True,
                        expert_id="judge.signal_weights_v1",
                        expert_version="1.0.0",
                        signal_threshold=0.162,
                        signal_weights=MINIMAL_WEIGHTS,
                        feature_neutrals=MINIMAL_NEUTRALS,
                        essential_features=["obi"],
                    ),
                    feature_neutrals=_make_feature_neutrals_expert_config(
                        enabled=False
                    ),
                ),
                chamber=ChamberConfig(),
                verdict=VerdictConfig(),
                shadow_log=JudgeShadowLogConfig(enabled=False),
            ),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_custom_cache_entry(
            plugin,
            features={
                **FEATURES_BULLISH,
                "obi": None,
            },
        )
        _fire_decision(plugin)

        judge_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_EXPERT_PRODUCED_V1"
        ]
        assert len(judge_events) == 1
        expert_payload = judge_events[0]["payload"]
        assert expert_payload["entry_verdict"] == "UNKNOWN"
        assert expert_payload["signal_direction"] == "NEUTRAL"
        assert expert_payload["reasoning"][0].startswith(
            "authoritative_entry_verdict:UNKNOWN"
        )
        assert "DEFER:obi" in expert_payload["reasoning"]

        chamber_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"
            and e["payload"].get("verdict_scope") == "ENTRY"
        ]
        assert len(chamber_events) == 1
        chamber_payload = chamber_events[0]["payload"]
        assert chamber_payload["expert_count"] == 1
        assert chamber_payload["responding_count"] == 0
        assert chamber_payload["abstaining_count"] == 1
        assert chamber_payload["admissibility"] == "QUORUM_INSUFFICIENT"
        assert chamber_payload["admissibility_reason"] == "responding_below_min_quorum"

        verdict_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"
        ]
        assert len(verdict_events) == 1
        verdict_payload = verdict_events[0]["payload"]
        assert verdict_payload["entry_verdict"] == "UNKNOWN"
        assert verdict_payload["authority_mode"] == "shadow"
        assert verdict_payload["applied"] is False

    def test_entry_unknown_runtime_branch_from_insufficient_active_features(self):
        """Entry expert abstains when active weighted evidence is below config floor."""
        bus = StubEventBus()
        cfg = AlphaSearchConfig(
            enabled=True,
            shadow_mode=True,
            triggers=TriggersConfig(),
            cache=CacheConfig(),
            providers={
                "judge_sw": ProviderConfig(
                    enabled=True,
                    threshold=0.162,
                    judge_expert=JudgeExpertProviderConfig(
                        expert_type="signal_weights"
                    ),
                ),
            },
            virtual_trader=VirtualTraderConfig(enabled=False),
            judge=JudgeCortexConfig(
                enabled=True,
                mode="shadow",
                experts=JudgeExpertsConfig(
                    signal_weights=SignalWeightsExpertConfig(
                        enabled=True,
                        expert_id="judge.signal_weights_v1",
                        expert_version="1.0.0",
                        signal_threshold=0.162,
                        min_active_features=3,
                        signal_weights=MINIMAL_WEIGHTS,
                        feature_neutrals=MINIMAL_NEUTRALS,
                        essential_features=["obi"],
                    ),
                    feature_neutrals=_make_feature_neutrals_expert_config(
                        enabled=False
                    ),
                ),
                chamber=ChamberConfig(),
                verdict=VerdictConfig(),
                shadow_log=JudgeShadowLogConfig(enabled=False),
            ),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_custom_cache_entry(
            plugin,
            features={
                "obi": 0.6,
                "delta_price": None,
                "ema_bias": 0.9,
                "macro_resid": 0.2,
            },
        )
        _fire_decision(plugin)

        judge_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_EXPERT_PRODUCED_V1"
        ]
        assert len(judge_events) == 1
        expert_payload = judge_events[0]["payload"]
        assert expert_payload["entry_verdict"] == "UNKNOWN"
        assert "NRR-INSUFFICIENT-ACTIVE-FEATURES:2/3" in expert_payload["reasoning"]

        chamber_payload = next(
            e["payload"]
            for e in bus.emitted
            if e["event"] == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"
            and e["payload"].get("verdict_scope") == "ENTRY"
        )
        assert chamber_payload["admissibility"] == "QUORUM_INSUFFICIENT"
        assert chamber_payload["admissibility_reason"] == "responding_below_min_quorum"

        verdict_payload = next(
            e["payload"]
            for e in bus.emitted
            if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"
        )
        assert verdict_payload["entry_verdict"] == "UNKNOWN"
        assert verdict_payload["suppression_reason"] is None
        assert verdict_payload["applied"] is False


# ---------------------------------------------------------------------------
# Test: JSONL shadow log written when enabled
# ---------------------------------------------------------------------------


class TestJSONLShadowLog:
    def test_jsonl_log_written_when_enabled(self):
        """JSONL file must be created with one line when shadow_log.enabled=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                shadow_log_enabled=True,
                shadow_log_dir=tmpdir,
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            # Find JSONL files
            jsonl_files = [f for f in os.listdir(
                tmpdir) if f.endswith(".jsonl")]
            assert len(jsonl_files) >= 1, f"No JSONL files in {tmpdir}"

            # Read and validate
            with open(os.path.join(tmpdir, jsonl_files[0]), "r") as f:
                lines = f.readlines()
            assert len(lines) == 1
            record = json.loads(lines[0])
            assert record["expert_id"] == "judge.signal_weights_v1"
            assert record["symbol"] == "BTCUSDT"
            assert record["cycle_key"] == "ENTRY:BTCUSDT:300:1700000000000"

    def test_jsonl_log_not_written_when_disabled(self):
        """No JSONL file when shadow_log.enabled=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                shadow_log_enabled=False,
                shadow_log_dir=tmpdir,
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            jsonl_files = [f for f in os.listdir(
                tmpdir) if f.endswith(".jsonl")]
            assert len(
                jsonl_files) == 0, f"Unexpected JSONL files: {jsonl_files}"

    def test_jsonl_log_multiple_symbols(self):
        """Separate JSONL files per symbol."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                shadow_log_enabled=True,
                shadow_log_dir=tmpdir,
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

            ts1 = 1700000000000
            ts2 = 1700000300000  # different bar
            _inject_cache_entry(plugin, symbol="BTCUSDT", bar_close_ts=ts1)
            _inject_cache_entry(plugin, symbol="ETHUSDT", bar_close_ts=ts2)
            _fire_decision(plugin, symbol="BTCUSDT", bar_close_ts=ts1)
            _fire_decision(plugin, symbol="ETHUSDT", bar_close_ts=ts2)

            # Both must have produced judge events
            judge_events = [e for e in bus.emitted if e["event"]
                            == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
            assert len(
                judge_events) == 2, f"Expected 2 judge events, got {judge_events}"

            jsonl_files = [f for f in os.listdir(
                tmpdir) if f.endswith(".jsonl")]
            assert len(
                jsonl_files) == 2, f"Expected 2 JSONL files, got {jsonl_files}"


# ---------------------------------------------------------------------------
# Test: Non-judge providers still use EVT:ALPHA_SCORE_CALCULATED
# ---------------------------------------------------------------------------


class DummyAuroraModel(AlphaModel):
    """Trivial non-judge model for testing."""

    def get_model_name(self) -> str:
        return "dummy_aurora"

    def calculate_alpha(self, symbol, market_data, features, context=None):
        return AlphaScore(
            model_name="dummy_aurora",
            symbol=symbol,
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            features_used=["obi"],
            why=["dummy"],
        )


class TestNonJudgeProviderUnchanged:
    def test_non_judge_provider_emits_alpha_score_calculated(self):
        """Non-judge provider still emits EVT:ALPHA_SCORE_CALCULATED."""
        bus = StubEventBus()
        cfg = AlphaSearchConfig(
            enabled=True,
            shadow_mode=True,
            providers={
                "dummy": ProviderConfig(enabled=True, threshold=0.1),
            },
            virtual_trader=VirtualTraderConfig(enabled=False),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        # Manually inject a dummy model (bypasses factory)
        plugin.providers["dummy"] = DummyAuroraModel()
        plugin.provider_configs["dummy"] = cfg.providers["dummy"]
        plugin.provider_stats["dummy"] = __import__(
            "apps.reference.domains.alpha_search.backtest_plugin",
            fromlist=["ProviderStats"],
        ).ProviderStats()

        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        alpha_events = [e for e in bus.emitted if e["event"]
                        == "EVT:ALPHA_SCORE_CALCULATED"]
        judge_events = [e for e in bus.emitted if e["event"]
                        == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
        assert len(
            alpha_events) == 1, "Non-judge provider must emit ALPHA_SCORE_CALCULATED"
        assert len(
            judge_events) == 0, "Non-judge provider must NOT emit JUDGE_EXPERT_PRODUCED"


# ---------------------------------------------------------------------------
# Test: Mixed providers — judge + non-judge in same plugin
# ---------------------------------------------------------------------------


class TestMixedProviders:
    def test_mixed_judge_and_nonjudge(self):
        """With both judge and non-judge providers, each uses correct event."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow", sw_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        # Add a non-judge dummy provider
        dummy_cfg = ProviderConfig(enabled=True, threshold=0.1)
        plugin.providers["dummy"] = DummyAuroraModel()
        plugin.provider_configs["dummy"] = dummy_cfg
        plugin.provider_stats["dummy"] = __import__(
            "apps.reference.domains.alpha_search.backtest_plugin",
            fromlist=["ProviderStats"],
        ).ProviderStats()
        plugin.open_positions["dummy"] = []
        plugin.closed_positions["dummy"] = []

        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        alpha_events = [e for e in bus.emitted if e["event"]
                        == "EVT:ALPHA_SCORE_CALCULATED"]
        judge_events = [e for e in bus.emitted if e["event"]
                        == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
        assert len(alpha_events) == 1, "Dummy must emit ALPHA_SCORE_CALCULATED"
        assert len(judge_events) == 1, "Judge must emit JUDGE_EXPERT_PRODUCED_V1"
        assert alpha_events[0]["payload"]["provider_id"] == "dummy"
        assert judge_events[0]["payload"]["expert_id"] == "judge.signal_weights_v1"


# ---------------------------------------------------------------------------
# Test: Judge mode off → no judge providers initialized
# ---------------------------------------------------------------------------


class TestJudgeModeOff:
    def test_judge_off_skips_expert_providers(self):
        """When judge mode='off', expert providers are not created."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="off", sw_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        # No providers should be created because judge mode is off
        assert "judge_sw" not in plugin.providers


class TestRepoResidentShadowActivation:
    def test_repo_config_opt_in_initializes_judge_providers(self):
        bus = StubEventBus()
        cfg = _load_repo_shadow_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        assert {"judge_sw", "judge_fn"}.issubset(plugin.providers.keys())
        assert plugin.provider_configs["judge_sw"].judge_expert is not None
        assert plugin.provider_configs["judge_sw"].judge_expert.expert_type == "signal_weights"
        assert plugin.provider_configs["judge_fn"].judge_expert is not None
        assert plugin.provider_configs["judge_fn"].judge_expert.expert_type == "feature_neutrals"

    def test_repo_config_opt_in_emits_full_shadow_chain_with_aligned_timestamps(self):
        bar_close_ts = 1700000000000
        bus = StubEventBus()
        cfg = _load_repo_shadow_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin, bar_close_ts=bar_close_ts)
        _fire_decision(plugin, bar_close_ts=bar_close_ts)

        judge_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_EXPERT_PRODUCED_V1"
        ]
        assert len(judge_events) == 2
        expert_outputs = [ExpertOutput(**e["payload"]) for e in judge_events]
        assert {eo.expert_id for eo in expert_outputs} == {
            "judge.signal_weights_v1",
            "judge.feature_neutrals_v1",
        }
        assert all(eo.ts_ms == bar_close_ts for eo in expert_outputs)

        chamber_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"
            and e["payload"].get("verdict_scope") == "ENTRY"
        ]
        env_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_EVIDENCE_ASSEMBLED_V1"
        ]
        verdict_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"
        ]
        alpha_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:ALPHA_SCORE_CALCULATED"
        ]

        assert len(chamber_events) == 1
        assert len(env_events) == 1
        assert len(verdict_events) == 1
        assert alpha_events

        chamber = ChamberAggregate(**chamber_events[0]["payload"])
        envelope = JudgeEvidenceEnvelope(**env_events[0]["payload"])
        verdict = JudgeVerdict(**verdict_events[0]["payload"])

        assert chamber.ts_ms == bar_close_ts
        assert envelope.ts_ms == bar_close_ts
        assert envelope.chamber_aggregate.ts_ms == bar_close_ts
        assert verdict.ts_ms == bar_close_ts
        assert chamber.cycle_key == f"ENTRY:BTCUSDT:300:{bar_close_ts}"
        assert envelope.cycle_key == f"ENTRY:BTCUSDT:300:{bar_close_ts}"
        assert verdict.cycle_key == f"ENTRY:BTCUSDT:300:{bar_close_ts}"
        assert envelope.features_ref == f"bar:BTCUSDT:300:{bar_close_ts}"
        assert envelope.chamber_aggregate.chamber_id == chamber.chamber_id
        assert verdict.chamber_id == chamber.chamber_id
        assert all(
            e["payload"]["provider_id"] in {"aurora", "ta_ensemble"}
            for e in alpha_events
        )


# ---------------------------------------------------------------------------
# Test: Both experts in one run
# ---------------------------------------------------------------------------


class TestBothExpertsSimultaneous:
    def test_both_experts_emit_separate_judge_events(self):
        """signal_weights + feature_neutrals both emit separate judge events."""
        bus = StubEventBus()
        cfg = _make_config(judge_mode="shadow",
                           sw_enabled=True, fn_enabled=True)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        judge_events = [e for e in bus.emitted if e["event"]
                        == "EVT:JUDGE_EXPERT_PRODUCED_V1"]
        alpha_events = [e for e in bus.emitted if e["event"]
                        == "EVT:ALPHA_SCORE_CALCULATED"]
        assert len(
            judge_events) == 2, f"Expected 2 judge events, got {len(judge_events)}"
        assert len(alpha_events) == 0, "No alpha events from judge experts"

        expert_ids = {e["payload"]["expert_id"] for e in judge_events}
        assert "judge.signal_weights_v1" in expert_ids
        assert "judge.feature_neutrals_v1" in expert_ids


# ---------------------------------------------------------------------------
# Test: Chamber event emitted after provider loop (Phase 3)
# ---------------------------------------------------------------------------


class TestChamberEventEmitted:
    def test_entry_chamber_event_emitted_shadow(self):
        """EVT:JUDGE_CHAMBER_AGGREGATED_V1 emitted when both experts run."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        chamber_events = [e for e in bus.emitted if e["event"]
                          == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"]
        assert len(chamber_events) >= 1, (
            f"Expected at least 1 chamber event, got {len(chamber_events)}"
        )
        # Entry chamber must be among them
        entry_events = [e for e in chamber_events
                        if e["payload"].get("verdict_scope") == "ENTRY"]
        assert len(entry_events) == 1

    def test_no_chamber_event_without_chamber_config(self):
        """Without chamber config, no chamber event emitted."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow", sw_enabled=True, chamber=None)
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        chamber_events = [e for e in bus.emitted if e["event"]
                          == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"]
        assert len(chamber_events) == 0

    def test_single_expert_still_triggers_chamber(self):
        """Even one expert triggers chamber aggregation."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=False,
            chamber=ChamberConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        chamber_events = [e for e in bus.emitted if e["event"]
                          == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"]
        assert len(chamber_events) >= 1


# ---------------------------------------------------------------------------
# Test: Chamber payload is valid ChamberAggregate
# ---------------------------------------------------------------------------


class TestChamberPayloadValid:
    def test_chamber_payload_deserializes_to_aggregate(self):
        """Chamber event payload round-trips through ChamberAggregate."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        chamber_events = [e for e in bus.emitted if e["event"]
                          == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"]
        assert len(chamber_events) >= 1
        payload = chamber_events[0]["payload"]

        agg = ChamberAggregate(**payload)
        assert agg.verdict_scope in ("ENTRY", "LIFECYCLE")
        assert agg.symbol == "BTCUSDT"
        assert agg.expert_count >= 1
        assert agg.responding_count + agg.abstaining_count == agg.expert_count
        assert agg.cycle_key == "ENTRY:BTCUSDT:300:1700000000000"

    def test_entry_chamber_reflects_both_experts(self):
        """Entry chamber with 2 experts: expert_count=2, both responding."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        entry_events = [e for e in bus.emitted
                        if e["event"] == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"
                        and e["payload"].get("verdict_scope") == "ENTRY"]
        assert len(entry_events) == 1
        p = entry_events[0]["payload"]
        assert p["expert_count"] == 2
        assert p["responding_count"] == 2
        assert p["admissibility"] == "ADMISSIBLE"


# ---------------------------------------------------------------------------
# Test: Lifecycle stub when explicitly enabled
# ---------------------------------------------------------------------------


class TestLifecycleStubEnabled:
    def test_lifecycle_event_emitted_when_enabled(self):
        """lifecycle_enabled=True → lifecycle chamber event emitted."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(lifecycle_enabled=True),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        chamber_events = [e for e in bus.emitted if e["event"]
                          == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"]
        lifecycle_events = [e for e in chamber_events
                            if e["payload"].get("verdict_scope") == "LIFECYCLE"]
        assert len(lifecycle_events) == 1, (
            f"Expected lifecycle stub event, got {len(lifecycle_events)}"
        )
        p = lifecycle_events[0]["payload"]
        assert p["expert_count"] == 0
        assert p["responding_count"] == 0
        assert p["admissibility"] == "QUORUM_INSUFFICIENT"
        assert p["admissibility_reason"] == "responding_below_min_quorum"


# ---------------------------------------------------------------------------
# Test: Lifecycle NOT emitted by default
# ---------------------------------------------------------------------------


class TestLifecycleStubDisabledByDefault:
    def test_no_lifecycle_event_when_disabled(self):
        """Default lifecycle_enabled=False → no lifecycle chamber event."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),  # lifecycle_enabled=False by default
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        chamber_events = [e for e in bus.emitted if e["event"]
                          == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"]
        lifecycle_events = [e for e in chamber_events
                            if e["payload"].get("verdict_scope") == "LIFECYCLE"]
        assert len(lifecycle_events) == 0


# ---------------------------------------------------------------------------
# Test: Roster-truth when an expert fails closed
# ---------------------------------------------------------------------------


class TestChamberRosterTruth:
    def test_roster_reflects_solicited_not_returned(self):
        """Both experts solicited, feature_neutrals disabled → expert_count
        still 2 from roster, responding_count 1, abstaining_count 1."""
        bus = StubEventBus()
        # Both providers declared in config...
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        # ...but sabotage fn expert so it returns None
        # Remove the fn provider entirely to simulate crash
        if "judge_fn" in plugin.providers:
            del plugin.providers["judge_fn"]

        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        entry_events = [e for e in bus.emitted
                        if e["event"] == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"
                        and e["payload"].get("verdict_scope") == "ENTRY"]
        assert len(entry_events) == 1
        p = entry_events[0]["payload"]
        # Roster solicited 2 experts even though only 1 returned
        assert p["expert_count"] == 2
        assert p["responding_count"] == 1
        assert p["abstaining_count"] == 1
        assert p["admissibility"] == "INADMISSIBLE"
        assert p["admissibility_reason"] == "solicited_expert_missing_output"

        verdict_events = [e for e in bus.emitted
                          if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"]
        assert len(verdict_events) == 1
        verdict_payload = verdict_events[0]["payload"]
        assert verdict_payload["entry_verdict"] == "SUPPRESS"
        assert (
            verdict_payload["suppression_reason"]
            == "entry_chamber_inadmissible:solicited_expert_missing_output"
        )
        assert verdict_payload["suppression_code"] == "ENTRY_CHAMBER_MISSING_OUTPUT"
        assert verdict_payload["applied"] is False


# ---------------------------------------------------------------------------
# Test: Chamber JSONL log written
# ---------------------------------------------------------------------------


class TestChamberJSONLLog:
    def test_chamber_jsonl_written_when_enabled(self):
        """Chamber JSONL file created when shadow_log enabled + chamber enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                fn_enabled=True,
                shadow_log_enabled=True,
                shadow_log_dir=tmpdir,
                chamber=ChamberConfig(),
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            # Look for chamber_ prefixed JSONL
            jsonl_files = [f for f in os.listdir(tmpdir) if f.startswith(
                "chamber_") and f.endswith(".jsonl")]
            assert len(jsonl_files) >= 1, (
                f"No chamber JSONL files in {tmpdir}: {os.listdir(tmpdir)}"
            )

            with open(os.path.join(tmpdir, jsonl_files[0]), "r") as f:
                lines = f.readlines()
            assert len(lines) >= 1
            record = json.loads(lines[0])
            assert record["verdict_scope"] == "ENTRY"
            assert record["symbol"] == "BTCUSDT"
            assert "expert_count" in record

    def test_no_chamber_jsonl_when_shadow_log_disabled(self):
        """No chamber JSONL when shadow_log disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                shadow_log_enabled=False,
                shadow_log_dir=tmpdir,
                chamber=ChamberConfig(),
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            chamber_files = [f for f in os.listdir(tmpdir) if f.startswith(
                "chamber_") and f.endswith(".jsonl")]
            assert len(chamber_files) == 0


# ---------------------------------------------------------------------------
# Test: Phase 4 — Verdict event emitted after chamber (entry path)
# ---------------------------------------------------------------------------


class TestVerdictEventEmitted:
    def test_entry_verdict_event_emitted(self):
        """EVT:JUDGE_ENTRY_VERDICT_V1 emitted when verdict config present."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        verdict_events = [e for e in bus.emitted
                          if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"]
        assert len(verdict_events) == 1

    def test_no_verdict_without_verdict_config(self):
        """No verdict event when verdict config absent (Phase 3 behavior)."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),
            verdict=None,
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        verdict_events = [e for e in bus.emitted
                          if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"]
        assert len(verdict_events) == 0

    def test_verdict_payload_valid_judge_verdict(self):
        """Verdict event payload deserializes to JudgeVerdict."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        verdict_events = [e for e in bus.emitted
                          if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"]
        assert len(verdict_events) == 1
        payload = verdict_events[0]["payload"]
        v = JudgeVerdict(**payload)
        assert v.verdict_scope == "ENTRY"
        assert v.authority_mode == "shadow"
        assert v.applied is False
        assert v.strategy_id == "aurora"
        assert v.cycle_key == "ENTRY:BTCUSDT:300:1700000000000"


# ---------------------------------------------------------------------------
# Test: Phase 4 — Envelope event emitted before verdict
# ---------------------------------------------------------------------------


class TestEnvelopeEventEmitted:
    def test_envelope_event_emitted(self):
        """EVT:JUDGE_EVIDENCE_ASSEMBLED_V1 emitted when verdict config present."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        env_events = [e for e in bus.emitted
                      if e["event"] == "EVT:JUDGE_EVIDENCE_ASSEMBLED_V1"]
        assert len(env_events) == 1

    def test_envelope_payload_valid(self):
        """Envelope event payload deserializes to JudgeEvidenceEnvelope."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        env_events = [e for e in bus.emitted
                      if e["event"] == "EVT:JUDGE_EVIDENCE_ASSEMBLED_V1"]
        assert len(env_events) == 1
        payload = env_events[0]["payload"]
        envelope = JudgeEvidenceEnvelope(**payload)
        assert envelope.verdict_scope == "ENTRY"
        assert envelope.strategy_id == "aurora"
        assert envelope.features_ref is not None
        assert envelope.cycle_key == "ENTRY:BTCUSDT:300:1700000000000"


# ---------------------------------------------------------------------------
# Test: Phase 4 — Lifecycle verdict when enabled
# ---------------------------------------------------------------------------


class TestLifecycleVerdictIntegration:
    def test_lifecycle_verdict_emitted_when_enabled(self):
        """lifecycle_enabled=True → lifecycle verdict emitted."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(lifecycle_enabled=True),
            verdict=VerdictConfig(lifecycle_enabled=True),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        lc_verdict_events = [e for e in bus.emitted
                             if e["event"] == "EVT:JUDGE_LIFECYCLE_VERDICT_V1"]
        assert len(lc_verdict_events) == 1
        payload = lc_verdict_events[0]["payload"]
        v = JudgeVerdict(**payload)
        assert v.verdict_scope == "LIFECYCLE"
        assert v.lifecycle_verdict == "UNKNOWN"
        assert v.applied is False
        assert v.cycle_key == "LIFECYCLE:BTCUSDT:300:1700000000000"

    def test_no_lifecycle_verdict_when_disabled(self):
        """lifecycle_enabled=False → no lifecycle verdict event."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(lifecycle_enabled=False),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        lc_verdict_events = [e for e in bus.emitted
                             if e["event"] == "EVT:JUDGE_LIFECYCLE_VERDICT_V1"]
        assert len(lc_verdict_events) == 0


# ---------------------------------------------------------------------------
# Test: Phase 4 — Verdict JSONL logs written
# ---------------------------------------------------------------------------


class TestVerdictJSONLLogs:
    def test_envelope_jsonl_written(self):
        """Envelope JSONL file created when shadow_log enabled + verdict enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                shadow_log_enabled=True,
                shadow_log_dir=tmpdir,
                chamber=ChamberConfig(),
                verdict=VerdictConfig(),
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            env_files = [f for f in os.listdir(tmpdir)
                         if f.startswith("envelope_") and f.endswith(".jsonl")]
            assert len(env_files) >= 1, (
                f"No envelope JSONL files in {tmpdir}: {os.listdir(tmpdir)}"
            )

    def test_verdict_jsonl_written(self):
        """Verdict JSONL file created when shadow_log enabled + verdict enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                shadow_log_enabled=True,
                shadow_log_dir=tmpdir,
                chamber=ChamberConfig(),
                verdict=VerdictConfig(),
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            verdict_files = [f for f in os.listdir(tmpdir)
                             if f.startswith("verdict_") and f.endswith(".jsonl")]
            assert len(verdict_files) >= 1, (
                f"No verdict JSONL files in {tmpdir}: {os.listdir(tmpdir)}"
            )

            with open(os.path.join(tmpdir, verdict_files[0]), "r") as f:
                lines = f.readlines()
            assert len(lines) >= 1
            record = json.loads(lines[0])
            assert record["verdict_scope"] == "ENTRY"
            assert record["authority_mode"] == "shadow"


# ---------------------------------------------------------------------------
# Test: J6-S3 — Shadow entry plan event/log emission
# ---------------------------------------------------------------------------


class TestShadowEntryPlanIntegration:
    def test_shadow_entry_plan_events_emitted_after_verdict(self):
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            fn_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(shadow_plan=_make_shadow_plan_config()),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        verdict_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_ENTRY_VERDICT_V1"
        ]
        shadow_plan_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_SHADOW_ENTRY_PLAN_V1"
        ]

        assert len(verdict_events) == 1
        assert len(shadow_plan_events) == 3

        plans = [ShadowEntryPlan(**event["payload"])
                 for event in shadow_plan_events]
        assert [plan.confidence_tier for plan in plans] == [
            "low", "medium", "high"]
        assert all(plan.entry_price_ref == 50000.0 for plan in plans)
        assert all(plan.source_verdict_id ==
                   verdict_events[0]["payload"]["verdict_id"] for plan in plans)
        assert all(plan.source_envelope_id ==
                   verdict_events[0]["payload"]["envelope_id"] for plan in plans)

        event_names = [event["event"] for event in bus.emitted]
        verdict_idx = event_names.index("EVT:JUDGE_ENTRY_VERDICT_V1")
        first_shadow_idx = event_names.index("EVT:JUDGE_SHADOW_ENTRY_PLAN_V1")
        assert verdict_idx < first_shadow_idx

    def test_shadow_entry_plan_jsonl_written_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = StubEventBus()
            cfg = _make_config(
                judge_mode="shadow",
                sw_enabled=True,
                fn_enabled=True,
                shadow_log_enabled=True,
                shadow_log_dir=tmpdir,
                chamber=ChamberConfig(),
                verdict=VerdictConfig(shadow_plan=_make_shadow_plan_config()),
            )
            plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
            _inject_cache_entry(plugin)
            _fire_decision(plugin)

            shadow_plan_files = [
                filename
                for filename in os.listdir(tmpdir)
                if filename.startswith("shadow_entry_plan_") and filename.endswith(".jsonl")
            ]
            assert len(shadow_plan_files) == 1

            with open(os.path.join(tmpdir, shadow_plan_files[0]), "r") as handle:
                lines = handle.readlines()
            assert len(lines) == 3

            record = json.loads(lines[0])
            plan = ShadowEntryPlan(**record)
            assert plan.symbol == "BTCUSDT"
            assert plan.entry_order_type == "HYPOTHETICAL_LIMIT"


# ---------------------------------------------------------------------------
# Test: Phase 4 — Event emission order
# ---------------------------------------------------------------------------


class TestPhase4EventOrder:
    def test_event_emission_order(self):
        """Events emitted in correct order: expert → chamber → envelope → verdict."""
        bus = StubEventBus()
        cfg = _make_config(
            judge_mode="shadow",
            sw_enabled=True,
            chamber=ChamberConfig(),
            verdict=VerdictConfig(),
        )
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
        _inject_cache_entry(plugin)
        _fire_decision(plugin)

        event_seq = [e["event"] for e in bus.emitted]
        # Expert produced must come before chamber
        expert_idx = next(
            i for i, e in enumerate(event_seq)
            if e == "EVT:JUDGE_EXPERT_PRODUCED_V1"
        )
        chamber_idx = next(
            i for i, e in enumerate(event_seq)
            if e == "EVT:JUDGE_CHAMBER_AGGREGATED_V1"
        )
        envelope_idx = next(
            i for i, e in enumerate(event_seq)
            if e == "EVT:JUDGE_EVIDENCE_ASSEMBLED_V1"
        )
        verdict_idx = next(
            i for i, e in enumerate(event_seq)
            if e == "EVT:JUDGE_ENTRY_VERDICT_V1"
        )
        assert expert_idx < chamber_idx < envelope_idx < verdict_idx
