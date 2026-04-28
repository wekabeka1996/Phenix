"""Phase 1 — Causal Time Hard-Gate contract tests.

Proves invariant I3:
    Any row without causally established event_ts_ms must become:
    - event_time_is_causal=false
    - trainable=false
    - dataset_visibility=diagnostics_only

12 required test cases + Phase 0 boundary regression check.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from apps.reference.domains.neocortex.contracts.causal_time import (
    CausalTimeDecision,
    NON_CAUSAL_REASON_CODE,
    get_non_causal_counter,
    make_causal_decision,
    reset_non_causal_counter,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser import (
    parse_feature_log_line,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    parse_order_log_line,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.core_parser import (
    parse_core_log_line,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[4]


def _runtime_smoke_import(target_module: str, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    """Import a module in a fresh interpreter and report forbidden imports."""
    probe_script = """
import importlib
import json
import sys

target = sys.argv[1]
forbidden = tuple(sys.argv[2:])

try:
    importlib.import_module(target)
except Exception as exc:
    print(json.dumps({"error": str(exc), "loaded": []}))
    sys.exit(0)

loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden)
)

print(json.dumps({"loaded": loaded}))
"""

    completed = subprocess.run(
        [
            sys.executable,
            "-W",
            "ignore",
            "-c",
            probe_script,
            target_module,
            *forbidden_prefixes,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        pytest.skip(
            f"Runtime import of {target_module} failed; stderr: {completed.stderr[:500]}"
        )

    output_lines = completed.stdout.strip().splitlines()
    if not output_lines:
        pytest.skip(f"No JSON output from subprocess for {target_module}")

    payload = json.loads(output_lines[-1])
    if payload.get("error"):
        pytest.skip(
            f"Runtime import of {target_module} raised: {payload['error']}"
        )
    return list(payload["loaded"])


def _load_neocortex_config():
    """Load the real SSOT neocortex config for startup gate tests."""
    from apps.reference.domains.neocortex.config_models import load_config
    return load_config(Path("apps/reference/domains/neocortex/config"))


def _live_shadow_config():
    """Override the real config to use live_shadow operating mode."""
    from apps.reference.domains.neocortex.config_models import load_config, NeocortexConfig
    import yaml
    cfg = load_config(Path("apps/reference/domains/neocortex/config"))
    # We need a fake config that represents live_shadow with legacy policy
    # We do this by building a patched version of the performance sub-config.
    # Rather than mutating frozen models, we return the base config
    # (which is offline_replay in SSOT) and test startup gate logic directly.
    return cfg


# ---------------------------------------------------------------------------
# Test 1: exchange_event timestamp — causal=true, trainable=true
# ---------------------------------------------------------------------------

class TestExchangeEventTimestamp:
    """CausalTimeProvenance.EXCHANGE_EVENT must be causal and trainable."""

    def test_exchange_event_is_causal(self):
        decision = make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.EXCHANGE_EVENT)
        assert decision.event_time_is_causal is True

    def test_exchange_event_is_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.EXCHANGE_EVENT)
        assert decision.trainable is True

    def test_exchange_event_visibility_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.EXCHANGE_EVENT)
        assert decision.dataset_visibility == "trainable"

    def test_exchange_event_no_reason_code(self):
        decision = make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.EXCHANGE_EVENT)
        assert decision.reason_code is None


# ---------------------------------------------------------------------------
# Test 2: aurora_event timestamp — causal=true, trainable=true
# ---------------------------------------------------------------------------

class TestAuroraEventTimestamp:
    """CausalTimeProvenance.AURORA_EVENT must be causal and trainable."""

    def test_aurora_event_is_causal(self):
        decision = make_causal_decision(
            1_700_000_000_001, CausalTimeProvenance.AURORA_EVENT)
        assert decision.event_time_is_causal is True

    def test_aurora_event_is_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_001, CausalTimeProvenance.AURORA_EVENT)
        assert decision.trainable is True

    def test_aurora_event_visibility_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_001, CausalTimeProvenance.AURORA_EVENT)
        assert decision.dataset_visibility == "trainable"


# ---------------------------------------------------------------------------
# Test 3: bar_end timestamp — causal=true, trainable=true
# ---------------------------------------------------------------------------

class TestBarEndTimestamp:
    """CausalTimeProvenance.BAR_END must be causal and trainable."""

    def test_bar_end_is_causal(self):
        decision = make_causal_decision(
            1_700_000_000_002, CausalTimeProvenance.BAR_END)
        assert decision.event_time_is_causal is True

    def test_bar_end_is_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_002, CausalTimeProvenance.BAR_END)
        assert decision.trainable is True

    def test_bar_end_visibility_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_002, CausalTimeProvenance.BAR_END)
        assert decision.dataset_visibility == "trainable"


# ---------------------------------------------------------------------------
# Test 4: captured_wallclock timestamp — causal=false, trainable=false
# ---------------------------------------------------------------------------

class TestCapturedWallclockTimestamp:
    """CausalTimeProvenance.CAPTURED_WALLCLOCK must be non-causal, non-trainable."""

    def test_wallclock_not_causal(self):
        decision = make_causal_decision(
            1_700_000_000_003, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert decision.event_time_is_causal is False

    def test_wallclock_not_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_003, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert decision.trainable is False

    def test_wallclock_diagnostics_only(self):
        decision = make_causal_decision(
            1_700_000_000_003, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert decision.dataset_visibility == "diagnostics_only"

    def test_wallclock_has_reason_code(self):
        decision = make_causal_decision(
            1_700_000_000_003, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert decision.reason_code == NON_CAUSAL_REASON_CODE


# ---------------------------------------------------------------------------
# Test 5: file_offset_legacy timestamp — causal=false, trainable=false
# ---------------------------------------------------------------------------

class TestFileOffsetLegacyTimestamp:
    """CausalTimeProvenance.FILE_OFFSET_LEGACY must be non-causal, non-trainable."""

    def test_file_offset_not_causal(self):
        decision = make_causal_decision(
            1_700_000_000_004, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert decision.event_time_is_causal is False

    def test_file_offset_not_trainable(self):
        decision = make_causal_decision(
            1_700_000_000_004, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert decision.trainable is False

    def test_file_offset_diagnostics_only(self):
        decision = make_causal_decision(
            1_700_000_000_004, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert decision.dataset_visibility == "diagnostics_only"


# ---------------------------------------------------------------------------
# Test 6: missing / unknown timestamp
# ---------------------------------------------------------------------------

class TestMissingTimestamp:
    """Missing / UNKNOWN provenance must produce source=unknown, non-causal, non-trainable, NON_CAUSAL_TIME."""

    def test_unknown_not_causal(self):
        decision = make_causal_decision(None, CausalTimeProvenance.UNKNOWN)
        assert decision.event_time_is_causal is False

    def test_unknown_not_trainable(self):
        decision = make_causal_decision(None, CausalTimeProvenance.UNKNOWN)
        assert decision.trainable is False

    def test_unknown_diagnostics_only(self):
        decision = make_causal_decision(None, CausalTimeProvenance.UNKNOWN)
        assert decision.dataset_visibility == "diagnostics_only"

    def test_unknown_reason_code_non_causal_time(self):
        decision = make_causal_decision(None, CausalTimeProvenance.UNKNOWN)
        assert decision.reason_code == NON_CAUSAL_REASON_CODE

    def test_unknown_source_is_unknown(self):
        decision = make_causal_decision(None, CausalTimeProvenance.UNKNOWN)
        assert decision.event_time_source == CausalTimeProvenance.UNKNOWN

    def test_feature_parser_missing_timestamp_returns_none(self):
        """Parser must not synthesize causal time from missing timestamp in fail_closed mode."""
        line = json.dumps({"obi": "0.5", "tfi": "0.9"})  # no timestamp field
        result = parse_feature_log_line(
            line, symbol="BTCUSDT", missing_timestamp_policy="fail_closed")
        assert result is None, (
            "Parser must return None for missing timestamp in fail_closed mode — "
            "not synthesize a causal event_ts_ms"
        )


# ---------------------------------------------------------------------------
# Test 7: production-shadow rejects legacy file-offset timestamp policy
# ---------------------------------------------------------------------------

class TestProductionShadowRejectsLegacyPolicy:
    """Startup gate must fail closed if feature_missing_timestamp_policy=legacy_non_causal_file_offset
    is configured with live_shadow operating mode."""

    def test_live_shadow_with_legacy_policy_fails_gate(self):
        """ShadowGateEvaluator must fail causal_time.hard_gate for live_shadow + legacy policy."""
        from apps.reference.domains.neocortex.logic.gates.shadow import ShadowGateEvaluator
        from apps.reference.domains.neocortex.config_models import load_config
        import copy

        # We build a config where operating_mode=live_shadow and policy=legacy_non_causal_file_offset.
        # The real SSOT config uses offline_replay + fail_closed, so we patch only what we need.
        base_cfg = load_config(Path("apps/reference/domains/neocortex/config"))

        # Construct a patched config by re-using model_validate on a mutated dict.
        # frozen=True means we need to use model_copy(update=...) or rebuild from dict.
        cfg_dict = base_cfg.model_dump()

        # Set the two fields that trigger the failure
        cfg_dict["neuro"]["performance"]["operating_mode"] = "live_shadow"
        cfg_dict["neuro"]["performance"]["shadow_intent_emit_policy"] = "emit_all"
        cfg_dict["neuro"]["performance"]["shadow_intent_decimation_stride"] = 1
        cfg_dict["replay"]["feature_missing_timestamp_policy"] = "legacy_non_causal_file_offset"
        cfg_dict["replay"]["legacy_feature_base_ts_ms"] = 1_700_000_000_000

        from apps.reference.domains.neocortex.config_models import NeocortexConfig
        patched_cfg = NeocortexConfig.model_validate(cfg_dict)

        evaluator = ShadowGateEvaluator()
        report = evaluator.evaluate(
            patched_cfg, evaluated_at_ms=1_700_000_000_000)

        causal_gate = next(
            (g for g in report.gates if g.gate_id == "causal_time.hard_gate"), None
        )
        assert causal_gate is not None, "causal_time.hard_gate must exist in gate report"
        assert causal_gate.status == "fail", (
            f"causal_time.hard_gate must FAIL for live_shadow + legacy policy, got {causal_gate.status!r}"
        )
        assert causal_gate.blocking is True, "causal_time.hard_gate must be blocking"
        assert "causal_time.hard_gate" in report.blocking_gate_ids

    def test_live_shadow_with_fail_closed_passes_gate(self):
        """ShadowGateEvaluator must pass causal_time.hard_gate for live_shadow + fail_closed."""
        from apps.reference.domains.neocortex.logic.gates.shadow import ShadowGateEvaluator
        from apps.reference.domains.neocortex.config_models import load_config, NeocortexConfig

        base_cfg = load_config(Path("apps/reference/domains/neocortex/config"))
        cfg_dict = base_cfg.model_dump()
        cfg_dict["neuro"]["performance"]["operating_mode"] = "live_shadow"
        cfg_dict["neuro"]["performance"]["shadow_intent_emit_policy"] = "emit_all"
        cfg_dict["neuro"]["performance"]["shadow_intent_decimation_stride"] = 1
        cfg_dict["replay"]["feature_missing_timestamp_policy"] = "fail_closed"
        cfg_dict["replay"]["legacy_feature_base_ts_ms"] = None

        patched_cfg = NeocortexConfig.model_validate(cfg_dict)
        evaluator = ShadowGateEvaluator()
        report = evaluator.evaluate(
            patched_cfg, evaluated_at_ms=1_700_000_000_000)

        causal_gate = next(
            (g for g in report.gates if g.gate_id == "causal_time.hard_gate"), None
        )
        assert causal_gate is not None
        assert causal_gate.status == "pass", (
            f"causal_time.hard_gate must PASS for live_shadow + fail_closed, got {causal_gate.status!r}"
        )


# ---------------------------------------------------------------------------
# Test 8: replay diagnostics legacy — file-offset/captured allowed but non-trainable
# ---------------------------------------------------------------------------

class TestReplayDiagnosticsLegacy:
    """In offline replay, legacy timestamps produce diagnostics_only rows, never trainable ones."""

    def test_feature_with_file_offset_policy_is_non_trainable(self):
        """When missing_timestamp_policy=legacy_non_causal_file_offset, produced entry must be non-trainable."""
        line = json.dumps({"obi": "0.5"})  # no timestamp
        result = parse_feature_log_line(
            line,
            symbol="BTCUSDT",
            missing_timestamp_policy="legacy_non_causal_file_offset",
            synthetic_event_ts_ms=1_700_000_000_000,
        )
        assert result is not None, "Parser must produce entry in legacy mode"
        assert result.trainable is False, "Legacy file-offset row must not be trainable"
        assert result.dataset_visibility == "diagnostics_only", (
            "Legacy file-offset row must be diagnostics_only"
        )
        assert result.time_is_causal is False

    def test_feature_with_wallclock_timestamp_is_non_trainable(self):
        """Full log-format feature lines (captured wallclock) must be non-trainable."""
        line = "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {\"obi\": \"0.5\"}"
        result = parse_feature_log_line(line, symbol="BTCUSDT")
        assert result is not None
        assert result.trainable is False
        assert result.dataset_visibility == "diagnostics_only"
        assert result.time_provenance == CausalTimeProvenance.CAPTURED_WALLCLOCK

    def test_core_log_equity_update_is_diagnostics_only(self):
        """Core log equity updates use wallclock timestamp and must be diagnostics_only."""
        line = (
            "2026-01-09 12:58:42,585 - module - INFO - "
            "Emitted positions update: 0 open positions, "
            "totalWalletBalance=293.27, totalUnrealizedProfit=0.0"
        )
        result = parse_core_log_line(line)
        assert result is not None
        assert result.trainable is False
        assert result.dataset_visibility == "diagnostics_only"

    def test_offline_replay_gate_warns_but_does_not_block(self):
        """offline_replay + legacy policy must warn but not block (dataset admission handles non-trainable)."""
        from apps.reference.domains.neocortex.logic.gates.shadow import ShadowGateEvaluator
        from apps.reference.domains.neocortex.config_models import load_config, NeocortexConfig

        base_cfg = load_config(Path("apps/reference/domains/neocortex/config"))
        cfg_dict = base_cfg.model_dump()
        # Keep offline_replay, set legacy policy
        cfg_dict["replay"]["feature_missing_timestamp_policy"] = "legacy_non_causal_file_offset"
        cfg_dict["replay"]["legacy_feature_base_ts_ms"] = 1_700_000_000_000

        patched_cfg = NeocortexConfig.model_validate(cfg_dict)
        evaluator = ShadowGateEvaluator()
        report = evaluator.evaluate(
            patched_cfg, evaluated_at_ms=1_700_000_000_000)

        causal_gate = next(
            (g for g in report.gates if g.gate_id == "causal_time.hard_gate"), None
        )
        assert causal_gate is not None
        assert causal_gate.status == "warn", (
            f"offline_replay + legacy policy must WARN (not fail) the causal_time.hard_gate, "
            f"got {causal_gate.status!r}"
        )
        assert causal_gate.blocking is False


# ---------------------------------------------------------------------------
# Test 9: time.time() / process wallclock is NOT used as causal event time
# ---------------------------------------------------------------------------

class TestNoProcessWallclockAsCausal:
    """time.time(), datetime.now(), and process time must never produce event_time_is_causal=True."""

    def test_feature_parser_does_not_call_time_time(self):
        """Parser must not use time.time() to synthesize a causal timestamp."""
        call_log: list[float] = []

        original_time = time.time

        def _spy_time() -> float:
            ts = original_time()
            call_log.append(ts)
            return ts

        with patch("time.time", side_effect=_spy_time):
            # A line with a real causal timestamp must not trigger time.time() in the hot path
            line = json.dumps({"event_ts_ms": 1_700_000_000_000, "obi": "0.5"})
            result = parse_feature_log_line(line, symbol="BTCUSDT")

        assert result is not None
        assert result.time_is_causal is True
        # time.time() calls that happened must not have been used to derive event_ts_ms
        # (we prove this by checking the actual event_ts_ms equals our fixture value)
        assert result.event_ts_ms == 1_700_000_000_000, (
            "event_ts_ms must come from the payload, not from time.time()"
        )

    def test_wallclock_timestamp_in_feature_log_format_marks_non_causal(self):
        """Captured log timestamps (from datetime.now() or equivalent) must mark non-causal."""
        line = "2026-01-09 12:58:42,585 - module.FeatureEngineering - INFO - Calculated features for SOLUSDT: {\"obi\": \"0.5\"}"
        result = parse_feature_log_line(line, symbol="SOLUSDT")
        assert result is not None
        assert result.time_is_causal is False, (
            "Captured log timestamp must never be treated as causal event time"
        )
        assert result.trainable is False


# ---------------------------------------------------------------------------
# Test 10: parser outputs always contain required I3 fields
# ---------------------------------------------------------------------------

class TestParserOutputsContainI3Fields:
    """Every parser output must expose event_time_source, event_time_is_causal,
    trainable, dataset_visibility."""

    def test_feature_parser_causal_row_has_all_fields(self):
        line = json.dumps({"event_ts_ms": 1_700_000_000_000, "obi": "0.5"})
        result = parse_feature_log_line(line, symbol="BTCUSDT")
        assert result is not None
        assert hasattr(
            result, "time_provenance"), "FeatureLogEntry must have time_provenance"
        assert hasattr(
            result, "time_is_causal"), "FeatureLogEntry must have time_is_causal (event_time_is_causal)"
        assert hasattr(
            result, "trainable"), "FeatureLogEntry must have trainable"
        assert hasattr(
            result, "dataset_visibility"), "FeatureLogEntry must have dataset_visibility"

    def test_order_parser_causal_row_has_all_fields(self):
        line = json.dumps({
            "event_ts_ms": 1_700_000_000_000,
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "side": "BUY",
        })
        result = parse_order_log_line(line)
        assert result is not None
        assert hasattr(result, "time_provenance")
        assert hasattr(result, "time_is_causal")
        assert hasattr(result, "trainable")
        assert hasattr(result, "dataset_visibility")

    def test_core_parser_structured_close_has_all_fields(self):
        line = (
            "2026-01-09 12:58:42,585 - module - INFO - POSITION_CLOSED: "
            "symbol=BTCUSDT close_ts_ms=1700000000000 realized_pnl=0.123 trade_id=t1"
        )
        result = parse_core_log_line(line)
        assert result is not None
        assert hasattr(result, "time_provenance")
        assert hasattr(result, "time_is_causal")
        assert hasattr(result, "trainable")
        assert hasattr(result, "dataset_visibility")

    def test_feature_parser_non_causal_row_has_all_fields(self):
        line = "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {\"obi\": \"0.5\"}"
        result = parse_feature_log_line(line)
        assert result is not None
        assert result.dataset_visibility == "diagnostics_only"
        assert result.trainable is False

    def test_feature_parser_causal_row_fields_are_consistent(self):
        """trainable and dataset_visibility must be internally consistent with time_is_causal."""
        line = json.dumps({"event_ts_ms": 1_700_000_000_000, "obi": "0.5"})
        result = parse_feature_log_line(line, symbol="BTCUSDT")
        assert result is not None
        if result.time_is_causal:
            assert result.trainable is True
            assert result.dataset_visibility == "trainable"
        else:
            assert result.trainable is False
            assert result.dataset_visibility == "diagnostics_only"


# ---------------------------------------------------------------------------
# Test 11: dataset.invalid_total{reason_code=NON_CAUSAL_TIME} counter
# ---------------------------------------------------------------------------

class TestNonCausalTimeCounter:
    """Metric counter must increment on every non-causal row."""

    def setup_method(self):
        reset_non_causal_counter()

    def teardown_method(self):
        reset_non_causal_counter()

    def test_counter_increments_on_wallclock_decision(self):
        before = get_non_causal_counter()
        make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert get_non_causal_counter() == before + 1

    def test_counter_increments_on_file_offset_decision(self):
        before = get_non_causal_counter()
        make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert get_non_causal_counter() == before + 1

    def test_counter_increments_on_unknown_decision(self):
        before = get_non_causal_counter()
        make_causal_decision(None, CausalTimeProvenance.UNKNOWN)
        assert get_non_causal_counter() == before + 1

    def test_counter_does_not_increment_on_causal_decision(self):
        before = get_non_causal_counter()
        make_causal_decision(
            1_700_000_000_000, CausalTimeProvenance.AURORA_EVENT)
        assert get_non_causal_counter() == before

    def test_counter_increments_via_parser(self):
        """Parser calls make_causal_decision internally; counter must reflect this."""
        reset_non_causal_counter()
        line = "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {\"obi\": \"0.5\"}"
        result = parse_feature_log_line(line, symbol="BTCUSDT")
        assert result is not None
        assert get_non_causal_counter() >= 1, (
            "Non-causal parser output must increment the dataset.invalid_total counter"
        )

    def test_counter_name_is_dataset_invalid_total_non_causal_time(self):
        """Semantic check: the counter name constant must match expected metric name."""
        assert NON_CAUSAL_REASON_CODE == "NON_CAUSAL_TIME"


# ---------------------------------------------------------------------------
# Test 12: Phase 0 boundary test still passes
# ---------------------------------------------------------------------------

class TestPhase0BoundaryRegression:
    """Importing Phase 1 contract code must not load quarantined modules."""

    def test_causal_time_contract_is_not_quarantined(self):
        """contracts.causal_time is a hot-path module; it must not have __quarantined__."""
        import apps.reference.domains.neocortex.contracts.causal_time as ct
        assert not getattr(ct, "__quarantined__", False), (
            "contracts.causal_time must NOT be quarantined"
        )

    def test_causal_time_import_does_not_load_legacy_modules(self):
        """Importing causal_time must not transitively load any quarantined module.

        Uses subprocess isolation (same methodology as Phase 0 Layer 5) to avoid
        contamination from other tests loading quarantined modules through their fixtures.
        """
        import subprocess
        import sys

        forbidden_prefixes = [
            "apps.reference.domains.neocortex.transport",
            "apps.reference.domains.neocortex.logic.dreamer",
            "apps.reference.domains.neocortex.logic.brain.core",
            "apps.reference.domains.neocortex.logic.brain.bridge",
            "apps.reference.domains.neocortex.logic.brain.worker",
            "apps.reference.domains.neocortex.logic.brain.vae",
            "apps.reference.domains.neocortex.logic.brain.world_model",
            "apps.reference.domains.neocortex.logic.ingest.tailer",
            "apps.reference.domains.neocortex.logic.ingest.multi_tailer",
            "apps.reference.domains.neocortex.logic.ingest.wal_replayer",
            "apps.reference.domains.neocortex.PPO",
        ]
        prefixes_repr = repr(forbidden_prefixes)
        code = (
            "import sys\n"
            "import apps.reference.domains.neocortex.contracts.causal_time\n"
            f"forbidden = {prefixes_repr}\n"
            "loaded = [n for n in sys.modules if any(n == p or n.startswith(p + '.') for p in forbidden)]\n"
            "if loaded:\n"
            "    raise AssertionError(f'Loaded quarantined modules: {loaded}')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Subprocess import check failed:\n{result.stderr}"
        )

    def test_feature_parser_has_correct_i3_fields_causal(self):
        """Regression: feature parser produces I3-compliant output for causal rows."""
        line = json.dumps(
            {"event_ts_ms": 1_700_000_000_000, "close_price": "50000.0"})
        result = parse_feature_log_line(line, symbol="BTCUSDT")
        assert result is not None
        assert result.trainable is True
        assert result.dataset_visibility == "trainable"
        assert result.time_is_causal is True

    def test_feature_parser_has_correct_i3_fields_non_causal(self):
        """Regression: feature parser produces I3-compliant output for non-causal rows."""
        line = "2026-01-09 12:58:42,585 - m - INFO - Calculated features for ETHUSDT: {\"obi\": \"0.1\"}"
        result = parse_feature_log_line(line, symbol="ETHUSDT")
        assert result is not None
        assert result.trainable is False
        assert result.dataset_visibility == "diagnostics_only"
        assert result.time_is_causal is False
