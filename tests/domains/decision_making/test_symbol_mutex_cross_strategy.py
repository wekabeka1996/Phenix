from __future__ import annotations

from apps.reference.domains.decision_making.decision_making import DecisionMaking


def _make_dm() -> DecisionMaking:
    dm = object.__new__(DecisionMaking)
    dm.latest_portfolio = {"positions": []}
    dm._pending_flips = {}
    return dm


def test_symbol_mutex_blocks_active_position_from_any_strategy() -> None:
    dm = _make_dm()
    dm.latest_portfolio = {
        "positions": [
            {"symbol": "ETHUSDT", "positionAmt": "0.25000000"},
        ]
    }

    result = dm._get_symbol_entry_block_reason(
        "ETHUSDT", reduce_only=False)

    assert result is not None
    assert result["reason"] == "active_position"
    assert result["position_state"] == "LONG"


def test_symbol_mutex_blocks_pending_flip_close() -> None:
    dm = _make_dm()
    dm._pending_flips = {
        "SOLUSDT": {"state": "closing", "from": "LONG", "to": "SHORT"}
    }

    result = dm._get_symbol_entry_block_reason(
        "SOLUSDT", reduce_only=False)

    assert result is not None
    assert result["reason"] == "pending_flip_close"


def test_reduce_only_close_is_not_blocked_by_symbol_mutex() -> None:
    dm = _make_dm()
    dm.latest_portfolio = {
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "1.00000000"},
        ]
    }

    result = dm._get_symbol_entry_block_reason(
        "BTCUSDT", reduce_only=True)

    assert result is None
