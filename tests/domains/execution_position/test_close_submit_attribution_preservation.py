from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.flows.close.close_executor import CloseExecutor
from apps.reference.domains.execution_position.flows.close.close_submission_adapter import (
    CloseSubmissionPayload,
)


def test_close_submit_boundary_payload_preserves_open_strategy_attribution() -> None:
    fsm = MagicMock()
    fsm._open_attribution_by_symbol = {
        "ETHUSDT": {
            "strategy_id": "mean_reversion",
            "entry_rid": "rid-de5d8de38df998bb",
            "decision_id": "99bca255-3b8e-48c7-9cd9-c1b9bbd0e3d2",
            "intent_id": "b85bb7f0-a3d0-4db8-957d-38dee3991410",
            "regime": "MEAN_REVERSION",
            "regime_confidence": 0.2742920276980952,
        }
    }
    decision = SimpleNamespace(rid="rid-de5d8de38df998bb", data_ref=[])
    submission = CloseSubmissionPayload(
        symbol="ETHUSDT",
        side="BUY",
        quantity="5.480",
        client_order_id="CLOSE-fc34a2f5bcd0",
        partial_close=False,
    )

    with patch(
        "apps.reference.domains.execution_position.flows.close.close_executor.get_clock"
    ) as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1781986504757
        payload = CloseExecutor(fsm)._build_close_submit_boundary_payload(
            event_type="ORDER_INTENT",
            trace_kind="CLOSE_SUBMIT_ATTEMPT",
            why="close_submit_attempt",
            rid="rid-de5d8de38df998bb",
            decision=decision,
            submission=submission,
        )

    assert payload["strategy_id"] == "mean_reversion"
    assert payload["entry_rid"] == "rid-de5d8de38df998bb"
    assert payload["decision_id"] == "99bca255-3b8e-48c7-9cd9-c1b9bbd0e3d2"
    assert payload["intent_id"] == "b85bb7f0-a3d0-4db8-957d-38dee3991410"
    assert payload["client_order_id"] == "CLOSE-fc34a2f5bcd0"
