from __future__ import annotations

import pytest

from apps.reference.domains.execution_position.guardian_background_orphan_cancel_bridge import (
    GuardianBackgroundOrphanCancelBridgeError,
    GuardianBackgroundOrphanCancelRequest,
    build_guardian_background_orphan_cancel_trace_ref,
)
from apps.reference.domains.execution_position.guardian_old_bracket_cleanup_bridge import (
    GuardianOldBracketCleanupBridgeError,
    GuardianOldBracketCleanupRequest,
    build_guardian_old_bracket_cleanup_trace_ref,
)
from apps.reference.domains.execution_position.guardian_pre_close_cleanup_bridge import (
    GuardianPreCloseCleanupBridgeError,
    GuardianPreCloseCleanupRequest,
    build_guardian_pre_close_cleanup_trace_ref,
)
from apps.reference.domains.execution_position.guardian_reconcile_cancel_bridge import (
    GuardianReconcileCancelBridgeError,
    GuardianReconcileCancelRequest,
    build_guardian_reconcile_cancel_trace_ref,
)
from apps.reference.domains.execution_position.reconcile_close_cancel_bridge import (
    ReconcileCloseCancelBridgeError,
    ReconcileCloseCancelRequest,
    build_reconcile_close_cancel_trace_ref,
)
from apps.reference.domains.execution_position.tracked_close_teardown_cancel_bridge import (
    TrackedCloseTeardownCancelBridgeError,
    TrackedCloseTeardownCancelRequest,
    build_tracked_close_teardown_cancel_trace_ref,
)


@pytest.mark.parametrize(
    ("factory", "error_type", "message"),
    [
        (
            lambda: GuardianPreCloseCleanupRequest.from_pre_close_bracket(
                symbol="BTCUSDT",
                order_id="sl-1",
                bracket_type="SL",
                parent_order_id=" ",
            ),
            GuardianPreCloseCleanupBridgeError,
            "guardian pre-close cleanup missing required field: parent_order_id",
        ),
        (
            lambda: GuardianReconcileCancelRequest.from_orphan_record(
                symbol="BTCUSDT",
                order_id="tp-1",
                order_type="",
                rid="rid-1",
            ),
            GuardianReconcileCancelBridgeError,
            "guardian reconcile cancel missing required field: order_type",
        ),
        (
            lambda: GuardianBackgroundOrphanCancelRequest.from_background_orphan(
                symbol=" ",
                order_id="sl-1",
                order_type="STOP_MARKET",
            ),
            GuardianBackgroundOrphanCancelBridgeError,
            "guardian background orphan cancel missing required field: symbol",
        ),
        (
            lambda: GuardianOldBracketCleanupRequest.from_outdated_bracket(
                symbol="BTCUSDT",
                order_id="sl-old",
                order_type="STOP_MARKET",
                keep_parent_order_id="",
            ),
            GuardianOldBracketCleanupBridgeError,
            "guardian old bracket cleanup missing required field: keep_parent_order_id",
        ),
        (
            lambda: TrackedCloseTeardownCancelRequest.from_runtime(
                symbol="BTCUSDT",
                order_id="",
                bracket_type="SL",
                close_rid="rid-close",
            ),
            TrackedCloseTeardownCancelBridgeError,
            "tracked close teardown missing required field: order_id",
        ),
        (
            lambda: ReconcileCloseCancelRequest.from_open_order(
                symbol="BTCUSDT",
                order_id="ord-1",
                order_type=" ",
                close_rid="rid-close",
            ),
            ReconcileCloseCancelBridgeError,
            "reconcile close cancel missing required field: order_type",
        ),
    ],
)
def test_bridge_request_missing_required_field_still_raises_same_bridge_error(
    factory,
    error_type,
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        factory()


@pytest.mark.parametrize(
    ("bridge_request", "expected_idempotent_key", "expected_why"),
    [
        (
            GuardianPreCloseCleanupRequest.from_pre_close_bracket(
                symbol="btcusdt",
                order_id=" sl-1 ",
                bracket_type="sl",
                parent_order_id=" entry-1 ",
            ),
            "BTCUSDT:guardian_pre_close_cleanup:entry-1:SL:sl-1",
            "guardian_pre_close_cleanup",
        ),
        (
            GuardianReconcileCancelRequest.from_orphan_record(
                symbol="btcusdt",
                order_id=" tp-1 ",
                order_type="take_profit_market",
                rid=" rid-1 ",
            ),
            "rid-1:guardian_reconcile_cancel:TAKE_PROFIT_MARKET:tp-1",
            "guardian_reconcile_orphan_cancel",
        ),
        (
            GuardianBackgroundOrphanCancelRequest.from_background_orphan(
                symbol="ethusdt",
                order_id=" sl-1 ",
                order_type="stop_market",
            ),
            "ETHUSDT:guardian_background_orphan_cancel:STOP_MARKET:sl-1",
            "guardian_background_orphan_cancel",
        ),
        (
            GuardianOldBracketCleanupRequest.from_outdated_bracket(
                symbol="ethusdt",
                order_id=" tp-old ",
                order_type="take_profit_market",
                keep_parent_order_id=" parent-keep ",
            ),
            "ETHUSDT:guardian_old_bracket_cleanup:parent-keep:TAKE_PROFIT_MARKET:tp-old",
            "guardian_old_bracket_cleanup",
        ),
        (
            TrackedCloseTeardownCancelRequest.from_runtime(
                symbol="btcusdt",
                order_id=" sl-1 ",
                bracket_type="sl",
                close_rid=" rid-close ",
            ),
            "rid-close:tracked_close_teardown:SL:sl-1",
            "tracked_close_teardown_sl",
        ),
        (
            ReconcileCloseCancelRequest.from_open_order(
                symbol="ethusdt",
                order_id=" ord-1 ",
                order_type="limit",
                close_rid=" rid-close ",
            ),
            "rid-close:reconcile_close_cancel:LIMIT:ord-1",
            "reconcile_close_cancel_limit",
        ),
    ],
)
def test_bridge_request_idempotent_key_and_why_are_unchanged(
    bridge_request,
    expected_idempotent_key: str,
    expected_why: str,
) -> None:
    assert bridge_request.idempotent_key() == expected_idempotent_key
    assert bridge_request.why() == expected_why


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (
            build_guardian_pre_close_cleanup_trace_ref(
                status="reject",
                bracket_type="SL",
                reason="bad-reason",
            ),
            "obs://execution_position/guardian_pre_close_cleanup?contract=guardian_pre_close_cleanup_v1&path=OrderGuardian.cleanup_before_close-%3EDEC%3ACANCEL_ORDER&status=reject&bracket_type=SL&trigger=guardian_pre_close_cleanup&reason=bad-reason",
        ),
        (
            build_guardian_reconcile_cancel_trace_ref(
                status="reject",
                order_type="STOP_MARKET",
                reason="bad-reason",
            ),
            "obs://execution_position/guardian_reconcile_cancel?contract=guardian_reconcile_cancel_v1&path=OrderGuardian.reconcile_symbol-%3Ecleanup_orphans-%3EDEC%3ACANCEL_ORDER&status=reject&order_type=STOP_MARKET&trigger=guardian_reconcile_orphan_cancel&reason=bad-reason",
        ),
        (
            build_guardian_background_orphan_cancel_trace_ref(
                status="reject",
                order_type="STOP_MARKET",
                reason="bad-reason",
            ),
            "obs://execution_position/guardian_background_orphan_cancel?contract=guardian_background_orphan_cancel_v1&path=OrderGuardian.cleanup_orphans%28hard%3DFalse%29-%3EDEC%3ACANCEL_ORDER&status=reject&order_type=STOP_MARKET&trigger=guardian_background_orphan_cancel&reason=bad-reason",
        ),
        (
            build_guardian_old_bracket_cleanup_trace_ref(
                status="reject",
                order_type="TAKE_PROFIT_MARKET",
                reason="bad-reason",
            ),
            "obs://execution_position/guardian_old_bracket_cleanup?contract=guardian_old_bracket_cleanup_v1&path=OrderGuardian.cleanup_other_brackets_for_symbol-%3EDEC%3ACANCEL_ORDER&status=reject&order_type=TAKE_PROFIT_MARKET&trigger=guardian_old_bracket_cleanup&reason=bad-reason",
        ),
        (
            build_tracked_close_teardown_cancel_trace_ref(
                status="reject",
                bracket_type="SL",
                reason="bad-reason",
            ),
            "obs://execution_position/tracked_close_teardown_cancel?contract=tracked_close_teardown_cancel_v1&path=DEC%3ACLOSE%3Atracked_brackets-%3EDEC%3ACANCEL_ORDER&status=reject&bracket_type=SL&trigger=DEC%3ACLOSE%3Atracked_bracket_teardown&reason=bad-reason",
        ),
        (
            build_reconcile_close_cancel_trace_ref(
                status="reject",
                order_type="LIMIT",
                reason="bad-reason",
            ),
            "obs://execution_position/reconcile_close_cancel?contract=reconcile_close_cancel_v1&path=DEC%3ACLOSE%3Areconcile_scan-%3EDEC%3ACANCEL_ORDER&status=reject&order_type=LIMIT&trigger=DEC%3ACLOSE%3Areconcile_scan_cancel&reason=bad-reason",
        ),
    ],
)
def test_bridge_trace_refs_remain_exactly_stable(actual: str, expected: str) -> None:
    assert actual == expected
