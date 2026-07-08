import os
import sys
import json
import time
import httpx
import asyncio
import hashlib
import logging
import threading
import uvicorn
from pathlib import Path
from typing import Dict, Any, List, Optional
from decimal import Decimal

# Adjust path to include apps/reference
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Set logger safely
def check_and_deduplicate_handlers():
    root_logger = logging.getLogger()
    seen_types = set()
    for handler in list(root_logger.handlers):
        h_type = type(handler)
        dest = getattr(handler, "stream", getattr(handler, "baseFilename", None))
        key = (h_type, dest)
        if key in seen_types:
            root_logger.removeHandler(handler)
        else:
            seen_types.add(key)
    for name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(name)
        if hasattr(logger, "handlers") and logger.handlers:
            logger.propagate = False

# Clear any pre-existing root handlers to avoid duplication
for h in list(logging.getLogger().handlers):
    logging.getLogger().removeHandler(h)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
LOG = logging.getLogger("DeepSeekPilotRunner")

# Force profile
os.environ["AURORA_RUNTIME_PROFILE"] = "deepseek_agent_only_testnet"

# Load environments
def load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip("'").strip('"')

load_env(Path("C:/Users/wekab/Music/Phenix/.env"))
load_env(Path("C:/Users/wekab/Music/deepseek-agent-os-workspace-changes/.env"))

# Imports from codebase
from apps.reference.domains.agent_bridge.contracts_p26 import (
    AgentTradeDecisionV0,
    AgentAuthorityDeepseekTestnetConfig
)
from apps.reference.domains.agent_bridge.deepseek_compiler import load_pilot_config
from apps.reference.domains.agent_bridge.deepseek_to_fsm_adapter import AgentTradeDecisionToSignalMapper
import apps.reference.main
import apps.reference.api.main

check_and_deduplicate_handlers()

# Sanitize/redact secrets helper
def redact(txt: str) -> str:
    for env_var in ["BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET", "DEEPSEEK_API_KEY"]:
        val = os.environ.get(env_var)
        if val and len(val) > 4:
            txt = txt.replace(val, "REDACTED")
    return txt

class DeepSeekPilotSession:
    def __init__(self):
        check_and_deduplicate_handlers()
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = load_pilot_config(self.project_root)
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.environ.get("DEEPSEEK_CENTRAL_MODEL_ID", "deepseek-chat")
        
        self.session_id = self.config.session_id
        self.ledger_dir = self.project_root / "ops" / "agent_bridge" / "deepseek_authority"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        
        self.decision_ledger_path = self.ledger_dir / "deepseek_decision_ledger_v1.jsonl"
        self.session_ledger_path = self.ledger_dir / "deepseek_session_ledger_v1.jsonl"
        
        self.placed_order_count = 0
        self.rejection_count = 0
        self.orders_by_symbol = {"BTCUSDT": 0, "ETHUSDT": 0}
        self.total_notional_allocated = Decimal("0")
        self.last_order_ts_ms = 0
        self.packet_count = 0
        
        self.recent_order_results = []
        self.fsm_listener_active = True

    def log_decision(self, row: dict):
        safe_row = json.loads(redact(json.dumps(row)))
        with open(self.decision_ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe_row) + "\n")
            
    def log_session_event(self, event_name: str, details: dict = None):
        row = {
            "timestamp_ms": int(time.time() * 1000),
            "session_id": self.session_id,
            "event": event_name,
            "details": details or {},
            "stats": {
                "packet_count": self.packet_count,
                "placed_order_count": self.placed_order_count,
                "rejection_count": self.rejection_count,
                "total_notional": str(self.total_notional_allocated)
            }
        }
        safe_row = json.loads(redact(json.dumps(row)))
        with open(self.session_ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe_row) + "\n")

    def start_api_server(self):
        LOG.info("Starting API Server via uvicorn in background thread...")
        
        def run_uvicorn():
            # Disable uvicorn log pollution
            uvicorn.run(apps.reference.api.main.app, host="127.0.0.1", port=18080, log_level="warning")
            
        t_uvicorn = threading.Thread(target=run_uvicorn, daemon=True)
        t_uvicorn.start()
        
        # Wait for port to be active
        for _ in range(20):
            try:
                res = httpx.get("http://127.0.0.1:18080/health", timeout=1.0)
                if res.status_code == 200:
                    LOG.info("API Server successfully started and healthy.")
                    return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("API Server failed to start on port 18080 within 10s")

    def start_trading_fsm(self):
        LOG.info("Cleaning up WAL and restore directories...")
        # Clean up WAL and restore directories to prevent replay/state contamination
        wal_dir = Path("ops/wal")
        if wal_dir.exists():
            for f in wal_dir.glob("*.jsonl"):
                try:
                    f.unlink()
                    LOG.info(f"Deleted WAL file: {f}")
                except Exception as e:
                    LOG.warning(f"Could not delete WAL file {f}: {e}")

        restore_dir = Path("ops/restore")
        if restore_dir.exists():
            for f in restore_dir.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                        LOG.info(f"Deleted restore file: {f}")
                except Exception as e:
                    LOG.warning(f"Could not delete restore file {f}: {e}")

        LOG.info("Starting FSM thread...")
        t = threading.Thread(target=apps.reference.main.main, daemon=True)
        t.start()
        
        # Wait for FSM to initialize
        for _ in range(90):
            fsm = getattr(apps.reference.main, "fsm", None)
            if fsm is not None and getattr(apps.reference.main, "execution_position", None) is not None:
                LOG.info("FSM successfully initialized.")
                return
            time.sleep(1.0)
        raise RuntimeError("FSM failed to initialize within 90s")

    def build_prompt(self, packet: dict) -> tuple[str, str]:
        allowed_syms_str = ", ".join(self.config.allowed_symbols)
        allowed_horiz_str = ", ".join(self.config.allowed_horizons)
        system_prompt = f"""You are the central DeepSeek Agent Authority (ID: {self.config.agent_id}) for the Aurora Core trading system.
Your job is to read market evidence from the AgentFeedPacket and output a single, structured JSON trade decision.

You must output a single JSON object conforming strictly to the following schema:
{{
  "schema_version": "agent-trade-decision/v0",
  "agent_id": "{self.config.agent_id}",
  "provider": "deepseek",
  "model": "{self.model}",
  "packet_ref": "agent-feed://packet/{packet['packet_id']}",
  "symbol": "<one of {allowed_syms_str}>",
  "horizon": "<one of {allowed_horiz_str}>",
  "action": "<TESTNET_OPEN_LONG | TESTNET_OPEN_SHORT | TESTNET_CLOSE | TESTNET_REDUCE | WAIT | OBSERVE | NO_ACTION>",
  "side": "<BUY | SELL | NONE>",
  "confidence": <float between 0.0 and 1.0>,
  "thesis": "<10 to 1000 characters detail explaining your logic>",
  "invalidation": "<10 to 1000 characters detail explaining what would invalidate your thesis>",
  "expected_scenarios": ["<scenario ids expected, e.g. S01_MR_RSI_HEAVY>"],
  "evidence_refs": ["<keys in packet used as evidence, e.g. close_price, volume>"],
  "acknowledged_warnings": ["<warnings from the packet acknowledged, if any>"],
  "risk_note": "<10 to 1000 characters summarizing specific risks>",
  "testnet_only": true
}}

Rules:
1. ONLY allowed symbols: {allowed_syms_str}.
2. Side rules:
   - TESTNET_OPEN_LONG requires side: "BUY".
   - TESTNET_OPEN_SHORT requires side: "SELL".
   - TESTNET_CLOSE or TESTNET_REDUCE requires side: "BUY" (to close/reduce short) or "SELL" (to close/reduce long).
   - WAIT, OBSERVE, NO_ACTION require side: "NONE".
3. Try to look at feature signals, momentum, and regime. If there is a setup, choose TESTNET_OPEN_LONG or TESTNET_OPEN_SHORT.
4. If there is no clear opportunity, output WAIT or NO_ACTION.
5. You are strictly forbidden from scalping. Avoid micro-timeframe setups. Focus on broader scalp/swing horizons with expected holding periods greater than 1 hour, looking for clear macro trends.
6. You must write valid JSON, no markdown around it (e.g. do not include ```json ... ``` blocks).
"""
        evidence = json.dumps(packet, indent=2)
        return system_prompt, evidence

    def call_deepseek(self, system: str, evidence: str) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": evidence}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        res = httpx.post(url, headers=headers, json=payload, timeout=float(self.config.provider_timeout_sec))
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        return content

    def register_fsm_listeners(self):
        fsm = apps.reference.main.fsm
        
        # We hook into FSM to intercept order submissions and results
        original_emit = fsm.emit
        
        def custom_emit(event_name: str, payload: dict = None, why: str = "", *args, **kwargs):
            if not self.fsm_listener_active:
                return original_emit(event_name, payload, why, *args, **kwargs)
                
            # Log order-related events
            if payload and ("ORDER_SUBMITTED" in event_name or "ORDER_RESULT" in event_name or "REJECTED" in event_name):
                LOG.info(f"[FSM Event Intercepted] {event_name}: {payload} (Why: {why})")
                self.recent_order_results.append({
                    "ts": int(time.time() * 1000),
                    "event": event_name,
                    "payload": payload,
                    "why": why
                })
                
            return original_emit(event_name, payload, why, *args, **kwargs)
            
        fsm.emit = custom_emit

    async def run_session(self):
        self.start_api_server()
        self.start_trading_fsm()
        self.register_fsm_listeners()
        
        fsm = apps.reference.main.fsm
        LOG.info(f"Emitting session started event...")
        fsm.emit("EVT:DEEPSEEK_AGENT_SESSION_STARTED", {"session_id": self.session_id}, "pilot_startup")
        self.log_session_event("SESSION_START")
        
        # Define instrument spec loader
        instruments = apps.reference.main.execution_position.config.instruments
        
        # We run the session loop
        # Duration: 30 minutes, or until max orders, or cancelled
        max_duration = self.config.max_session_duration_sec
        start_time = time.time()
        
        LOG.info(f"Starting pilot agent loop (duration: {max_duration}s)...")
        
        while time.time() - start_time < max_duration:
            self.packet_count += 1
            now_ms = int(time.time() * 1000)
            
            # 1. Fetch feed packet
            LOG.info(f"\n--- Observation Cycle {self.packet_count} ---")
            try:
                # Poll API for BTCUSDT,ETHUSDT packet
                res = httpx.get("http://127.0.0.1:18080/agent-feed/v0/packet?symbols=BTCUSDT,ETHUSDT", timeout=10.0)
                res.raise_for_status()
                packet = res.json()
            except Exception as e:
                LOG.error(f"Error fetching feed packet: {e}")
                await asyncio.sleep(30.0)
                continue
                
            LOG.info(f"Fetched packet {packet.get('packet_id')} (estimated tokens: {packet.get('budget', {}).get('estimated_tokens')})")
            
            # Print current prices & positions for convenience
            for sm in packet.get("symbol_markets", []):
                LOG.info(f"Price {sm.get('symbol')}: {sm.get('close_price')}")
            for pos in packet.get("position_life", {}).get("positions", []):
                LOG.info(f"Position {pos.get('symbol')}: {pos.get('side')} size={pos.get('qty')}")
            
            # Choose symbol to make decision on (alternating or just both in parallel)
            # Let's request a decision for BTCUSDT or ETHUSDT depending on tick
            symbol_to_trade = "BTCUSDT" if self.packet_count % 2 == 1 else "ETHUSDT"
            
            # DELIBERATE REJECTION TEST: Propose invalid intent on Cycle 3
            if self.packet_count == 3:
                invalid_intent = {
                    "rid": "intent_deliberate_invalid_123",
                    "symbol": "DUMMYUSDT",
                    "side": "INVALID_SIDE",
                    "order": {
                        "qty": "0.0",
                        "order_type": "MARKET"
                    }
                }
                LOG.info("Deliberately proposing invalid trade intent for rejection validation...")
                try:
                    fsm.emit("EVT:TRADE_INTENT_PROPOSED", invalid_intent, "pilot_deliberate_invalid_test")
                except Exception as e:
                    LOG.info(f"Deliberate invalid intent successfully rejected by FSM payload validation: {e}")
                    self.log_decision({
                        "timestamp_ms": int(time.time() * 1000),
                        "packet_ref": packet.get("packet_id", "N/A"),
                        "symbol": "DUMMYUSDT",
                        "decision": {"action": "TESTNET_OPEN_LONG", "side": "LONG"},
                        "compiled": False,
                        "submitted": False,
                        "rejection_reason": f"FSM_VALIDATION_REJECTED: {str(e)}"
                    })
                await asyncio.sleep(2.0)
            
            # 2. Call DeepSeek
            system_prompt, evidence = self.build_prompt(packet)
            
            # We override symbol in system prompt to focus DeepSeek on symbol_to_trade
            system_prompt += f"\nFor this cycle, focus your trade evaluation exclusively on: {symbol_to_trade}."
            
            LOG.info(f"Sending decision request to DeepSeek for {symbol_to_trade}...")
            call_start = time.perf_counter()
            decision_raw = None
            try:
                decision_raw = self.call_deepseek(system_prompt, evidence)
                latency_ms = (time.perf_counter() - call_start) * 1000
                LOG.info(f"Received DeepSeek response in {latency_ms:.2f}ms")
            except Exception as e:
                LOG.error(f"Error calling DeepSeek: {e}")
                self.log_decision({
                    "timestamp_ms": int(time.time() * 1000),
                    "symbol": symbol_to_trade,
                    "compiled": False,
                    "rejection_reason": f"API_ERROR: {str(e)}"
                })
                await asyncio.sleep(40.0)
                continue
                
            # 3. Parse JSON output
            try:
                decision_data = json.loads(decision_raw)
                decision = AgentTradeDecisionV0.model_validate(decision_data)
                LOG.info(f"Parsed Decision: Action={decision.action}, Symbol={decision.symbol}, Thesis={decision.thesis[:120]}")
                fsm.emit("EVT:DEEPSEEK_AGENT_DECISION_RECEIVED", decision.model_dump(), "pilot_model_call")
            except Exception as e:
                LOG.error(f"Failed to parse or validate decision: {e}. Raw response: {decision_raw}")
                self.rejection_count += 1
                self.log_decision({
                    "timestamp_ms": int(time.time() * 1000),
                    "symbol": symbol_to_trade,
                    "compiled": False,
                    "rejection_reason": f"PARSE_OR_VALIDATION_ERROR: {str(e)}",
                    "raw_output": decision_raw
                })
                fsm.emit("EVT:DEEPSEEK_AGENT_DECISION_REJECTED", {"reason": str(e), "raw": decision_raw}, "pilot_parser_failure")
                await asyncio.sleep(40.0)
                continue
                
            # 4. Map decision to signal payload
            close_price = None
            for sym_mkt in packet.get("symbol_markets", []):
                if sym_mkt.get("symbol") == decision.symbol:
                    close_price = sym_mkt.get("close_price")
                    break

            price_ctx = {}
            if close_price:
                price_ctx["entry_price"] = str(close_price)
                price_ctx["close_price"] = str(close_price)

            try:
                signal_payload = AgentTradeDecisionToSignalMapper.map_decision(
                    decision,
                    decision_id=f"ds-dec-{int(time.time() * 1000)}",
                    ts_ms=int(time.time() * 1000),
                    price_ctx=price_ctx
                )
                LOG.info(f"Mapped Signal Payload: {json.dumps(signal_payload, indent=2)}")
                fsm.emit("EVT:DEEPSEEK_AGENT_DECISION_MAPPED", signal_payload, "pilot_adapter")
            except Exception as e:
                LOG.error(f"Mapper rejected decision: {e}")
                self.rejection_count += 1
                self.log_decision({
                    "timestamp_ms": int(time.time() * 1000),
                    "symbol": decision.symbol,
                    "compiled": False,
                    "rejection_reason": f"MAPPER_REJECTED: {str(e)}",
                    "decision": decision.model_dump()
                })
                fsm.emit("EVT:DEEPSEEK_AGENT_DECISION_REJECTED", {"reason": str(e)}, "pilot_mapper_rejection")
                await asyncio.sleep(40.0)
                continue

            # 5. Apply session & risk validation gates
            is_valid = True
            reason = ""
            
            # Check maximum orders limit
            if decision.action not in {"WAIT", "OBSERVE", "NO_ACTION"}:
                if self.placed_order_count >= self.config.max_orders_per_session:
                    is_valid = False
                    reason = f"Max orders per session ({self.config.max_orders_per_session}) reached."
                elif self.orders_by_symbol.get(decision.symbol, 0) >= self.config.max_orders_per_symbol:
                    is_valid = False
                    reason = f"Max orders for symbol {decision.symbol} ({self.config.max_orders_per_symbol}) reached."
                
                # Check cooldown
                cooldown_sec = self.config.min_seconds_between_orders
                time_since_last_order = (time.time() * 1000 - self.last_order_ts_ms) / 1000.0
                if time_since_last_order < cooldown_sec:
                    is_valid = False
                    reason = f"Cooldown in progress. Time elapsed: {time_since_last_order:.1f}s, required: {cooldown_sec}s"

            if not is_valid:
                LOG.warning(f"Risk gate rejected mapped signal: {reason}")
                self.rejection_count += 1
                self.log_decision({
                    "timestamp_ms": int(time.time() * 1000),
                    "symbol": decision.symbol,
                    "compiled": True,
                    "validation_status": "rejected",
                    "rejection_reason": f"RISK_GATE_REJECTED: {reason}",
                    "decision": decision.model_dump(),
                    "signal_payload": signal_payload
                })
                fsm.emit("EVT:DEEPSEEK_AGENT_DECISION_REJECTED", {"reason": reason}, "pilot_risk_rejection")
                await asyncio.sleep(40.0)
                continue

            # 6. Propose signal to FSM
            if decision.action in {"WAIT", "OBSERVE", "NO_ACTION"}:
                LOG.info("Decision action is passive (WAIT/OBSERVE/NO_ACTION). Emitting no order.")
                self.log_decision({
                    "timestamp_ms": int(time.time() * 1000),
                    "symbol": decision.symbol,
                    "compiled": True,
                    "validation_status": "accepted",
                    "submitted": False,
                    "decision": decision.model_dump(),
                    "signal_payload": signal_payload
                })
            else:
                LOG.info(f"Risk gate passed. Proposing strategy signal to FSM...")
                self.placed_order_count += 1
                self.orders_by_symbol[decision.symbol] = self.orders_by_symbol.get(decision.symbol, 0) + 1
                self.last_order_ts_ms = int(time.time() * 1000)
                
                # Emit to FSM!
                fsm.emit("EVT:DEEPSEEK_AGENT_TESTNET_SIGNAL_SUBMITTED", signal_payload, "pilot_signal_submitted")
                
                self.recent_order_results.clear()
                fsm.emit("EVT:STRATEGY_SIGNAL_PRODUCED", signal_payload, "pilot_agent_signal")
                
                # Wait a few seconds for FSM to process order and trigger the uvicorn logs / events
                await asyncio.sleep(5.0)
                
                order_result_status = "unknown"
                order_reject_reason = ""
                # Inspect recent order results
                for event in self.recent_order_results:
                    if "REJECTED" in event["event"]:
                        order_result_status = "rejected"
                        order_reject_reason = event["payload"].get("reason", "unknown FSM rejection")
                    elif "ORDER_RESULT" in event["event"] or "FILL" in event["event"] or "FILLED" in event["event"]:
                        order_result_status = "filled"
                        
                LOG.info(f"Signal routing result: {order_result_status} (error if any: {order_reject_reason})")
                
                self.log_decision({
                    "timestamp_ms": int(time.time() * 1000),
                    "symbol": decision.symbol,
                    "compiled": True,
                    "validation_status": "accepted",
                    "submitted": True,
                    "order_result": order_result_status,
                    "order_reject_reason": order_reject_reason,
                    "decision": decision.model_dump(),
                    "signal_payload": signal_payload
                })
                
                # If stop_on_first_execution_error is active and order got rejected, check if we should abort
                if order_result_status == "rejected" and self.config.stop_on_first_execution_error:
                    LOG.error("Execution error occurred and stop_on_first_execution_error is enabled. Stopping session.")
                    break

            # Check if we have met target session requirements:
            # - at least 20 packet observations
            # - at least 5 decisions
            # - at least 1 order if setup occurs
            if max_duration <= 1800 and self.packet_count >= 22:
                LOG.info("Reached 22 cycles (target packet observations for short preflight run). Ending session.")
                break

            LOG.info(f"Cycle completed. Time elapsed: {time.time() - start_time:.1f}s / {max_duration}s")
            
            # cadency: sleep 40s to easily fit 20 cycles in 15-20 mins
            await asyncio.sleep(40.0)

        # End of session
        LOG.info("Session duration reached or terminated. Shutting down...")
        fsm.emit("EVT:DEEPSEEK_AGENT_SESSION_STOPPED", {"session_id": self.session_id}, "pilot_shutdown")
        self.log_session_event("SESSION_STOP")
        self.cleanup()

    def cleanup(self):
        LOG.info("Cleaning up session processes...")
        self.fsm_listener_active = False
        try:
            main_mod = apps.reference.main
            if hasattr(main_mod, "wal_gc") and main_mod.wal_gc is not None:
                main_mod.wal_gc.stop()
            if hasattr(main_mod, "csv_recorder") and main_mod.csv_recorder is not None:
                main_mod.csv_recorder.stop()
            if hasattr(main_mod, "guardian_runtime") and main_mod.guardian_runtime is not None:
                main_mod.guardian_runtime.stop(timeout=2.0)
        except Exception as e:
            LOG.warning(f"Error stopping main.py subcomponents: {e}")

def run_pilot():
    runner = DeepSeekPilotSession()
    try:
        asyncio.run(runner.run_session())
    except KeyboardInterrupt:
        LOG.info("KeyboardInterrupt received.")
        runner.cleanup()
    except Exception as e:
        LOG.exception("Error running pilot session:")
        runner.cleanup()

if __name__ == "__main__":
    run_pilot()
