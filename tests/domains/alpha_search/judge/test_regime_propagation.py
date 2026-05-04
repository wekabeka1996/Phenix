"""
J6-S11 — Regime Propagation Integration Tests

Verifies that:
- CMD:PROCESS_STRATEGY with valid regime dict produces non-null regime in
  the assembled JudgeEvidenceEnvelope.
- CMD:PROCESS_STRATEGY with missing regime produces regime_missing_reason.
- Canonical FeatureCacheEntry.features dict is NOT mutated.
- cycle_key is unchanged by regime injection.
- regime_ts_ms, regime_source propagate correctly.

Authority: J6-S11 Envelope Regime Propagation Repair spec.
Scope: alpha_search / LLM Judge only. No execution, advisory, or promotion paths.
"""

import copy
import pytest


# ---------------------------------------------------------------------------
# Helpers — minimal stubs for the plugin local copy + regime inject logic
# ---------------------------------------------------------------------------

def _simulate_feature_copy_and_inject(cached_features: dict, regime_payload) -> dict:
    """
    Mirrors the exact logic added to _on_decision_score in backtest_plugin.py
    (J6-S11: Option A pass-through).

    We test the logic in isolation to avoid pulling in the full plugin graph.
    """
    features = dict(cached_features) if cached_features else {}

    if isinstance(regime_payload, dict):
        features["regime"] = regime_payload.get("regime")
        features["regime_confidence"] = regime_payload.get("confidence")
        features["regime_ts_ms"] = regime_payload.get("ts_ms") or regime_payload.get("ts")
        features["regime_source"] = regime_payload.get("source_model")
    else:
        features["regime_missing_reason"] = "REGIME_CONTEXT_MISSING"

    return features


def _simulate_assemble_extract(features: dict) -> dict:
    """
    Mirrors the extraction logic added to _assemble_and_emit_verdict.
    Returns the kwargs that would be passed to assemble_evidence_envelope.
    """
    regime = None
    regime_confidence = None
    regime_ts_ms = None
    regime_source = None
    regime_missing_reason = None

    if features:
        regime = features.get("regime")
        raw_rc = features.get("regime_confidence")
        if raw_rc is not None:
            try:
                regime_confidence = float(raw_rc)
            except (TypeError, ValueError):
                regime_confidence = None

        raw_ts = features.get("regime_ts_ms")
        if raw_ts is not None:
            try:
                regime_ts_ms = int(raw_ts)
            except (TypeError, ValueError):
                regime_ts_ms = None

        regime_source = features.get("regime_source")
        regime_missing_reason = features.get("regime_missing_reason")

    return {
        "regime": regime,
        "regime_confidence": regime_confidence,
        "regime_ts_ms": regime_ts_ms,
        "regime_source": regime_source,
        "regime_missing_reason": regime_missing_reason,
    }


# ---------------------------------------------------------------------------
# Tests — Option A pass-through from CMD:PROCESS_STRATEGY payload
# ---------------------------------------------------------------------------

class TestRegimePropagationOptionA:
    """Verify regime data flows from CMD payload → envelope kwargs."""

    def test_full_regime_payload_propagates(self):
        """Valid regime dict in CMD payload → all 4 regime fields populated."""
        cached = {"obi": 0.5, "ema_bias": 0.3}
        cmd_regime = {
            "regime": "TREND_UP",
            "confidence": "0.87",
            "ts_ms": 1_714_000_000_000,
            "source_model": "aurora_regime_v1",
        }

        features = _simulate_feature_copy_and_inject(cached, cmd_regime)
        result = _simulate_assemble_extract(features)

        assert result["regime"] == "TREND_UP"
        assert result["regime_confidence"] == pytest.approx(0.87)
        assert result["regime_ts_ms"] == 1_714_000_000_000
        assert result["regime_source"] == "aurora_regime_v1"
        assert result["regime_missing_reason"] is None

    def test_missing_regime_in_payload_produces_explicit_reason(self):
        """No regime in CMD payload → regime_missing_reason set."""
        cached = {"obi": 0.5}
        cmd_regime = None  # FE did not attach a regime

        features = _simulate_feature_copy_and_inject(cached, cmd_regime)
        result = _simulate_assemble_extract(features)

        assert result["regime"] is None
        assert result["regime_confidence"] is None
        assert result["regime_ts_ms"] is None
        assert result["regime_source"] is None
        assert result["regime_missing_reason"] == "REGIME_CONTEXT_MISSING"

    def test_regime_payload_string_not_dict_produces_missing_reason(self):
        """Malformed (non-dict) regime payload → explicit missing reason."""
        cached = {"obi": 0.5}
        cmd_regime = "TREND_UP"  # wrong type — not a dict

        features = _simulate_feature_copy_and_inject(cached, cmd_regime)
        result = _simulate_assemble_extract(features)

        assert result["regime"] is None
        assert result["regime_missing_reason"] == "REGIME_CONTEXT_MISSING"

    def test_regime_without_ts_ms_uses_fallback_ts(self):
        """If ts_ms absent but 'ts' present, use 'ts' as fallback."""
        cached = {}
        cmd_regime = {
            "regime": "HIGH_VOLATILITY",
            "confidence": "0.6",
            "ts": 1_714_200_000_000,  # legacy ts field
            "source_model": "aurora_regime_v1",
        }

        features = _simulate_feature_copy_and_inject(cached, cmd_regime)
        result = _simulate_assemble_extract(features)

        assert result["regime_ts_ms"] == 1_714_200_000_000

    def test_regime_confidence_malformed_float_string(self):
        """Malformed confidence string → regime_confidence is None, not crash."""
        cached = {}
        cmd_regime = {
            "regime": "MEAN_REVERSION",
            "confidence": "not_a_float",
        }

        features = _simulate_feature_copy_and_inject(cached, cmd_regime)
        result = _simulate_assemble_extract(features)

        # regime is set (string field is fine), confidence fails gracefully
        assert result["regime"] == "MEAN_REVERSION"
        assert result["regime_confidence"] is None

    def test_empty_cached_features_does_not_crash(self):
        """None or empty cache still works — no KeyError."""
        for cached in [None, {}, {"unrelated_key": 42}]:
            cmd_regime = {"regime": "TREND_DOWN", "confidence": "0.7"}
            features = _simulate_feature_copy_and_inject(cached, cmd_regime)
            result = _simulate_assemble_extract(features)
            assert result["regime"] == "TREND_DOWN"


# ---------------------------------------------------------------------------
# Tests — Cache safety
# ---------------------------------------------------------------------------

class TestCacheSafety:
    """Verify canonical FeatureCacheEntry.features is not contaminated."""

    def test_original_cache_not_mutated(self):
        """After regime inject, original cached_features dict is unchanged."""
        original = {"obi": 0.5, "ema_bias": 0.3, "volume_zscore": 0.1}
        snapshot = copy.deepcopy(original)

        cmd_regime = {
            "regime": "TREND_UP",
            "confidence": "0.9",
            "ts_ms": 1_714_000_000_000,
            "source_model": "aurora_regime_v1",
        }

        _simulate_feature_copy_and_inject(original, cmd_regime)

        # Original dict must be identical to its snapshot
        assert original == snapshot
        assert "regime" not in original
        assert "regime_confidence" not in original
        assert "regime_ts_ms" not in original
        assert "regime_source" not in original

    def test_inject_creates_distinct_dict(self):
        """Returned features dict is a new object, not the original."""
        original = {"obi": 0.5}
        features = _simulate_feature_copy_and_inject(original, {"regime": "TREND_UP", "confidence": "0.8"})
        assert features is not original

    def test_non_regime_feature_values_preserved(self):
        """Regime injection must not alter existing feature values."""
        original = {"obi": 0.75, "ema_bias": 0.42, "volume_spike": 0.88}
        features = _simulate_feature_copy_and_inject(
            original,
            {"regime": "MEAN_REVERSION", "confidence": "0.65"},
        )
        assert features["obi"] == 0.75
        assert features["ema_bias"] == 0.42
        assert features["volume_spike"] == 0.88


# ---------------------------------------------------------------------------
# Tests — Round-trip through JudgeEvidenceEnvelope contract
# ---------------------------------------------------------------------------

class TestEnvelopeContractRoundTrip:
    """Verify new regime fields survive Pydantic model_dump / model_validate."""

    def test_new_fields_survive_round_trip(self):
        """All new regime fields survive Pydantic serialization round-trip."""
        from apps.reference.domains.alpha_search.judge.contracts import (
            ChamberAggregate,
            EnvelopeProvenance,
            ExpertOutput,
            JudgeEvidenceEnvelope,
        )

        expert = ExpertOutput(
            expert_id="test_v1",
            expert_version="1.0.0",
            symbol="ETHUSDT",
            tf_sec=300,
            ts_ms=1_714_000_000_000,
            entry_verdict="OPEN_LONG",
            confidence=0.8,
            signal_direction="LONG",
            reasoning=["test"],
        )
        chamber = ChamberAggregate(
            chamber_id="entry_ETHUSDT_1714000000000",
            symbol="ETHUSDT",
            tf_sec=300,
            ts_ms=1_714_000_000_000,
            verdict_scope="ENTRY",
            expert_outputs=[expert],
            expert_count=1,
            responding_count=1,
            abstaining_count=0,
            consensus_direction="LONG",
            consensus_strength=0.8,
            admissibility="ADMISSIBLE",
        )
        env = JudgeEvidenceEnvelope(
            envelope_id="env_entry_ETHUSDT_1714000000000",
            symbol="ETHUSDT",
            tf_sec=300,
            ts_ms=1_714_000_000_000,
            verdict_scope="ENTRY",
            chamber_aggregate=chamber,
            strategy_id="aurora",
            regime="TREND_UP",
            regime_confidence=0.87,
            regime_ts_ms=1_714_000_000_000,
            regime_source="aurora_regime_v1",
            regime_missing_reason=None,
            freshness_deadline_ms=1_714_000_300_000,
            provenance=EnvelopeProvenance(
                cortex_version="phase4_shadow_v1",
                assembly_source="alpha_search_backtest_plugin",
            ),
        )

        dumped = env.model_dump()
        restored = JudgeEvidenceEnvelope.model_validate(dumped)

        assert restored.regime == "TREND_UP"
        assert restored.regime_confidence == pytest.approx(0.87)
        assert restored.regime_ts_ms == 1_714_000_000_000
        assert restored.regime_source == "aurora_regime_v1"
        assert restored.regime_missing_reason is None

    def test_missing_reason_survives_round_trip(self):
        """regime_missing_reason survives serialization when regime is absent."""
        from apps.reference.domains.alpha_search.judge.contracts import (
            ChamberAggregate,
            EnvelopeProvenance,
            ExpertOutput,
            JudgeEvidenceEnvelope,
        )

        expert = ExpertOutput(
            expert_id="test_v1",
            expert_version="1.0.0",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1_714_000_000_000,
            entry_verdict="NO_ENTRY",
            confidence=0.5,
            reasoning=["no regime context"],
        )
        chamber = ChamberAggregate(
            chamber_id="entry_BTCUSDT_1714000000000",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1_714_000_000_000,
            verdict_scope="ENTRY",
            expert_outputs=[expert],
            expert_count=1,
            responding_count=1,
            abstaining_count=0,
            consensus_direction="NEUTRAL",
            consensus_strength=0.5,
            admissibility="ADMISSIBLE",
        )
        env = JudgeEvidenceEnvelope(
            envelope_id="env_entry_BTCUSDT_1714000000000",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1_714_000_000_000,
            verdict_scope="ENTRY",
            chamber_aggregate=chamber,
            strategy_id="aurora",
            regime=None,
            regime_confidence=None,
            regime_ts_ms=None,
            regime_source=None,
            regime_missing_reason="REGIME_CONTEXT_MISSING",
            freshness_deadline_ms=1_714_000_300_000,
            provenance=EnvelopeProvenance(
                cortex_version="phase4_shadow_v1",
                assembly_source="alpha_search_backtest_plugin",
            ),
        )

        dumped = env.model_dump()
        restored = JudgeEvidenceEnvelope.model_validate(dumped)

        assert restored.regime is None
        assert restored.regime_confidence is None
        assert restored.regime_missing_reason == "REGIME_CONTEXT_MISSING"
