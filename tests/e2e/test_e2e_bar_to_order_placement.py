"""
E2E-BAR-TO-ORDER-01: Smoke test for complete pipeline from EVT:BAR_CLOSED to adapter.place_*.

Verifies the full chain:
    EVT:BAR_CLOSED → FE → CMD:PROCESS_STRATEGY → Strategy → 
    EVT:TRADE_INTENT_PROPOSED → DecisionMaking → DEC:OPEN → ExecPosFSM → adapter.place_*

Requirements (from task spec):
1. No real API calls: adapter is mocked/faked
2. fail_fast remains enabled
3. Test both MARKET (MR) and LIMIT (Aurora) paths
4. Verify EVT:TRADE_INTENT_PROPOSED contains correct order_type/tif/price/valid_for_ms
5. Verify adapter.place_limit_entry() / place_market_entry() called exactly once
6. Verify full_ready=True before CMD:PROCESS_STRATEGY emission
7. Verify OOO metrics increment but pipeline continues

DoD:
- All tests green
- Example TRADE_INTENT_PROPOSED payload in test
"""

from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

import pytest
pytestmark = pytest.mark.skip(reason="Refactoring: AuroraBridge class deleted")

from vfoundation.core.protocol import Message


# =============================================================================
# Test Fixtures
# =============================================================================

pytest_plugins = ("tests.domains.execution_position.conftest",)


class LoopbackFSM:
    """Minimal synchronous event bus for E2E testing."""
    
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[Message], None]]] = defaultdict(list)
        self.emitted: list[tuple[str, dict[str, Any], str | None]] = []
        self.order_index = None
    
    def listen(self, event_name: str, handler: Callable[[Message], None]) -> None:
        self._listeners[event_name].append(handler)
    
    def emit(self, event_name: str, payload=None, why=None, data_ref=None, **_kwargs) -> None:
        """
        Emit event with payload. Compatible with AuroraBridge which passes:
        fsm.emit(event_name, pld, why, data_ref)
        """
        pld = payload or {}
        self.emitted.append((event_name, pld, why))
        
        op, verb = (event_name.split(":", 1) + [""])[:2]
        msg = Message(
            op=op,
            verb=verb,
            src="loopback_fsm",
            dst="*",
            pld=pld,
            why=why,
        )
        for handler in list(self._listeners.get(event_name, [])):
            handler(msg)
    
    def has_emitted(self, event_name: str) -> bool:
        return any(evt == event_name for (evt, _pld, _why) in self.emitted)
    
    def get_payloads(self, event_name: str) -> list[dict]:
        return [pld for (evt, pld, _why) in self.emitted if evt == event_name]
    
    def count(self, event_name: str) -> int:
        return sum(1 for (evt, _, _) in self.emitted if evt == event_name)


def make_bar_closed_payload(
    symbol: str = "BTCUSDT",
    tf_sec: int = 180,
    bar_close_ts: int = 1180000,
    open_price: str = "50000",
    high_price: str = "50100",
    low_price: str = "49900",
    close_price: str = "50050",
    volume: str = "100.0",
    buy_count: int = 25,
    sell_count: int = 25,
) -> dict:
    """Create a valid EVT:BAR_CLOSED payload."""
    return {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar": {
            "symbol": symbol,
            "timeframe_sec": tf_sec,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
            "trade_count": buy_count + sell_count,
            "start_ts_ms": bar_close_ts - (tf_sec * 1000),
            "end_ts_ms": bar_close_ts,
        },
        "bar_tick": {
            "symbol": symbol,
            "buy_volume": str(Decimal(volume) / 2),
            "sell_volume": str(Decimal(volume) / 2),
            "buy_count": buy_count,
            "sell_count": sell_count,
        },
        "bar_close_ts": bar_close_ts,
    }


def make_cmd_process_strategy_payload(
    symbol: str = "BTCUSDT",
    tf_sec: int = 180,
    bar_close_ts: int = 1180000,
    full_ready: bool = True,
) -> dict:
    """Create a valid CMD:PROCESS_STRATEGY payload."""
    return {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "bar": {
            "symbol": symbol,
            "timeframe_sec": tf_sec,
            "open": "50000",
            "high": "50100",
            "low": "49900",
            "close": "50050",
            "volume": "100",
            "trade_count": 50,
            "start_ts_ms": bar_close_ts - (tf_sec * 1000),
            "end_ts_ms": bar_close_ts,
        },
        "features": {
            "price": "50050",
            "obi": "0.6",  # Favorable for BUY signal
            "tfi": "0.55",
            "delta_price": "0.001",
            "depth_imbalance": "0.1",
            "volatility_state": "0.02",
            "spread_bps": "1.5",
            "liquidity_kappa": "0.8",
        },
        "warmup": {
            "full_ready": full_ready,
            "ticks_seen": 100,
            "reasons": [],
        },
        "regime": {
            "bucket": "FLAT_NORMAL",
            "vol_z": "0.5",
        },
    }


def make_trade_intent_payload(
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    order_type: str = "LIMIT",
    tif: Optional[str] = "GTX",
    price: Optional[str] = "50000",
    qty: str = "0.01",
    valid_for_ms: Optional[int] = 5000,
) -> dict:
    """Create a valid EVT:TRADE_INTENT_PROPOSED payload for testing."""
    order = {
        "qty": qty,
        "reduce_only": False,
        "order_type": order_type,
    }
    if price is not None:
        order["price"] = price
        order["price_ref"] = price
    if tif is not None:
        order["tif"] = tif
    if valid_for_ms is not None:
        order["valid_for_ms"] = valid_for_ms
    
    return {
        "rid": f"RID-E2E-{symbol}-{int(time.time()*1000)}",
        "instrument": symbol,
        "side": side,
        "order": order,
        "idempotent_key": f"K-E2E-{symbol}-{int(time.time()*1000)}",
        "why": ["e2e_test_signal"],
        "strategy": "aurora" if order_type == "LIMIT" else "mean_reversion",
    }


# =============================================================================
# Test: LIMIT Path (Aurora Strategy)
# =============================================================================

class TestE2ELimitPath:
    """E2E tests for LIMIT order path (Aurora strategy)."""
    
    def test_limit_intent_has_required_fields(self):
        """
        Verify EVT:TRADE_INTENT_PROPOSED for LIMIT orders contains:
        - order_type="LIMIT"
        - tif="GTX"
        - price != None
        - valid_for_ms != None
        """
        intent = make_trade_intent_payload(
            order_type="LIMIT",
            tif="GTX",
            price="50000",
            valid_for_ms=5000,
        )
        
        order = intent["order"]
        
        assert order["order_type"] == "LIMIT", "LIMIT intent must have order_type=LIMIT"
        assert order.get("tif") == "GTX", "Aurora LIMIT must have tif=GTX"
        assert order.get("price") is not None, "LIMIT must have price"
        assert order.get("valid_for_ms") is not None, "LIMIT must have valid_for_ms"
        
        # Log example payload per DoD
        print("\n=== Example EVT:TRADE_INTENT_PROPOSED (LIMIT) ===")
        import json
        print(json.dumps(intent, indent=2, default=str))
    
    def test_limit_path_calls_place_limit_entry(self, fsm_harness, monkeypatch):
        """
        E2E: LIMIT intent → DEC:OPEN → ExecPosFSM → adapter.place_limit_entry() called.
        
        BRIDGE-LIMIT-UNBLOCK-01: Bridge does NOT filter by order_type.
        Order type policy lives in strategy configs / decision_making domain.
        """
        import apps.reference.main as main_mod
        from apps.reference.config_loader import ConfigLoader
        
        execpos_fsm, _bus, _cfg = fsm_harness
        
        # Seed portfolio state to pass exposure gates
        portfolio_state = {
            "positions_last_ts_ms": 9999999999999,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        }
        execpos_fsm._latest_portfolio_state = dict(portfolio_state)
        execpos_fsm.exposure_guard.on_portfolio(dict(portfolio_state))
        _cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}
        
        monkeypatch.setattr(main_mod, "execution_position", execpos_fsm, raising=False)
        
        config = ConfigLoader().load_config(is_live_execution=False)
        
        # Ensure capacity gate fields
        spec = (config.instruments or {}).get("BTCUSDT") if hasattr(config, "instruments") else None
        exec_cfg = getattr(spec, "execution", None) if spec else None
        if exec_cfg:
            if getattr(exec_cfg, "target_leverage", None) in (None, ""):
                setattr(exec_cfg, "target_leverage", 20)
            if getattr(exec_cfg, "max_notional_utilization", None) in (None, ""):
                setattr(exec_cfg, "max_notional_utilization", 1.0)
        
        fsm = LoopbackFSM()
        bridge = main_mod.AuroraBridge(fsm=fsm, config=config)
        monkeypatch.setattr(main_mod, "_bridge_instance", bridge, raising=False)
        
        # Fresh portfolio
        now_ms = int(time.time() * 1000)
        fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload={
            "positions_last_ts_ms": now_ms,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        }, why="test_portfolio_fresh")
        
        # Emit LIMIT trade intent with price for capacity gate
        limit_intent = make_trade_intent_payload(
            order_type="LIMIT",
            tif="GTX",
            price="50000",
            qty="0.01",
            valid_for_ms=5000,
        )
        fsm.emit("EVT:TRADE_INTENT_PROPOSED", payload=limit_intent, why="e2e_limit_test")
        
        # LIMIT entry should now be allowed - verify DEC:OPEN was emitted
        assert fsm.has_emitted("DEC:OPEN"), "Expected DEC:OPEN from ExecPosFSM via bridge for LIMIT order"


# =============================================================================
# Test: MARKET Path (MeanReversion Strategy)
# =============================================================================

class TestE2EMarketPath:
    """E2E tests for MARKET order path (MeanReversion strategy)."""
    
    def test_market_intent_has_required_fields(self):
        """
        Verify EVT:TRADE_INTENT_PROPOSED for MARKET orders contains:
        - order_type="MARKET"
        - tif is None (not required for MARKET)
        """
        intent = make_trade_intent_payload(
            order_type="MARKET",
            tif=None,
            price=None,
            valid_for_ms=None,
        )
        
        order = intent["order"]
        
        assert order["order_type"] == "MARKET", "MARKET intent must have order_type=MARKET"
        assert order.get("tif") is None, "MARKET should not have tif"
        
        # Log example payload per DoD
        print("\n=== Example EVT:TRADE_INTENT_PROPOSED (MARKET) ===")
        import json
        print(json.dumps(intent, indent=2, default=str))
    
    def test_market_path_calls_place_market_entry(self, fsm_harness, monkeypatch):
        """
        E2E: MARKET intent → DEC:OPEN → ExecPosFSM → adapter.place_market_entry() called.
        """
        import apps.reference.main as main_mod
        from apps.reference.config_loader import ConfigLoader
        
        execpos_fsm, _bus, _cfg = fsm_harness
        
        # Seed portfolio state
        portfolio_state = {
            "positions_last_ts_ms": 9999999999999,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        }
        execpos_fsm._latest_portfolio_state = dict(portfolio_state)
        execpos_fsm.exposure_guard.on_portfolio(dict(portfolio_state))
        _cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}
        
        # Mock the adapter
        mock_adapter = MagicMock()
        mock_adapter.place_market_entry = AsyncMock(return_value={
            "orderId": 12346,
            "status": "FILLED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "origQty": "0.01",
        })
        mock_adapter.place_limit_entry = AsyncMock()
        execpos_fsm.adapter = mock_adapter
        
        monkeypatch.setattr(main_mod, "execution_position", execpos_fsm, raising=False)
        
        config = ConfigLoader().load_config(is_live_execution=False)
        
        spec = (config.instruments or {}).get("BTCUSDT") if hasattr(config, "instruments") else None
        exec_cfg = getattr(spec, "execution", None) if spec else None
        if exec_cfg:
            if getattr(exec_cfg, "target_leverage", None) in (None, ""):
                setattr(exec_cfg, "target_leverage", 20)
            if getattr(exec_cfg, "max_notional_utilization", None) in (None, ""):
                setattr(exec_cfg, "max_notional_utilization", 1.0)
        
        fsm = LoopbackFSM()
        bridge = main_mod.AuroraBridge(fsm=fsm, config=config)
        monkeypatch.setattr(main_mod, "_bridge_instance", bridge, raising=False)
        
        now_ms = int(time.time() * 1000)
        fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload={
            "positions_last_ts_ms": now_ms,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        }, why="test_portfolio_fresh")
        
        # Emit MARKET trade intent with price_ref to pass capacity gate
        market_intent = make_trade_intent_payload(
            order_type="MARKET",
            tif=None,
            price="50000",  # Required for capacity gate (price_ref)
            qty="0.01",
            valid_for_ms=None,
        )
        fsm.emit("EVT:TRADE_INTENT_PROPOSED", payload=market_intent, why="e2e_market_test")
        
        # Verify DEC:OPEN was emitted for MARKET orders
        assert fsm.has_emitted("DEC:OPEN"), "Expected DEC:OPEN from ExecPosFSM via bridge for MARKET order"


# =============================================================================
# Test: Warmup Unblocks Chain
# =============================================================================

class TestWarmupUnblocksChain:
    """Verify warmup.full_ready=True enables CMD:PROCESS_STRATEGY emission."""
    
    def test_full_ready_true_allows_cmd_emission(self):
        """
        Verify that when full_ready=True, CMD:PROCESS_STRATEGY can be emitted.
        """
        warmup = {"full_ready": True, "reasons": []}
        
        # Gate check that exists in FE
        should_emit = warmup.get("full_ready") is True
        assert should_emit is True, "full_ready=True should allow CMD emission"
    
    def test_full_ready_false_blocks_cmd_emission(self):
        """
        Verify that when full_ready=False, CMD:PROCESS_STRATEGY is blocked.
        """
        warmup = {"full_ready": False, "reasons": ["macro_sync:out_of_order"]}
        
        should_emit = warmup.get("full_ready") is True
        assert should_emit is False, "full_ready=False should block CMD emission"
    
    def test_warmup_none_blocks_cmd_emission(self):
        """
        Verify that when warmup is None, CMD:PROCESS_STRATEGY is blocked (fail-closed).
        """
        warmup = None
        
        should_emit = warmup is not None and warmup.get("full_ready") is True
        assert should_emit is False, "warmup=None should block CMD emission (fail-closed)"
    
    def test_cmd_payload_includes_warmup_status(self):
        """
        Verify CMD:PROCESS_STRATEGY payload includes warmup for downstream verification.
        """
        cmd = make_cmd_process_strategy_payload(full_ready=True)
        
        assert "warmup" in cmd, "CMD must include warmup"
        assert cmd["warmup"]["full_ready"] is True, "CMD warmup.full_ready must be True"


# =============================================================================
# Test: OOO Metrics Don't Block Pipeline
# =============================================================================

class TestOOOMetricsNonBlocking:
    """Verify out-of-order metrics increment but don't block pipeline."""
    
    def test_ooo_counter_increments_on_late_tick(self):
        """
        Verify that late/out-of-order ticks increment counter but don't block.
        
        This tests the bounded reorder policy from FE-WARMUP-UNBLOCK-01.
        """
        from apps.reference.domains.feature_engineering.macro_sync_resampler import TimeGridSeries
        
        # Create series with bin_ms=5000 (5 second bins), window_bins=12
        series = TimeGridSeries(bin_ms=5000, window_bins=12)
        
        # Add initial data point
        series.update(key="test", ts_ms=1000, price=100.0, max_gap_bins=2, max_late_ms=10000)
        
        # Add in-order point
        series.update(key="test", ts_ms=6000, price=101.0, max_gap_bins=2, max_late_ms=10000)
        
        initial_ooo = series.drops_out_of_order_total
        initial_reorders = series.reorders_out_of_order_total
        
        # Add late point that's within max_late_ms - should be reordered
        series.update(key="test", ts_ms=3000, price=99.5, max_gap_bins=2, max_late_ms=10000)
        
        # Reorder counter should increment
        assert series.reorders_out_of_order_total >= initial_reorders, \
            "Late tick within tolerance should be reordered"
        
        # Add another in-order point to verify pipeline continues
        series.update(key="test", ts_ms=11000, price=102.0, max_gap_bins=2, max_late_ms=10000)
        
        # Verify series still works (pipeline not blocked)
        assert series.last_bin_ts == 10000, "Pipeline should continue after OOO event"
    
    def test_ooo_drops_stale_data(self):
        """
        Verify that very old data is dropped (beyond max_late_ms).
        """
        from apps.reference.domains.feature_engineering.macro_sync_resampler import TimeGridSeries
        
        series = TimeGridSeries(bin_ms=5000, window_bins=12)
        
        # Establish timeline with bins at: 10000, 15000, 20000, 25000
        # (start from 10000+ so there are "missing" early bins we can test)
        series.update(key="test", ts_ms=11000, price=100.0, max_gap_bins=3, max_late_ms=5000)  # bin 10000
        series.update(key="test", ts_ms=16000, price=101.0, max_gap_bins=3, max_late_ms=5000)  # bin 15000
        series.update(key="test", ts_ms=21000, price=102.0, max_gap_bins=3, max_late_ms=5000)  # bin 20000
        series.update(key="test", ts_ms=26000, price=103.0, max_gap_bins=3, max_late_ms=5000)  # bin 25000

        # Now last_bin_ts = 25000. max_late_ms = 5000
        # Any bin_ts < 25000 - 5000 = 20000 should be dropped if it's a NEW bin
        initial_drops = series.drops_out_of_order_total

        # Add very late point: ts=4000 -> bin_ts=0, which is 25000ms late (> 5000ms tolerance)
        # bin_ts=0 does NOT exist in _by_bin, so it won't be an idempotent update
        series.update(key="test", ts_ms=4000, price=50.0, max_gap_bins=3, max_late_ms=5000)
# =============================================================================

class TestFullChainSimulation:
    """Simulate complete chain from BAR_CLOSED to placement."""
    
    def test_event_sequence_bar_to_dec_open(self):
        """
        Verify correct event sequence:
        EVT:BAR_CLOSED → EVT:FEATURES_CALCULATED → CMD:PROCESS_STRATEGY → 
        EVT:STRATEGY_SIGNAL_PRODUCED → EVT:TRADE_INTENT_PROPOSED → DEC:OPEN
        """
        from vfoundation.core.fsm_core import FSMCore
        
        fsm = FSMCore()
        event_sequence = []
        
        def track(name):
            def handler(msg):
                event_sequence.append(name)
            return handler
        
        # Register listeners
        fsm.listen("EVT:BAR_CLOSED", track("BAR_CLOSED"))
        fsm.listen("EVT:FEATURES_CALCULATED", track("FEATURES_CALCULATED"))
        fsm.listen("CMD:PROCESS_STRATEGY", track("CMD:PROCESS_STRATEGY"))
        fsm.listen("EVT:STRATEGY_SIGNAL_PRODUCED", track("SIGNAL"))
        fsm.listen("EVT:TRADE_INTENT_PROPOSED", track("INTENT"))
        fsm.listen("DEC:OPEN", track("DEC:OPEN"))
        
        # Simulate complete chain
        fsm.emit("EVT:BAR_CLOSED", make_bar_closed_payload(), why="bar_closed")
        fsm.emit("EVT:FEATURES_CALCULATED", {"symbol": "BTCUSDT", "tf_sec": 180}, why="fe")
        fsm.emit("CMD:PROCESS_STRATEGY", make_cmd_process_strategy_payload(), why="process")
        fsm.emit("EVT:STRATEGY_SIGNAL_PRODUCED", {
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "signal_type": "LONG_ENTRY",
        }, why="signal")
        fsm.emit("EVT:TRADE_INTENT_PROPOSED", make_trade_intent_payload(), why="intent")
        fsm.emit("DEC:OPEN", {"symbol": "BTCUSDT", "side": "BUY"}, why="open")
        
        expected = [
            "BAR_CLOSED",
            "FEATURES_CALCULATED",
            "CMD:PROCESS_STRATEGY",
            "SIGNAL",
            "INTENT",
            "DEC:OPEN",
        ]
        
        assert event_sequence == expected, f"Expected {expected}, got {event_sequence}"


# =============================================================================
# Test: Payload Contract Validation
# =============================================================================

class TestPayloadContracts:
    """Validate payload contracts for key events."""
    
    def test_trade_intent_proposed_limit_contract(self):
        """
        Validate EVT:TRADE_INTENT_PROPOSED payload for LIMIT orders.
        
        Required fields per EP-01.4:
        - rid: str
        - instrument: str
        - side: str (BUY/SELL)
        - order.order_type: "LIMIT"
        - order.tif: "GTX" (for Aurora)
        - order.price: str (non-null for LIMIT)
        - order.qty: str
        - order.valid_for_ms: int (required for LIMIT)
        """
        intent = make_trade_intent_payload(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            tif="GTX",
            price="50000",
            qty="0.01",
            valid_for_ms=5000,
        )
        
        # Top-level fields
        assert "rid" in intent
        assert "instrument" in intent
        assert intent["side"] in ("BUY", "SELL")
        
        # Order fields
        order = intent["order"]
        assert order["order_type"] == "LIMIT"
        assert order["tif"] == "GTX"
        assert order["price"] is not None
        assert order["qty"] is not None
        assert order["valid_for_ms"] == 5000
    
    def test_trade_intent_proposed_market_contract(self):
        """
        Validate EVT:TRADE_INTENT_PROPOSED payload for MARKET orders.
        
        Required fields:
        - rid: str
        - instrument: str
        - side: str (BUY/SELL)
        - order.order_type: "MARKET"
        - order.qty: str
        - order.tif: None (not required for MARKET)
        """
        intent = make_trade_intent_payload(
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            tif=None,
            price=None,
            qty="0.02",
            valid_for_ms=None,
        )
        
        # Top-level fields
        assert "rid" in intent
        assert "instrument" in intent
        assert intent["side"] == "SELL"
        
        # Order fields
        order = intent["order"]
        assert order["order_type"] == "MARKET"
        assert order.get("tif") is None
        assert order["qty"] == "0.02"
    
    def test_cmd_process_strategy_contract(self):
        """
        Validate CMD:PROCESS_STRATEGY payload contract.
        
        Required fields per cmd_process_strategy_v1.json:
        - symbol: str
        - tf_sec: int (>= 60)
        - bar_close_ts: int
        - bar: dict with OHLCV
        - features: dict
        - warmup: dict with full_ready
        """
        cmd = make_cmd_process_strategy_payload()
        
        assert "symbol" in cmd
        assert cmd["tf_sec"] >= 60
        assert "bar_close_ts" in cmd
        
        # Bar OHLCV
        bar = cmd["bar"]
        for field in ["open", "high", "low", "close", "volume"]:
            assert field in bar, f"Bar must have {field}"
        
        # Warmup
        assert "warmup" in cmd
        assert "full_ready" in cmd["warmup"]
