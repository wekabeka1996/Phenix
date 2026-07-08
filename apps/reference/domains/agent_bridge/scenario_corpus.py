"""Deterministic no-model/no-execution ActionReview corpus generation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from .action_review import ActionReviewV1, finalize_action_review, review_ref


HORIZONS = ("micro_observation", "scalp_observation")
Horizon = Literal["micro_observation", "scalp_observation"]


@dataclass(frozen=True)
class PacketObservation:
    packet_id: str
    produced_ts_ms: int
    payload: dict[str, Any]
    source_ref: str


def load_packet_observations(path: Path) -> list[PacketObservation]:
    observations: list[PacketObservation] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            envelope = json.loads(line)
            packet = envelope.get("packet", envelope)
            packet_id = str(packet["packet_id"])
            produced = int(packet["produced_ts_ms"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        observations.append(PacketObservation(
            packet_id=packet_id,
            produced_ts_ms=produced,
            payload=packet,
            source_ref=f"agent-feed-sample://{Path(path).name}#line={line_no}",
        ))
    return observations


def validate_fresh_packet_observations(
    observations: Iterable[PacketObservation],
    *,
    required_symbols: Iterable[str] = ("BTCUSDT", "ETHUSDT"),
) -> list[PacketObservation]:
    """Fail closed unless every packet proves fresh direct-main no-order observation."""

    rows = list(observations)
    if not rows:
        raise ValueError("fresh packet observation set is empty")
    required = {symbol.strip().upper() for symbol in required_symbols}
    seen_ids: set[str] = set()
    for row in rows:
        packet = row.payload
        if row.packet_id in seen_ids:
            raise ValueError(f"duplicate packet id: {row.packet_id}")
        seen_ids.add(row.packet_id)
        if packet.get("read_only") is not True:
            raise ValueError(f"packet is not read-only: {row.packet_id}")
        freshness = packet.get("freshness_summary") or {}
        fresh = int(freshness.get("fresh") or 0)
        unavailable = int(freshness.get("stale") or 0) + int(freshness.get("missing") or 0)
        if fresh <= unavailable:
            raise ValueError(f"freshness is not dominant: {row.packet_id}")
        markets = {
            str(item.get("symbol", "")).upper(): item
            for item in packet.get("symbol_markets", [])
            if isinstance(item, dict)
        }
        if not required.issubset(markets):
            raise ValueError(f"required symbol market missing: {row.packet_id}")
        for symbol in required:
            meta = markets[symbol].get("meta") or {}
            if meta.get("freshness") != "fresh" or meta.get("source_ownership") != "direct_main_publication":
                raise ValueError(f"symbol is not fresh direct-main publication: {row.packet_id}:{symbol}")
        execution = packet.get("execution_body") or {}
        meta = execution.get("meta") or {}
        if meta.get("freshness") != "fresh" or meta.get("source_ownership") != "direct_main_publication":
            raise ValueError(f"execution readiness is not fresh direct-main publication: {row.packet_id}")
        invariants = {item.get("name"): item for item in execution.get("invariants", []) if isinstance(item, dict)}
        isolation = invariants.get("no_order_execution_isolation") or {}
        if isolation.get("status") != "ready":
            raise ValueError(f"no-order isolation is not ready: {row.packet_id}")
    return rows


def load_fresh_packet_observations(
    path: Path,
    *,
    required_symbols: Iterable[str] = ("BTCUSDT", "ETHUSDT"),
) -> list[PacketObservation]:
    return validate_fresh_packet_observations(
        load_packet_observations(path), required_symbols=required_symbols
    )


def load_multi_session_packet_observations(
    path: Path,
    *,
    minimum_sessions: int = 3,
    minimum_packets_per_session: int = 100,
    required_symbols: Iterable[str] = ("BTCUSDT", "ETHUSDT"),
) -> dict[str, list[PacketObservation]]:
    """Load a tagged JSONL sample and fail closed on session count, size, or overlap."""

    grouped: dict[str, list[PacketObservation]] = {}
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        try:
            envelope = json.loads(line)
            session_id = str(envelope["p14_session_id"]).strip().lower()
            packet = envelope.get("packet", envelope)
            observation = PacketObservation(
                packet_id=str(packet["packet_id"]),
                produced_ts_ms=int(packet["produced_ts_ms"]),
                payload=packet,
                source_ref=f"agent-feed-sample://{Path(path).name}#session={session_id}&line={line_no}",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid tagged session row {line_no}") from exc
        if not session_id or not session_id.replace("_", "").isalnum():
            raise ValueError(f"invalid session id at row {line_no}")
        grouped.setdefault(session_id, []).append(observation)
    if len(grouped) < minimum_sessions:
        raise ValueError(f"expected at least {minimum_sessions} sessions, got {len(grouped)}")
    seen_ids: set[str] = set()
    boundaries: list[tuple[int, int, str]] = []
    for session_id, rows in grouped.items():
        if len(rows) < minimum_packets_per_session:
            raise ValueError(f"session {session_id} has only {len(rows)} packets")
        validate_fresh_packet_observations(rows, required_symbols=required_symbols)
        overlap = seen_ids.intersection(row.packet_id for row in rows)
        if overlap:
            raise ValueError(f"packet id reused across sessions: {sorted(overlap)[0]}")
        seen_ids.update(row.packet_id for row in rows)
        boundaries.append((rows[0].produced_ts_ms, rows[-1].produced_ts_ms, session_id))
    boundaries.sort()
    for previous, current in zip(boundaries, boundaries[1:]):
        if current[0] <= previous[1]:
            raise ValueError(f"sessions overlap: {previous[2]} and {current[2]}")
    return {session_id: grouped[session_id] for _, _, session_id in boundaries}


def _symbol_values(packet: dict[str, Any], symbol: str) -> tuple[Optional[float], Optional[float]]:
    market = next((item for item in packet.get("symbol_markets", []) if item.get("symbol") == symbol), {})
    features = next((item for item in packet.get("feature_signals", []) if item.get("symbol") == symbol), {})
    try:
        price = float(market.get("close_price"))
    except (TypeError, ValueError):
        price = None
    try:
        volatility = float(features.get("volatility"))
    except (TypeError, ValueError):
        volatility = None
    return price, volatility


def classify_scenario(
    before: PacketObservation,
    after: PacketObservation,
    *,
    symbol: str,
    horizon: Horizon,
) -> tuple[str, str]:
    """Apply explicit packet-only heuristics; never infer PnL or trading permission."""

    return classify_scenario_with_thresholds(
        before, after, symbol=symbol, horizon=horizon,
        directional_scale=1.0, volatility_threshold=0.25,
    )


def classify_scenario_with_thresholds(
    before: PacketObservation,
    after: PacketObservation,
    *,
    symbol: str,
    horizon: Horizon,
    directional_scale: float,
    volatility_threshold: float,
) -> tuple[str, str]:
    """Offline-capable threshold variant; production baseline calls it with P12 values."""

    if not 0.5 <= directional_scale <= 2.0:
        raise ValueError("directional_scale must be between 0.5 and 2.0")
    if not 0.10 <= volatility_threshold <= 0.50:
        raise ValueError("volatility_threshold must be between 0.10 and 0.50")

    freshness = after.payload.get("freshness_summary") or {}
    fresh = int(freshness.get("fresh") or 0)
    unavailable = int(freshness.get("stale") or 0) + int(freshness.get("missing") or 0)
    if unavailable > fresh:
        return "data_stale_or_missing", "Stale or missing packet cards outnumber fresh cards."
    price_before, vol_before = _symbol_values(before.payload, symbol)
    price_after, vol_after = _symbol_values(after.payload, symbol)
    if price_before is None or price_after is None or price_before == 0:
        return "data_stale_or_missing", "A required symbol price is absent from the packet window."
    if vol_before is not None and vol_after is not None and vol_before > 0:
        vol_change = (vol_after - vol_before) / vol_before
        if vol_change >= volatility_threshold:
            return "volatility_expansion", f"Volatility proxy increased {vol_change:.4%}."
        if vol_change <= -volatility_threshold:
            return "volatility_compression", f"Volatility proxy decreased {vol_change:.4%}."
    move = (price_after - price_before) / price_before
    threshold = (0.0005 if horizon == "micro_observation" else 0.0015) * directional_scale
    if abs(move) >= threshold:
        return "continuation", f"Absolute close change {abs(move):.4%} met the {threshold:.4%} threshold."
    return "no_clear_scenario", f"Absolute close change {abs(move):.4%} stayed below {threshold:.4%}."


def build_review_pair(
    before: PacketObservation,
    after: PacketObservation,
    *,
    symbol: str,
    horizon: Horizon,
    sequence: int,
    source_label: str,
    corpus_phase: str = "p11",
) -> tuple[ActionReviewV1, ActionReviewV1]:
    symbol = symbol.strip().upper()
    realized, explanation = classify_scenario(before, after, symbol=symbol, horizon=horizon)
    phase = corpus_phase.strip().lower()
    if not phase or not phase.replace("_", "").isalnum():
        raise ValueError("corpus_phase must be a simple identifier")
    review_id = f"review_{phase}_{source_label}_{sequence:03d}_{symbol.lower()}_{horizon}"
    packet_ref = f"agent-feed://packet/{before.packet_id}"
    later_ref = f"agent-feed://packet/{after.packet_id}"
    stale_expected = realized == "data_stale_or_missing"
    expected = (
        [
            ("data_stale_or_missing", 0.70, "The later packet may remain stale or incomplete."),
            ("no_clear_scenario", 0.30, "Usable data may still remain inconclusive."),
        ]
        if stale_expected else
        [
            ("no_clear_scenario", 0.60, "The bounded close change may remain below the horizon threshold."),
            ("continuation", 0.25, "A directional close change may exceed the fixed horizon threshold."),
            ("volatility_expansion", 0.15, "The packet volatility proxy may expand by at least 25 percent."),
        ]
    )
    proposed = ("OBSERVE", "WAIT", "NO_ACTION")[(sequence - 1) % 3]
    first_data = {
        "review_id": review_id,
        "revision": 1,
        "created_ts_ms": before.produced_ts_ms,
        "updated_ts_ms": before.produced_ts_ms,
        "mode": "no_execution",
        "source": "no_model_local_sample",
        "agent_id": (
            f"p14.{source_label}.deterministic.multi-session-corpus" if phase == "p14"
            else f"p15.{source_label}.deterministic.cross-time-corpus" if phase == "p15"
            else f"p16.{source_label}.deterministic.cross-day-corpus" if phase == "p16"
            else f"p17.{source_label}.deterministic.second-window-corpus" if phase == "p17"
            else f"{phase}.deterministic.fresh-runtime-corpus" if phase == "p12"
            else f"{phase}.deterministic.corpus"
        ),
        "operator_ref": f"{phase}://deterministic-packet-corpus",
        "packet_ref": packet_ref,
        "symbol": symbol,
        "horizon": horizon,
        "pre_action_note": {
            "review_id": review_id,
            "packet_id": before.packet_id,
            "symbol": symbol,
            "horizon": horizon,
            "proposed_action": proposed,
            "thesis": f"Apply fixed {horizon} packet thresholds to {symbol} without model inference or execution.",
            "invalidation": "The later packet is missing, malformed, or not later than the source packet.",
            "expected_scenarios": [
                {
                    "scenario_id": scenario,
                    "confidence": confidence,
                    "thesis": thesis,
                    "evidence_refs": [packet_ref, before.source_ref],
                }
                for scenario, confidence, thesis in expected
            ],
            "warnings_acknowledged": [
                "deterministic corpus statistics are descriptive only",
                f"{phase.upper()} has no model or execution authority",
            ],
            "data_refs_used": [packet_ref, before.source_ref],
            "tool_refs_used": [f"agent-memory://{phase}-deterministic-heuristics/v1"],
            "confidence": 0.60,
            "no_execution": True,
        },
        "execution_note": {
            "status": "not_submitted_p9_no_execution",
            "submitted": False,
            "detail": f"{phase.upper()} records deterministic review memory only; no action route was invoked.",
            "no_execution": True,
        },
        "raw_refs": [packet_ref, before.source_ref],
        "compact_summary": f"Deterministic {proposed} review for {symbol}/{horizon}; no action was submitted.",
        "token_estimate": 1,
    }
    first = finalize_action_review(first_data)
    expected_ids = {item.scenario_id for item in first.pre_action_note.expected_scenarios}
    achieved = realized in expected_ids
    lesson = {
        "data_stale_or_missing": "Prefer visible missing-data classification over invented market interpretation.",
        "continuation": "Record threshold movement descriptively without converting it into permission.",
        "volatility_expansion": "Keep volatility changes descriptive and require separate authority for action.",
        "volatility_compression": "Compression memory is context only and does not imply an entry.",
        "no_clear_scenario": "Preserve uncertainty when deterministic thresholds are not met.",
    }.get(realized, "Keep deterministic scenario memory separate from trading authority.")
    second_data = first.model_dump(mode="python")
    second_data.update({
        "revision": 2,
        "supersedes_ref": review_ref(review_id, 1),
        "updated_ts_ms": max(before.produced_ts_ms, after.produced_ts_ms),
        "outcome_review": {
            "observed_from_packet_ref": packet_ref,
            "observed_to_packet_ref": later_ref,
            "observation_window_ms": max(0, after.produced_ts_ms - before.produced_ts_ms),
            "what_happened": f"Deterministic packet comparison classified {symbol}/{horizon} as {realized}.",
            "realized_scenario": realized,
            "scenario_confidence": 0.80,
            "evidence_refs": [packet_ref, later_ref, before.source_ref, after.source_ref],
            "expected_result_achieved": achieved,
            "outcome_unexpected": not achieved,
            "logical_explanation": explanation,
            "lesson_to_remember": lesson,
            "future_review_needed": False,
            "no_trade_pnl_claim": True,
        },
        "raw_refs": [packet_ref, later_ref, before.source_ref, after.source_ref],
        "compact_summary": f"Completed deterministic {symbol}/{horizon} review: {realized}; no execution or PnL claim.",
        "token_estimate": 1,
    })
    return first, finalize_action_review(second_data)


def generate_corpus(
    sources: Iterable[tuple[str, Path, int]],
    *,
    symbols: Iterable[str] = ("BTCUSDT", "ETHUSDT"),
    corpus_phase: str = "p11",
    require_fresh_runtime: bool = False,
    spread_windows: bool = False,
) -> list[ActionReviewV1]:
    rows: list[ActionReviewV1] = []
    sequence = 0
    for source_label, path, window_count in sources:
        observations = (
            load_fresh_packet_observations(path, required_symbols=symbols)
            if require_fresh_runtime else load_packet_observations(path)
        )
        count = min(window_count, len(observations) // 2)
        if spread_windows and count:
            width = len(observations) / count
            pairs = [
                (observations[int(window * width)], observations[min(len(observations) - 1, int((window + 1) * width) - 1)])
                for window in range(count)
            ]
        else:
            pairs = [(observations[window * 2], observations[window * 2 + 1]) for window in range(count)]
        for before, after in pairs:
            for symbol in symbols:
                for horizon in HORIZONS:
                    sequence += 1
                    rows.extend(build_review_pair(
                        before,
                        after,
                        symbol=symbol,
                        horizon=horizon,
                        sequence=sequence,
                        source_label=source_label,
                        corpus_phase=corpus_phase,
                    ))
    return rows


__all__ = [
    "HORIZONS", "PacketObservation", "build_review_pair", "classify_scenario",
    "classify_scenario_with_thresholds",
    "generate_corpus", "load_fresh_packet_observations", "load_multi_session_packet_observations",
    "load_packet_observations",
    "validate_fresh_packet_observations",
]
