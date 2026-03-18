"""
P0 Regression Tests: Regime-Flip Close Path Safety

Tests the four critical guarantees:
1. Aurora symbol regime-flip close resolves strategy_id="aurora" from registry
2. md_amr symbol (XRPUSDT) close resolves strategy_id="md_amr", not "aurora"
3. Ambiguous multi-owner strategy fails-closed (no close emitted, reject event fired via canonical helper)
4. Close path not blocked by LIMIT TTL logic (reduce_only=True exemption in _resolve_order_policy)

Architecture note:
  IntentEmitter is constructed with injected callables:
    emit_reduce_only_close_fn  -> records close calls
    registry_lookup_fn         -> mocked to return configured owners

All tests are isolated unit tests — no FSM/bus required for tests 1-3.
Test 4 exercises IntentBuilder._resolve_order_policy directly.
"""

from __future__ import annotations

import decimal
from typing import Any
from unittest.mock import MagicMock, call


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_clock(now_ms: int = 1_000_000, now_sec: float = 1000.0) -> Any:
    clock = MagicMock()
    clock.now_ms.return_value = now_ms
    clock.now_sec.return_value = now_sec
    return clock


def _make_emitter(
    *,
    registry_owners: list[str],
    close_calls: list,
    reject_calls: list,
):
    """Build an IntentEmitter with mocked injected callables."""
    from apps.reference.domains.decision_making.intent_emitter import IntentEmitter

    fsm = MagicMock()
    clock = _make_clock()
    config = MagicMock()
    config.domains.decision_making.risk_gate.min_intents_for_check = 100
    config.trading.mode = "testnet"
    config.strategies.aurora.decision.retry_ttl_ms = 5000
    config.strategies.aurora.decision.retry_max_count = 3

    portfolio_store: list[dict] = []

    def emit_reduce_only_close_fn(*, symbol, reason, rid, strategy_id, **kw):
        close_calls.append({"symbol": symbol, "reason": reason, "rid": rid, "strategy_id": strategy_id})
        return True

    def registry_lookup_fn(sym: str) -> list[str]:
        return registry_owners

    emitter = IntentEmitter(
        fsm=fsm,
        clock=clock,
        config=config,
        alert_manager=None,
        get_portfolio=lambda: {"positions": portfolio_store},
        propose_trade_intent=MagicMock(),
        logger=MagicMock(),
        emit_reduce_only_close_fn=emit_reduce_only_close_fn,
        registry_lookup_fn=registry_lookup_fn,
    )

    # Patch emit_trade_intent_rejected to record calls without WAL side-effect
    def _capture_reject(**kw):
        reject_calls.append(kw)

    emitter.emit_trade_intent_rejected = _capture_reject  # type: ignore[method-assign]

    return emitter, portfolio_store


# ---------------------------------------------------------------------------
# Test 1: Aurora symbol resolves strategy_id="aurora" from registry
# ---------------------------------------------------------------------------

def test_aurora_symbol_regime_flip_close_uses_aurora_strategy():
    """
    BTCUSDT is assigned to ["aurora"] in registry.
    Regime flip should call emit_reduce_only_close with strategy_id="aurora".
    """
    close_calls: list = []
    reject_calls: list = []

    emitter, portfolio = _make_emitter(
        registry_owners=["aurora"],
        close_calls=close_calls,
        reject_calls=reject_calls,
    )

    # Inject a LONG position
    portfolio.append({"symbol": "BTCUSDT", "positionAmt": "0.5"})

    # Simulate TREND_DOWN regime flip (long position should be closed)
    emitter.handle_regime_flip("BTCUSDT", {"regime": "TREND_DOWN", "structural": True})

    assert len(close_calls) == 1, "Expected exactly one close call"
    assert close_calls[0]["symbol"] == "BTCUSDT"
    assert close_calls[0]["strategy_id"] == "aurora"
    assert len(reject_calls) == 0, "No reject should be emitted for unambiguous aurora"


# ---------------------------------------------------------------------------
# Test 2: md_amr symbol resolves strategy_id="md_amr", NOT "aurora"
# ---------------------------------------------------------------------------

def test_md_amr_symbol_regime_flip_close_uses_md_amr_strategy():
    """
    XRPUSDT is assigned to ["md_amr"] in registry.
    Regime flip close must use strategy_id="md_amr", not the "aurora" default.
    This is the P0 bug: before the fix, the default was always "aurora".
    """
    close_calls: list = []
    reject_calls: list = []

    emitter, portfolio = _make_emitter(
        registry_owners=["md_amr"],
        close_calls=close_calls,
        reject_calls=reject_calls,
    )

    # Inject a SHORT position for XRPUSDT
    portfolio.append({"symbol": "XRPUSDT", "positionAmt": "-100.0"})

    emitter.handle_regime_flip("XRPUSDT", {"regime": "TREND_UP", "structural": True})

    assert len(close_calls) == 1, "Expected exactly one close call"
    assert close_calls[0]["symbol"] == "XRPUSDT"
    assert close_calls[0]["strategy_id"] == "md_amr", (
        f"Expected 'md_amr', got {close_calls[0]['strategy_id']!r}. "
        "Bug: aurora was silently defaulted for non-aurora symbol."
    )
    assert len(reject_calls) == 0


# ---------------------------------------------------------------------------
# Test 3: Ambiguous strategy (multi-owner) fails-closed
# ---------------------------------------------------------------------------

def test_ambiguous_strategy_fails_closed_no_close_emitted():
    """
    Symbol has multiple registered strategies: ["aurora", "mean_reversion"].
    Position dict has no strategy_id field (as per current PositionData schema).
    
    Expected: NO close is emitted. Instead, reject event via canonical helper.
    No silent default to "aurora".
    """
    close_calls: list = []
    reject_calls: list = []

    emitter, portfolio = _make_emitter(
        registry_owners=["aurora", "mean_reversion"],  # multi-owner = ambiguous
        close_calls=close_calls,
        reject_calls=reject_calls,
    )

    portfolio.append({"symbol": "BTCUSDT", "positionAmt": "0.5"})

    emitter.handle_regime_flip("BTCUSDT", {"regime": "TREND_DOWN", "structural": True})

    assert len(close_calls) == 0, (
        "No close should be emitted for ambiguous multi-owner strategy. "
        f"Got close_calls={close_calls}"
    )
    assert len(reject_calls) == 1, "Expected one reject event via canonical helper"
    assert reject_calls[0]["reason_code"] == "REGIME_FLIP_STRATEGY_UNRESOLVABLE"
    assert reject_calls[0]["symbol"] == "BTCUSDT"
    assert reject_calls[0]["strategy_id"] == "UNRESOLVED"


# ---------------------------------------------------------------------------
# Test 4: LIMIT reduce_only close not blocked by TTL logic
# ---------------------------------------------------------------------------

def test_reduce_only_limit_close_not_blocked_by_ttl_rejection():
    """
    Regression guard for intent_builder._resolve_order_policy:
    LIMIT + reduce_only=True should NOT require tf_sec or valid_for_ms.
    
    Before fix: reduce_only=True still reached "LIMIT requires valid_for_ms"
    rejection at line 501 when tf_sec=None and the TTL config couldn't populate valid_for_ms.
    
    After fix: LIMIT + reduce_only=True skips the entire TTL block.
    valid_for_ms=None is acceptable and no rejection is emitted.
    """
    reject_calls: list = []
    emitted_payloads: list = []

    # Build minimal IntentBuilder harness
    from apps.reference.domains.decision_making.intent_builder import IntentBuilder

    fsm = MagicMock()
    fsm.emit.side_effect = lambda evt, payload=None, **kw: emitted_payloads.append((evt, payload))
    clock = _make_clock()

    # Config: aurora strategy with LIMIT order type (worst case for close path)
    # _resolve_order_policy reads: config.strategies.<strategy_id>.execution.entry_order_type
    exec_pos_cfg = MagicMock()
    exec_pos_cfg.pending_entry_ttl.enabled = True
    exec_pos_cfg.pending_entry_ttl.ttl_by_tf_sec = {60: 120}  # only 60s tf_sec mapped
    exec_pos_cfg.pending_entry_ttl.reject_unknown_tf = True

    aurora_exec_cfg = MagicMock()
    aurora_exec_cfg.entry_order_type = "LIMIT"
    aurora_exec_cfg.entry_tif = "GTC"

    config = MagicMock()
    config.domains.execution_position = exec_pos_cfg
    # Wire the strategy execution config so _resolve_order_policy finds LIMIT
    config.strategies.aurora.execution = aurora_exec_cfg

    def capture_reject(**kw):
        reject_calls.append(kw)

    builder = IntentBuilder(
        fsm=fsm,
        clock=clock,
        config=config,
        tca_prefs={},
        risk_budgets={},
        safe_decimal_fn=lambda v, d=None: decimal.Decimal(str(v)) if v is not None else d,
        check_strategy_arbitration_fn=lambda sym, sid, **kw: {"allowed": True, "reason": ""},
        warmup_gate_fn=lambda **kw: False,
        emit_rejected_fn=capture_reject,
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0.5, 60, 0.6, 5)),
        side_intent_window={},
        logger=MagicMock(),
    )

    # Call _resolve_order_policy with reduce_only=True and tf_sec=None
    # (no timeframe context for a close — this is the correct production state)
    order_type, tif, valid_for_ms = builder._resolve_order_policy(
        symbol="BTCUSDT",
        strategy_id="aurora",
        side="SELL",
        rid="rid-test-close",
        reduce_only=True,    # ← regime-flip close path
        tf_sec=None,         # ← no tf_sec for close path (correct)
        why_chain=["regime_flip"],
    )

    # The key assertion: no TTL rejection, valid_for_ms is None (acceptable for close)
    assert len(reject_calls) == 0, (
        f"LIMIT + reduce_only=True should not trigger TTL rejection. "
        f"Got reject_calls={reject_calls}"
    )
    assert order_type == "LIMIT", f"Order type should be LIMIT, got {order_type!r}"
    assert valid_for_ms is None, (
        "valid_for_ms must be None for reduce_only closes — no pending-entry TTL semantics. "
        f"Got valid_for_ms={valid_for_ms}"
    )
