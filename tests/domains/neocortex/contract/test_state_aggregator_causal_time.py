"""Phase 1 Closure — state_aggregator_v2 causal-time propagation contract tests.

Proves that NeocortexStateAggregator satisfies invariant I3:
- Every emitted NeocortexStateSnapshot carries event_time_is_causal, trainable,
  dataset_visibility derived from the feature row's CausalTimeProvenance.
- A causal feature row produces a causal/trainable snapshot.
- A non-causal feature row produces a non-trainable, diagnostics_only snapshot.
- reason_code NON_CAUSAL_TIME is preserved in non-causal decisions.
- The aggregator never synthesizes causal event_ts_ms from wallclock/captured/file-offset.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import numpy as np
import pytest

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.contracts.causal_time import (
    NON_CAUSAL_REASON_CODE,
    get_non_causal_counter,
    reset_non_causal_counter,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
    NeocortexStateSnapshot,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FEATURE_LIST = ["obi", "tfi", "mid_price", "volatility"]


def _make_ingest_config() -> IngestConfig:
    return IngestConfig(
        feature_list=FEATURE_LIST,
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        price_feature_mode="raw",
        delta_price_mode="raw",
        feature_clip_abs={},
        buffer_size=1000,
        min_samples_before_ready=1,
        nan_strategy="zero",
    )


def _make_aggregator(*, enforcement_mode: str = "disabled") -> NeocortexStateAggregator:
    return NeocortexStateAggregator(
        _make_ingest_config(),
        neocortex_enforcement_mode=enforcement_mode,
        strict_clock=False,
    )


def _feature_event(
    ts_ms: int,
    provenance: CausalTimeProvenance,
    symbol: str = "BTCUSDT",
) -> Dict[str, Any]:
    """Build a synthetic FEATURES_CALCULATED event with explicit provenance."""
    return {
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": symbol,
        "payload": {
            "symbol": symbol,
            "event_ts_ms": ts_ms,
            "time_provenance": provenance.value,
            "obi": 0.3,
            "tfi": 0.5,
            "mid_price": 50000.0,
            "volatility": 0.01,
        },
    }


def _bar_event(
    ts_ms: int,
    provenance: CausalTimeProvenance,
    symbol: str = "BTCUSDT",
) -> Dict[str, Any]:
    """Build a synthetic BAR_CLOSED tick-trigger event."""
    return {
        "event_type": "EVT:BAR_CLOSED",
        "symbol": symbol,
        "payload": {
            "symbol": symbol,
            "event_ts_ms": ts_ms,
            "time_provenance": provenance.value,
        },
    }


def _emit_snapshot(
    aggregator: NeocortexStateAggregator,
    feature_provenance: CausalTimeProvenance,
    bar_provenance: CausalTimeProvenance = CausalTimeProvenance.BAR_END,
    feature_ts_ms: int = 1_700_000_000_000,
    bar_ts_ms: int = 1_700_000_001_000,
    symbol: str = "BTCUSDT",
) -> NeocortexStateSnapshot | None:
    """Helper: ingest a feature event then a bar-close trigger; return emitted snapshot."""
    aggregator.ingest_event(_feature_event(feature_ts_ms, feature_provenance, symbol))
    snapshot = aggregator.ingest_event(_bar_event(bar_ts_ms, bar_provenance, symbol))
    return snapshot


# ---------------------------------------------------------------------------
# Test 1: causal feature row → causal / trainable snapshot
# ---------------------------------------------------------------------------

class TestCausalFeatureRowProducesCausalSnapshot:

    def test_exchange_event_snapshot_is_causal(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.EXCHANGE_EVENT)
        assert snap is not None
        assert snap.event_time_is_causal is True

    def test_aurora_event_snapshot_is_trainable(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        assert snap.trainable is True

    def test_bar_end_snapshot_is_trainable_and_visible(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.BAR_END)
        assert snap is not None
        assert snap.trainable is True
        assert snap.dataset_visibility == "trainable"

    def test_causal_snapshot_has_no_non_causal_dataset_visibility(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        assert snap.dataset_visibility != "diagnostics_only"


# ---------------------------------------------------------------------------
# Test 2: non-causal parser row remains trainable=False after aggregation
# ---------------------------------------------------------------------------

class TestNonCausalFeatureRowRemainsNonTrainable:

    def test_captured_wallclock_feature_not_trainable(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert snap is not None, (
            "In enforcement_mode='disabled', non-causal event is not dropped — "
            "snapshot is emitted but must be non-trainable"
        )
        assert snap.trainable is False, (
            "Captured wallclock feature must produce trainable=False snapshot"
        )

    def test_file_offset_feature_not_trainable(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert snap is not None
        assert snap.trainable is False

    def test_unknown_provenance_feature_not_trainable(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.UNKNOWN)
        assert snap is not None
        assert snap.trainable is False


# ---------------------------------------------------------------------------
# Test 3: non-causal feature row has dataset_visibility=diagnostics_only
# ---------------------------------------------------------------------------

class TestNonCausalSnapshotDatasetVisibility:

    def test_captured_wallclock_is_diagnostics_only(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert snap is not None
        assert snap.dataset_visibility == "diagnostics_only", (
            "Captured wallclock snapshot must have dataset_visibility='diagnostics_only'"
        )

    def test_file_offset_is_diagnostics_only(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert snap is not None
        assert snap.dataset_visibility == "diagnostics_only"

    def test_unknown_is_diagnostics_only(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.UNKNOWN)
        assert snap is not None
        assert snap.dataset_visibility == "diagnostics_only"

    def test_causal_events_are_not_diagnostics_only(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        assert snap.dataset_visibility == "trainable"


# ---------------------------------------------------------------------------
# Test 4: reason_code NON_CAUSAL_TIME is preserved / counter increments
# ---------------------------------------------------------------------------

class TestNonCausalReasonCodePreserved:
    """The aggregator calls make_causal_decision() which increments the
    dataset.invalid_total{reason_code=NON_CAUSAL_TIME} counter for non-causal
    feature provenance. This proves observability at the aggregator level."""

    def setup_method(self):
        reset_non_causal_counter()

    def teardown_method(self):
        reset_non_causal_counter()

    def test_non_causal_snapshot_increments_counter(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        before = get_non_causal_counter()
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert snap is not None
        after = get_non_causal_counter()
        assert after > before, (
            "Emitting a non-causal snapshot must increment the NON_CAUSAL_TIME counter"
        )

    def test_causal_snapshot_does_not_increment_counter(self):
        agg = _make_aggregator()
        before = get_non_causal_counter()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        after = get_non_causal_counter()
        assert after == before, (
            "Emitting a causal snapshot must NOT increment the NON_CAUSAL_TIME counter"
        )

    def test_non_causal_snapshot_feature_provenance_matches_non_causal(self):
        """Snapshot.feature_time_provenance must match the non-causal source."""
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert snap is not None
        assert snap.feature_time_provenance == CausalTimeProvenance.CAPTURED_WALLCLOCK


# ---------------------------------------------------------------------------
# Test 5: aggregator does NOT synthesize causal event_ts_ms from wallclock
# ---------------------------------------------------------------------------

class TestAggregatorDoesNotSynthesizeCausalTime:
    """The aggregator must never upgrade a non-causal provenance to causal.
    It must also not use time.time() / datetime.now() to derive event_ts_ms."""

    def test_wallclock_provenance_is_not_upgraded_to_causal(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert snap is not None
        # The snapshot carries the original provenance — not upgraded
        assert snap.feature_time_provenance == CausalTimeProvenance.CAPTURED_WALLCLOCK
        assert snap.event_time_is_causal is False

    def test_file_offset_provenance_is_not_upgraded_to_causal(self):
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.FILE_OFFSET_LEGACY)
        assert snap is not None
        assert snap.feature_time_provenance == CausalTimeProvenance.FILE_OFFSET_LEGACY
        assert snap.event_time_is_causal is False

    def test_feature_event_ts_ms_matches_payload_not_wall_clock(self):
        """feature_event_ts_ms on snapshot must equal the payload event_ts_ms, not time.time()."""
        EXPECTED_TS_MS = 1_700_555_000_000
        agg = _make_aggregator()
        agg.ingest_event(_feature_event(EXPECTED_TS_MS, CausalTimeProvenance.AURORA_EVENT))
        snap = agg.ingest_event(_bar_event(EXPECTED_TS_MS + 1000, CausalTimeProvenance.BAR_END))
        assert snap is not None
        assert snap.feature_event_ts_ms == EXPECTED_TS_MS, (
            f"feature_event_ts_ms must come from payload ({EXPECTED_TS_MS}), "
            f"not from wall clock (got {snap.feature_event_ts_ms})"
        )

    def test_shadow_mode_drops_non_causal_events(self):
        """In enforcement_mode='shadow', non-causal events are dropped (return None)."""
        agg = _make_aggregator(enforcement_mode="shadow")
        # Ingest a non-causal feature event then a bar trigger
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        # The bar trigger fires but feature cache is empty (non-causal was dropped)
        # So _build_snapshot returns None because feature_cache has no entry
        assert snap is None, (
            "In enforcement_mode='shadow', non-causal events must be dropped "
            "and the aggregator must not emit a snapshot"
        )

    def test_enforcement_disabled_allows_non_causal_but_marks_it(self):
        """In enforcement_mode='disabled', non-causal events pass through
        but the snapshot must carry event_time_is_causal=False."""
        agg = _make_aggregator(enforcement_mode="disabled")
        snap = _emit_snapshot(agg, CausalTimeProvenance.CAPTURED_WALLCLOCK)
        assert snap is not None, "enforcement_mode='disabled' must not drop non-causal events"
        assert snap.event_time_is_causal is False, (
            "Even in disabled mode, the snapshot must be honest about causal status"
        )
        assert snap.trainable is False


# ---------------------------------------------------------------------------
# Test 6: I3 fields are always present on NeocortexStateSnapshot
# ---------------------------------------------------------------------------

class TestSnapshotAlwaysHasI3Fields:

    def test_snapshot_has_event_time_is_causal_field(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        assert hasattr(snap, "event_time_is_causal"), (
            "NeocortexStateSnapshot must have event_time_is_causal field"
        )

    def test_snapshot_has_trainable_field(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        assert hasattr(snap, "trainable"), (
            "NeocortexStateSnapshot must have trainable field"
        )

    def test_snapshot_has_dataset_visibility_field(self):
        agg = _make_aggregator()
        snap = _emit_snapshot(agg, CausalTimeProvenance.AURORA_EVENT)
        assert snap is not None
        assert hasattr(snap, "dataset_visibility"), (
            "NeocortexStateSnapshot must have dataset_visibility field"
        )

    def test_snapshot_i3_fields_are_internally_consistent(self):
        """If causal → trainable=True, visibility=trainable. If not → trainable=False."""
        for provenance, expect_causal in [
            (CausalTimeProvenance.AURORA_EVENT, True),
            (CausalTimeProvenance.BAR_END, True),
            (CausalTimeProvenance.CAPTURED_WALLCLOCK, False),
            (CausalTimeProvenance.FILE_OFFSET_LEGACY, False),
        ]:
            agg = _make_aggregator(enforcement_mode="disabled")
            snap = _emit_snapshot(agg, provenance)
            assert snap is not None, f"snapshot must be emitted for {provenance}"
            if expect_causal:
                assert snap.event_time_is_causal is True, f"expected causal for {provenance}"
                assert snap.trainable is True, f"expected trainable for {provenance}"
                assert snap.dataset_visibility == "trainable", f"expected trainable visibility for {provenance}"
            else:
                assert snap.event_time_is_causal is False, f"expected non-causal for {provenance}"
                assert snap.trainable is False, f"expected non-trainable for {provenance}"
                assert snap.dataset_visibility == "diagnostics_only", f"expected diagnostics_only for {provenance}"
