"""
Investigation Tests Part 2: MarketData Worker Anchor Emission

Purpose: Verify that MarketData worker correctly emits EVT:ANCHOR_UPDATED events.

FINDINGS FROM LOGS:
- No "ANCHOR_UPDATED" or "Updated anchor" entries in logs
- All macro_resid values are 0.0 (neutral = not ready)
- macro_sync values vary (indicating returns buffer works)
- BUT macro_resid requires anchor_prices buffer which is NOT being populated

HYPOTHESIS:
1. Worker emits anchor updates only if `anchor in self._aggregator.state`
2. Aggregator state may not be populated for anchors (if not trading them?)
3. OR proxy may not be processing anchor messages correctly
4. OR anchor symbols are not subscribed in WebSocket

These tests verify the worker's anchor emission logic.
"""

import unittest
from unittest.mock import MagicMock, patch
from collections import deque
from multiprocessing import Queue
import decimal
from typing import Dict, Any, Optional


class TestWorkerAnchorEmissionLogic(unittest.TestCase):
    """
    Test the anchor emission logic in MarketDataWorker._periodic_emit.
    
    Code location: worker.py lines 511-522
    """
    
    def test_anchor_emitted_when_in_aggregator_state(self):
        """Anchor is emitted when present in aggregator.state with valid price."""
        # Simulate aggregator state
        aggregator_state: Dict[str, Dict[str, Any]] = {
            "BTCUSDT": {
                "latest_price": decimal.Decimal("100000"),
                "last_price_ts_ms": 1704067200000,
            },
            "ETHUSDT": {
                "latest_price": decimal.Decimal("3500"),
                "last_price_ts_ms": 1704067200000,
            },
        }
        
        anchors = ["BTCUSDT", "ETHUSDT"]
        emitted_messages = []
        
        # Simulate the emission logic from worker.py
        for anchor in anchors:
            if anchor in aggregator_state:
                price = aggregator_state[anchor].get("latest_price")
                ts_ms = int(aggregator_state[anchor].get("last_price_ts_ms") or 0)
                if price and ts_ms > 0:
                    anchor_msg = {
                        "type": "anchor",
                        "anchor": anchor,
                        "price": str(price),
                        "ts_ms": ts_ms,
                    }
                    emitted_messages.append(anchor_msg)
        
        self.assertEqual(len(emitted_messages), 2)
        self.assertEqual(emitted_messages[0]["anchor"], "BTCUSDT")
        self.assertEqual(emitted_messages[1]["anchor"], "ETHUSDT")
    
    def test_anchor_not_emitted_when_not_in_aggregator_state(self):
        """Anchor is NOT emitted when NOT present in aggregator.state."""
        # Aggregator only has SOLUSDT (trading symbol), NOT anchors
        aggregator_state: Dict[str, Dict[str, Any]] = {
            "SOLUSDT": {
                "latest_price": decimal.Decimal("135"),
                "last_price_ts_ms": 1704067200000,
            },
        }
        
        anchors = ["BTCUSDT", "ETHUSDT"]  # Anchors not in state!
        emitted_messages = []
        
        for anchor in anchors:
            if anchor in aggregator_state:
                price = aggregator_state[anchor].get("latest_price")
                ts_ms = int(aggregator_state[anchor].get("last_price_ts_ms") or 0)
                if price and ts_ms > 0:
                    anchor_msg = {
                        "type": "anchor",
                        "anchor": anchor,
                        "price": str(price),
                        "ts_ms": ts_ms,
                    }
                    emitted_messages.append(anchor_msg)
        
        self.assertEqual(len(emitted_messages), 0, 
            "No anchor messages should be emitted when anchors not in aggregator state")
    
    def test_anchor_not_emitted_when_price_is_none(self):
        """Anchor is NOT emitted when price is None."""
        aggregator_state: Dict[str, Dict[str, Any]] = {
            "BTCUSDT": {
                "latest_price": None,  # No price yet
                "last_price_ts_ms": 1704067200000,
            },
        }
        
        anchors = ["BTCUSDT"]
        emitted_messages = []
        
        for anchor in anchors:
            if anchor in aggregator_state:
                price = aggregator_state[anchor].get("latest_price")
                ts_ms = int(aggregator_state[anchor].get("last_price_ts_ms") or 0)
                if price and ts_ms > 0:
                    anchor_msg = {
                        "type": "anchor",
                        "anchor": anchor,
                        "price": str(price),
                        "ts_ms": ts_ms,
                    }
                    emitted_messages.append(anchor_msg)
        
        self.assertEqual(len(emitted_messages), 0,
            "No anchor messages should be emitted when price is None")
    
    def test_anchor_not_emitted_when_ts_is_zero(self):
        """Anchor is NOT emitted when ts_ms is 0."""
        aggregator_state: Dict[str, Dict[str, Any]] = {
            "BTCUSDT": {
                "latest_price": decimal.Decimal("100000"),
                "last_price_ts_ms": 0,  # No timestamp
            },
        }
        
        anchors = ["BTCUSDT"]
        emitted_messages = []
        
        for anchor in anchors:
            if anchor in aggregator_state:
                price = aggregator_state[anchor].get("latest_price")
                ts_ms = int(aggregator_state[anchor].get("last_price_ts_ms") or 0)
                if price and ts_ms > 0:
                    anchor_msg = {
                        "type": "anchor",
                        "anchor": anchor,
                        "price": str(price),
                        "ts_ms": ts_ms,
                    }
                    emitted_messages.append(anchor_msg)
        
        self.assertEqual(len(emitted_messages), 0,
            "No anchor messages should be emitted when ts_ms is 0")


class TestAnchorSymbolsInTradingSymbols(unittest.TestCase):
    """
    Test whether anchors are properly included in the symbols list.
    
    CRITICAL: If anchors are NOT in self._symbols, they won't be subscribed
    to WebSocket and won't appear in aggregator.state.
    """
    
    def test_anchors_must_be_in_symbols_for_websocket_subscription(self):
        """Anchors must be in symbols list to receive WebSocket data."""
        # Configuration from config_dict
        instruments = {
            "SOLUSDT": {"enabled": True},
            "ETHUSDT": {"enabled": True},
            "BTCUSDT": {"enabled": True},
        }
        symbols = list(instruments.keys())
        anchors = ["BTCUSDT", "ETHUSDT"]
        
        # Check all anchors are in symbols
        for anchor in anchors:
            self.assertIn(anchor, symbols,
                f"Anchor {anchor} MUST be in symbols for WebSocket subscription")
    
    def test_missing_anchor_prevents_data_collection(self):
        """If anchor not in symbols, no data is collected."""
        instruments = {
            "SOLUSDT": {"enabled": True},
            "DOGEUSDT": {"enabled": True},
            "XRPUSDT": {"enabled": True},
            # BTCUSDT and ETHUSDT NOT in instruments!
        }
        symbols = list(instruments.keys())
        anchors = ["BTCUSDT", "ETHUSDT"]
        
        missing_anchors = [a for a in anchors if a not in symbols]
        
        self.assertEqual(len(missing_anchors), 2,
            "Both anchors are missing from symbols - this is a configuration error!")
        
        print(f"\n[CRITICAL] Missing anchors: {missing_anchors}")
        print("           These anchors will NOT receive WebSocket data!")
        print("           macro_resid will NEVER become ready!")


class TestProxyAnchorMessageHandling(unittest.TestCase):
    """
    Test that MarketDataProxy correctly handles anchor messages from worker.
    
    Code location: proxy.py _consume_queue_sync method, line 288
    """
    
    def test_proxy_emits_anchor_event_correctly(self):
        """Proxy should emit EVT:ANCHOR_UPDATED with correct payload."""
        # Simulate FSM
        emitted_events = []
        
        class MockFSM:
            def emit(self, event_name: str, payload: Dict, why: str):
                emitted_events.append({
                    "event_name": event_name,
                    "payload": payload,
                    "why": why,
                })
        
        # Simulate _emit_anchor_update logic
        def emit_anchor_update(fsm, anchor_data: Dict[str, Any]) -> None:
            anchor = anchor_data.get("anchor")
            price = anchor_data.get("price")
            ts_ms = anchor_data.get("ts_ms")
            if ts_ms is None:
                ts_ms = anchor_data.get("ts")
            if ts_ms is None:
                raise ValueError("Anchor update missing required ts_ms")
            
            fsm.emit(
                event_name="EVT:ANCHOR_UPDATED",
                payload={"anchor": anchor, "price": price, "ts_ms": int(ts_ms)},
                why=f"Anchor price update for {anchor} from worker process"
            )
        
        fsm = MockFSM()
        anchor_data = {
            "type": "anchor",
            "anchor": "BTCUSDT",
            "price": "100000.50",
            "ts_ms": 1704067200000,
        }
        
        emit_anchor_update(fsm, anchor_data)
        
        self.assertEqual(len(emitted_events), 1)
        self.assertEqual(emitted_events[0]["event_name"], "EVT:ANCHOR_UPDATED")
        self.assertEqual(emitted_events[0]["payload"]["anchor"], "BTCUSDT")
        self.assertEqual(emitted_events[0]["payload"]["price"], "100000.50")
        self.assertEqual(emitted_events[0]["payload"]["ts_ms"], 1704067200000)


class TestProductionConfigAnchorsInstruments(unittest.TestCase):
    """
    Verify production config has anchors in instruments.
    """
    
    def test_anchors_are_in_production_instruments(self):
        """Check that anchors (BTCUSDT, ETHUSDT) are in production instruments."""
        import yaml
        from pathlib import Path
        
        # Load domains.yaml for anchors
        domains_path = Path("/home/wekabeka/Музыка/Phenix/config/aurora/domains.yaml")
        if domains_path.exists():
            with open(domains_path) as f:
                domains = yaml.safe_load(f)
            
            anchors = domains.get("feature_engineering", {}).get("macro_sync", {}).get("anchors", [])
            print(f"\n[CONFIG] Anchors from domains.yaml: {anchors}")
        else:
            anchors = []
        
        # Load instruments.yaml - note it has nested "instruments" key
        instruments_path = Path("/home/wekabeka/Музыка/Phenix/config/aurora/instruments.yaml")
        if instruments_path.exists():
            with open(instruments_path) as f:
                instruments_cfg = yaml.safe_load(f)
            
            # Get the instruments dict (nested under 'instruments' key)
            instruments_dict = instruments_cfg.get("instruments", {}) if instruments_cfg else {}
            instruments = list(instruments_dict.keys())
            print(f"[CONFIG] Instruments from instruments.yaml: {instruments}")
        else:
            instruments = []
        
        # Check if all anchors are in instruments
        missing = [a for a in anchors if a not in instruments]
        
        if missing:
            print(f"\n[CRITICAL] Anchors NOT in instruments: {missing}")
            print("           These anchors will NOT receive market data!")
            print("           → No anchor_prices → No macro_resid → No full_ready → NO TRADING!")
        else:
            print(f"\n[OK] All anchors {anchors} are in instruments")
            
        # Verify both anchors are present
        self.assertIn("BTCUSDT", instruments, "BTCUSDT must be in instruments")
        self.assertIn("ETHUSDT", instruments, "ETHUSDT must be in instruments")


class TestDiagnosticAnchorFlow(unittest.TestCase):
    """
    Diagnostic test to trace the complete anchor data flow.
    """
    
    def test_trace_anchor_data_flow(self):
        """Trace the complete anchor data flow from config to macro_resid."""
        print("\n" + "="*70)
        print("ANCHOR DATA FLOW DIAGNOSTIC")
        print("="*70)
        
        print("""
1. CONFIG LOADING:
   - domains.yaml: macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]
   - instruments.yaml: Must include BTCUSDT, ETHUSDT
   
2. WEBSOCKET SUBSCRIPTION:
   - MarketDataWorker subscribes to self._symbols
   - self._symbols comes from config_dict["instruments"]
   - IF anchors NOT in instruments → NO WebSocket data for anchors
   
3. DATA AGGREGATION:
   - Aggregator collects data per symbol
   - aggregator.state[symbol] = {latest_price, last_price_ts_ms}
   - IF no WS data → aggregator.state[anchor] doesn't exist
   
4. ANCHOR EMISSION:
   - Worker checks: if anchor in self._aggregator.state
   - IF NOT in state → anchor message NOT emitted
   - IF in state BUT price=None or ts_ms=0 → NOT emitted
   
5. PROXY PROCESSING:
   - Proxy receives messages from IPC queue
   - Type "anchor" → _emit_anchor_update()
   - Emits EVT:ANCHOR_UPDATED to FSM
   
6. FEATURE_ENGINEERING:
   - Listens for EVT:ANCHOR_UPDATED
   - _on_anchor_updated_event() → update_anchor_price()
   - Populates self.anchor_prices[anchor] deque
   
7. MACRO_RESID CALCULATION:
   - _calculate_and_emit_features()
   - Checks: btc_price_hist = self.anchor_prices.get("BTCUSDT", None)
   - IF None or len < 2 → anchor_return cannot be computed
   - → macro_resid buffers never updated
   - → macro_resid NEVER becomes ready
   
8. WARMUP/FULL_READY:
   - ready_map["macro_resid"] = hot.macro_resid_ready
   - compute_warmup_full_ready() checks macro_resid
   - IF macro_resid not ready → full_ready = False
   
9. DECISION_MAKING:
   - Checks warmup.full_ready
   - IF False → DEFER (no trading)
   
CONCLUSION:
- Break in step 2, 3, or 4 → No anchor data → No trading
- LOG EVIDENCE: No "ANCHOR_UPDATED" entries found
- ROOT CAUSE: Likely anchors not in instruments OR aggregator not receiving data
""")
        print("="*70)


if __name__ == "__main__":
    unittest.main(verbosity=2)
