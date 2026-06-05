from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BoundaryAuthority(str, Enum):
    REPLAY = "replay_authoritative"
    PARTIAL_REPLAY_CANDIDATE = "partial_replay_candidate"
    RESTORE = "restore_authoritative"
    FORENSIC = "forensic_only"
    OBSERVABILITY = "observability_only"
    LEGACY_OR_UNPROVEN = "legacy_or_unproven"
    CACHE = "cache_only"
    NON_AUTHORITATIVE_LOG = "non_authoritative_log"


@dataclass(frozen=True)
class ReplayBoundaryVerb:
    event_name: str
    required_for_restore_replay: bool
    authority: BoundaryAuthority
    replay_role: str
    required_join_keys: tuple[str, ...]
    w5_eligible: bool = False
    notes: str = ""


EXECUTION_BOUNDARY_CLASSIFICATIONS: tuple[ReplayBoundaryVerb, ...] = (
    ReplayBoundaryVerb(
        event_name="EVT:ORDER_PLACED",
        required_for_restore_replay=True,
        authority=BoundaryAuthority.REPLAY,
        replay_role="canonical_order_placement_outcome",
        required_join_keys=(
            "rid",
            "symbol",
            "side",
            "client_order_id",
            "exchange_order_id",
            "order_id",
            "corr_id",
            "ts_ms",
        ),
        w5_eligible=True,
        notes=(
            "Bracket child replay additionally depends on parent_client_order_id, "
            "oco_group_id, and role-specific lineage when present."
        ),
    ),
    ReplayBoundaryVerb(
        event_name="EVT:ORDER_REJECTED",
        required_for_restore_replay=True,
        authority=BoundaryAuthority.REPLAY,
        replay_role="canonical_order_reject_outcome",
        required_join_keys=(
            "symbol",
            "event_ts_ms",
            "rid_or_order_identity",
            "reason_or_reason_code",
        ),
        w5_eligible=True,
    ),
    ReplayBoundaryVerb(
        event_name="EVT:ORDER_STATE_CHANGED",
        required_for_restore_replay=False,
        authority=BoundaryAuthority.REPLAY,
        replay_role="terminal_non_fill_outcome_uniform_wal_ownership",
        required_join_keys=(
            "symbol",
            "event_ts_ms",
            "status",
            "canonical_identity_key",
            "order_id_or_client_order_id_or_rid",
        ),
        w5_eligible=True,
        notes=(
            "Websocket terminal non-fill, timeout/idempotent-timeout cancellation, and watchdog "
            "REST fallback all have local canonical WAL ownership. Watchdog fallback additionally "
            "has controlled runtime induction proof for CANCELED, REJECTED, and EXPIRED. This "
            "promotion is replay-authoritative only for report-only W5 bounded replay and does "
            "not expand restore authority."
        ),
    ),
    ReplayBoundaryVerb(
        event_name="EVT:ORDER_FILL",
        required_for_restore_replay=False,
        authority=BoundaryAuthority.LEGACY_OR_UNPROVEN,
        replay_role="legacy_execution_position_fill_ingress_compatibility",
        required_join_keys=(
            "symbol",
            "ts_or_ts_ms",
            "order_identity_or_rid",
        ),
        notes=(
            "Legacy compatibility ingress only. No active canonical WAL producer was found in the "
            "audited runtime slice, so this event is not replay-authoritative for W5."
        ),
    ),
    ReplayBoundaryVerb(
        event_name="EVT:TRADE_EXECUTED",
        required_for_restore_replay=True,
        authority=BoundaryAuthority.REPLAY,
        replay_role="canonical_fill_truth",
        required_join_keys=(
            "symbol",
            "side",
            "quantity",
            "price",
            "ts",
            "venue",
            "rid",
        ),
        w5_eligible=True,
        notes=(
            "Replay-authoritative through the position_tracking authoritative-consumer WAL seam, "
            "not through direct source-owned producer WAL. Order and trade identifiers remain "
            "strongly preferred even when some emitters treat them as optional."
        ),
    ),
    ReplayBoundaryVerb(
        event_name="EVT:PENDING_BRACKETS_STORED",
        required_for_restore_replay=True,
        authority=BoundaryAuthority.REPLAY,
        replay_role="canonical_deferred_bracket_seed",
        required_join_keys=(
            "entry_order_id",
            "symbol",
            "side",
            "qty",
            "rid",
            "idem_key",
            "tick_size",
            "ts_ms",
        ),
        w5_eligible=True,
    ),
    ReplayBoundaryVerb(
        event_name="EVT:PENDING_BRACKETS_CLEARED",
        required_for_restore_replay=True,
        authority=BoundaryAuthority.REPLAY,
        replay_role="canonical_deferred_bracket_clear",
        required_join_keys=(
            "entry_order_id",
            "symbol",
            "reason",
            "ts_ms",
        ),
        w5_eligible=True,
    ),
    ReplayBoundaryVerb(
        event_name="EVT:EXECUTION_CLOSE_RECONCILED",
        required_for_restore_replay=False,
        authority=BoundaryAuthority.OBSERVABILITY,
        replay_role="business_close_observability_signal",
        required_join_keys=(
            "symbol",
            "source",
            "ts_ms",
            "why",
        ),
        notes=(
            "Bus-only emitter found in the audited slice. Payload lineage is weak and not sufficient "
            "for replay authority, so this remains observability-only until producer + join-key hardening exists."
        ),
    ),
)


SELECTED_EXECUTION_REPLAY_BOUNDARY: tuple[ReplayBoundaryVerb, ...] = tuple(
    spec
    for spec in EXECUTION_BOUNDARY_CLASSIFICATIONS
    if spec.authority == BoundaryAuthority.REPLAY and spec.w5_eligible
)


W5_CANDIDATE_REPLAY_EVENT_NAMES: frozenset[str] = frozenset(
    spec.event_name for spec in SELECTED_EXECUTION_REPLAY_BOUNDARY
)


PARTIAL_REPLAY_CANDIDATE_EVENTS: frozenset[str] = frozenset(
    spec.event_name
    for spec in EXECUTION_BOUNDARY_CLASSIFICATIONS
    if spec.authority == BoundaryAuthority.PARTIAL_REPLAY_CANDIDATE
)


OBSERVABILITY_ONLY_EVENTS: frozenset[str] = frozenset(
    spec.event_name
    for spec in EXECUTION_BOUNDARY_CLASSIFICATIONS
    if spec.authority == BoundaryAuthority.OBSERVABILITY
)


LEGACY_OR_UNPROVEN_EVENTS: frozenset[str] = frozenset(
    spec.event_name
    for spec in EXECUTION_BOUNDARY_CLASSIFICATIONS
    if spec.authority == BoundaryAuthority.LEGACY_OR_UNPROVEN
)


FORENSIC_ONLY_EVENTS: frozenset[str] = frozenset(
    {
        "EVT:EXECUTION_DIVERGENCE_DETECTED",
        "EVT:EXECUTION_GUARD_BLOCKED",
    }
)

FORENSIC_ONLY_LOGS: frozenset[str] = frozenset(
    {
        "logs/order_log_v1.jsonl",
        "logs/shadow_critical_event_journal_v1.jsonl",
        "logs/trade_lifecycle.jsonl",
        "logs/shadow_telemetry/decision_ledger_v1.jsonl",
        "authority_request_journal_v1.jsonl",
        "authority_response_journal_v1.jsonl",
    }
)

RESTORE_AUTHORITATIVE_ARTIFACTS: frozenset[str] = frozenset(
    {
        "ops/restore/execution_position_restore_envelope_v1.json",
    }
)


RESTORE_AUTHORITATIVE_SCOPES: frozenset[str] = frozenset(
    {
        "linked_bracket_exact_lineage",
    }
)

CACHE_ONLY_ARTIFACTS: frozenset[str] = frozenset(
    {
        "logs/execution_terminal_identity_cache_v1.json",
        "logs/execution_truth_warm_state_v1.json",
    }
)


def is_selected_replay_boundary_event(event_name: str) -> bool:
    return any(spec.event_name == event_name for spec in SELECTED_EXECUTION_REPLAY_BOUNDARY)


def get_boundary_classification_spec(event_name: str) -> ReplayBoundaryVerb | None:
    for spec in EXECUTION_BOUNDARY_CLASSIFICATIONS:
        if spec.event_name == event_name:
            return spec
    return None


def get_selected_replay_boundary_spec(event_name: str) -> ReplayBoundaryVerb | None:
    for spec in SELECTED_EXECUTION_REPLAY_BOUNDARY:
        if spec.event_name == event_name:
            return spec
    return None
