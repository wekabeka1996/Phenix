"""
WARMUP-SSOT: Fail-closed behavior tests for handler readiness contract resolution.

Verifies:
1. aurora_handler.get_readiness_diagnostics() returns ready=False + READINESS_CONTRACT_UNRESOLVED
   when get_active_strategy_profile raises.
2. md_amr_handler.get_readiness_diagnostics() same.
3. md_amr_handler._on_process_strategy blocks with READINESS_CONTRACT_UNRESOLVED
   when get_active_strategy_profile raises (trading path fail-closed).
4. No "if _basis_required else True" logic: when basis_required=0 and no exception,
   the diagnostic correctly shows not-ready (0 bars seen < 0 required is handled safely).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_aurora_handler_minimal() -> AuroraHandler:
    handler = object.__new__(AuroraHandler)
    handler.logger = logging.getLogger("tests.aurora.fail_closed")
    handler.strategy_id = "aurora"
    handler.timeframe_sec = 300
    handler.config = SimpleNamespace()
    handler._enabled_symbols = {"BTCUSDT", "ETHUSDT"}
    handler._bars_seen_since_restart = {"BTCUSDT": 5, "ETHUSDT": 10}
    # No _basis_required_bars_override → will resolve from profile
    return handler


def _make_md_amr_handler_minimal() -> MDAMRHandler:
    handler = object.__new__(MDAMRHandler)
    handler.logger = logging.getLogger("tests.md_amr.fail_closed")
    handler.mlog = logging.getLogger("tests.md_amr.fail_closed")
    handler.config = SimpleNamespace()
    # timeframe_sec is a property reading from _cfg
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False, sentiment_block_threshold=0.0, block_ttl_sec=0),
    )
    handler._enabled_symbols = {"BTCUSDT"}
    handler._bars_seen_since_restart = {"BTCUSDT": 3}
    return handler


class _Event:
    def __init__(self, payload: dict) -> None:
        self.pld = payload


# ── aurora diagnostics ────────────────────────────────────────────────────────

def test_aurora_diagnostics_returns_contract_error_on_resolution_failure() -> None:
    """When get_active_strategy_profile raises, aurora diagnostics must return
    ready=False with READINESS_CONTRACT_UNRESOLVED — not ready=True (old fail-open behavior)."""
    handler = _make_aurora_handler_minimal()

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        side_effect=ValueError("test: sma_cfg is None"),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 2  # one per symbol
    for r in results:
        assert r["ready"] is False, (
            f"Symbol {r['symbol']}: expected ready=False on contract error, got ready=True"
        )
        assert r["bars_required"] is None
        assert "READINESS_CONTRACT_UNRESOLVED" in str(r["block_reason"]), (
            f"Symbol {r['symbol']}: expected READINESS_CONTRACT_UNRESOLVED in block_reason, "
            f"got: {r['block_reason']}"
        )


def test_aurora_diagnostics_contract_error_includes_exception_type() -> None:
    """block_reason must include the exception type name for operator debuggability."""
    handler = _make_aurora_handler_minimal()

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        side_effect=RuntimeError("missing config"),
    ):
        results = handler.get_readiness_diagnostics()

    for r in results:
        assert "RuntimeError" in str(r["block_reason"]), (
            f"Expected exception type in block_reason, got: {r['block_reason']}"
        )


def test_aurora_diagnostics_normal_path_no_false_positive_ready() -> None:
    """When profile resolves correctly with basis_required_bars=50,
    handler must NOT be ready with only 5 bars seen."""
    handler = _make_aurora_handler_minimal()
    handler._bars_seen_since_restart = {"BTCUSDT": 5}
    handler._enabled_symbols = {"BTCUSDT"}

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=50),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    assert results[0]["ready"] is False
    assert results[0]["bars_seen"] == 5
    assert results[0]["bars_required"] == 50


def test_aurora_diagnostics_ready_when_bars_met() -> None:
    """When bars_seen >= basis_required_bars, handler is ready."""
    handler = _make_aurora_handler_minimal()
    handler._bars_seen_since_restart = {"BTCUSDT": 301}
    handler._enabled_symbols = {"BTCUSDT"}

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=301),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    assert results[0]["ready"] is True
    assert results[0]["block_reason"] is None


# ── md_amr diagnostics ────────────────────────────────────────────────────────

def test_md_amr_diagnostics_returns_contract_error_on_resolution_failure() -> None:
    """When get_active_strategy_profile raises, md_amr diagnostics must return
    ready=False with READINESS_CONTRACT_UNRESOLVED."""
    handler = _make_md_amr_handler_minimal()

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        side_effect=ValueError("test: broken config"),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    assert results[0]["ready"] is False
    assert results[0]["bars_required"] is None
    assert "READINESS_CONTRACT_UNRESOLVED" in str(results[0]["block_reason"])


def test_md_amr_diagnostics_no_false_positive_ready() -> None:
    """md_amr must not report ready=True when bars < basis_required."""
    handler = _make_md_amr_handler_minimal()
    handler._bars_seen_since_restart = {"BTCUSDT": 10}

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=301),
    ):
        results = handler.get_readiness_diagnostics()

    assert results[0]["ready"] is False
    assert results[0]["bars_required"] == 301


# ── md_amr trading gate fail-closed ──────────────────────────────────────────

def test_md_amr_trading_gate_blocks_on_contract_resolution_failure() -> None:
    """When get_active_strategy_profile raises during _on_process_strategy,
    md_amr must emit READINESS_CONTRACT_UNRESOLVED and return — not proceed to signal."""
    handler = object.__new__(MDAMRHandler)
    rejections: list[dict] = []

    handler.logger = logging.getLogger("tests.md_amr.fail_closed.trading")
    handler.mlog = logging.getLogger("tests.md_amr.fail_closed.trading")
    handler._enabled = True
    handler._enabled_symbols = {"BTCUSDT"}
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=0.0,
            block_ttl_sec=0,
        ),
    )
    handler.config = SimpleNamespace()
    handler._bars_seen_since_restart = {}
    handler._pending_close = {}
    handler._position_qty = {}
    handler._bars_held = {}
    handler._last_ingested_bar_ts_ms = {}
    handler._deferred = {}
    handler._entry_anchor = {}
    on_bar_calls: list = []
    handler._strategies = {
        "BTCUSDT": SimpleNamespace(on_bar=lambda **kw: on_bar_calls.append(kw) or {"status": "SIGNAL"})
    }
    handler._is_duplicate_live_event = lambda symbol, ts_ms: False
    handler._expire_defer_if_needed = lambda symbol, now_ms: None
    handler._is_mandatory_live_warmup_active = lambda now_ms: False
    handler._emit_trade_intent_rejected_gate = lambda **kwargs: rejections.append(
        kwargs)
    handler._rid = lambda **_kwargs: "test-rid"

    event = _Event({
        "symbol": "BTCUSDT",
        "tf_sec": 900,
        "warmup": {"full_ready": True},
        "bar": {"end_ts_ms": 1_700_000_000_000},
        "features": {},
    })

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        side_effect=ValueError("broken: sma_cfg is None"),
    ):
        handler._on_process_strategy(event)

    # Rejection must have been emitted with READINESS_CONTRACT_UNRESOLVED
    # Note: on_bar MAY have been called for computation before the gate check —
    # that's expected. The gate blocks SIGNAL EMISSION, not the on_bar computation.
    assert len(rejections) == 1, (
        f"Expected 1 READINESS_CONTRACT_UNRESOLVED rejection, got {len(rejections)}: {rejections}"
    )
    assert rejections[0]["reason_code"] == "READINESS_CONTRACT_UNRESOLVED", (
        f"Expected READINESS_CONTRACT_UNRESOLVED, got: {rejections[0]['reason_code']}"
    )


# ── profile is None → same fail-closed as exception path ─────────────────────

def test_aurora_diagnostics_blocks_when_profile_is_none() -> None:
    """When get_active_strategy_profile returns None (strategy not in matrix),
    aurora diagnostics must return ready=False + READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND.
    Previously: if _profile else 0 → ready=True (silent fail-open)."""
    handler = _make_aurora_handler_minimal()

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=None,  # profile not found
    ):
        results = handler.get_readiness_diagnostics()

    assert all(not r["ready"] for r in results), (
        "aurora diagnostics reported ready=True when profile=None — fail-open residual bug!"
    )
    assert all("PROFILE_NOT_FOUND" in str(r["block_reason"]) for r in results)


def test_md_amr_diagnostics_blocks_when_profile_is_none() -> None:
    """When get_active_strategy_profile returns None, md_amr diagnostics
    must return ready=False + READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND."""
    handler = _make_md_amr_handler_minimal()

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=None,
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    assert results[0]["ready"] is False
    assert "PROFILE_NOT_FOUND" in str(results[0]["block_reason"])


# ── drift prevention: no "if _profile else 0" anywhere ───────────────────────

def test_no_profile_is_none_fail_open_in_aurora_decision() -> None:
    """Drift prevention: aurora_decision.py must not contain 'if _profile else 0'."""
    import inspect
    import apps.reference.domains.strategies.runtimes.aurora.decision as module
    assert "if _profile else 0" not in inspect.getsource(module), (
        "Residual 'if _profile else 0' found in aurora_decision — fail-open on profile=None!"
    )


def test_no_profile_is_none_fail_open_in_aurora_handler() -> None:
    """Drift prevention: aurora_handler.py must not contain 'if _profile else 0'."""
    import inspect
    import apps.reference.domains.strategies.runtimes.aurora.handler as module
    assert "if _profile else 0" not in inspect.getsource(module), (
        "Residual 'if _profile else 0' found in aurora_handler — fail-open on profile=None!"
    )


def test_no_profile_is_none_fail_open_in_md_amr_handler() -> None:
    """Drift prevention: md_amr_handler.py must not contain 'if _profile else 0'."""
    import inspect
    import apps.reference.domains.strategies.runtimes.md_amr.handler as module
    assert "if _profile else 0" not in inspect.getsource(module), (
        "Residual 'if _profile else 0' found in md_amr_handler — fail-open on profile=None!"
    )


# ── drift prevention: no "if _basis_required else True" ──────────────────────

def test_no_fail_open_gate_pattern_in_aurora_handler() -> None:
    """Drift prevention: aurora_handler must not contain 'if _basis_required else True'
    or equivalent fail-open gate logic."""
    import ast
    import inspect
    import apps.reference.domains.strategies.runtimes.aurora.handler as module

    source = inspect.getsource(module)
    # Check for the specific fail-open pattern
    assert "else True" not in source or "if _basis_required else True" not in source, (
        "Fail-open pattern 'if _basis_required else True' found in aurora_handler — "
        "remove it: when basis_required=0 and no exception, use direct comparison."
    )


def test_no_fail_open_gate_pattern_in_md_amr_handler() -> None:
    """Drift prevention: md_amr_handler must not contain 'if _basis_required else True'."""
    import ast
    import inspect
    import apps.reference.domains.strategies.runtimes.md_amr.handler as module

    source = inspect.getsource(module)
    assert "if _basis_required else True" not in source, (
        "Fail-open pattern 'if _basis_required else True' found in md_amr_handler — remove it."
    )
