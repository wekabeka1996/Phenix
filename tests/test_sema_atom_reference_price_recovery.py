from __future__ import annotations

import SEMA_ATOM_POC_02_REAL_LOG_ADAPTER as poc02
from sema_atom_reference_price_resolver import (
    LEVEL_0,
    LEVEL_1,
    LEVEL_2,
    LEVEL_3,
    LEVEL_4,
    LEVEL_5,
    TRAINABILITY_DIAGNOSTICS_ONLY,
    TRAINABILITY_INVALID,
    TRAINABILITY_MISSING,
    TRAINABILITY_TRAINABLE,
    ReferencePriceResolution,
    resolve_reference_price,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rejected_row(
    *,
    rid: str = "r-test",
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    strategy_id: str = "aurora",
    regime: str = "LOW_VOLATILITY",
    regime_confidence: float = 0.4,
    timestamp: int = 1_778_202_000_000,
    metadata: dict | None = None,
    **extra,
) -> dict:
    row: dict = {
        "rid": rid,
        "event_type": "DECISION_INTENT_REJECTED",
        "symbol": symbol,
        "side": side,
        "strategy_id": strategy_id,
        "regime": regime,
        "regime_confidence": regime_confidence,
        "timestamp": timestamp,
    }
    if metadata is not None:
        row["metadata"] = metadata
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# Tests 1–7: pure resolver tests (no collector)
# ---------------------------------------------------------------------------


def test_level_0_low_vol_cost_floor_is_trainable() -> None:
    row = _rejected_row(
        metadata={"low_vol_cost_floor": {"entry_price": 101.5, "direction_confidence": 0.3}}
    )
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_0
    assert r.trainability == TRAINABILITY_TRAINABLE
    assert r.reference_price == 101.5
    assert r.causal_link_ok is True


def test_level_1_metadata_reference_price_is_trainable() -> None:
    row = _rejected_row(metadata={"reference_price": 99.0})
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_1
    assert r.trainability == TRAINABILITY_TRAINABLE
    assert r.reference_price == 99.0
    assert r.causal_link_ok is True


def test_level_1_top_level_intended_entry_price_is_trainable() -> None:
    # Top-level intended_entry_price (no metadata price fields set)
    row = _rejected_row(intended_entry_price=98.5)
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_1
    assert r.trainability == TRAINABILITY_TRAINABLE
    assert r.reference_price == 98.5
    assert r.causal_link_ok is True


def test_level_2_economics_context_entry_price_is_trainable() -> None:
    row = _rejected_row(metadata={"economics_context": {"entry_price": 97.25}})
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_2
    assert r.trainability == TRAINABILITY_TRAINABLE
    assert r.reference_price == 97.25
    assert r.causal_link_ok is True


def test_level_3_linked_order_intent_with_valid_causal_link_is_trainable() -> None:
    # link_ts < row_ts → causal link valid
    row = _rejected_row(
        timestamp=1_000_000,
        metadata={
            "linked_order_intent": {
                "entry_price": 95.0,
                "timestamp": 999_000,  # before rejected event
            }
        },
    )
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_3
    assert r.trainability == TRAINABILITY_TRAINABLE
    assert r.reference_price == 95.0
    assert r.causal_link_ok is True


def test_level_3_linked_order_intent_after_rejected_ts_is_invalid() -> None:
    # link_ts > row_ts → causal link broken, must not create a trainable atom
    row = _rejected_row(
        timestamp=1_000_000,
        metadata={
            "linked_order_intent": {
                "entry_price": 95.0,
                "timestamp": 1_000_001,  # AFTER the rejected event
            }
        },
    )
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_3
    assert r.trainability == TRAINABILITY_INVALID
    assert r.reference_price is None
    assert r.causal_link_ok is False


def test_level_4_recorder_bar_price_is_diagnostics_only_not_trainable() -> None:
    # Row has no trainable price fields; recorder_bar_price injected externally
    row = _rejected_row()  # no metadata prices
    r = resolve_reference_price(row, recorder_bar_price=88.8)
    assert r.source_level == LEVEL_4
    assert r.trainability == TRAINABILITY_DIAGNOSTICS_ONLY
    assert r.reference_price == 88.8
    assert r.causal_link_ok is False


def test_level_5_no_price_is_missing() -> None:
    row = _rejected_row()  # no metadata, no recorder price
    r = resolve_reference_price(row)
    assert r.source_level == LEVEL_5
    assert r.trainability == TRAINABILITY_MISSING
    assert r.reference_price is None


# ---------------------------------------------------------------------------
# Tests 8–10: collector integration via POC_02 RejectedDecisionCollector
# ---------------------------------------------------------------------------


def test_level_5_missing_price_produces_no_atom_in_collector() -> None:
    # Row with no price fields → Level 5 → collector skips → 0 contracts
    rows = [_rejected_row()]
    contracts, results = poc02.RejectedDecisionCollector(rows).collect()
    assert contracts == []
    assert results["rejected_events_found"] == 1
    buckets = results["incomplete_rejected_buckets"]
    assert buckets.get("incomplete_rejected_missing_reference_price", 0) == 1
    assert results["reference_price_source_level_histogram"].get(LEVEL_5, 0) == 1


def test_no_trainable_atom_created_from_diagnostics_only_price(monkeypatch) -> None:
    # Monkeypatch resolver inside poc02 module to return diagnostics_only
    diag_resolution = ReferencePriceResolution(
        reference_price=88.8,
        source="recorder_bar_price",
        source_level=LEVEL_4,
        trainability=TRAINABILITY_DIAGNOSTICS_ONLY,
        recovery_reason="level_4_recorder_derived_diagnostics_only",
        causal_link_ok=False,
    )
    monkeypatch.setattr(poc02, "resolve_reference_price", lambda row, **kw: diag_resolution)

    rows = [_rejected_row()]
    contracts, results = poc02.RejectedDecisionCollector(rows).collect()
    assert contracts == []
    buckets = results["incomplete_rejected_buckets"]
    assert buckets.get("incomplete_rejected_diagnostics_only_reference_price", 0) == 1


def test_source_level_histogram_reconciles_with_rejected_counts() -> None:
    # 3 rows: level 0 (trainable), level 1 (trainable), level 5 (missing)
    row_l0 = _rejected_row(
        rid="r0",
        metadata={"low_vol_cost_floor": {"entry_price": 100.0}},
    )
    row_l1 = _rejected_row(
        rid="r1",
        metadata={"reference_price": 101.0},
    )
    row_l5 = _rejected_row(rid="r5")  # no prices

    rows = [row_l0, row_l1, row_l5]
    contracts, results = poc02.RejectedDecisionCollector(rows).collect()

    histogram = results["reference_price_source_level_histogram"]
    # All 3 rejected events counted in histogram (before skip)
    assert sum(histogram.values()) == 3
    assert histogram.get(LEVEL_0, 0) == 1
    assert histogram.get(LEVEL_1, 0) == 1
    assert histogram.get(LEVEL_5, 0) == 1

    # Only 2 trainable rows become contracts
    assert len(contracts) == 2
    assert all(
        c.provenance["reference_price_trainability"] == TRAINABILITY_TRAINABLE
        for c in contracts
    )
    # Level 5 skipped
    buckets = results["incomplete_rejected_buckets"]
    assert buckets.get("incomplete_rejected_missing_reference_price", 0) == 1
