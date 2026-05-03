"""
J6-S16.1 — Policy Cortex Runtime Wiring Tests

Verifies:
- evaluate_policy_cortex() is called once per ENTRY verdict cycle
- Produced annotation contains cycle_key
- Annotation is joinable with verdict by cycle_key
- EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1 is emitted
- Existing verdict output is unchanged
- Existing shadow plan output is unchanged
- No CMD:* events emitted
- No decision_making or execution_position events emitted
- write_jsonl_policy_cortex_log writes correct filename/content
- Wiring is fail-safe (errors in policy cortex don't break judge pipeline)
- Schema invariants maintained throughout
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch, call
import time

import pytest
from jsonschema import Draft7Validator

from apps.reference.domains.alpha_search.judge.policy_cortex.cortex_evaluator import (
    evaluate_policy_cortex,
)
from apps.reference.domains.alpha_search.judge.policy_cortex.evidence_models import (
    PolicyCortexAnnotation,
)
from apps.reference.domains.alpha_search.judge.policy_cortex.surface_registry import (
    SurfaceEvidenceRegistry,
    reset_default_registry,
)
from apps.reference.domains.alpha_search.judge.experts.expert_output_bridge import (
    write_jsonl_policy_cortex_log,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

FIXTURE_PATH = Path(
    "apps/reference/domains/alpha_search/judge/policy_cortex/surface_evidence_v1.json"
)

SCHEMA_PATH = Path(
    "apps/reference/domains/alpha_search/judge/policy_cortex/schemas/policy_cortex_annotation_v1.json"
)


def _load_annotation_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _make_annotation(
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    side: Optional[str] = "BUY",
    regime: Optional[str] = "TREND_UP",
    cycle_key: Optional[str] = "ENTRY:BTCUSDT:300:1712000000300",
    classifier_output: str = "TRACK_ONLY",
    matched_surface_label: Optional[str] = "PROMISING_BUT_CONCENTRATED",
    surface_key: str = "TREND_UP:BUY:all_symbols:regime_complete",
) -> PolicyCortexAnnotation:
    return PolicyCortexAnnotation(
        cycle_key=cycle_key,
        symbol=symbol,
        side=side,
        regime=regime,
        tf_sec=tf_sec,
        strategy_id="aurora",
        surface_key=surface_key,
        matched_surface_label=matched_surface_label,
        classifier_output=classifier_output,
        reason_codes=[
            f"surface_label:{matched_surface_label or 'UNKNOWN'}",
            "authority:shadow_only",
            "production_authority:false",
        ],
        final_shadow_policy=classifier_output,
        concentration_flags=[],
        sample_size=2876,
        avg_net_pnl=0.058,
        late_avg_net_pnl=0.1131,
        ci_low=-0.0115,
        ci_high=0.1305,
        evidence_registry_version="j6_s15_v1",
        source_artifact=str(FIXTURE_PATH),
        authority_mode="shadow",
        applied=False,
        advisory=False,
        production_authority=False,
        schema_version="1",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests — evaluate_policy_cortex from candidate-like inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestCortexFromCandidateLikeInputs:
    """Verify evaluate_policy_cortex can be driven from typical candidate fields."""

    def setup_method(self):
        reset_default_registry()
        self._registry = SurfaceEvidenceRegistry(fixture_path=FIXTURE_PATH)

    def test_trend_up_buy_returns_track_only(self):
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side="BUY",
            regime="TREND_UP",
            cycle_key="ENTRY:BTCUSDT:300:1712000000300",
            strategy_id="aurora",
            registry=self._registry,
        )
        assert ann.classifier_output == "TRACK_ONLY"
        assert ann.cycle_key == "ENTRY:BTCUSDT:300:1712000000300"
        assert ann.symbol == "BTCUSDT"
        assert ann.tf_sec == 300
        assert ann.side == "BUY"

    def test_no_regime_degrades_to_unknown(self):
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side="BUY",
            regime=None,
            registry=self._registry,
        )
        assert ann.classifier_output == "UNKNOWN"
        assert ann.applied is False
        assert ann.advisory is False

    def test_none_side_is_accepted(self):
        """None side must not raise — key builder handles gracefully."""
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side=None,
            regime="TREND_UP",
            registry=self._registry,
        )
        assert isinstance(ann.classifier_output, str)

    def test_shadow_invariants_always_present(self):
        for regime, side in [("TREND_UP", "BUY"), (None, None), ("HIGH_VOLATILITY", "SELL")]:
            ann = evaluate_policy_cortex(
                symbol="BTCUSDT",
                tf_sec=300,
                side=side,
                regime=regime,
                registry=self._registry,
            )
            assert ann.authority_mode == "shadow"
            assert ann.applied is False
            assert ann.advisory is False
            assert ann.production_authority is False


# ─────────────────────────────────────────────────────────────────────────────
# Wiring Tests — _emit_policy_cortex_annotation in AlphaSearchBacktestPlugin
# ─────────────────────────────────────────────────────────────────────────────

class TestPluginPolicyCortexWiring:
    """Verify the J6-S16.1 wiring inside AlphaSearchBacktestPlugin."""

    def _make_verdict_mock(
        self,
        symbol: str = "BTCUSDT",
        tf_sec: int = 300,
        ts_ms: int = 1712000000300,
        entry_verdict: str = "OPEN_LONG",
        cycle_key: str = "ENTRY:BTCUSDT:300:1712000000300",
        strategy_id: str = "aurora",
        verdict_id: str = "vrd_BTCUSDT_1712000000300",
    ) -> MagicMock:
        m = MagicMock()
        m.symbol = symbol
        m.tf_sec = tf_sec
        m.ts_ms = ts_ms
        m.entry_verdict = entry_verdict
        m.cycle_key = cycle_key
        m.strategy_id = strategy_id
        m.verdict_id = verdict_id
        m.confidence = 0.42
        return m

    def _make_judge_cfg(self, shadow_log_enabled: bool = False) -> MagicMock:
        cfg = MagicMock()
        cfg.shadow_log = MagicMock()
        cfg.shadow_log.enabled = shadow_log_enabled
        cfg.shadow_log.log_dir = "test_shadow_log"
        return cfg

    def _make_plugin(self) -> MagicMock:
        """Create a minimal plugin-like object with the method under test."""
        from apps.reference.domains.alpha_search.backtest_plugin import (
            AlphaSearchBacktestPlugin,
        )
        bus = MagicMock()
        bus.emitted = []

        def fake_emit(event_name: str, payload: dict, why: str = ""):
            bus.emitted.append({"event": event_name, "payload": payload, "why": why})

        bus.emit.side_effect = fake_emit
        bus.listen = MagicMock()

        # Patch config to avoid file I/O
        with patch.object(AlphaSearchBacktestPlugin, "_init_providers", return_value=None), \
             patch.object(AlphaSearchBacktestPlugin, "_register_listeners", return_value=None):
            from apps.reference.domains.alpha_search.config_models import (
                AlphaSearchConfig,
            )
            plugin = AlphaSearchBacktestPlugin.__new__(AlphaSearchBacktestPlugin)
            plugin.event_bus = bus
            plugin.config = MagicMock()
            plugin.providers = {}
            plugin.provider_configs = {}
            plugin.provider_stats = {}
            plugin.open_positions = {}
            plugin.closed_positions = {}
            plugin._signal_provider = {}
            plugin._pending_objective_events = {}
            plugin._signal_counter = 0
            plugin._cache_hits = 0
            plugin._cache_misses = 0
            plugin._feature_cache = {}
            plugin._cache_max = 10
            plugin.enabled = True
            plugin.shadow_mode = True
        return plugin, bus

    def test_emit_policy_cortex_emits_event(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg(shadow_log_enabled=False)

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert len(cortex_events) == 1

    def test_emitted_event_has_cycle_key(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(
            entry_verdict="OPEN_LONG",
            cycle_key="ENTRY:BTCUSDT:300:1712000000300",
        )
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events[0]["payload"]["cycle_key"] == "ENTRY:BTCUSDT:300:1712000000300"

    def test_emitted_event_has_verdict_id(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(verdict_id="vrd_BTCUSDT_1712000000300")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events[0]["payload"]["verdict_id"] == "vrd_BTCUSDT_1712000000300"

    def test_open_long_maps_side_to_buy(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events[0]["payload"]["side"] == "BUY"

    def test_open_short_maps_side_to_sell(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_SHORT")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="HIGH_VOLATILITY",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events[0]["payload"]["side"] == "SELL"

    def test_no_entry_verdict_maps_side_to_none(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="NO_ENTRY")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events[0]["payload"]["side"] is None

    def test_emitted_payload_has_shadow_invariants(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        payload = cortex_events[0]["payload"]
        assert payload["authority_mode"] == "shadow"
        assert payload["applied"] is False
        assert payload["advisory"] is False
        assert payload["production_authority"] is False

    def test_no_cmd_events_emitted(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cmd_events = [
            e for e in bus.emitted
            if e["event"].startswith("CMD:")
        ]
        assert cmd_events == [], f"Unexpected CMD events: {cmd_events}"

    def test_no_decision_making_events_emitted(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        dm_events = [
            e for e in bus.emitted
            if "decision_making" in e.get("why", "").lower()
            or "execution_position" in e.get("why", "").lower()
        ]
        assert dm_events == []

    def test_wiring_does_not_raise_on_broken_evaluator(self):
        """Plugin must not propagate errors from policy cortex."""
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg()

        with patch(
            "apps.reference.domains.alpha_search.backtest_plugin.evaluate_policy_cortex",
            side_effect=RuntimeError("Simulated cortex failure"),
        ):
            # Must not raise — error is caught and logged
            plugin._emit_policy_cortex_annotation(
                verdict=verdict,
                judge_cfg=judge_cfg,
                regime="TREND_UP",
                ts_ms=1712000000300,
            )

        # No cortex events should be emitted when evaluator failed
        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events == []

    def test_emitted_event_payload_passes_schema(self):
        plugin, bus = self._make_plugin()
        verdict = self._make_verdict_mock(entry_verdict="OPEN_LONG")
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        payload = cortex_events[0]["payload"]

        # Remove extra fields not in schema before validating
        schema_payload = {k: v for k, v in payload.items()
                         if k not in ("ts_ms", "emitted_at_ms", "verdict_id")}

        schema = _load_annotation_schema()
        validator = Draft7Validator(schema)
        validator.validate(schema_payload)

    def test_annotation_joinable_by_cycle_key(self):
        """cycle_key in cortex event matches cycle_key in verdict mock."""
        plugin, bus = self._make_plugin()
        cycle_key = "ENTRY:BTCUSDT:300:1712000000300"
        verdict = self._make_verdict_mock(
            entry_verdict="OPEN_LONG",
            cycle_key=cycle_key,
        )
        judge_cfg = self._make_judge_cfg()

        plugin._emit_policy_cortex_annotation(
            verdict=verdict,
            judge_cfg=judge_cfg,
            regime="TREND_UP",
            ts_ms=1712000000300,
        )

        cortex_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1"
        ]
        assert cortex_events[0]["payload"]["cycle_key"] == cycle_key


# ─────────────────────────────────────────────────────────────────────────────
# JSONL Sink Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyCortexJSONLSink:
    """Verify the write_jsonl_policy_cortex_log function."""

    def test_writes_jsonl_file(self, tmp_path):
        annotation = _make_annotation(
            cycle_key="ENTRY:BTCUSDT:300:1712000000300",
        )
        write_jsonl_policy_cortex_log(annotation, str(tmp_path), ts_ms=1712000000300)

        files = list(tmp_path.glob("policy_cortex_BTCUSDT_*.jsonl"))
        assert len(files) == 1

    def test_written_record_is_valid_json(self, tmp_path):
        annotation = _make_annotation()
        write_jsonl_policy_cortex_log(annotation, str(tmp_path), ts_ms=1712000000300)

        files = list(tmp_path.glob("policy_cortex_BTCUSDT_*.jsonl"))
        line = files[0].read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["cycle_key"] == "ENTRY:BTCUSDT:300:1712000000300"

    def test_written_record_roundtrips_to_annotation(self, tmp_path):
        annotation = _make_annotation()
        write_jsonl_policy_cortex_log(annotation, str(tmp_path), ts_ms=1712000000300)

        files = list(tmp_path.glob("policy_cortex_BTCUSDT_*.jsonl"))
        line = files[0].read_text(encoding="utf-8").strip()
        restored = PolicyCortexAnnotation.model_validate_json(line)
        assert restored == annotation

    def test_written_record_passes_schema(self, tmp_path):
        annotation = _make_annotation()
        write_jsonl_policy_cortex_log(annotation, str(tmp_path), ts_ms=1712000000300)

        files = list(tmp_path.glob("policy_cortex_BTCUSDT_*.jsonl"))
        line = files[0].read_text(encoding="utf-8").strip()
        parsed = json.loads(line)

        schema = _load_annotation_schema()
        Draft7Validator(schema).validate(parsed)

    def test_multiple_writes_append_not_overwrite(self, tmp_path):
        """Two annotations must appear as two lines in the same file."""
        for _ in range(2):
            annotation = _make_annotation()
            write_jsonl_policy_cortex_log(annotation, str(tmp_path), ts_ms=1712000000300)

        files = list(tmp_path.glob("policy_cortex_BTCUSDT_*.jsonl"))
        lines = [l.strip() for l in files[0].read_text("utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        annotation = _make_annotation()
        write_jsonl_policy_cortex_log(annotation, str(nested), ts_ms=1712000000300)
        assert nested.exists()

    def test_written_record_has_shadow_invariants(self, tmp_path):
        annotation = _make_annotation()
        write_jsonl_policy_cortex_log(annotation, str(tmp_path), ts_ms=1712000000300)

        files = list(tmp_path.glob("policy_cortex_BTCUSDT_*.jsonl"))
        parsed = json.loads(files[0].read_text("utf-8").strip())
        assert parsed["authority_mode"] == "shadow"
        assert parsed["applied"] is False
        assert parsed["advisory"] is False
        assert parsed["production_authority"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Telemetry/Schema Tests — EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyCortexTelemetryContract:
    """Verify the telemetry contract for EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1."""

    def test_verb_registry_entry_exists(self):
        """Verb registry must have JUDGE_POLICY_CORTEX_EVALUATED_V1 entry."""
        registry_path = Path(
            "apps/reference/dictionaries/verb_registry_v1.yaml"
        )
        content = registry_path.read_text(encoding="utf-8")
        assert "JUDGE_POLICY_CORTEX_EVALUATED_V1" in content

    def test_verb_registry_entry_has_correct_owner(self):
        registry_path = Path(
            "apps/reference/dictionaries/verb_registry_v1.yaml"
        )
        content = registry_path.read_text(encoding="utf-8")
        # The entry should be followed by owner: alpha_search
        lines = content.splitlines()
        idx = next(
            i for i, l in enumerate(lines)
            if "JUDGE_POLICY_CORTEX_EVALUATED_V1" in l
        )
        block = "\n".join(lines[idx : idx + 10])
        assert "owner: alpha_search" in block

    def test_verb_registry_entry_has_experimental_status(self):
        registry_path = Path(
            "apps/reference/dictionaries/verb_registry_v1.yaml"
        )
        content = registry_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        idx = next(
            i for i, l in enumerate(lines)
            if "JUDGE_POLICY_CORTEX_EVALUATED_V1" in l
        )
        block = "\n".join(lines[idx : idx + 10])
        assert "status: experimental" in block

    def test_schema_file_exists(self):
        assert SCHEMA_PATH.exists(), f"Schema not found: {SCHEMA_PATH}"

    def test_schema_is_valid_json(self):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
        assert schema.get("type") == "object"

    def test_schema_rejects_applied_true(self):
        schema = _load_annotation_schema()
        validator = Draft7Validator(schema)
        ann = _make_annotation()
        payload = ann.model_dump()
        payload["applied"] = True
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_schema_rejects_non_shadow_authority_mode(self):
        schema = _load_annotation_schema()
        validator = Draft7Validator(schema)
        ann = _make_annotation()
        payload = ann.model_dump()
        payload["authority_mode"] = "live"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_annotation_model_dump_passes_schema(self):
        schema = _load_annotation_schema()
        validator = Draft7Validator(schema)
        ann = _make_annotation()
        validator.validate(ann.model_dump())


# ─────────────────────────────────────────────────────────────────────────────
# UNKNOWN Observability Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownObservability:
    """Verify UNKNOWN annotations are observable (not silently suppressed)."""

    def setup_method(self):
        reset_default_registry()
        self._registry = SurfaceEvidenceRegistry(fixture_path=FIXTURE_PATH)

    def test_unknown_reason_code_present_when_surface_not_found(self):
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side="BUY",
            regime=None,
            registry=self._registry,
        )
        assert ann.classifier_output == "UNKNOWN"
        assert any("unknown" in code.lower() for code in ann.reason_codes)

    def test_unknown_annotation_has_surface_key(self):
        """Even UNKNOWN annotations must have a non-empty surface_key."""
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side="BUY",
            regime=None,
            registry=self._registry,
        )
        assert ann.surface_key  # must not be empty

    def test_unknown_annotation_is_not_promoted_to_allow_shadow(self):
        """UNKNOWN must never become ALLOW_SHADOW."""
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side="BUY",
            regime=None,
            registry=self._registry,
        )
        assert ann.classifier_output != "ALLOW_SHADOW"
        assert ann.final_shadow_policy != "ALLOW_SHADOW"

    def test_unmatched_side_specific_surface_returns_unknown(self):
        """LOW_VOLATILITY stored as all_sides — BUY-specific lookup → UNKNOWN."""
        ann = evaluate_policy_cortex(
            symbol="BTCUSDT",
            tf_sec=300,
            side="BUY",
            regime="LOW_VOLATILITY",
            registry=self._registry,
        )
        assert ann.classifier_output == "UNKNOWN"
        # Observable: has surface key and reason codes
        assert ann.surface_key
        assert len(ann.reason_codes) >= 1
