"""
ALPHA_SEARCH_SHADOW_SCENARIO_EXPANSION_V1 — focused test suite.

Tests cover:
  1. Registry validates ≥25 enabled scenarios
  2. No scenario missing required fields
  3. All outputs shadow_only=True, authority_applied=False, no_effect=True
  4. Score-to-side emits BUY/SELL when score crosses threshold
  5. Confidence nonzero when score valid and above threshold
  6. Below-threshold → NEUTRAL with SCORE_BELOW_THRESHOLD
  7. Duplicate detection catches identical config tuples
  8. Virtual lifecycle never emits real ORDER_INTENT/CMD:OPEN/CMD:CLOSE
  9. Scenario result schema validates positive payload, rejects missing fields
 10. Existing alpha_search integration still imports and runs
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[6]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REGISTRY_YAML = PROJECT_ROOT / "config" / "alpha_search" / "scenario_registry_v2.yaml"


# ---------------------------------------------------------------------------
# Test 1 — Registry has ≥25 enabled scenarios
# ---------------------------------------------------------------------------

def test_registry_has_at_least_25_enabled_scenarios():
    """Registry must validate without error and contain ≥25 enabled scenarios."""
    from apps.reference.domains.alpha_search.shadow.scenario_registry import load_registry

    registry = load_registry(str(REGISTRY_YAML))
    enabled = registry.get_enabled()
    assert len(enabled) >= 25, (
        f"Expected ≥25 enabled scenarios, got {len(enabled)}"
    )


# ---------------------------------------------------------------------------
# Test 2 — No scenario missing required fields
# ---------------------------------------------------------------------------

def test_no_scenario_missing_required_fields():
    """All scenarios must have scenario_id, name, family, entry_threshold, version."""
    from apps.reference.domains.alpha_search.shadow.scenario_registry import load_registry

    registry = load_registry(str(REGISTRY_YAML))

    for spec in registry.scenarios:
        assert spec.scenario_id, f"Missing scenario_id on a scenario"
        assert spec.name, f"[{spec.scenario_id}] Missing name"
        assert spec.family, f"[{spec.scenario_id}] Missing family"
        assert spec.version, f"[{spec.scenario_id}] Missing version"
        assert spec.entry_threshold >= 0.0, f"[{spec.scenario_id}] Negative entry_threshold"


# ---------------------------------------------------------------------------
# Test 3 — All outputs carry correct authority boundary fields
# ---------------------------------------------------------------------------

def test_all_scenarios_carry_shadow_authority_fields():
    """Every ShadowScenarioSpec must have shadow_only=True, authority_applied=False, no_effect=True."""
    from apps.reference.domains.alpha_search.shadow.scenario_registry import load_registry

    registry = load_registry(str(REGISTRY_YAML))

    for spec in registry.scenarios:
        assert spec.shadow_only is True, f"[{spec.scenario_id}] shadow_only must be True"
        assert spec.authority_applied is False, f"[{spec.scenario_id}] authority_applied must be False"
        assert spec.no_effect is True, f"[{spec.scenario_id}] no_effect must be True"


def test_shadow_signal_event_authority_fields_immutable():
    """ShadowSignalEvent must always carry shadow_only=True, authority_applied=False, no_effect=True."""
    from apps.reference.domains.alpha_search.shadow.signal_materializer import materialize_shadow_signal

    evt = materialize_shadow_signal(
        scenario_id="test_auth",
        scenario_version="1.0.0",
        provider_id="ta_ensemble",
        symbol="BTCUSDT",
        ts_ms=1_700_000_000_000,
        raw_score=0.25,
        confidence=0.8,
        threshold=0.10,
        regime="TREND_UP",
    )
    d = evt.to_dict()
    assert d["shadow_only"] is True
    assert d["authority_applied"] is False
    assert d["no_effect"] is True


# ---------------------------------------------------------------------------
# Test 4 — Score-to-side: BUY/SELL when score crosses threshold
# ---------------------------------------------------------------------------

def test_score_above_threshold_emits_buy():
    from apps.reference.domains.alpha_search.shadow.signal_materializer import (
        materialize_shadow_signal, ShadowReasonCode,
    )

    evt = materialize_shadow_signal(
        scenario_id="S01",
        scenario_version="1.0.0",
        provider_id="ta_ensemble",
        symbol="ETHUSDT",
        ts_ms=1_700_000_001_000,
        raw_score=0.20,
        confidence=0.7,
        threshold=0.10,
        regime="TREND_UP",
    )
    assert evt.side == "BUY"
    assert ShadowReasonCode.SHADOW_SIGNAL_EMITTED in evt.reason_codes


def test_score_below_negative_threshold_emits_sell():
    from apps.reference.domains.alpha_search.shadow.signal_materializer import (
        materialize_shadow_signal, ShadowReasonCode,
    )

    evt = materialize_shadow_signal(
        scenario_id="S02",
        scenario_version="1.0.0",
        provider_id="ta_ensemble",
        symbol="ETHUSDT",
        ts_ms=1_700_000_002_000,
        raw_score=-0.25,
        confidence=0.65,
        threshold=0.10,
        regime="TREND_DOWN",
    )
    assert evt.side == "SELL"
    assert ShadowReasonCode.SHADOW_SIGNAL_EMITTED in evt.reason_codes


# ---------------------------------------------------------------------------
# Test 5 — Confidence nonzero when score valid and above threshold
# ---------------------------------------------------------------------------

def test_derived_confidence_nonzero_when_score_valid():
    """derive_shadow_confidence should return > 0 when score exceeds threshold and no fail_closed."""
    from apps.reference.domains.alpha_search.shadow.signal_materializer import derive_shadow_confidence

    result = derive_shadow_confidence(
        raw_score=0.15,
        threshold=0.08,
        regime="TREND_UP",
        upstream_confidence=0.0,
        upstream_why=["score_above_threshold"],
    )
    assert result > 0.0, f"Expected nonzero confidence, got {result}"


def test_derived_confidence_zero_on_fail_closed():
    """derive_shadow_confidence must return 0.0 when fail_closed in upstream_why."""
    from apps.reference.domains.alpha_search.shadow.signal_materializer import derive_shadow_confidence

    result = derive_shadow_confidence(
        raw_score=0.15,
        threshold=0.08,
        regime="TREND_UP",
        upstream_confidence=0.0,
        upstream_why=["fail_closed:ta_features_missing_for_bar"],
    )
    assert result == 0.0


# ---------------------------------------------------------------------------
# Test 6 — Below-threshold → NEUTRAL + SCORE_BELOW_THRESHOLD
# ---------------------------------------------------------------------------

def test_below_threshold_emits_neutral_with_reason():
    from apps.reference.domains.alpha_search.shadow.signal_materializer import (
        materialize_shadow_signal, ShadowReasonCode,
    )

    evt = materialize_shadow_signal(
        scenario_id="S03",
        scenario_version="1.0.0",
        provider_id="aurora",
        symbol="BTCUSDT",
        ts_ms=1_700_000_003_000,
        raw_score=0.05,
        confidence=0.3,
        threshold=0.12,
        regime="UNCERTAIN",
    )
    assert evt.side == "NEUTRAL"
    assert ShadowReasonCode.SCORE_BELOW_THRESHOLD in evt.reason_codes


# ---------------------------------------------------------------------------
# Test 7 — Duplicate detection catches identical config tuples
# ---------------------------------------------------------------------------

def test_duplicate_fingerprint_detection():
    """Registry.duplicate_fingerprints() should detect scenarios with identical config."""
    from apps.reference.domains.alpha_search.shadow.scenario_registry import (
        ShadowScenarioRegistry, ShadowScenarioSpec, ScenarioFamily,
    )

    # Build a minimal registry with two identical configs
    base_data = {
        "registry_id": "test_dup",
        "version": 1,
        "scenarios": [
            {
                "scenario_id": f"DUP_{i:02d}",
                "name": f"Duplicate {i}",
                "family": "mean_reversion",
                "version": "1.0.0",
                "enabled": True,
                "entry_threshold": 0.10,
                "score_provider": "ta_ensemble",
                "score_overrides": {},
                "shadow_only": True,
                "authority_applied": False,
                "no_effect": True,
            }
            for i in range(1, 27)  # 26 to pass ≥25 check
        ],
    }
    # First 2 are identical by design — rest differ by threshold to keep them unique
    for j, s in enumerate(base_data["scenarios"][2:], start=2):
        s["entry_threshold"] = round(0.10 + j * 0.001, 4)

    registry = ShadowScenarioRegistry.model_validate(base_data)
    dupes = registry.duplicate_fingerprints()
    # DUP_01 and DUP_02 share score_provider=ta_ensemble, threshold=0.10, overrides={}
    assert len(dupes) > 0, "Expected at least one duplicate fingerprint group"


# ---------------------------------------------------------------------------
# Test 8 — Virtual lifecycle never emits real trading events
# ---------------------------------------------------------------------------

def test_virtual_lifecycle_has_no_real_trading_verbs():
    """VirtualLifecycle.to_dict() must not produce any forbidden real trading verbs."""
    from apps.reference.domains.alpha_search.shadow.virtual_lifecycle import (
        VirtualLifecycleEngine, PriceBar,
    )
    from apps.reference.domains.alpha_search.shadow.authority_guard import (
        FORBIDDEN_VERBS, assert_shadow_boundary,
    )

    engine = VirtualLifecycleEngine()
    bars = [PriceBar(ts=1_000_000 + i * 300_000, close=50000.0 + i * 50) for i in range(10)]

    lc = engine.simulate(
        scenario_id="S01",
        scenario_version="1.0.0",
        symbol="BTCUSDT",
        side="BUY",
        signal_ts=1_000_000,
        signal_price=50000.0,
        future_bars=bars,
        exit_model="horizon_3_bar",
        fee_model="taker_10bps",
        slippage_model="spread_half",
    )
    d = lc.to_dict()

    # Assert authority guard sees no violations
    assert_shadow_boundary(d, context="test_virtual_lifecycle")

    # Assert no forbidden verb exists in the dict values
    for v in d.values():
        assert str(v) not in FORBIDDEN_VERBS, f"Forbidden verb found in lifecycle output: {v}"


def test_virtual_lifecycle_authority_fields():
    """VirtualLifecycle output must carry shadow_only=True, authority_applied=False, no_effect=True."""
    from apps.reference.domains.alpha_search.shadow.virtual_lifecycle import (
        VirtualLifecycleEngine, PriceBar,
    )

    engine = VirtualLifecycleEngine()
    bars = [PriceBar(ts=i * 300_000, close=3000.0 - i * 10) for i in range(5)]

    lc = engine.simulate(
        scenario_id="S07",
        scenario_version="1.0.0",
        symbol="ETHUSDT",
        side="SELL",
        signal_ts=0,
        signal_price=3000.0,
        future_bars=bars,
        exit_model="fixed_tp_sl",
        tp_bps=30.0,
        sl_bps=20.0,
    )
    d = lc.to_dict()
    assert d["shadow_only"] is True
    assert d["authority_applied"] is False
    assert d["no_effect"] is True


# ---------------------------------------------------------------------------
# Test 9 — Authority guard rejects real trading event payloads
# ---------------------------------------------------------------------------

def test_authority_guard_rejects_forbidden_verb():
    """audit_shadow_event must flag ORDER_INTENT verb as a violation."""
    from apps.reference.domains.alpha_search.shadow.authority_guard import audit_shadow_event

    evil_event = {"verb": "ORDER_INTENT", "shadow_only": True}
    violations = audit_shadow_event(evil_event)
    assert len(violations) > 0
    assert any(v.field == "verb" for v in violations)


def test_authority_guard_rejects_shadow_only_false():
    """audit_shadow_event must flag shadow_only=False."""
    from apps.reference.domains.alpha_search.shadow.authority_guard import audit_shadow_event

    bad_event = {"verb": "SCORE_EMITTED", "shadow_only": False}
    violations = audit_shadow_event(bad_event)
    assert any(v.field == "shadow_only" for v in violations)


def test_authority_guard_clean_on_valid_event():
    """Valid shadow event dict must produce zero violations."""
    from apps.reference.domains.alpha_search.shadow.authority_guard import audit_shadow_event

    good_event = {
        "verb": "SHADOW_SIGNAL_EMITTED",
        "shadow_only": True,
        "authority_applied": False,
        "no_effect": True,
    }
    violations = audit_shadow_event(good_event)
    assert violations == []


# ---------------------------------------------------------------------------
# Test 10 — Existing alpha_search integration still imports and runs
# ---------------------------------------------------------------------------

def test_alpha_search_scenario_worker_imports():
    """Core alpha_search module must remain importable after shadow expansion."""
    import importlib

    mods = [
        "apps.reference.domains.alpha_search.runtime.scenario_worker",
        "apps.reference.domains.alpha_search.runtime.config_resolver",
        "apps.reference.domains.alpha_search.shadow.scenario_registry",
        "apps.reference.domains.alpha_search.shadow.signal_materializer",
        "apps.reference.domains.alpha_search.shadow.virtual_lifecycle",
        "apps.reference.domains.alpha_search.shadow.authority_guard",
        "apps.reference.domains.alpha_search.shadow.wal_comparator",
        "apps.reference.domains.alpha_search.shadow.metrics_engine",
    ]
    for mod in mods:
        loaded = importlib.import_module(mod)
        assert loaded is not None, f"Failed to import {mod}"


def test_registry_scenario_ids_are_unique():
    """All scenario_ids in the registry must be globally unique."""
    from apps.reference.domains.alpha_search.shadow.scenario_registry import load_registry

    registry = load_registry(str(REGISTRY_YAML))
    ids = [s.scenario_id for s in registry.scenarios]
    assert len(ids) == len(set(ids)), f"Duplicate scenario IDs: {set(x for x in ids if ids.count(x) > 1)}"


def test_registry_rejects_shadow_only_false():
    """Registry schema must raise ValueError if shadow_only=False is set."""
    from pydantic import ValidationError
    from apps.reference.domains.alpha_search.shadow.scenario_registry import ShadowScenarioSpec

    with pytest.raises(ValidationError, match="shadow_only must be True"):
        ShadowScenarioSpec(
            scenario_id="EVIL",
            name="Evil Scenario",
            family="mean_reversion",
            entry_threshold=0.10,
            shadow_only=False,
            authority_applied=False,
            no_effect=True,
        )


# ===========================================================================
# PHASE 3 — ScenarioManager registry wiring tests
# ===========================================================================

def test_registry_adapter_produces_30_scenario_matrix():
    """registry_adapter converts 30-scenario registry to ScenarioMatrixConfig."""
    from apps.reference.domains.alpha_search.shadow.registry_adapter import (
        load_registry_as_matrix_config,
    )

    cfg = load_registry_as_matrix_config(
        str(REGISTRY_YAML),
        source_mode="replay",
        stream_path="logs/alpha_input/alpha_input_v1.jsonl",
    )
    assert len(cfg.scenarios) == 30
    assert len([s for s in cfg.scenarios if s.enabled]) == 30
    assert cfg.matrix_id.startswith("registry:")


def test_registry_adapter_strategy_type_mapping():
    """Adapter correctly maps score_provider + family to strategy_type."""
    from apps.reference.domains.alpha_search.shadow.registry_adapter import (
        load_registry_as_matrix_config,
    )

    cfg = load_registry_as_matrix_config(
        str(REGISTRY_YAML),
        source_mode="replay",
        stream_path="logs/alpha_input/alpha_input_v1.jsonl",
    )
    specs_by_id = {s.scenario_id: s for s in cfg.scenarios}

    # Mean reversion family + ta_ensemble → mean_reversion
    assert specs_by_id["S01_MR_RSI_HEAVY"].strategy_type == "mean_reversion"
    # Trend continuation family + aurora → aurora
    assert specs_by_id["S08_TREND_15M_MOMENTUM"].strategy_type == "aurora"
    # Trend continuation family + ta_ensemble → ensemble
    assert specs_by_id["S07_TREND_5M_MOMENTUM"].strategy_type == "ensemble"


def test_registry_adapter_threshold_overrides_set():
    """Adapter injects entry_threshold into correct override paths."""
    from apps.reference.domains.alpha_search.shadow.registry_adapter import (
        load_registry_as_matrix_config,
    )

    cfg = load_registry_as_matrix_config(
        str(REGISTRY_YAML),
        source_mode="replay",
        stream_path="logs/alpha_input/alpha_input_v1.jsonl",
    )
    specs_by_id = {s.scenario_id: s for s in cfg.scenarios}

    # MR: ta_ensemble threshold path
    mr = specs_by_id["S01_MR_RSI_HEAVY"]
    assert mr.overrides["alpha_search.providers.ta_ensemble.threshold"] == 0.08
    assert mr.overrides["mean_reversion.strategy.entry_threshold"] == 0.08

    # Aurora: aurora threshold path
    au = specs_by_id["S08_TREND_15M_MOMENTUM"]
    assert au.overrides["aurora.decision.signal_threshold"] == 0.10
    assert au.overrides["alpha_search.providers.aurora.threshold"] == 0.10


def test_registry_adapter_score_overrides_normalised():
    """score_overrides with mean_reversion.* prefix get alpha_search_system. prepended."""
    from apps.reference.domains.alpha_search.shadow.registry_adapter import (
        load_registry_as_matrix_config,
    )

    cfg = load_registry_as_matrix_config(
        str(REGISTRY_YAML),
        source_mode="replay",
        stream_path="logs/alpha_input/alpha_input_v1.jsonl",
    )
    specs_by_id = {s.scenario_id: s for s in cfg.scenarios}

    # S01 has score_overrides: {mean_reversion.weights.rsi: 0.55, ...}
    s01 = specs_by_id["S01_MR_RSI_HEAVY"]
    assert "alpha_search_system.mean_reversion.weights.rsi" in s01.overrides
    assert s01.overrides["alpha_search_system.mean_reversion.weights.rsi"] == pytest.approx(0.55)


def test_launcher_load_matrix_config_detects_registry_format():
    """load_matrix_config auto-detects registry format from YAML keys."""
    from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config

    # Registry format
    cfg_reg = load_matrix_config(REGISTRY_YAML)
    assert cfg_reg.matrix_id.startswith("registry:")
    assert len(cfg_reg.scenarios) == 30

    # Matrix format
    matrix_path = PROJECT_ROOT / "config" / "alpha_search" / "scenario_matrix.yaml"
    cfg_mat = load_matrix_config(matrix_path)
    assert not cfg_mat.matrix_id.startswith("registry:")
    assert len(cfg_mat.scenarios) == 12


def test_launcher_missing_registry_raises():
    """load_matrix_config raises FileNotFoundError for missing registry file."""
    from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config

    with pytest.raises(FileNotFoundError):
        load_matrix_config(PROJECT_ROOT / "config" / "alpha_search" / "does_not_exist.yaml")


def test_registry_adapter_max_scenarios_cap_respected():
    """Produced ScenarioMatrixConfig must not exceed its own max_scenarios limit."""
    from apps.reference.domains.alpha_search.shadow.registry_adapter import (
        load_registry_as_matrix_config,
    )

    cfg = load_registry_as_matrix_config(
        str(REGISTRY_YAML),
        source_mode="replay",
        stream_path="logs/alpha_input/alpha_input_v1.jsonl",
    )
    enabled = [s for s in cfg.scenarios if s.enabled]
    assert len(enabled) <= cfg.runtime.max_scenarios, (
        f"Enabled scenario count {len(enabled)} exceeds max_scenarios {cfg.runtime.max_scenarios}"
    )


def test_old_12_scenario_matrix_not_silently_used_for_registry_path():
    """When registry path is passed, result must have 30 scenarios, not 12."""
    from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config

    cfg = load_matrix_config(REGISTRY_YAML)
    assert len(cfg.scenarios) >= 25, (
        f"Registry loading should produce ≥25 scenarios; got {len(cfg.scenarios)} "
        f"(old 12-scenario matrix was silently used?)"
    )


def test_registry_loaded_scenarios_carry_version_family_provider_metadata():
    """Registry-adapted runtime specs preserve scenario_id/version/family/provider provenance."""
    from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config

    cfg = load_matrix_config(REGISTRY_YAML)
    for spec in cfg.scenarios:
        assert spec.scenario_id
        assert spec.version
        assert spec.family
        assert spec.provider
        assert spec.shadow_only is True
        assert spec.authority_applied is False
        assert spec.no_effect is True
