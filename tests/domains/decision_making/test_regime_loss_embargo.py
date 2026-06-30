from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
)
from apps.reference.domains.decision_making.gates.regime_loss_embargo import (
    RegimeLossEmbargo,
)
from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway


def _make_policy(
    *,
    enabled: bool = True,
    threshold: float = 0.0,
    fee_only_close_policy: str = "ignore",
):
    symbol_states = {}
    config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                regime_loss_embargo=SimpleNamespace(
                    enabled=enabled,
                    min_loss_threshold_net=threshold,
                    fee_only_close_policy=fee_only_close_policy,
                )
            )
        )
    )
    clock = MagicMock()
    clock.now_ms.return_value = 1_700_000_000_000
    logger = MagicMock()
    return RegimeLossEmbargo(
        config=config,
        symbol_states=symbol_states,
        clock=clock,
        logger=logger,
    ), symbol_states, clock


def test_epoch_minted_on_first_regime_and_unchanged_on_heartbeat() -> None:
    policy, states, _clock = _make_policy()

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    first_epoch = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=222, ts_ms=200)
    assert states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"] == first_epoch


def test_epoch_changes_only_when_changed_true() -> None:
    policy, states, _clock = _make_policy()

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    first_epoch = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_regime(symbol="BTCUSDT", changed=True,
                     bar_close_ts_ms=333, ts_ms=300)

    assert states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"] != first_epoch


def test_current_epoch_losing_close_latches_symbol() -> None:
    policy, states, _clock = _make_policy(threshold=0.05)

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    epoch_ref = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=epoch_ref,
        close_ts_ms=222,
        realized_pnl_net=-0.25,
        realized_pnl=-0.20,
        fees=0.05,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    block = policy.get_entry_block("BTCUSDT")
    assert block["blocked"] is True
    assert block["block_reason"] == RegimeLossEmbargo.LOSS_LATCHED
    assert block["trigger_pnl_net"] == -0.25


def test_fee_only_close_does_not_latch_when_policy_ignore() -> None:
    policy, states, _clock = _make_policy(
        threshold=0.0, fee_only_close_policy="ignore")

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    epoch_ref = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=epoch_ref,
        close_ts_ms=222,
        realized_pnl_net=-0.25,
        realized_pnl=0.0,
        fees=0.25,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    assert policy.get_entry_block("BTCUSDT") == {"blocked": False}


def test_fee_only_close_latches_when_policy_latch() -> None:
    policy, states, _clock = _make_policy(
        threshold=0.0, fee_only_close_policy="latch")

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    epoch_ref = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=epoch_ref,
        close_ts_ms=222,
        realized_pnl_net=-0.25,
        realized_pnl=0.0,
        fees=0.25,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    block = policy.get_entry_block("BTCUSDT")
    assert block["blocked"] is True
    assert block["block_reason"] == RegimeLossEmbargo.LOSS_LATCHED


def test_loss_below_threshold_does_not_latch() -> None:
    policy, states, _clock = _make_policy(threshold=0.25)

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    epoch_ref = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=epoch_ref,
        close_ts_ms=222,
        realized_pnl_net=-0.24,
        realized_pnl=-0.12,
        fees=0.12,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    assert policy.get_entry_block("BTCUSDT") == {"blocked": False}


def test_unresolved_close_pnl_latches_unproven_not_profit() -> None:
    policy, states, _clock = _make_policy(threshold=0.05)

    policy.on_regime(symbol="BTCUSDT", changed=False, bar_close_ts_ms=111, ts_ms=100)
    epoch_ref = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=epoch_ref,
        close_ts_ms=222,
        realized_pnl_net=None,
        realized_pnl=None,
        fees=None,
        close_reason="CLOSE",
    )

    block = policy.get_entry_block("BTCUSDT")
    assert block["blocked"] is True
    assert block["block_reason"] == RegimeLossEmbargo.CAUSAL_CONTEXT_UNPROVEN
    assert block["trigger_pnl_net"] is None


def test_previous_epoch_losing_close_does_not_latch_current_epoch() -> None:
    policy, states, _clock = _make_policy()

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    old_epoch = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_regime(symbol="BTCUSDT", changed=True,
                     bar_close_ts_ms=222, ts_ms=200)

    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=old_epoch,
        close_ts_ms=333,
        realized_pnl_net=-0.5,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    assert policy.get_entry_block("BTCUSDT") == {"blocked": False}


def test_missing_entry_epoch_causes_unproven_block_when_enabled() -> None:
    policy, states, _clock = _make_policy()

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=None,
        close_ts_ms=222,
        realized_pnl_net=-0.5,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    block = policy.get_entry_block("BTCUSDT")
    assert block["blocked"] is True
    assert block["block_reason"] == RegimeLossEmbargo.CAUSAL_CONTEXT_UNPROVEN
    assert block["trigger_pnl_net"] is None


def test_missing_current_epoch_causes_fail_closed_block_when_enabled() -> None:
    policy, _states, _clock = _make_policy()

    block = policy.get_entry_block("BTCUSDT")
    assert block["blocked"] is True
    assert block["block_reason"] == RegimeLossEmbargo.CAUSAL_CONTEXT_UNPROVEN


def test_next_epoch_clears_loss_latch_and_unproven_block() -> None:
    policy, states, _clock = _make_policy()

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    epoch_ref = states["BTCUSDT"]["regime_loss_embargo"]["stable_regime_epoch_ref"]
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=epoch_ref,
        close_ts_ms=222,
        realized_pnl_net=-0.5,
        close_reason="POSITION_CLOSED_DETECTED",
    )
    assert policy.get_entry_block("BTCUSDT")["blocked"] is True

    policy.on_regime(symbol="BTCUSDT", changed=True,
                     bar_close_ts_ms=333, ts_ms=300)
    assert policy.get_entry_block("BTCUSDT") == {"blocked": False}

    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=None,
        close_ts_ms=444,
        realized_pnl_net=-0.5,
        close_reason="POSITION_CLOSED_DETECTED",
    )
    assert policy.get_entry_block(
        "BTCUSDT")["block_reason"] == RegimeLossEmbargo.CAUSAL_CONTEXT_UNPROVEN

    policy.on_regime(symbol="BTCUSDT", changed=True,
                     bar_close_ts_ms=555, ts_ms=500)
    assert policy.get_entry_block("BTCUSDT") == {"blocked": False}


def test_enabled_false_disables_all_state_mutation_and_reports_not_blocked() -> None:
    policy, states, _clock = _make_policy(enabled=False)

    policy.on_regime(symbol="BTCUSDT", changed=False,
                     bar_close_ts_ms=111, ts_ms=100)
    policy.on_position_closed(
        symbol="BTCUSDT",
        entry_regime_epoch_ref=None,
        close_ts_ms=222,
        realized_pnl_net=-0.5,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    assert states == {}
    assert policy.get_entry_block("BTCUSDT") == {"blocked": False}


def test_strategy_gateway_rejects_fresh_entry_when_embargo_blocks() -> None:
    dm = MagicMock()
    dm._clock = MagicMock()
    dm._clock.now_ms.return_value = 1_700_000_000_000
    dm.logger = MagicMock()
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                risk_skew=SimpleNamespace(
                    until_refresh_max_hold_sec=300, until_refresh_retry_sec=30),
            ),
            risk_management=SimpleNamespace(
                trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0),
            ),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                enabled=True,
                mode="runtime",
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0
                ),
            ),
        ),
        system=SimpleNamespace(market_data=None),
    )
    dm.symbol_states = {"BTCUSDT": {"risk_skew_guard": {}}}
    dm._check_strategy_arbitration.return_value = {"allowed": True}
    dm._emit_trade_intent_rejected = MagicMock()
    dm._record_blocked_intent = MagicMock()
    dm._regime_loss_embargo = MagicMock()
    dm._regime_loss_embargo.get_entry_block.return_value = {
        "blocked": True,
        "block_reason": RegimeLossEmbargo.LOSS_LATCHED,
        "details": {
            "block_reason": RegimeLossEmbargo.LOSS_LATCHED,
            "epoch_ref": "stable_epoch:BTCUSDT:1700000000000",
            "latched_ts_ms": 1700000000001,
            "trigger_pnl_net": -0.5,
            "trigger_close_reason": "POSITION_CLOSED_DETECTED",
        },
    }

    gw = StrategyGateway(dm)
    msg = Message(
        op="EVT",
        verb="STRATEGY_SIGNAL_PRODUCED",
        src="feature_engineering",
        dst="decision_making",
        why="test",
        pld={
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "rid": "rid-1",
            "ts_ms": 1700000000000,
            "tf_sec": 300,
            "intent_kind": "ENTRY",
            "readiness": {"warmup_ok": True},
        },
    )

    gw.process_signal(msg)

    dm._emit_trade_intent_rejected.assert_called_once()
    reject_call = dm._emit_trade_intent_rejected.call_args.kwargs
    assert reject_call["reason_code"] == NormalizedRejectReasons.REGIME_LOSS_EMBARGO_BLOCKED
    assert reject_call["details"]["block_reason"] == RegimeLossEmbargo.LOSS_LATCHED


def test_strategy_gateway_reduce_only_path_bypasses_embargo() -> None:
    dm = MagicMock()
    dm._clock = MagicMock()
    dm._clock.now_ms.return_value = 1_700_000_000_000
    dm.logger = MagicMock()
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                risk_skew=SimpleNamespace(
                    until_refresh_max_hold_sec=300, until_refresh_retry_sec=30),
            ),
            risk_management=SimpleNamespace(
                trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0),
            ),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
        ),
        strategies=SimpleNamespace(
            md_amr=SimpleNamespace(decision=SimpleNamespace(
                retry_max_count=5, retry_backoff_factor=2.0)),
            aurora=SimpleNamespace(decision=SimpleNamespace(
                retry_max_count=5, retry_backoff_factor=2.0)),
        ),
        system=SimpleNamespace(market_data=None),
    )
    dm.symbol_states = {"BTCUSDT": {"risk_skew_guard": {}}}
    dm._check_strategy_arbitration.return_value = {"allowed": True}
    dm._emit_trade_intent_rejected = MagicMock()
    dm._record_blocked_intent = MagicMock()
    dm._emit_reduce_only_close = MagicMock(return_value=True)
    dm._regime_loss_embargo = MagicMock()

    gw = StrategyGateway(dm)
    msg = Message(
        op="EVT",
        verb="STRATEGY_SIGNAL_PRODUCED",
        src="feature_engineering",
        dst="decision_making",
        why="test",
        pld={
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "rid": "rid-1",
            "ts_ms": 1700000000000,
            "intent_kind": "FULL_CLOSE",
            "readiness": {"warmup_ok": True},
            "trace": {
                "dir_score": 0.4,
                "thr_buy": 0.2,
                "thr_sell": 0.2,
                "w_raw": {"d1": 1.0, "h1": 1.0, "m30": 1.0, "m15": 1.0},
                "w_norm": {"d1": 0.25, "h1": 0.25, "m30": 0.25, "m15": 0.25},
                "qty_base": 1.0,
                "qty_new": 1.0,
                "conf_ratio": 1.0,
            },
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": False,
            },
            "exit_reason_code": "MD_AMR_EXIT",
        },
    )

    gw.process_signal(msg)

    dm._emit_reduce_only_close.assert_called_once()
    dm._emit_trade_intent_rejected.assert_not_called()
    dm._regime_loss_embargo.get_entry_block.assert_not_called()
