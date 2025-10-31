#!/usr/bin/env python3
"""
Aurora Core Main Application

Demonstrates the complete Aurora Core FSM federation with all 5 domains:
- market_data: Receives market ticks from Binance WebSocket
- feature_engineering: Calculates trading features from market data
- risk_management: Assesses risk levels for positions
- position_tracking: Tracks portfolio state and P&L
- decision_making: Generates trade intents based on all inputs

Run with: python apps/reference/main.py
Set LOG_LEVEL environment variable to control logging:
- LOG_LEVEL=DEBUG - Show all messages including debug
- LOG_LEVEL=INFO (default) - Show info, warning, error messages
- LOG_LEVEL=WARNING - Show only warnings and errors
- LOG_LEVEL=ERROR - Show only errors
"""

import json
import logging
import sys
import time
import os
from pathlib import Path
from typing import Any
from logging.handlers import RotatingFileHandler

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add project root to path for imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message

# Import domain classes
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.account_observer.account_observer import AccountObserver
from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import SnapshotScheduler
from apps.reference.domains.execution_position.fsm import ExecPosFSM

# Import config loader
from apps.reference.config_loader import ConfigLoader


# Local FSMCore mock has been removed. The real FSMCore from vfoundation is now used.

# JSON Formatter for structured logging
class JSONFormatter(logging.Formatter):
    """JSON formatter for structured event chain logging."""

    def format(self, record):
        # Extract extra fields from record
        extra_fields = {}
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                              'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                              'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                              'thread', 'threadName', 'processName', 'process', 'message']:
                    extra_fields[key] = value

        # Create structured log entry
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add extra fields
        log_entry.update(extra_fields)

        return json.dumps(log_entry, default=str, ensure_ascii=False)

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

# Global FSM instance
fsm: FSMCore | None = None
execution_position: ExecPosFSM | None = None

# Create logs directory if it doesn't exist
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, log_level, logging.INFO))

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(getattr(logging, log_level, logging.INFO))
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
console_handler.setFormatter(console_formatter)
console_handler.stream.reconfigure(encoding='utf-8')  # type: ignore
root_logger.addHandler(console_handler)

# File handler for detailed logs
log_file = logs_dir / "aurora_core.log"
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)  # Log everything to the file
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

# Domain-specific log handlers
domain_handlers = {}

# Feature Engineering domain logs
fe_log_file = logs_dir / "domain_feature_engineering.log"
fe_handler = RotatingFileHandler(fe_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
fe_handler.setLevel(logging.DEBUG)
fe_handler.setFormatter(file_formatter)
fe_handler.addFilter(lambda record: 'feature_engineering' in record.name)
domain_handlers['feature_engineering'] = fe_handler
root_logger.addHandler(fe_handler)

# Risk Management domain logs
rm_log_file = logs_dir / "domain_risk_management.log"
rm_handler = RotatingFileHandler(rm_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
rm_handler.setLevel(logging.DEBUG)
rm_handler.setFormatter(file_formatter)
rm_handler.addFilter(lambda record: 'risk_management' in record.name)
domain_handlers['risk_management'] = rm_handler
root_logger.addHandler(rm_handler)

# Decision Making domain logs
dm_log_file = logs_dir / "domain_decision_making.log"
dm_handler = RotatingFileHandler(dm_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
dm_handler.setLevel(logging.DEBUG)
dm_handler.setFormatter(file_formatter)
dm_handler.addFilter(lambda record: 'decision_making' in record.name)
domain_handlers['decision_making'] = dm_handler
root_logger.addHandler(dm_handler)

# Execution Management domain logs
em_log_file = logs_dir / "domain_execution_management.log"
em_handler = RotatingFileHandler(em_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
em_handler.setLevel(logging.DEBUG)
em_handler.setFormatter(file_formatter)
em_handler.addFilter(lambda record: 'execution_position' in record.name)
domain_handlers['execution_management'] = em_handler
root_logger.addHandler(em_handler)

# Position Tracking domain logs
pt_log_file = logs_dir / "domain_position_tracking.log"
pt_handler = RotatingFileHandler(pt_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
pt_handler.setLevel(logging.DEBUG)
pt_handler.setFormatter(file_formatter)
pt_handler.addFilter(lambda record: 'position_tracking' in record.name)
domain_handlers['position_tracking'] = pt_handler
root_logger.addHandler(pt_handler)

# Event Chain structured logs (JSON format)
chain_log_file = logs_dir / "event_chain.log"
chain_handler = RotatingFileHandler(chain_log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
chain_handler.setLevel(logging.INFO)
json_formatter = JSONFormatter()
chain_handler.setFormatter(json_formatter)
chain_handler.addFilter(lambda record: hasattr(record, 'rid') or record.name == 'event_chain')
domain_handlers['event_chain'] = chain_handler
root_logger.addHandler(chain_handler)

LOG = logging.getLogger("AuroraCore")


def on_trade_intent_proposed(event: Any) -> None:
    """
    Listens for trade intents from the decision_making domain and transforms
    them into executable commands for the execution_position domain.
    
    Bridge pattern: EVT:TRADE_INTENT_PROPOSED → CMD:OPEN
    - Preserves XAI chain via why field
    - Maps analytical output to execution command
    - Shadow mode: execution_position processes but doesn't execute
    """
    LOG.info("🔥🔥🔥 BRIDGE: on_trade_intent_proposed CALLED! 🔥🔥🔥")
    LOG.info(
        f"BRIDGE: Received TRADE_INTENT_PROPOSED rid={event.pld.get('rid')} for {event.pld.get('instrument', 'unknown')} "
        f"with side {event.pld.get('side', 'unknown')}. Transforming to CMD:OPEN."
    )

    # Check for forbidden LIMIT entry
    order_details = event.pld.get("order", {})
    if order_details.get("order_type") == "LIMIT":
        LOG.error("BRIDGE: LIMIT entry forbidden. Only MARKET entry allowed.")
        return

    # Transform EVT to CMD
    # Extract order details from nested structure
    order_details = event.pld.get("order", {})
    
    command_payload = {
        "rid": event.pld.get("rid"),  # Pass through request ID for tracing
        "symbol": event.pld.get("instrument"),  # Map 'instrument' to 'symbol'
        "side": event.pld.get("side"),
        "qty": order_details.get("qty"),  # Get qty from order.qty (as string)
        "price": order_details.get("price"),  # Get price from order.price (as string)
        "order_type": "LIMIT",  # Use LIMIT orders with specified price
        "tif": "GTC",  # Good-Till-Cancel
        "idempotent_key": event.pld.get("idempotent_key"),  # Pass through for deduplication (AURORA_IDEMPOTENCY_V1)
        "price_ref": order_details.get("price_ref"),  # Pass current market price for min_notional checks
    }

    LOG.debug(f"BRIDGE: CMD:OPEN payload being sent: {command_payload}")
    LOG.info(f"BRIDGE: Idempotent key passed through: {command_payload.get('idempotent_key')}")

    # Preserve XAI chain: take first why from event payload, or fallback
    event_why_chain = event.pld.get("why", [])
    bridge_why = event_why_chain[0] if event_why_chain else "Execute trade intent from decision"

    # Create Message for CMD:OPEN
    # RID will be auto-generated by Message, linking to event.rid via span_id
    open_command = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",  # Source is decision_making
        dst="execution_position",
        parent_span_id=event.span_id,  # Link to parent event for tracing
        why=bridge_why,  # Preserve XAI chain from decision
        pld=command_payload,
    )

    LOG.info(f"BRIDGE: Dispatched CMD:OPEN with rid={open_command.rid}, parent_span={event.span_id}")

    # Handle the command with execution_position FSM
    if execution_position is not None:
        result = execution_position.handle(open_command)
        if result:
            LOG.info(f"BRIDGE: Execution FSM processed CMD:OPEN, result: {result.op}:{result.verb}")
            if result.op == "ERR":
                LOG.error(f"BRIDGE: Execution rejected - why={result.why}, pld={result.pld}")
        else:
            LOG.info("BRIDGE: Execution FSM processed CMD:OPEN, no decision emitted")
    else:
        LOG.error("BRIDGE: execution_position FSM not initialized")


def debug_event_listener(event: Any) -> None:
    """
    Debug listener to see all events flowing through the system.
    """
    print(f"📡 EVENT: {event.op}:{event.verb} from {event.src} - {event.why}")
    if hasattr(event, 'pld') and event.pld:
        # Only show key fields for market data to avoid spam
        if event.verb == "MARKET_TICK_RECEIVED":
            pld = event.pld
            print(f"   📊 {pld.get('symbol')} bid={pld.get('bid')} ask={pld.get('ask')}")
        elif event.verb in ["FEATURES_CALCULATED", "RISK_ASSESSMENT_COMPLETED", "PORTFOLIO_STATE_UPDATED"]:
            print(f"   📊 {event.verb} for {event.pld.get('symbol', 'unknown')}")
        elif event.verb == "TRADE_INTENT_PROPOSED":
            order_details = event.pld.get("order", {})
            quantity = order_details.get("qty", "None")
            order_details.get("price", "None")
            trade_info = f"   🎯 TRADE INTENT: {event.pld.get('side')} {quantity} {event.pld.get('instrument')}"
            print(trade_info)
            
            # Log formatted trade info to formatted log file (exactly as shown in console)
            # Note: Structured logging handled by AuroraLogAdapter in execution_position/fsm.py
            trade_formatted_logger = logging.getLogger('aurora.trade_formatted')
            trade_formatted_logger.info(trade_info)


def initialize_domains(config: dict[str, Any]) -> FSMCore:
    """Initialize all application domains and wire them up."""
    global fsm, execution_position
    
    LOG.info("Initializing Aurora Core domains...")
    
    # 1. Create the central FSMCore instance
    fsm = FSMCore()

    # 2. Initialize EXECUTION POSITION FSM FIRST (before market_data triggers trade intents)
    # This ensures execution_position is ready when on_trade_intent_proposed is called
    config_dict = config
    execution_position = ExecPosFSM(config=config_dict, fsm=fsm)
    LOG.info("✅ Execution position FSM initialized first")

    # 3. Initialize other domains
    # Note: This replay() function is legacy code, may need full config refactoring
    market_data = MarketDataConnector(fsm, config_dict)  # Pass full config
    feature_engineering = FeatureEngineering(fsm, config_dict.get("trading", {}))
    risk_management = RiskManagement(fsm, config_dict.get("trading", {}))  # ПЕРЕДАТИ trading секцію для доступу до risk конфігурації
    position_tracking = PositionTracking(fsm, config_dict.get("system", {}))
    decision_making = DecisionMaking(fsm, config_dict)  # ПЕРЕДАТИ ПОВНИЙ СЛОВНИК для доступу до symbols_to_track
    account_balance = AccountConnector(fsm, config_dict)
    account_observer = AccountObserver(fsm, config_dict)
    snapshot_scheduler = SnapshotScheduler(fsm, config_dict)

    # 4. Register domains in the FSM core for inter-domain communication if needed
    fsm.register_domain("market_data", market_data)
    fsm.register_domain("feature_engineering", feature_engineering)
    fsm.register_domain("risk_management", risk_management)
    fsm.register_domain("position_tracking", position_tracking)
    fsm.register_domain("decision_making", decision_making)
    fsm.register_domain("account_balance", account_balance)
    fsm.register_domain("account_observer", account_observer)
    fsm.register_domain("snapshot_scheduler", snapshot_scheduler)
    fsm.register_domain("execution_position", execution_position)

    LOG.info("All domains initialized and registered.")
    return fsm


def main() -> None:
    """Main application entry point."""
    LOG.info("Starting Aurora Core...")

    # Step 1: Load configuration
    LOG.info("Loading configuration...")
    # ConfigLoader accepts config_dir parameter (path to aurora configs)
    config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
    config = config_loader.load_config()
    LOG.info("Configuration loaded successfully")

    # Step 2: Initialize FSM Core
    LOG.info("Initializing FSM Core...")
    global fsm
    fsm = FSMCore()

    # Step 3: Initialize all domain components FIRST
    LOG.info("Initializing domain components...")
    fsm = initialize_domains(config.to_dict())

    # Step 4: Create event listeners AFTER domains are initialized
    LOG.info("Setting up event listeners...")
    fsm.listen("EVT:TRADE_INTENT_PROPOSED", on_trade_intent_proposed)

    # Add debug listener for all events (optional, can be removed for production)
    debug_events = [
        "EVT:MARKET_TICK_RECEIVED",
        "EVT:FEATURES_CALCULATED",
        "EVT:RISK_ASSESSMENT_COMPLETED",
        "EVT:PORTFOLIO_STATE_UPDATED",
        "EVT:TRADE_INTENT_PROPOSED"
    ]
    for event_name in debug_events:
        fsm.listen(event_name, debug_event_listener)

    # Step 5: Start all components
    LOG.info("Starting market data connector...")
    market_data = fsm.get_domain("market_data")
    market_data.start()

    LOG.info("Starting account connector...")
    account_balance = fsm.get_domain("account_balance")
    account_balance.start()

    LOG.info("Starting account observer...")
    account_observer = fsm.get_domain("account_observer")
    account_observer.start()

    LOG.info("Starting market data connector...")
    market_data.start()

    LOG.info("Starting feature engineering...")
    feature_engineering = fsm.get_domain("feature_engineering")
    feature_engineering.start()

    LOG.info("Starting risk management...")
    risk_management = fsm.get_domain("risk_management")
    risk_management.start()

    LOG.info("Starting position tracking...")
    position_tracking = fsm.get_domain("position_tracking")
    position_tracking.start()

    LOG.info("Starting decision making...")
    decision_making = fsm.get_domain("decision_making")
    decision_making.start()

    LOG.info("Starting snapshot scheduler (DR)...")
    snapshot_scheduler = fsm.get_domain("snapshot_scheduler")
    snapshot_scheduler.start()

    # Step 5: Keep the application running
    LOG.info("Aurora Core is running... Press Ctrl+C to stop.")
    print("\n" + "="*60)
    print("🌟 AURORA CORE IS ACTIVE 🌟")
    print("Waiting for market data and trade signals...")
    print("Press Ctrl+C to stop the application.")
    print("="*60 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("Shutting down Aurora Core...")
        print("\nShutting down Aurora Core...")

        LOG.info("Shutdown signal received. Stopping all components...")

        # Helper to stop components safely if they exist
        for name in [
            'account_balance', 'account_observer', 'market_data',
            'feature_engineering', 'risk_management', 'position_tracking',
            'decision_making', 'snapshot_scheduler', 'execution_position'
        ]:
            try:
                comp = locals().get(name)
                if comp is not None and hasattr(comp, 'stop'):
                    comp.stop()
                    LOG.info(f"{name} stopped.")
            except Exception as e:
                LOG.error(f"Error stopping {name}: {e}")

        LOG.info("All components stopped or shutdown attempted. Exiting.")
        print("Aurora Core shutdown complete.")


if __name__ == "__main__":
    main()