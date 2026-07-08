from __future__ import annotations

import os
import re
import json
import time
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from pathlib import Path

from .contracts_p26 import AgentTradeDecisionV0, AgentAuthorityDeepseekTestnetConfig
from apps.reference.config.shared.instruments import InstrumentPrecisionSpec

LOG = logging.getLogger("apps.reference.domains.agent_bridge.deepseek_compiler")


class DeepSeekCompilerError(Exception):
    def __init__(self, reason_code: str, why: str):
        super().__init__(why)
        self.reason_code = reason_code
        self.why = why


def load_pilot_config(project_root: Path) -> AgentAuthorityDeepseekTestnetConfig:
    config_path = project_root / "config" / "agent_authority_deepseek_testnet.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Pilot configuration file missing: {config_path}")
    
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    return AgentAuthorityDeepseekTestnetConfig.model_validate(data)


def compile_decision_to_intent_payload(
    decision: AgentTradeDecisionV0,
    packet: Dict[str, Any],
    config: AgentAuthorityDeepseekTestnetConfig,
    instrument: InstrumentPrecisionSpec,
    now_ms: int,
) -> Dict[str, Any]:
    """DEPRECATED: Compile AgentTradeDecisionV0 to executable TRADE_INTENT_PROPOSED payload.
    
    Deprecated in P28. Use deepseek_to_fsm_adapter.py instead.
    """
    
    # 1. Validation checks
    if not decision.testnet_only:
        raise DeepSeekCompilerError("TESTNET_ONLY_FALSE", "testnet_only must be True")
        
    if decision.symbol not in config.allowed_symbols:
        raise DeepSeekCompilerError("SYMBOL_NOT_ALLOWED", f"Symbol {decision.symbol} not in config allowed_symbols")
        
    if decision.action not in config.allowed_actions:
        raise DeepSeekCompilerError("ACTION_NOT_ALLOWED", f"Action {decision.action} not allowed")
        
    if decision.confidence < 0.0 or decision.confidence > 1.0:
        raise DeepSeekCompilerError("CONFIDENCE_OUT_OF_RANGE", "Confidence must be between 0.0 and 1.0")
        
    if not decision.evidence_refs:
        raise DeepSeekCompilerError("EVIDENCE_REFS_MISSING", "Evidence refs must not be empty")

    # Check packet freshness
    packet_ts = packet.get("produced_ts_ms", 0)
    packet_age_sec = (now_ms - packet_ts) / 1000.0
    if packet_age_sec > config.decision_timeout_sec:
        raise DeepSeekCompilerError(
            "PACKET_STALE",
            f"Packet {decision.packet_ref} is stale (age: {packet_age_sec:.2f}s, limit: {config.decision_timeout_sec}s)"
        )

    # 2. Close Price resolution from symbol_markets in the feed packet
    close_price = None
    for sym_mkt in packet.get("symbol_markets", []):
        if sym_mkt.get("symbol") == decision.symbol:
            close_price = sym_mkt.get("close_price")
            break
            
    if not close_price or float(close_price) <= 0.0:
        raise DeepSeekCompilerError("PRICE_UNRESOLVED", f"Could not resolve close price for {decision.symbol}")

    close_price_dec = Decimal(str(close_price))

    # 3. Order sizing calculations
    # Quantity mode is derived from max_notional_per_order
    requested_notional = Decimal(str(config.max_notional_per_order))
    
    # Quantize quantity to step size (LOT_SIZE) - floor
    raw_qty = requested_notional / close_price_dec
    step_size = instrument.step_size
    
    # Floor to step size precision
    qty_dec = (raw_qty / step_size).quantize(Decimal("1"), rounding="ROUND_DOWN") * step_size
    
    # 4. Limit and Min Notional Checks
    if qty_dec < instrument.min_qty:
        raise DeepSeekCompilerError(
            "QTY_BELOW_MINIMUM", 
            f"Computed qty {qty_dec} is below instrument minimum {instrument.min_qty}"
        )
        
    actual_notional = qty_dec * close_price_dec
    if actual_notional < instrument.min_notional:
        raise DeepSeekCompilerError(
            "NOTIONAL_BELOW_MINIMUM",
            f"Computed notional {actual_notional} is below instrument minimum {instrument.min_notional}"
        )

    if actual_notional > requested_notional:
        raise DeepSeekCompilerError(
            "NOTIONAL_EXCEEDS_MAXIMUM",
            f"Computed notional {actual_notional} exceeds max permitted {requested_notional}"
        )

    # 5. Side mapping and reduce only setup
    reduce_only = False
    side = "NONE"
    
    if decision.action == "TESTNET_OPEN_LONG":
        side = "BUY"
    elif decision.action == "TESTNET_OPEN_SHORT":
        side = "SELL"
    elif decision.action in {"TESTNET_CLOSE", "TESTNET_REDUCE"}:
        reduce_only = True
        # For close/reduce, the side is opposite of the active position
        # We can look up active position in the packet position_life
        pos_side = None
        for pos in packet.get("position_life", {}).get("positions", []):
            if pos.get("symbol") == decision.symbol:
                pos_side = pos.get("side")
                break
        
        if pos_side == "LONG":
            if decision.side != "SELL":
                raise DeepSeekCompilerError(
                    "LIFECYCLE_UNKNOWN",
                    f"Decision side {decision.side} does not match active position side {pos_side} for close/reduce"
                )
            side = "SELL"
        elif pos_side == "SHORT":
            if decision.side != "BUY":
                raise DeepSeekCompilerError(
                    "LIFECYCLE_UNKNOWN",
                    f"Decision side {decision.side} does not match active position side {pos_side} for close/reduce"
                )
            side = "BUY"
        else:
            # Fallback if no active position is found: use the side specified in decision
            if decision.side in {"BUY", "SELL"}:
                side = decision.side
            else:
                raise DeepSeekCompilerError(
                    "LIFECYCLE_UNKNOWN",
                    "Could not determine active position side for reduce action"
                )

    # Price for LIMIT order
    # Quantize price to tick size
    price_dec = close_price_dec.quantize(instrument.tick_size)

    # Create intent correlation IDs
    ident = re.sub(r"[^a-z0-9_]", "", decision.agent_id.lower()) + "_" + str(now_ms)[-8:]
    intent_id = f"intent_ds_{ident}"
    trace_id = f"trace_ds_{ident}"
    idempotent_key = f"idempotent_ds_{ident}"

    order_block = {
        "qty": str(qty_dec),
        "reduce_only": reduce_only,
        "order_type": config.default_order_type,
        "price": str(price_dec) if config.default_order_type == "LIMIT" else None,
        "tif": config.default_time_in_force if config.default_order_type == "LIMIT" else None,
    }

    intent_payload = {
        "rid": intent_id,
        "symbol": decision.symbol,
        "instrument": decision.symbol,
        "side": side,
        "strategy": decision.agent_id,
        "strategy_id": decision.agent_id,
        "decision_id": f"decision_{ident}",
        "intent_id": intent_id,
        "order": order_block,
        "reduce_only": reduce_only,
        "valid_for_ms": 120000,  # 2 minutes
        "idempotent_key": idempotent_key,
        "trace": {
            "trace_id": trace_id,
            "session_id": config.session_id,
            "packet_ref": decision.packet_ref,
        },
        "tca_budget": {
            "max_slippage_bps": 50,
            "max_latency_ms": 3000,
            "maker_preference": "neutral",
        },
        "risk_context": {
            "trade_cvar95_bps": 100,
            "risk_score": 0.5,
        }
    }

    return intent_payload
