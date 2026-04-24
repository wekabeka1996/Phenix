"""
Tests for ORDER-POLICY-01 reduce_only close path fix.

Root cause (runtime_21h forensic): IntentBuilder._resolve_order_policy always
read entry_order_type/entry_tif even for reduce_only close intents.  When the
strategy has entry_order_type=LIMIT but exit_order_type=MARKET (like md_amr),
the close payload was built with order_type=LIMIT and valid_for_ms=None.
The trade_intent_v1.json schema conditional requires valid_for_ms as integer
when order_type==LIMIT, causing FSM EMIT FAILED: 'None is not of type integer'.

Fix: _resolve_order_policy now reads exit_order_type/exit_tif for
reduce_only=True, falling back to entry fields for backward compatibility.
"""

import decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.decision_making.intent.builder import IntentBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exec_cfg(
    *,
    entry_order_type="LIMIT",
    entry_tif="GTX",
    exit_order_type=None,
    exit_tif=None,
    exit_limit_ttl_ms=None,
):
    return SimpleNamespace(
        entry_order_type=entry_order_type,
        entry_tif=entry_tif,
        exit_order_type=exit_order_type,
        exit_tif=exit_tif,
        exit_limit_ttl_ms=exit_limit_ttl_ms,
    )


def _make_config(exec_cfg, *, strategy_id="md_amr"):
    strat = SimpleNamespace(execution=exec_cfg)
    strategies = SimpleNamespace(**{strategy_id: strat})

    # Order capabilities
    caps = SimpleNamespace(
        supported_order_types=["LIMIT", "MARKET"],
        supported_tif=["GTC", "GTX", "IOC", "FOK"],
    )
    ep_cfg = SimpleNamespace(order_capabilities=caps)
    domains = SimpleNamespace(execution_position=ep_cfg)

    config = MagicMock()
    config.strategies = strategies
    config.domains = domains
    return config


def _make_builder(config) -> IntentBuilder:
    clock = MagicMock()
    clock.now_ms.return_value = 1700000000000
    clock.now_sec.return_value = 1700000000
    return IntentBuilder(
        logger=MagicMock(),
        fsm=MagicMock(),
        clock=clock,
        config=config,
        tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100,
                   "maker_preference": False},
        risk_budgets={"trade_cvar95_max_bps": 50,
                      "session_cvar95_max_bps": 100},
        safe_decimal_fn=lambda x, default: decimal.Decimal(
            x) if x else default,
        check_strategy_arbitration_fn=MagicMock(
            return_value={"allowed": True}),
        warmup_gate_fn=lambda **kw: False,
        emit_rejected_fn=MagicMock(),
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0, 600, 0.6, 0.9)),
        side_intent_window={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReduceOnlyOrderPolicy:
    """ORDER-POLICY-01: reduce_only close path must use exit_order_type."""

    def test_reduce_only_uses_exit_order_type_market(self):
        """md_amr config: entry=LIMIT/GTX, exit=MARKET/null.
        Close path must resolve to MARKET, not LIMIT."""
        exec_cfg = _make_exec_cfg(
            entry_order_type="LIMIT",
            entry_tif="GTX",
            exit_order_type="MARKET",
            exit_tif=None,
        )
        config = _make_config(exec_cfg, strategy_id="md_amr")
        builder = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="XRPUSDT",
            strategy_id="md_amr",
            side="SELL",
            rid="test-rid-001",
            tf_sec=None,
            reduce_only=True,
            why_chain=["test"],
        )

        assert order_type == "MARKET", (
            f"reduce_only close must use exit_order_type=MARKET, got {order_type}"
        )
        assert tif is None, (
            f"MARKET order must have tif=None, got {tif}"
        )
        assert valid_for_ms is None, (
            f"MARKET order must have valid_for_ms=None, got {valid_for_ms}"
        )

    def test_entry_path_still_uses_entry_order_type(self):
        """Entry path must NOT be affected by exit_order_type config."""
        exec_cfg = _make_exec_cfg(
            entry_order_type="LIMIT",
            entry_tif="GTX",
            exit_order_type="MARKET",
            exit_tif=None,
        )
        config = _make_config(exec_cfg, strategy_id="md_amr")

        # Mock pending_entry_ttl for LIMIT entry resolution
        pe_ttl = SimpleNamespace(
            enabled=True,
            ttl_by_tf_sec={900: 60},
            reject_unknown_tf=False,
        )
        config.domains.execution_position.pending_entry_ttl = pe_ttl

        builder = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="XRPUSDT",
            strategy_id="md_amr",
            side="BUY",
            rid="test-rid-002",
            tf_sec=900,
            reduce_only=False,
            why_chain=["test"],
        )

        assert order_type == "LIMIT", (
            f"entry path must use entry_order_type=LIMIT, got {order_type}"
        )
        assert tif == "GTX", (
            f"entry path must use entry_tif=GTX, got {tif}"
        )
        assert valid_for_ms == 60000, (
            f"LIMIT entry must have valid_for_ms=60000, got {valid_for_ms}"
        )

    def test_reduce_only_falls_back_to_entry_when_no_exit_config(self):
        """When exit_order_type is not set, close falls back to entry_order_type.
        For LIMIT fallback, reject because exit_limit_ttl_ms is also unset."""
        exec_cfg = _make_exec_cfg(
            entry_order_type="LIMIT",
            entry_tif="GTX",
            exit_order_type=None,
            exit_tif=None,
            exit_limit_ttl_ms=None,
        )
        config = _make_config(exec_cfg, strategy_id="aurora")
        builder = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="BTCUSDT",
            strategy_id="aurora",
            side="SELL",
            rid="test-rid-003",
            tf_sec=None,
            reduce_only=True,
            why_chain=["test"],
        )

        # Falls back to LIMIT, but no exit_limit_ttl_ms → reject
        assert order_type is None, (
            "reduce_only LIMIT without exit_limit_ttl_ms must reject"
        )

    def test_reduce_only_limit_with_exit_ttl_succeeds(self):
        """reduce_only LIMIT close with exit_limit_ttl_ms set must pass."""
        exec_cfg = _make_exec_cfg(
            entry_order_type="LIMIT",
            entry_tif="GTX",
            exit_order_type="LIMIT",
            exit_tif="GTC",
            exit_limit_ttl_ms=30000,
        )
        config = _make_config(exec_cfg, strategy_id="aurora")
        builder = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="BTCUSDT",
            strategy_id="aurora",
            side="SELL",
            rid="test-rid-004",
            tf_sec=None,
            reduce_only=True,
            why_chain=["test"],
        )

        assert order_type == "LIMIT", f"Expected LIMIT, got {order_type}"
        assert tif == "GTC", f"Expected GTC, got {tif}"
        assert valid_for_ms == 30000, f"Expected 30000, got {valid_for_ms}"

    def test_reduce_only_market_entry_market_no_exit_config(self):
        """mean_reversion: entry=MARKET, no exit config.
        Close should fall back to MARKET."""
        exec_cfg = _make_exec_cfg(
            entry_order_type="MARKET",
            entry_tif=None,
            exit_order_type=None,
            exit_tif=None,
        )
        config = _make_config(exec_cfg, strategy_id="mean_reversion")
        builder = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="DOGEUSDT",
            strategy_id="mean_reversion",
            side="SELL",
            rid="test-rid-005",
            tf_sec=None,
            reduce_only=True,
            why_chain=["test"],
        )

        assert order_type == "MARKET", f"Expected MARKET, got {order_type}"
        assert tif is None, f"Expected None, got {tif}"
        assert valid_for_ms is None, f"Expected None, got {valid_for_ms}"

    def test_no_reject_emitted_for_valid_market_close(self):
        """Verify no rejection event emitted for valid MARKET close."""
        exec_cfg = _make_exec_cfg(
            entry_order_type="LIMIT",
            entry_tif="GTX",
            exit_order_type="MARKET",
            exit_tif=None,
        )
        config = _make_config(exec_cfg, strategy_id="md_amr")
        builder = _make_builder(config)

        builder._resolve_order_policy(
            symbol="BNBUSDT",
            strategy_id="md_amr",
            side="SELL",
            rid="test-rid-006",
            tf_sec=None,
            reduce_only=True,
            why_chain=["test"],
        )

        builder._emit_rejected.assert_not_called()
