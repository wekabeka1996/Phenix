"""
P0 Regression Tests: Regime-Flip Close Path Safety

Tests the four critical guarantees:
1. Aurora symbol regime-flip close resolves strategy_id="aurora" from registry
2. md_amr symbol (XRPUSDT) close resolves strategy_id="md_amr", not "aurora"
3. Ambiguous multi-owner strategy fails-closed (no close emitted, reject event fired via canonical helper)
4. Close path not blocked by entry TTL logic; reduce_only LIMIT close uses exit_limit_ttl_ms

Architecture note:
  IntentEmitter is constructed with injected callables:
    emit_reduce_only_close_fn  -> records close calls
    registry_lookup_fn         -> mocked to return configured owners

All tests are isolated unit tests: no FSM/bus required for tests 1-3.
Test 4 exercises IntentBuilder._resolve_order_policy directly.
"""

from __future__ import annotations

import decimal
from typing import Any
from unittest.mock import MagicMock


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
    from apps.reference.domains.decision_making.intent.emitter import IntentEmitter

    fsm = MagicMock()
    clock = _make_clock()
    config = MagicMock()
    config.domains.decision_making.risk_gate.min_intents_for_check = 100
    config.trading.mode = "testnet"
    config.strategies.aurora.decision.retry_ttl_ms = 5000
    config.strategies.aurora.decision.retry_max_count = 3

    portfolio_store: list[dict] = []

    def emit_reduce_only_close_fn(*, symbol, reason, rid, strategy_id, **kw):
        close_calls.append(
            {
                "symbol": symbol,
                "reason": reason,
                "rid": rid,
                "strategy_id": strategy_id,
            }
        )
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

    def _capture_reject(**kw):
        reject_calls.append(kw)

    emitter.emit_trade_intent_rejected = _capture_reject  # type: ignore[method-assign]

    return emitter, portfolio_store


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

    portfolio.append({"symbol": "BTCUSDT", "positionAmt": "0.5"})

    emitter.handle_regime_flip("BTCUSDT", {"regime": "TREND_DOWN", "structural": True})

    assert len(close_calls) == 1
    assert close_calls[0]["symbol"] == "BTCUSDT"
    assert close_calls[0]["strategy_id"] == "aurora"
    assert len(reject_calls) == 0


def test_md_amr_symbol_regime_flip_close_uses_md_amr_strategy():
    """
    XRPUSDT is assigned to ["md_amr"] in registry.
    Regime flip close must use strategy_id="md_amr", not the "aurora" default.
    """
    close_calls: list = []
    reject_calls: list = []

    emitter, portfolio = _make_emitter(
        registry_owners=["md_amr"],
        close_calls=close_calls,
        reject_calls=reject_calls,
    )

    portfolio.append({"symbol": "XRPUSDT", "positionAmt": "-100.0"})

    emitter.handle_regime_flip("XRPUSDT", {"regime": "TREND_UP", "structural": True})

    assert len(close_calls) == 1
    assert close_calls[0]["symbol"] == "XRPUSDT"
    assert close_calls[0]["strategy_id"] == "md_amr"
    assert len(reject_calls) == 0


def test_ambiguous_strategy_fails_closed_no_close_emitted():
    """
    Symbol has multiple registered strategies: ["aurora", "mean_reversion"].

    Expected: no close is emitted. Instead, reject event via canonical helper.
    No silent default to "aurora".
    """
    close_calls: list = []
    reject_calls: list = []

    emitter, portfolio = _make_emitter(
        registry_owners=["aurora", "mean_reversion"],
        close_calls=close_calls,
        reject_calls=reject_calls,
    )

    portfolio.append({"symbol": "BTCUSDT", "positionAmt": "0.5"})

    emitter.handle_regime_flip("BTCUSDT", {"regime": "TREND_DOWN", "structural": True})

    assert len(close_calls) == 0
    assert len(reject_calls) == 1
    assert reject_calls[0]["reason_code"] == "REGIME_FLIP_STRATEGY_UNRESOLVABLE"
    assert reject_calls[0]["symbol"] == "BTCUSDT"
    assert reject_calls[0]["strategy_id"] == "UNRESOLVED"


def test_reduce_only_limit_close_uses_exit_limit_ttl_without_entry_ttl_rejection():
    """
    Regression guard for the current reduce_only LIMIT close contract.

    Close path must bypass entry-path tf_sec -> ttl_by_tf_sec lookup and instead
    use execution.exit_limit_ttl_ms when the close order type is LIMIT.
    """
    reject_calls: list = []
    emitted_payloads: list = []

    from apps.reference.domains.decision_making.intent.builder import IntentBuilder

    fsm = MagicMock()
    fsm.emit.side_effect = (
        lambda evt, payload=None, **kw: emitted_payloads.append((evt, payload))
    )
    clock = _make_clock()

    exec_pos_cfg = MagicMock()
    exec_pos_cfg.pending_entry_ttl.enabled = True
    exec_pos_cfg.pending_entry_ttl.ttl_by_tf_sec = {60: 120}
    exec_pos_cfg.pending_entry_ttl.reject_unknown_tf = True

    aurora_exec_cfg = MagicMock()
    aurora_exec_cfg.entry_order_type = "LIMIT"
    aurora_exec_cfg.entry_tif = "GTC"
    aurora_exec_cfg.exit_order_type = "LIMIT"
    aurora_exec_cfg.exit_tif = "GTC"
    aurora_exec_cfg.exit_limit_ttl_ms = 30_000

    config = MagicMock()
    config.domains.execution_position = exec_pos_cfg
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

    order_type, tif, valid_for_ms = builder._resolve_order_policy(
        symbol="BTCUSDT",
        strategy_id="aurora",
        side="SELL",
        rid="rid-test-close",
        reduce_only=True,
        tf_sec=None,
        why_chain=["regime_flip"],
    )

    assert len(reject_calls) == 0, (
        f"LIMIT + reduce_only=True should not trigger TTL rejection. "
        f"Got reject_calls={reject_calls}"
    )
    assert order_type == "LIMIT"
    assert tif == "GTC"
    assert valid_for_ms == 30_000
