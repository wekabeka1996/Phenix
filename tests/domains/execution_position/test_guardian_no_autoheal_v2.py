"""
Test that OrderGuardian auto-heal methods are properly disabled in V2 compat mode.

Verifies:
1. v2_compat_mode flag disables auto-heal methods (raises RuntimeError)
2. V2 runtime doesn't import/call auto-heal methods (AST parsing)
3. BracketService remains pure (no adapter calls)

RID: GUARD-V2-NO-AUTOHEAL-001
WHY: Ensure V2 runtime uses observe-only philosophy (services recommend, runtime executes)
"""
import ast
import inspect
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from apps.reference.services.order_guardian import (
    OrderGuardian,
    AggregatedOcoGuardianConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketService


# =============================================================================
# TEST 1: v2_compat_mode disables auto-heal methods
# =============================================================================


@pytest.fixture
def guardian_v2_compat():
    """OrderGuardian with v2_compat_mode=True"""
    cfg = AggregatedOcoGuardianConfig(
        enabled=True,
        v2_compat_mode=True,  # CRITICAL: disable auto-heal
        ttl_protect_new_bracket_ms=60000,
        allow_unprotected_position=False,
    )
    adapter_mock = AsyncMock()
    clock_mock = Mock()
    clock_mock.time = Mock(return_value=1234567890.0)  # Fixed timestamp

    guardian = OrderGuardian(
        adapter=adapter_mock,
        bus=None,
        aggregated_oco_cfg=cfg,  # CORRECT parameter name
        store=Mock(),
        clock=clock_mock,
        poll_interval_ms=0,  # disable background loop
    )
    return guardian


@pytest.mark.asyncio
async def test_ensure_single_bracket_set_disabled_in_v2(guardian_v2_compat):
    """GUARD-V2-001: ensure_single_bracket_set_for_position() raises RuntimeError in v2_compat_mode"""
    with pytest.raises(RuntimeError, match="ensure_single_bracket_set_for_position\\(\\) disabled in V2 compat mode"):
        guardian_v2_compat.ensure_single_bracket_set_for_position(
            symbol="BTCUSDT",
            side="LONG",
            position_amt=0.5,
            open_orders=[],
        )


@pytest.mark.asyncio
async def test_cleanup_orphans_disabled_in_v2(guardian_v2_compat):
    """GUARD-V2-002: cleanup_orphans() raises RuntimeError in v2_compat_mode"""
    with pytest.raises(RuntimeError, match="cleanup_orphans\\(\\) disabled in V2 compat mode"):
        await guardian_v2_compat.cleanup_orphans(symbol="BTCUSDT")


@pytest.mark.asyncio
async def test_cleanup_before_close_disabled_in_v2(guardian_v2_compat):
    """GUARD-V2-003: cleanup_before_close() raises RuntimeError in v2_compat_mode"""
    with pytest.raises(RuntimeError, match="cleanup_before_close\\(\\) disabled in V2 compat mode"):
        await guardian_v2_compat.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="123",
        )


@pytest.mark.asyncio
async def test_cleanup_other_brackets_disabled_in_v2(guardian_v2_compat):
    """GUARD-V2-004: cleanup_other_brackets_for_symbol() raises RuntimeError in v2_compat_mode"""
    with pytest.raises(RuntimeError, match="cleanup_other_brackets_for_symbol\\(\\) disabled in V2 compat mode"):
        await guardian_v2_compat.cleanup_other_brackets_for_symbol(
            symbol="BTCUSDT",
            keep_parent_order_id="123",
        )


@pytest.mark.asyncio
async def test_reconcile_symbol_disabled_in_v2(guardian_v2_compat):
    """GUARD-V2-005: reconcile_symbol() raises RuntimeError in v2_compat_mode"""
    with pytest.raises(RuntimeError, match="reconcile_symbol\\(\\) disabled in V2 compat mode"):
        await guardian_v2_compat.reconcile_symbol(symbol="BTCUSDT")


@pytest.mark.asyncio
async def test_start_disabled_in_v2(guardian_v2_compat):
    """GUARD-V2-006: start() does NOT spawn background loop in v2_compat_mode"""
    await guardian_v2_compat.start()
    # Should not create _poller_task
    assert guardian_v2_compat._poller_task is None


# =============================================================================
# TEST 2: V2 runtime doesn't import auto-heal methods
# =============================================================================


def test_v2_runtime_no_autoheal_imports():
    """GUARD-V2-007: ExecPosRuntimeV2 doesn't import auto-heal methods (AST analysis)"""
    runtime_path = Path(
        "apps/reference/domains/execution_position/shadow_execpos/execpos_runtime_v2.py")
    if not runtime_path.exists():
        pytest.skip("ExecPosRuntimeV2 not found, skipping AST test")

    with open(runtime_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(runtime_path))

    # List of forbidden method names (auto-heal)
    forbidden = [
        "ensure_single_bracket_set_for_position",
        "cleanup_orphans",
        "cleanup_before_close",
        "cleanup_other_brackets_for_symbol",
        "reconcile_symbol",
        "_poll_loop",
    ]

    # Search for calls to forbidden methods
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                if method_name in forbidden:
                    calls.append(method_name)

    assert not calls, (
        f"V2 runtime should NOT call auto-heal methods, but found: {calls}. "
        f"Remove these calls or use BracketService.evaluate() instead."
    )


# =============================================================================
# TEST 3: BracketService is pure (no adapter calls)
# =============================================================================


def test_bracket_service_is_pure():
    """GUARD-V2-008: BracketService doesn't call adapter (pure computation)"""
    source = inspect.getsource(BracketService)

    # Forbidden patterns (adapter method calls)
    forbidden_patterns = [
        ".cancel_order(",
        ".place_order(",
        ".get_open_orders(",
        ".get_open_positions(",
        "adapter.",  # any adapter reference
    ]

    found = []
    for pattern in forbidden_patterns:
        if pattern in source:
            found.append(pattern)

    assert not found, (
        f"BracketService should be PURE (no adapter calls), but found: {found}. "
        f"Use runtime to execute recommended actions instead."
    )


# =============================================================================
# TEST 4: Query-only methods still work in v2_compat_mode
# =============================================================================


@pytest.mark.asyncio
async def test_query_methods_work_in_v2(guardian_v2_compat):
    """GUARD-V2-009: Query-only methods (get_active_bracket_set, etc.) still work in v2_compat_mode"""
    # These should NOT raise errors
    result = guardian_v2_compat.get_active_bracket_set("BTCUSDT", "LONG")
    assert result is None  # no data yet, but no error

    result = guardian_v2_compat.list_all_bracket_sets()  # no symbol parameter
    assert isinstance(result, list)


# =============================================================================
# TEST 5: Legacy mode still allows auto-heal (v2_compat_mode=False)
# =============================================================================


@pytest.mark.asyncio
async def test_autoheal_allowed_in_legacy_mode():
    """GUARD-V2-010: Auto-heal methods work when v2_compat_mode=False (legacy compatibility)"""
    cfg = AggregatedOcoGuardianConfig(
        enabled=True,
        v2_compat_mode=False,  # LEGACY mode
        ttl_protect_new_bracket_ms=60000,
        allow_unprotected_position=False,
    )
    adapter_mock = AsyncMock()
    adapter_mock.get_open_positions.return_value = []
    adapter_mock.get_open_orders.return_value = []

    clock_mock = Mock()
    clock_mock.time = Mock(return_value=1234567890.0)

    guardian = OrderGuardian(
        adapter=adapter_mock,
        bus=None,
        aggregated_oco_cfg=cfg,  # CORRECT parameter name
        store=Mock(),
        clock=clock_mock,
        poll_interval_ms=0,
    )

    # Should NOT raise errors (legacy mode allows auto-heal)
    count = await guardian.cleanup_orphans(symbol="BTCUSDT")
    assert isinstance(count, int)  # no error, returns count
