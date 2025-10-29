"""
FSMP-P1-T02: Orchestration of 3 FSM flows for execution_position domain.

This FSM acts as a wrapper, routing commands to the appropriate flow FSM
(Open, Manage, Close) on a per-symbol basis. It integrates directly with
the vFoundation BinanceAdapter to execute trades in the configured environment.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple

from vfoundation.core.protocol import Message
from vfoundation.dr import wal
from vfoundation.adapters.binance_adapter import BinanceAdapter, BinanceAPIError

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM
from .fsm_close import CloseFlowFSM
from .utils import (
    quantize_stop_price, validate_anti_2021, generate_client_order_id,
    calc_tp_sl_from_mark, validate_not_immediate, opposite_side
)
from .aurora_log_adapter import AuroraLogAdapter
from .metrics_collector import MetricsCollector
from .utils import quantize_stop_price, validate_anti_2021, generate_client_order_id

LOG = logging.getLogger(__name__)

class ExecPosFSM:
    """
    Wrapper FSM for the execution_position domain. It manages FSM instances
    per symbol and handles trade execution via the BinanceAdapter.
    """
    
    def __init__(self, config: Dict[str, Any], fsm, shadow_mode: bool = False):
        self.config = config
        self.fsm = fsm
        self.shadow_mode = shadow_mode
        self.adapter: Optional[BinanceAdapter] = None
        
        self.open_flows: Dict[str, OpenFlowFSM] = {}
        self.manage_flows: Dict[str, ManageFlowFSM] = {}
        self.close_flows: Dict[str, CloseFlowFSM] = {}

        self.log_adapter = AuroraLogAdapter()
        self.metrics_collector = MetricsCollector()

        if not self.shadow_mode:
            self._initialize_adapter()

    def _initialize_adapter(self):
        """Initializes the BinanceAdapter based on the domain-level trading_mode."""
        # Check if config_loader has get_domain_mode method (new approach)
        mode = "testnet"  # Default fallback
        
        # Try to get domain-specific mode first
        if hasattr(self.config, 'get_domain_mode'):
            try:
                mode = self.config.get_domain_mode("execution_position")
                LOG.info(f"✅ ExecPosFSM using domain-specific mode: {mode}")
            except Exception as e:
                LOG.warning(f"Could not get domain mode, using fallback: {e}")
                mode = self.config.get("trading_mode", "testnet")
        else:
            # Fallback to global mode
            mode = self.config.get("trading_mode", "testnet")
            LOG.info(f"ExecPosFSM using global trading_mode: {mode}")
        
        LOG.info(f"🎯 EXECUTION POSITION FSM MODE: {mode.upper()}")
        
        api_config = self.config.get("binance_api", {})
        
        env_config = {}
        if mode == "live":
            env_config = api_config.get("live", {})
            LOG.info("❌ ExecPosFSM adapter is configured for LIVE execution.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            env_config = api_config.get("testnet", {})
            LOG.info(f"✅ ExecPosFSM adapter is configured for TESTNET execution (mode: {mode}).")

        if not all([env_config.get("api_key"), env_config.get("api_secret"), env_config.get("rest_url")]):
            LOG.error(f"API configuration for execution in '{mode}' mode is incomplete. Execution will be simulated.")
            LOG.debug(f"  - API Key present: {bool(env_config.get('api_key'))}")
            LOG.debug(f"  - API Secret present: {bool(env_config.get('api_secret'))}")
            LOG.debug(f"  - REST URL: {env_config.get('rest_url')}")
            self.shadow_mode = True # Fallback to shadow mode if config is missing
            return

        self.adapter = BinanceAdapter(
            api_key=env_config["api_key"],
            api_secret=env_config["api_secret"],
            rest_url=env_config["rest_url"]
        )
        LOG.info(f"✅ BinanceAdapter initialized for ExecPosFSM with base URL: {self.adapter.base_url}")

    def _get_or_create_flows(self, symbol: str) -> Tuple[OpenFlowFSM, ManageFlowFSM, CloseFlowFSM]:
        """Get or create the set of FSMs for a given symbol."""
        if symbol not in self.manage_flows:
            LOG.info(f"Creating new set of FSMs for symbol: {symbol}")
            exec_config = self.config.get('trading', {}).get('execution', {})
            cooldown_ms = float(exec_config.get('cooldown_ms', 1000))
            cooldown_sec = cooldown_ms / 1000.0
            guard_enabled = exec_config.get('guard_enabled', True)

            self.open_flows[symbol] = OpenFlowFSM(cooldown_sec=cooldown_sec, guard_enabled=guard_enabled, config=self.config)
            self.manage_flows[symbol] = ManageFlowFSM(config=self.config)
            self.close_flows[symbol] = CloseFlowFSM()
        
        return self.open_flows[symbol], self.manage_flows[symbol], self.close_flows[symbol]

    def hydrate(self, position_data: Dict[str, Any]):
        """Hydrate the FSMs for a given position from a snapshot."""
        symbol = position_data.get('symbol')
        if not symbol:
            LOG.error("HYDRATION_ERROR: position_data is missing 'symbol'")
            return

        _, manage_flow, close_flow = self._get_or_create_flows(symbol)
        
        LOG.info(f"Hydrating FSMs for symbol {symbol} from snapshot.")
        manage_flow.hydrate(position_data)
        close_flow.hydrate(position_data)

    def handle(self, msg: Message) -> Optional[Message]:
        """Route message to the appropriate flow and handle execution decisions."""
        pld = msg.pld or {}
        symbol = pld.get("symbol")
        if not symbol:
            LOG.warning(f"ExecPosFSM received message without symbol: {msg.verb}")
            return None

        open_flow, manage_flow, close_flow = self._get_or_create_flows(symbol)
        result = None

        # Route to the correct FSM based on the message verb
        if msg.verb == "OPEN":
            result = open_flow.handle(msg)
        elif msg.verb in ["PARTIAL_FILL", "FILL", "TRADE_EXECUTED", "ORDER_UPDATED"]:
            manage_result = manage_flow.handle(msg)
            close_result = close_flow.handle(msg)
            result = manage_result if manage_result else close_result
        elif msg.verb == "CLOSE":
            result = close_flow.handle(msg)
        else:
            result = manage_flow.handle(msg)
        
        # If a decision was made, log it and execute if not in shadow mode
        if result and result.op == "DEC":
            wal.append(result.model_dump())
            if not self.shadow_mode and self.adapter:
                # Asynchronously execute the trade decision
                loop = asyncio.get_event_loop()
                loop.create_task(self._execute_decision(result))
        
        return result

    async def _execute_decision(self, decision: Message):
        """Asynchronously execute a trading decision using the adapter."""
        if not self.adapter:
            return

        # --- CRITICAL SAFETY GUARDRAIL ---
        # Get domain-specific mode (execution_position should be testnet)
        domain_mode = "testnet"
        if hasattr(self.config, 'get_domain_mode'):
            try:
                domain_mode = self.config.get_domain_mode("execution_position")
            except:
                domain_mode = self.config.get("trading_mode", "testnet")
        else:
            domain_mode = self.config.get("trading_mode", "testnet")
        
        LOG.info(f"🎯 Executing with domain_mode={domain_mode}")
        
        if domain_mode == "testnet":
            if "testnet" not in self.adapter.base_url:
                LOG.critical(
                    "🚨 GUARDRAIL TRIGGERED: Domain mode is TESTNET, but adapter is configured for LIVE API! Order BLOCKED."
                )
                # Optionally emit a critical error event
                self.fsm.emit("ERR:FATAL_CONFIG_MISMATCH", why="Testnet mode with live execution URL", payload={"reason": "Testnet mode with live execution URL"})
                return
            else:
                LOG.info("✅ Testnet mode confirmed: adapter URL contains 'testnet'")
        elif domain_mode == "live":
            LOG.warning("⚠️ LIVE execution mode - ensure you know what you're doing!")
        
        # --- END GUARDRAIL ---

        try:
            symbol = decision.pld['symbol']
            side = decision.pld['side'].upper()
            qty = decision.pld['qty']
            
            # Get mark price and filters
            mark = await self.adapter.get_mark_price(symbol)
            exchange_info = await self.adapter.get_exchange_info(symbol)
            tick_size = float(next(f['tickSize'] for f in exchange_info['symbols'][0]['filters'] if f['filterType'] == 'PRICE_FILTER'))
            
            # Assume tp_bps and sl_bps from config or default
            tp_bps = 100  # example
            sl_bps = 50   # example
            
            tp, sl = calc_tp_sl_from_mark(mark, 'LONG' if side == 'BUY' else 'SHORT', tp_bps, sl_bps)
            
            # Quantize
            tp = quantize_stop_price(tp, tick_size, side='BUY' if side == 'BUY' else 'SELL')
            sl = quantize_stop_price(sl, tick_size, side='SELL' if side == 'BUY' else 'BUY')
            
            # Validate
            validate_not_immediate('LONG' if side == 'BUY' else 'SHORT', tp, sl, mark)
            
            # Place MARKET entry
            entry_id = generate_client_order_id('ENTRY', symbol)
            entry_resp = await self.adapter.place_market_entry(symbol, side, qty, entry_id)
            LOG.info(f"✅ MARKET entry placed: {entry_resp}")
            
            # Check for existing brackets to avoid duplicates
            open_orders = await self.adapter.get_open_orders(symbol)
            existing_sl = any(o['type'] == 'STOP_MARKET' and o.get('closePosition') == 'true' for o in open_orders)
            existing_tp = any(o['type'] in ['TAKE_PROFIT_MARKET', 'LIMIT'] and o.get('closePosition') == 'true' or o.get('reduceOnly') == 'true' for o in open_orders)
            
            if existing_sl:
                LOG.warning(f"SL already exists for {symbol}, skipping")
            else:
                # Place SL
                sl_side = opposite_side(side)
                sl_id = generate_client_order_id('SL', symbol)
                sl_resp = await self.adapter.place_stop_market_close_position(symbol, sl_side, str(sl), new_client_order_id=sl_id)
                LOG.info(f"✅ SL placed: {sl_resp}")
            
            if existing_tp:
                LOG.warning(f"TP already exists for {symbol}, skipping")
            else:
                # Place TP with retry/fallback
                tp_side = opposite_side(side)
                tp_id = generate_client_order_id('TP', symbol)
                try:
                    tp_resp = await self.adapter.place_take_profit_market_close_position(symbol, tp_side, str(tp), new_client_order_id=tp_id)
                    LOG.info(f"✅ TP TAKE_PROFIT_MARKET placed: {tp_resp}")
                except BinanceAPIError as e:
                    if e.code == -2021:
                        # Retry with widened TP
                        tp_adj = tp * 1.002  # +20 bps approx
                        tp_adj = quantize_stop_price(tp_adj, tick_size, side='BUY' if side == 'BUY' else 'SELL')
                        try:
                            tp_resp = await self.adapter.place_take_profit_market_close_position(symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
                            LOG.info(f"✅ TP TAKE_PROFIT_MARKET retried: {tp_resp}")
                        except BinanceAPIError:
                            # Fallback to LIMIT reduceOnly
                            tp_resp = await self.adapter.place_limit_reduce_only(symbol, tp_side, str(tp_adj), qty, new_client_order_id=tp_id)
                            LOG.info(f"✅ TP LIMIT fallback placed: {tp_resp}")
                    else:
                        raise
            
        except Exception as e:
            LOG.error(f"❌ Adapter failed to execute decision {decision.verb} for {decision.pld.get('symbol')}: {e}", exc_info=True)
            # Emit an error event
            self.fsm.emit("ERR:EXECUTION_FAILED", why="Execution failed due to adapter error", payload={"error": str(e), "original_decision": decision.model_dump()})

    def get_metrics(self) -> Dict[str, Any]:
        """Aggregate metrics from all managed FSMs."""
        all_metrics = {}
        for symbol, open_fsm in self.open_flows.items():
            all_metrics[f'{symbol}_open'] = open_fsm.get_metrics()
        for symbol, manage_fsm in self.manage_flows.items():
            all_metrics[f'{symbol}_manage'] = manage_fsm.get_metrics()
        for symbol, close_fsm in self.close_flows.items():
            all_metrics[f'{symbol}_close'] = close_fsm.get_metrics()
        return all_metrics

    def open_flow(self, symbol: str) -> OpenFlowFSM:
        """Get or create OpenFlowFSM for the given symbol."""
        open_f, _, _ = self._get_or_create_flows(symbol)
        return open_f

    def manage_flow(self, symbol: str) -> ManageFlowFSM:
        """Get or create ManageFlowFSM for the given symbol."""
        _, manage_f, _ = self._get_or_create_flows(symbol)
        return manage_f

    def close_flow(self, symbol: str) -> CloseFlowFSM:
        """Get or create CloseFlowFSM for the given symbol."""
        _, _, close_f = self._get_or_create_flows(symbol)
        return close_f