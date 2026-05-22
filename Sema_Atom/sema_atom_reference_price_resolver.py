from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LEVEL_0 = "0_explicit_low_vol_cost_floor"
LEVEL_1 = "1_explicit_reference_or_intended"
LEVEL_2 = "2_explicit_economics_context"
LEVEL_3 = "3_linked_order_intent"
LEVEL_4 = "4_recorder_derived_diagnostics_only"
LEVEL_5 = "5_missing"

TRAINABILITY_TRAINABLE = "trainable"
TRAINABILITY_DIAGNOSTICS_ONLY = "diagnostics_only"
TRAINABILITY_MISSING = "missing"
TRAINABILITY_INVALID = "invalid"

TRAINABLE_LEVELS: frozenset[str] = frozenset({LEVEL_0, LEVEL_1, LEVEL_2, LEVEL_3})
DIAGNOSTICS_ONLY_LEVELS: frozenset[str] = frozenset({LEVEL_4})


@dataclass(slots=True)
class ReferencePriceResolution:
    reference_price: float | None
    source: str
    source_level: str
    trainability: str
    recovery_reason: str
    causal_link_ok: bool


def _safe_float_r(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_nested(data: Any, *keys: str) -> Any:
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def resolve_reference_price(
    row: dict[str, Any],
    *,
    recorder_bar_price: float | None = None,
) -> ReferencePriceResolution:
    """
    Deterministic reference price resolver for rejected decisions.

    Priority order:
      Level 0 — metadata.low_vol_cost_floor.entry_price          → trainable
      Level 1 — metadata.reference_price / intended_entry_price  → trainable
      Level 2 — metadata.economics_context.entry_price           → trainable
      Level 3 — metadata.linked_order_intent.entry_price         → trainable (causal link required)
      Level 4 — recorder_bar_price (injected externally)         → diagnostics_only, NOT trainable
      Level 5 — no usable price                                  → missing

    Recorder-derived price is never trainable; it is market-observed, not
    proven strategy-intended entry price.
    """
    metadata: dict[str, Any] = (
        row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    )

    # Level 0 — explicit low_vol_cost_floor.entry_price
    price = _safe_float_r(_get_nested(metadata, "low_vol_cost_floor", "entry_price"))
    if price is not None:
        return ReferencePriceResolution(
            reference_price=price,
            source="metadata.low_vol_cost_floor.entry_price",
            source_level=LEVEL_0,
            trainability=TRAINABILITY_TRAINABLE,
            recovery_reason="level_0_explicit_low_vol_cost_floor",
            causal_link_ok=True,
        )

    # Level 1 — explicit reference_price / intended_entry_price
    _level1: list[tuple[str, float | None]] = [
        ("metadata.reference_price", _safe_float_r(metadata.get("reference_price"))),
        (
            "metadata.intended_entry_price",
            _safe_float_r(metadata.get("intended_entry_price")),
        ),
        ("reference_price", _safe_float_r(row.get("reference_price"))),
        ("intended_entry_price", _safe_float_r(row.get("intended_entry_price"))),
    ]
    for source_name, price in _level1:
        if price is not None:
            return ReferencePriceResolution(
                reference_price=price,
                source=source_name,
                source_level=LEVEL_1,
                trainability=TRAINABILITY_TRAINABLE,
                recovery_reason="level_1_explicit_reference_or_intended",
                causal_link_ok=True,
            )

    # Level 2 — economics_context.entry_price
    price = _safe_float_r(_get_nested(metadata, "economics_context", "entry_price"))
    if price is not None:
        return ReferencePriceResolution(
            reference_price=price,
            source="metadata.economics_context.entry_price",
            source_level=LEVEL_2,
            trainability=TRAINABILITY_TRAINABLE,
            recovery_reason="level_2_explicit_economics_context",
            causal_link_ok=True,
        )

    # Level 3 — linked_order_intent.entry_price with causal link validation
    linked_oi = metadata.get("linked_order_intent")
    if isinstance(linked_oi, dict):
        price = _safe_float_r(linked_oi.get("entry_price"))
        if price is not None:
            link_ts = _safe_float_r(linked_oi.get("timestamp"))
            row_ts = _safe_float_r(row.get("timestamp"))
            if link_ts is not None and row_ts is not None and link_ts > row_ts:
                return ReferencePriceResolution(
                    reference_price=None,
                    source="metadata.linked_order_intent.entry_price",
                    source_level=LEVEL_3,
                    trainability=TRAINABILITY_INVALID,
                    recovery_reason="level_3_causal_link_failed_timestamp_after_rejected",
                    causal_link_ok=False,
                )
            return ReferencePriceResolution(
                reference_price=price,
                source="metadata.linked_order_intent.entry_price",
                source_level=LEVEL_3,
                trainability=TRAINABILITY_TRAINABLE,
                recovery_reason="level_3_linked_order_intent",
                causal_link_ok=True,
            )

    # Level 3 fallbacks — other linked price fields
    _level3_fallbacks: list[tuple[str, float | None]] = [
        (
            "metadata.linked_planned_entry_price",
            _safe_float_r(metadata.get("linked_planned_entry_price")),
        ),
        (
            "metadata.planned_entry_price",
            _safe_float_r(metadata.get("planned_entry_price")),
        ),
        ("planned_entry_price", _safe_float_r(row.get("planned_entry_price"))),
    ]
    for source_name, price in _level3_fallbacks:
        if price is not None:
            return ReferencePriceResolution(
                reference_price=price,
                source=source_name,
                source_level=LEVEL_3,
                trainability=TRAINABILITY_TRAINABLE,
                recovery_reason="level_3_linked_order_intent_fallback",
                causal_link_ok=True,
            )

    # Level 4 — recorder-derived price (diagnostics_only, not trainable)
    if recorder_bar_price is not None:
        price = _safe_float_r(recorder_bar_price)
        if price is not None:
            return ReferencePriceResolution(
                reference_price=price,
                source="recorder_bar_price",
                source_level=LEVEL_4,
                trainability=TRAINABILITY_DIAGNOSTICS_ONLY,
                recovery_reason="level_4_recorder_derived_diagnostics_only",
                causal_link_ok=False,
            )

    # Level 5 — no usable price
    return ReferencePriceResolution(
        reference_price=None,
        source="none",
        source_level=LEVEL_5,
        trainability=TRAINABILITY_MISSING,
        recovery_reason="level_5_missing_no_usable_price",
        causal_link_ok=False,
    )
