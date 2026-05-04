"""
Neocortex causal state aggregation based on semantic fixed-tick triggers.

This replaces the post-mortem multi-stream stitching pattern from multi_tailer.py
with a clocked state builder that emits a synchronous S_t only when a causal tick
event arrives, for example EVT:BAR_CLOSED or EVT:FEATURES_CALCULATED.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Mapping, MutableMapping, Optional, Sequence

import numpy as np

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.contracts.causal_time import (
    NON_CAUSAL_REASON_CODE,
    make_causal_decision,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
    PRODUCTION_CAUSAL_TIME_PROVENANCE,
    coerce_causal_time_provenance,
)
from apps.reference.domains.neocortex.logic.ingest.normalizer import MultiSymbolWelfordNormalizer
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser


logger = logging.getLogger(__name__)


FEATURE_EVENT_TYPES = {"FEATURES_CALCULATED", "EVT:FEATURES_CALCULATED"}
BAR_EVENT_TYPES = {"BAR_CLOSED", "EVT:BAR_CLOSED"}
REGIME_EVENT_TYPES = {"REGIME_DETECTED", "EVT:REGIME_DETECTED"}
INTENT_EVENT_TYPES = {
    "TRADE_INTENT_PROPOSED",
    "EVT:TRADE_INTENT_PROPOSED",
    "ORDER_INTENT",
}
PORTFOLIO_EVENT_TYPES = {
    "PORTFOLIO_STATE_UPDATED",
    "EVT:PORTFOLIO_STATE_UPDATED",
    "POSITION_OPENED",
    "EVT:POSITION_OPENED",
    "POSITION_CLOSED",
    "EVT:POSITION_CLOSED",
}


@dataclass(frozen=True, slots=True)
class NeocortexStateSnapshot:
    symbol: str
    tick_ts_ms: int
    trigger_event_type: str
    observation: MarketObservation
    context_vector: np.ndarray
    state_vector: np.ndarray
    regime_label: Optional[str]
    regime_confidence: float
    position_side: Optional[str]
    intent_side: Optional[str]
    feature_event_ts_ms: int
    feature_time_provenance: CausalTimeProvenance
    regime_event_ts_ms: Optional[int]
    portfolio_event_ts_ms: Optional[int]
    # Phase 1 I3 fields — always set by _build_snapshot
    event_time_is_causal: bool = False
    trainable: bool = False
    dataset_visibility: str = "diagnostics_only"


class NeocortexStateAggregator:
    """
    Build causal, synchronous state tensors on explicit semantic tick events.

    Design rules:
    - Update internal caches on every relevant event.
    - Emit a state snapshot only on configured trigger events.
    - Normalize using statistics available strictly before the current snapshot.
    - Reject out-of-order trigger timestamps per symbol when strict_clock=True.
    """

    CONTEXT_DIM = 11

    def __init__(
        self,
        ingest_config: IngestConfig,
        *,
        tick_trigger_event_types: Optional[Sequence[str]] = None,
        strict_clock: bool = True,
        neocortex_enforcement_mode: str = "disabled",
        allow_legacy_non_causal_time: bool = False,
    ) -> None:
        self._feature_parser = FeatureParser(ingest_config)
        self._normalizer = MultiSymbolWelfordNormalizer(
            dim=len(ingest_config.feature_list))
        self._tick_triggers = {
            _canonical_event_type(event_type)
            for event_type in (
                tick_trigger_event_types
                if tick_trigger_event_types is not None
                else ("EVT:BAR_CLOSED", "EVT:FEATURES_CALCULATED")
            )
        }
        self._strict_clock = bool(strict_clock)
        self._enforcement_mode = str(
            neocortex_enforcement_mode).strip().lower()
        self._allow_legacy_non_causal_time = bool(allow_legacy_non_causal_time)
        self._feature_cache: dict[str, MutableMapping[str, Any]] = {}
        self._feature_ts_ms: dict[str, int] = {}
        self._regime_cache: dict[str, MutableMapping[str, Any]] = {}
        self._regime_ts_ms: dict[str, int] = {}
        self._portfolio_cache: dict[str, MutableMapping[str, Any]] = {}
        self._portfolio_ts_ms: dict[str, int] = {}
        self._intent_cache: dict[str, MutableMapping[str, Any]] = {}
        self._last_emitted_tick_ts_ms: dict[str, int] = {}

    def ingest_event(self, event: Mapping[str, Any]) -> Optional[NeocortexStateSnapshot]:
        payload = _payload_view(event)
        event_type = _canonical_event_type(event)
        ts_ms = _extract_timestamp_ms(event, payload)
        if ts_ms is None:
            return None

        time_provenance = _extract_time_provenance(event, payload, event_type)

        symbol = _extract_symbol(event, payload)
        if symbol is None:
            return None

        if self._should_drop_non_causal_time(
            symbol=symbol,
            event_type=event_type,
            time_provenance=time_provenance,
        ):
            return None

        if event_type in FEATURE_EVENT_TYPES:
            feature_payload = dict(payload)
            feature_payload.setdefault("symbol", symbol)
            feature_payload.setdefault("timestamp", ts_ms)
            feature_payload.setdefault("event_ts_ms", ts_ms)
            feature_payload.setdefault(
                "time_provenance", time_provenance.value)
            self._feature_cache[symbol] = feature_payload
            self._feature_ts_ms[symbol] = ts_ms

        if event_type in REGIME_EVENT_TYPES:
            self._regime_cache[symbol] = dict(payload)
            self._regime_ts_ms[symbol] = ts_ms

        if event_type in PORTFOLIO_EVENT_TYPES:
            self._portfolio_cache[symbol] = dict(payload)
            self._portfolio_ts_ms[symbol] = ts_ms

        if event_type in INTENT_EVENT_TYPES:
            self._intent_cache[symbol] = dict(payload)

        if event_type not in self._tick_triggers:
            return None

        last_tick_ts_ms = self._last_emitted_tick_ts_ms.get(symbol)
        if self._strict_clock and last_tick_ts_ms is not None and ts_ms <= last_tick_ts_ms:
            return None

        snapshot = self._build_snapshot(
            symbol=symbol, tick_ts_ms=ts_ms, trigger_event_type=event_type)
        if snapshot is not None:
            self._last_emitted_tick_ts_ms[symbol] = ts_ms
        return snapshot

    def reset_symbol(self, symbol: str) -> None:
        normalized = _normalize_symbol(symbol)
        if normalized is None:
            return
        self._feature_cache.pop(normalized, None)
        self._feature_ts_ms.pop(normalized, None)
        self._regime_cache.pop(normalized, None)
        self._regime_ts_ms.pop(normalized, None)
        self._portfolio_cache.pop(normalized, None)
        self._portfolio_ts_ms.pop(normalized, None)
        self._intent_cache.pop(normalized, None)
        self._last_emitted_tick_ts_ms.pop(normalized, None)

    def _build_snapshot(
        self,
        *,
        symbol: str,
        tick_ts_ms: int,
        trigger_event_type: str,
    ) -> Optional[NeocortexStateSnapshot]:
        feature_payload = self._feature_cache.get(symbol)
        feature_ts_ms = self._feature_ts_ms.get(symbol)
        if feature_payload is None or feature_ts_ms is None or feature_ts_ms > tick_ts_ms:
            record_failure_outcome(
                FailureOutcomeTaxonomy.SKIP_ROW,
                "MISSING_REQUIRED_STATE",
                location="neocortex.state_aggregator_v2._build_snapshot",
                detail=symbol,
            )
            return None

        try:
            raw_observation = self._feature_parser.parse(dict(feature_payload))
        except ValueError as error:
            logger.warning(
                "Skipping snapshot due to incomplete feature payload symbol=%s trigger=%s error=%s",
                symbol,
                trigger_event_type,
                error,
            )
            return None
        normalized_features = self._normalizer.normalize(
            symbol, raw_observation.features_vector)
        self._normalizer.update(symbol, raw_observation.features_vector)

        observation = MarketObservation(
            ts=tick_ts_ms / 1000.0,
            mid_price=raw_observation.mid_price,
            volatility=raw_observation.volatility,
            obi=raw_observation.obi,
            features_vector=normalized_features.astype(np.float32),
            event_ts_ms=raw_observation.event_ts_ms,
            time_provenance=raw_observation.time_provenance,
            normalized=True,
        )

        regime_payload = self._regime_cache.get(symbol, {})
        portfolio_payload = self._portfolio_cache.get(symbol, {})
        intent_payload = self._intent_cache.get(symbol, {})

        regime_confidence = _safe_float(
            regime_payload.get("confidence")
            or regime_payload.get("regime_confidence")
            or regime_payload.get("stable_confidence"),
            default=0.0,
        )
        position_qty = _safe_float(
            portfolio_payload.get("position_qty")
            or portfolio_payload.get("quantity")
            or portfolio_payload.get("portfolio_position_amt"),
            default=0.0,
        )
        mark_price = _safe_float(
            portfolio_payload.get(
                "mark_price") or portfolio_payload.get("mid_price"),
            default=0.0,
        )
        unrealized_pnl = _safe_float(
            portfolio_payload.get("unrealized_pnl_usdt")
            or portfolio_payload.get("unrealized_pnl")
            or portfolio_payload.get("realized_pnl_net"),
            default=0.0,
        )
        intent_quantity = _safe_float(
            intent_payload.get("quantity"), default=0.0)

        context_vector = np.asarray(
            [
                regime_confidence,
                position_qty,
                mark_price,
                unrealized_pnl,
                intent_quantity,
                _encode_side(portfolio_payload.get("side")
                             or portfolio_payload.get("position_side")),
                _encode_side(intent_payload.get("side")),
                1.0 if feature_ts_ms <= tick_ts_ms else 0.0,
                1.0 if symbol in self._regime_ts_ms and self._regime_ts_ms[
                    symbol] <= tick_ts_ms else 0.0,
                1.0 if symbol in self._portfolio_ts_ms and self._portfolio_ts_ms[
                    symbol] <= tick_ts_ms else 0.0,
                1.0 if trigger_event_type in BAR_EVENT_TYPES else 0.0,
            ],
            dtype=np.float32,
        )
        state_vector = np.concatenate(
            [observation.features_vector, context_vector]).astype(np.float32)

        _decision = make_causal_decision(
            feature_ts_ms, raw_observation.time_provenance
        )
        return NeocortexStateSnapshot(
            symbol=symbol,
            tick_ts_ms=tick_ts_ms,
            trigger_event_type=trigger_event_type,
            observation=observation,
            context_vector=context_vector,
            state_vector=state_vector,
            regime_label=_first_non_empty(
                regime_payload.get("regime"),
                regime_payload.get("label"),
            ),
            regime_confidence=regime_confidence,
            position_side=_first_non_empty(
                portfolio_payload.get("side"),
                portfolio_payload.get("position_side"),
            ),
            intent_side=_first_non_empty(intent_payload.get("side")),
            feature_event_ts_ms=feature_ts_ms,
            feature_time_provenance=raw_observation.time_provenance,
            regime_event_ts_ms=self._regime_ts_ms.get(symbol),
            portfolio_event_ts_ms=self._portfolio_ts_ms.get(symbol),
            event_time_is_causal=_decision.event_time_is_causal,
            trainable=_decision.trainable,
            dataset_visibility=_decision.dataset_visibility,
        )

    def _should_drop_non_causal_time(
        self,
        *,
        symbol: str,
        event_type: str,
        time_provenance: CausalTimeProvenance,
    ) -> bool:
        if self._enforcement_mode not in {"shadow", "enforce"}:
            return False
        if self._allow_legacy_non_causal_time:
            return False
        if time_provenance in PRODUCTION_CAUSAL_TIME_PROVENANCE:
            return False
        record_failure_outcome(
            FailureOutcomeTaxonomy.SKIP_ROW,
            NON_CAUSAL_REASON_CODE,
            location="neocortex.state_aggregator_v2._should_drop_non_causal_time",
            detail=symbol,
        )
        logger.warning(
            "Dropping non-causal Neocortex event symbol=%s event_type=%s provenance=%s mode=%s reason_code=%s",
            symbol,
            event_type,
            time_provenance.value,
            self._enforcement_mode,
            NON_CAUSAL_REASON_CODE,
        )
        return True


def _payload_view(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = event.get("payload") or event.get("pld")
    return payload if isinstance(payload, Mapping) else event


def _canonical_event_type(event: Mapping[str, Any] | str) -> str:
    raw: object | None
    op: object | None
    if isinstance(event, str):
        raw = event
        op = None
    else:
        raw = event.get("event_type") or event.get(
            "verb") or event.get("event_name")
        op = event.get("op")
    text = str(raw or "UNKNOWN").strip().upper()
    if op == "EVT" and not text.startswith("EVT:"):
        return f"EVT:{text}"
    return text


def _normalize_symbol(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _extract_symbol(event: Mapping[str, Any], payload: Mapping[str, Any]) -> Optional[str]:
    return _normalize_symbol(
        payload.get("symbol")
        or payload.get("instrument")
        or event.get("symbol")
        or event.get("instrument")
    )


def _extract_timestamp_ms(event: Mapping[str, Any], payload: Mapping[str, Any]) -> Optional[int]:
    for candidate in (
        payload.get("event_ts_ms"),
        payload.get("timestamp_ms"),
        payload.get("timestamp"),
        payload.get("ts_ms"),
        payload.get("ts"),
        event.get("event_ts_ms"),
        event.get("timestamp_ms"),
        event.get("timestamp"),
        event.get("ts_ms"),
        event.get("ts"),
    ):
        normalized = _normalize_epoch_to_ms(candidate)
        if normalized is not None:
            return normalized
    return None


def _extract_time_provenance(
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
    event_type: str,
) -> CausalTimeProvenance:
    _PROVENANCE_KEYS = (
        "time_provenance",
        "causal_time_provenance",
        "event_time_provenance",
        "time_source",
        "event_time_source",
    )
    # Phase 1 I3: If ANY provenance key is explicitly present in payload or event,
    # respect the explicit value — even if it resolves to UNKNOWN (non-causal).
    # Only apply structural fallbacks when NO provenance field is present at all.
    for key in _PROVENANCE_KEYS:
        if key in payload:
            return coerce_causal_time_provenance(payload[key])
        if key in event:
            return coerce_causal_time_provenance(event[key])

    # No provenance field present at all: apply structural fallback based on event type.
    # Handles events from sources that pre-date explicit provenance annotation.
    if event_type in BAR_EVENT_TYPES:
        return CausalTimeProvenance.BAR_END
    if event_type in FEATURE_EVENT_TYPES | REGIME_EVENT_TYPES | INTENT_EVENT_TYPES | PORTFOLIO_EVENT_TYPES:
        return CausalTimeProvenance.AURORA_EVENT
    return CausalTimeProvenance.UNKNOWN


def _normalize_epoch_to_ms(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric) or numeric <= 0.0:
        return None
    if numeric >= 1e11:
        return int(round(numeric))
    if numeric >= 1e9:
        return int(round(numeric * 1000.0))
    return None


def _safe_float(value: Any, *, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(numeric):
        return float(default)
    return float(numeric)


def _encode_side(value: Any) -> float:
    text = str(value or "").strip().upper()
    if text in {"BUY", "LONG"}:
        return 1.0
    if text in {"SELL", "SHORT"}:
        return -1.0
    return 0.0


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
