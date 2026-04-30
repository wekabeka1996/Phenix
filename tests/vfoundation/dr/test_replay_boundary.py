from vfoundation.dr.replay_boundary import (
    BoundaryAuthority,
    CACHE_ONLY_ARTIFACTS,
    FORENSIC_ONLY_EVENTS,
    FORENSIC_ONLY_LOGS,
    LEGACY_OR_UNPROVEN_EVENTS,
    OBSERVABILITY_ONLY_EVENTS,
    PARTIAL_REPLAY_CANDIDATE_EVENTS,
    RESTORE_AUTHORITATIVE_ARTIFACTS,
    RESTORE_AUTHORITATIVE_SCOPES,
    W5_CANDIDATE_REPLAY_EVENT_NAMES,
    get_boundary_classification_spec,
    get_selected_replay_boundary_spec,
    is_selected_replay_boundary_event,
)


def test_selected_boundary_includes_deferred_bracket_events() -> None:
    stored = get_selected_replay_boundary_spec("EVT:PENDING_BRACKETS_STORED")
    cleared = get_selected_replay_boundary_spec("EVT:PENDING_BRACKETS_CLEARED")

    assert stored is not None
    assert stored.required_for_restore_replay is True
    assert stored.authority == BoundaryAuthority.REPLAY
    assert stored.w5_eligible is True
    assert "entry_order_id" in stored.required_join_keys
    assert cleared is not None
    assert cleared.required_for_restore_replay is True
    assert cleared.authority == BoundaryAuthority.REPLAY
    assert cleared.w5_eligible is True
    assert "reason" in cleared.required_join_keys


def test_w5_candidate_subset_is_narrow_and_honest() -> None:
    assert W5_CANDIDATE_REPLAY_EVENT_NAMES == {
        "EVT:ORDER_PLACED",
        "EVT:ORDER_REJECTED",
        "EVT:TRADE_EXECUTED",
        "EVT:PENDING_BRACKETS_STORED",
        "EVT:PENDING_BRACKETS_CLEARED",
    }
    assert "EVT:ORDER_FILL" not in W5_CANDIDATE_REPLAY_EVENT_NAMES
    assert "EVT:EXECUTION_CLOSE_RECONCILED" not in W5_CANDIDATE_REPLAY_EVENT_NAMES
    assert "EVT:ORDER_STATE_CHANGED" not in W5_CANDIDATE_REPLAY_EVENT_NAMES


def test_order_fill_is_legacy_or_unproven_not_replay_authoritative() -> None:
    spec = get_boundary_classification_spec("EVT:ORDER_FILL")

    assert spec is not None
    assert spec.authority == BoundaryAuthority.LEGACY_OR_UNPROVEN
    assert spec.required_for_restore_replay is False
    assert spec.w5_eligible is False
    assert "EVT:ORDER_FILL" in LEGACY_OR_UNPROVEN_EVENTS
    assert "no active canonical wal producer" in spec.notes.lower()
    assert is_selected_replay_boundary_event("EVT:ORDER_FILL") is False


def test_execution_close_reconciled_is_observability_only_not_replay_authoritative() -> None:
    spec = get_boundary_classification_spec("EVT:EXECUTION_CLOSE_RECONCILED")

    assert spec is not None
    assert spec.authority == BoundaryAuthority.OBSERVABILITY
    assert spec.required_for_restore_replay is False
    assert spec.w5_eligible is False
    assert "EVT:EXECUTION_CLOSE_RECONCILED" in OBSERVABILITY_ONLY_EVENTS
    assert "bus-only emitter" in spec.notes.lower()
    assert is_selected_replay_boundary_event(
        "EVT:EXECUTION_CLOSE_RECONCILED") is False


def test_order_state_changed_remains_partial_candidate_until_wal_ownership_is_uniform() -> None:
    spec = get_boundary_classification_spec("EVT:ORDER_STATE_CHANGED")

    assert spec is not None
    assert spec.authority == BoundaryAuthority.PARTIAL_REPLAY_CANDIDATE
    assert spec.required_for_restore_replay is False
    assert spec.w5_eligible is False
    assert "EVT:ORDER_STATE_CHANGED" in PARTIAL_REPLAY_CANDIDATE_EVENTS
    assert "watchdog fallback" in spec.notes.lower()
    assert is_selected_replay_boundary_event(
        "EVT:ORDER_STATE_CHANGED") is False


def test_trade_executed_replay_authority_is_conditioned_on_position_tracking_wal_seam() -> None:
    spec = get_selected_replay_boundary_spec("EVT:TRADE_EXECUTED")

    assert spec is not None
    assert spec.authority == BoundaryAuthority.REPLAY
    assert spec.required_for_restore_replay is True
    assert spec.w5_eligible is True
    assert "position_tracking" in spec.notes
    assert "not through direct source-owned producer WAL" in spec.notes


def test_linked_bracket_exact_lineage_remains_restore_authoritative_not_replay_authoritative() -> None:
    assert "linked_bracket_exact_lineage" in RESTORE_AUTHORITATIVE_SCOPES
    assert "ops/restore/execution_position_restore_envelope_v1.json" in RESTORE_AUTHORITATIVE_ARTIFACTS
    assert "linked_bracket_exact_lineage" not in W5_CANDIDATE_REPLAY_EVENT_NAMES


def test_boundary_explicitly_excludes_forensic_only_planes() -> None:
    assert is_selected_replay_boundary_event(
        "EVT:EXECUTION_DIVERGENCE_DETECTED") is False
    assert is_selected_replay_boundary_event(
        "EVT:EXECUTION_GUARD_BLOCKED") is False
    assert "EVT:EXECUTION_DIVERGENCE_DETECTED" in FORENSIC_ONLY_EVENTS
    assert "logs/order_log_v1.jsonl" in FORENSIC_ONLY_LOGS
    assert "logs/shadow_critical_event_journal_v1.jsonl" in FORENSIC_ONLY_LOGS
    assert "logs/trade_lifecycle.jsonl" in FORENSIC_ONLY_LOGS
    assert "ops/restore/execution_position_restore_envelope_v1.json" in RESTORE_AUTHORITATIVE_ARTIFACTS
    assert "logs/execution_terminal_identity_cache_v1.json" in CACHE_ONLY_ARTIFACTS
    assert "EVT:EXECUTION_CLOSE_RECONCILED" in OBSERVABILITY_ONLY_EVENTS
