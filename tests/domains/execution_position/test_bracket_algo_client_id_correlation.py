"""
Tests for Binance algo order clientAlgoId bracket correlation fix.

Package: BRACKET_ALGO_CLIENT_ID_CORRELATION

Proves:
1. clientAlgoId from bracket placement response is registered as primary
   clientOrderId in OrderIndex (matching WS fill identity)
2. ManageFlowFSM._resolve_bracket_match() matches fills by algo_client_id
3. Legacy "SL-xxx"/"TP-xxx" IDs are registered as secondary fallback
4. set_bracket_ids() propagates algo client IDs to ManageFlowFSM
5. _clear_lifecycle_tracking() resets algo client IDs
6. Exchange fragmentation (N partial fills) remains safe after fix
"""

import pytest
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.bracket_manager import BracketManager
from apps.reference.domains.execution_position.order_index import (
    OrderIndex,
    OrderRef,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manage_flow():
    """Create a ManageFlowFSM with minimal config for testing."""
    from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM

    # Build a minimal AuroraConfig mock that satisfies ManageFlowFSM __init__
    config = MagicMock()
    config.trading.execution.manage = MagicMock()
    config.trading.execution.manage.brackets = MagicMock()
    config.trading.execution.manage.brackets.oco_emulation = True
    config.trading.execution.manage.emergency = MagicMock()
    config.trading.execution.manage.emergency.wait_mode_bars = 2
    config.strategies.aurora = MagicMock()
    config.strategies.aurora.decision.bar_gating.bar_ms = 900000

    flow = ManageFlowFSM(config=config)
    return flow


def _make_bracket_manager_fsm():
    order_index = OrderIndex(ttl_sec=600)
    fsm = SimpleNamespace(
        order_index=order_index,
        fsm=SimpleNamespace(order_index=order_index),
        order_guardian=MagicMock(),
        correlation_store=MagicMock(),
        manage_flows={},
        _pending_brackets={},
        _symbol_brackets={},
        _orphan_metrics={"tp_sl_placed_success": 0},
        config=SimpleNamespace(
            domains=SimpleNamespace(
                execution_position=SimpleNamespace(
                    bracket_placement=SimpleNamespace(tp_widen_first_bps=10)
                )
            )
        ),
    )

    def _set_symbol_bracket_order(symbol, *, order_role, order_id):
        brackets = fsm._symbol_brackets.setdefault(symbol, {})
        if order_role == "SL":
            brackets["sl_order_id"] = order_id
        elif order_role == "TP":
            brackets["tp_order_id"] = order_id

    fsm._set_symbol_bracket_order = MagicMock(
        side_effect=_set_symbol_bracket_order)
    fsm._remember_bracket_owner = MagicMock(return_value={})
    fsm._append_bracket_ownership_record = MagicMock()
    fsm._has_active_lifecycle_for_symbol = MagicMock(return_value=True)
    fsm._persist_restore_artifact_snapshot = MagicMock()

    def _clear_pending_brackets(entry_order_id, *, reason, symbol=None, persist_snapshot=False):
        entry_order_id = str(entry_order_id)
        if entry_order_id not in fsm._pending_brackets:
            return False
        fsm._pending_brackets.pop(entry_order_id, None)
        if persist_snapshot:
            fsm._persist_restore_artifact_snapshot(
                trigger=f"bracket_deferred_cleared:{reason}",
                allow_empty=True,
            )
        return True

    fsm._clear_pending_brackets = MagicMock(
        side_effect=_clear_pending_brackets)
    return fsm


# ---------------------------------------------------------------------------
# 1. OrderIndex registration uses clientAlgoId as primary
# ---------------------------------------------------------------------------

class TestOrderIndexAlgoClientIdRegistration:
    """Bracket child registration uses clientAlgoId for WS fill correlation."""

    @pytest.fixture
    def idx(self):
        return OrderIndex(ttl_sec=600)

    def test_primary_registration_uses_algo_client_id(self, idx):
        """When clientAlgoId is available, it should be the primary clientOrderId."""
        # Simulate what bracket_manager does with algo response:
        # sl_algo_client_id = sl_resp.get("clientAlgoId") -> "SL-abc123"
        # sl_id (system-generated) = "SL-7f3a2b1c90de"
        # The primary registration should use clientAlgoId
        ref = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",  # This is the clientAlgoId
            # This is the algoId (normalized to orderId)
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # Must be findable by clientAlgoId (what WS fills send as clientOrderId)
        assert idx.get(clientOrderId="SL-abc123") is ref
        assert ref.order_kind == "SL"

    def test_secondary_registration_keeps_system_id(self, idx):
        """Both clientAlgoId and system sl_id should resolve to an OrderRef."""
        # Primary: clientAlgoId
        ref1 = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # Secondary: system-generated sl_id
        ref2 = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-7f3a2b1c90de",
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # Both should be findable
        assert idx.get(clientOrderId="SL-abc123") is ref1
        assert idx.get(clientOrderId="SL-7f3a2b1c90de") is ref2
        # Both share the same exchangeOrderId
        assert ref1.exchangeOrderId == ref2.exchangeOrderId == "500001"

    def test_ws_fill_lookup_by_algo_client_id(self, idx):
        """Simulates WS fill arriving with clientOrderId=clientAlgoId."""
        idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="TP-xyz789",  # clientAlgoId
            exchangeOrderId="600001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            order_kind="TP",
        )
        # WS fill arrives: clientOrderId = clientAlgoId, exchangeOrderId = NEW child ID
        ref = idx.get(clientOrderId="TP-xyz789")
        assert ref is not None
        assert ref.order_kind == "TP"
        assert ref.symbol == "ETHUSDT"

    def test_ws_fill_lookup_miss_when_only_system_id_registered(self, idx):
        """Without clientAlgoId fix, only system sl_id is registered — WS fill misses."""
        # Register with system sl_id (the OLD bug)
        idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-7f3a2b1c90de",  # system-generated
            exchangeOrderId="500001",           # algoId
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # WS fill arrives with clientAlgoId (different from system sl_id)
        ref = idx.get(clientOrderId="SL-abc123")
        assert ref is None  # MISS — this is the bug the fix addresses


# ---------------------------------------------------------------------------
# 2. ManageFlowFSM._resolve_bracket_match() uses algo_client_id
# ---------------------------------------------------------------------------

class TestManageFlowAlgoClientIdMatch:
    """ManageFlowFSM matches bracket fills by algo_client_id."""

    def test_sl_matched_by_algo_client_id(self):
        """SL fill matched when client_order_id equals sl_algo_client_id."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"       # algoId/orderId
        # Binance clientAlgoId is typically the system-generated newClientOrderId
        # passed at placement time; however it may differ from what gets stored
        # as sl_order_id.  Here we use a non-"SL-" prefix to prove algo_client_id
        # matching works independently of prefix matching.
        flow.sl_algo_client_id = "algo_sl_99001"
        flow.tp_order_id = "600001"
        flow.tp_algo_client_id = "algo_tp_99002"

        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",               # NEW child exchangeOrderId
            client_order_id="algo_sl_99001",  # = clientAlgoId (non SL- prefix)
        )
        assert matched is True
        assert role == "SL"
        assert "algo_client_id" in reason

    def test_tp_matched_by_algo_client_id(self):
        """TP fill matched when client_order_id equals tp_algo_client_id."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "algo_sl_99001"
        flow.tp_order_id = "600001"
        flow.tp_algo_client_id = "algo_tp_99002"

        role, matched, reason = flow._resolve_bracket_match(
            order_id="888001",
            client_order_id="algo_tp_99002",
        )
        assert matched is True
        assert role == "TP"
        assert "algo_client_id" in reason

    def test_no_match_without_algo_client_id(self):
        """Without algo_client_id set, child fills with non-prefix IDs don't match."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.tp_order_id = "600001"
        # algo_client_id not set (None)

        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="algo_sl_99001",  # non-prefix, untracked
        )
        assert matched is False
        assert role == "UNKNOWN"

    def test_sl_prefix_match_still_works_for_sl_format_ids(self):
        """clientAlgoId in "SL-xxx" format is caught by prefix match (defense in depth)."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "SL-abc123"  # Same as newClientOrderId

        # Even without algo_client_id, prefix match catches "SL-" format
        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="SL-abc123",
        )
        assert matched is True
        assert role == "SL"
        # Prefix match fires first (defense in depth)
        assert "client_order_id_prefix" in reason

    def test_legacy_exact_match_still_works(self):
        """Legacy exact exchange_order_id match still works alongside algo path."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "algo_sl_99001"

        # Legacy: order_id exactly matches tracked sl_order_id
        role, matched, reason = flow._resolve_bracket_match(
            order_id="500001",
            client_order_id="irrelevant",
        )
        assert matched is True
        assert role == "SL"
        assert "exchange_order_id_exact" in reason


# ---------------------------------------------------------------------------
# 3. set_bracket_ids() propagates algo client IDs
# ---------------------------------------------------------------------------

class TestSetBracketIdsAlgoClientId:
    """set_bracket_ids() stores algo client IDs for bracket matching."""

    def test_algo_client_ids_stored(self):
        flow = _make_manage_flow()
        flow.set_bracket_ids(
            sl_order_id="500001",
            tp_order_id="600001",
            sl_algo_client_id="SL-abc123",
            tp_algo_client_id="TP-xyz789",
        )
        assert flow.sl_order_id == "500001"
        assert flow.tp_order_id == "600001"
        assert flow.sl_algo_client_id == "SL-abc123"
        assert flow.tp_algo_client_id == "TP-xyz789"

    def test_backward_compatible_without_algo_ids(self):
        """set_bracket_ids() works without algo_client_id (backward compat)."""
        flow = _make_manage_flow()
        flow.set_bracket_ids(
            sl_order_id="500001",
            tp_order_id="600001",
        )
        assert flow.sl_order_id == "500001"
        assert flow.tp_order_id == "600001"
        assert flow.sl_algo_client_id is None
        assert flow.tp_algo_client_id is None


# ---------------------------------------------------------------------------
# 4. _clear_lifecycle_tracking() resets algo client IDs
# ---------------------------------------------------------------------------

class TestClearLifecycleAlgoClientId:
    """Lifecycle clearing resets algo client IDs to prevent stale matching."""

    def test_algo_ids_cleared(self):
        flow = _make_manage_flow()
        flow.sl_algo_client_id = "SL-abc123"
        flow.tp_algo_client_id = "TP-xyz789"
        flow._clear_lifecycle_tracking(reason="test", clear_symbol=True)
        assert flow.sl_algo_client_id is None
        assert flow.tp_algo_client_id is None


# ---------------------------------------------------------------------------
# 5. BracketManager persists actual child identity into guardian
# ---------------------------------------------------------------------------


class TestBracketManagerGuardianClientIdentity:
    """Bracket placement persists the exact child client identity into guardian."""

    def test_primary_registration_prefers_algo_client_id_for_guardian(self):
        fsm = _make_bracket_manager_fsm()
        manager = BracketManager(fsm)
        decision = SimpleNamespace(
            corr_id="corr-1",
            oco_group_id="oco-1",
            rid="rid-1",
            idempotent_key="idem-1",
            side="BUY",
        )

        manager._register_bracket_results(
            symbol="BTCUSDT",
            sl_resp={"orderId": "500001", "clientAlgoId": "algo-sl-1"},
            tp_resp={"orderId": "600001", "clientAlgoId": "algo-tp-1"},
            sl_id="SL-legacy-1",
            tp_id="TP-legacy-1",
            entry_resp={"orderId": "entry-1",
                        "clientOrderId": "ENTRY-1", "side": "BUY"},
            decision=decision,
            corr_id="corr-1",
            oco_group_id="oco-1",
            owner_context=None,
            placement_path="primary",
        )

        guardian_call = fsm.order_guardian.register_brackets.call_args.kwargs
        assert guardian_call["sl_client_id"] == "algo-sl-1"
        assert guardian_call["tp_client_id"] == "algo-tp-1"

    def test_primary_registration_falls_back_to_legacy_client_id_when_algo_missing(self):
        fsm = _make_bracket_manager_fsm()
        manager = BracketManager(fsm)
        decision = SimpleNamespace(
            corr_id="corr-1",
            oco_group_id="oco-1",
            rid="rid-1",
            idempotent_key="idem-1",
            side="BUY",
        )

        manager._register_bracket_results(
            symbol="BTCUSDT",
            sl_resp={"orderId": "500001"},
            tp_resp=None,
            sl_id="SL-legacy-1",
            tp_id="TP-legacy-1",
            entry_resp={"orderId": "entry-1",
                        "clientOrderId": "ENTRY-1", "side": "BUY"},
            decision=decision,
            corr_id="corr-1",
            oco_group_id="oco-1",
            owner_context=None,
            placement_path="primary",
        )

        guardian_call = fsm.order_guardian.register_brackets.call_args.kwargs
        assert guardian_call["sl_client_id"] == "SL-legacy-1"

    @pytest.mark.asyncio
    async def test_deferred_registration_prefers_algo_client_id_for_guardian(self):
        fsm = _make_bracket_manager_fsm()
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                return_value={"orderId": "500001", "clientAlgoId": "algo-sl-1"}
            ),
            place_take_profit_market_close_position=AsyncMock(
                return_value={"orderId": "600001", "clientAlgoId": "algo-tp-1"}
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)

        manager = BracketManager(fsm)
        manager.preflight_position_check = AsyncMock(return_value=True)

        await manager.place_deferred_brackets(
            "entry-1",
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "sl": Decimal("99"),
                "tp": Decimal("101"),
                "rid": "rid-1",
                "idem_key": "idem-1",
                "tick_size": Decimal("0.1"),
                "corr_id": "corr-1",
                "oco_group_id": "oco-1",
                "entry_client_order_id": "ENTRY-1",
            },
        )

        sl_call = fsm.order_guardian.register_bracket.call_args_list[0].kwargs
        tp_call = fsm.order_guardian.register_bracket.call_args_list[1].kwargs
        assert sl_call["client_order_id"] == "algo-sl-1"
        assert tp_call["client_order_id"] == "algo-tp-1"


class TestDeferredBracketClearTiming:
    def _entry_payload(self) -> Dict[str, Any]:
        return {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "sl": Decimal("99"),
            "tp": Decimal("101"),
            "rid": "rid-1",
            "idem_key": "idem-1",
            "tick_size": Decimal("0.1"),
            "corr_id": "corr-1",
            "oco_group_id": "oco-1",
            "entry_client_order_id": "ENTRY-1",
        }

    @pytest.mark.asyncio
    async def test_success_clears_pending_brackets_exactly_once(self, fsm_harness):
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                return_value={"orderId": "500001", "clientAlgoId": "algo-sl-1"}
            ),
            place_take_profit_market_close_position=AsyncMock(
                return_value={"orderId": "600001", "clientAlgoId": "algo-tp-1"}
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        fsm._pending_brackets["entry-1"] = dict(self._entry_payload())

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=True)

        with patch.object(fsm, "_clear_pending_brackets", wraps=fsm._clear_pending_brackets) as clear_pending, patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ) as pending_cleared, patch.object(
            fsm, "_persist_restore_artifact_snapshot"
        ) as persist_snapshot:
            result = await manager.place_deferred_brackets("entry-1", self._entry_payload())

        assert result is True
        assert "entry-1" not in fsm._pending_brackets
        clear_pending.assert_called_once_with(
            "entry-1",
            reason="filled",
            symbol="BTCUSDT",
            persist_snapshot=True,
        )
        pending_cleared.assert_called_once_with(
            entry_order_id="entry-1",
            reason="filled",
            symbol="BTCUSDT",
        )
        persist_snapshot.assert_any_call(
            trigger="bracket_deferred_cleared:filled",
            allow_empty=True,
        )

    @pytest.mark.asyncio
    async def test_existing_live_synced_brackets_suppress_duplicate_deferred_placement(self, fsm_harness):
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                return_value={"orderId": "700001",
                              "clientAlgoId": "algo-sl-new"}
            ),
            place_take_profit_market_close_position=AsyncMock(
                return_value={"orderId": "800001",
                              "clientAlgoId": "algo-tp-new"}
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.get_our_open_brackets = AsyncMock(
            return_value=[
                {"orderId": "500001"},
                {"orderId": "600001"},
            ]
        )
        fsm._has_active_lifecycle_for_symbol = MagicMock(return_value=True)
        fsm._set_symbol_brackets_snapshot(
            "BTCUSDT",
            sl_order_id="500001",
            tp_order_id="600001",
        )
        fsm._pending_brackets["entry-1"] = dict(self._entry_payload())

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=True)

        with patch.object(fsm, "_clear_pending_brackets", wraps=fsm._clear_pending_brackets) as clear_pending, patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ) as pending_cleared:
            result = await manager.place_deferred_brackets("entry-1", self._entry_payload())

        assert result is True
        assert "entry-1" not in fsm._pending_brackets
        fsm.order_guardian.get_our_open_brackets.assert_awaited_once_with(
            "BTCUSDT")
        fsm.adapter.place_stop_market_close_position.assert_not_awaited()
        fsm.adapter.place_take_profit_market_close_position.assert_not_awaited()
        clear_pending.assert_called_once_with(
            "entry-1",
            reason="filled",
            symbol="BTCUSDT",
            persist_snapshot=True,
        )
        pending_cleared.assert_called_once_with(
            entry_order_id="entry-1",
            reason="filled",
            symbol="BTCUSDT",
        )

    @pytest.mark.asyncio
    async def test_preflight_false_preserves_pending_brackets(self, fsm_harness):
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm._pending_brackets["entry-1"] = dict(self._entry_payload())

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=False)

        with patch.object(fsm, "_clear_pending_brackets", wraps=fsm._clear_pending_brackets) as clear_pending, patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ) as pending_cleared:
            result = await manager.place_deferred_brackets("entry-1", self._entry_payload())

        assert result is False
        assert "entry-1" in fsm._pending_brackets
        clear_pending.assert_not_called()
        pending_cleared.assert_not_called()

    @pytest.mark.asyncio
    async def test_guardian_veto_preserves_pending_brackets(self, fsm_harness):
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.order_guardian.should_place_brackets = AsyncMock(
            return_value=False)
        fsm._pending_brackets["entry-1"] = dict(self._entry_payload())

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=True)

        with patch.object(fsm, "_clear_pending_brackets", wraps=fsm._clear_pending_brackets) as clear_pending, patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ) as pending_cleared:
            result = await manager.place_deferred_brackets("entry-1", self._entry_payload())

        assert result is False
        assert "entry-1" in fsm._pending_brackets
        clear_pending.assert_not_called()
        pending_cleared.assert_not_called()

    @pytest.mark.asyncio
    async def test_placement_exception_preserves_pending_brackets(self, fsm_harness):
        fsm, _, _cfg = fsm_harness
        fsm.config.domains.execution_position.bracket_placement.tp_widen_first_bps = 10
        fsm.adapter = SimpleNamespace(
            place_stop_market_close_position=AsyncMock(
                side_effect=RuntimeError("sl boom")),
            place_take_profit_market_close_position=AsyncMock(
                return_value={"orderId": "600001", "clientAlgoId": "algo-tp-1"}
            ),
        )
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm.order_guardian.register_bracket = MagicMock()
        fsm._pending_brackets["entry-1"] = dict(self._entry_payload())

        manager = fsm._bracket_mgr
        manager.preflight_position_check = AsyncMock(return_value=True)

        with patch.object(fsm, "_clear_pending_brackets", wraps=fsm._clear_pending_brackets) as clear_pending, patch(
            "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
        ) as pending_cleared:
            result = await manager.place_deferred_brackets("entry-1", self._entry_payload())

        assert result is False
        assert "entry-1" in fsm._pending_brackets
        clear_pending.assert_not_called()
        pending_cleared.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Exchange fragmentation safety
# ---------------------------------------------------------------------------

class TestExchangeFragmentationSafety:
    """Multiple partial fills for the same bracket order remain safe."""

    def test_second_fill_does_not_match_after_flat(self):
        """After SL fill transitions to FLAT, second partial fill doesn't re-match."""
        flow = _make_manage_flow()
        flow.sl_order_id = "500001"
        flow.sl_algo_client_id = "algo_sl_99001"
        flow.tp_order_id = "600001"
        flow.tp_algo_client_id = "algo_tp_99002"

        # First fill matches
        role, matched, reason = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="algo_sl_99001",
        )
        assert matched is True
        assert role == "SL"

        # Simulate lifecycle clear (happens in _handle_bracket_fill -> _clear_lifecycle_tracking)
        flow._clear_lifecycle_tracking(reason="sl_filled", clear_symbol=True)

        # Second fill: all IDs cleared, should not match
        role2, matched2, reason2 = flow._resolve_bracket_match(
            order_id="777001",
            client_order_id="algo_sl_99001",
        )
        assert matched2 is False
        assert role2 == "UNKNOWN"

    def test_orderindex_multiple_fills_same_client_id(self):
        """Multiple fills with same clientOrderId all resolve to same OrderRef."""
        idx = OrderIndex(ttl_sec=600)
        ref = idx.register_bracket_child(
            rid="parent-rid",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="500001",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        # All 3 partial fills use same clientOrderId
        for _ in range(3):
            found = idx.get(clientOrderId="SL-abc123")
            assert found is ref
            assert found.order_kind == "SL"
