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

import logging
import sys
import time
import os
from pathlib import Path
from typing import Any
from logging.handlers import RotatingFileHandler

# Add project root to path for imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.account_observer.account_observer import AccountObserver
from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import SnapshotScheduler

# Local FSMCore mock has been removed. The real FSMCore from vfoundation is now used.

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
console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(message)s")
console_handler.setFormatter(console_formatter)
console_handler.stream.reconfigure(encoding="utf-8")  # Fix encoding for Windows
root_logger.addHandler(console_handler)

# File handler for detailed logs
log_file = logs_dir / "aurora_core.log"
file_handler = RotatingFileHandler(
    log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)  # Log everything to the file
file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

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
    LOG.info(
        f"BRIDGE: Received TRADE_INTENT_PROPOSED for {event.pld.get('instrument', 'unknown')} "
        f"with side {event.pld.get('side', 'unknown')}. Transforming to CMD:OPEN."
    )

    # Transform EVT to CMD
    # Extract order details from nested structure
    order_details = event.pld.get("order", {})

    command_payload = {
        "symbol": event.pld.get("instrument"),  # Map 'instrument' to 'symbol'
        "side": event.pld.get("side"),
        "qty": order_details.get("qty"),  # Get qty from order.qty (as string)
        "price": order_details.get("price"),  # Get price from order.price (as string)
        "order_type": "LIMIT",  # Use LIMIT orders with specified price
        "tif": "GTC",  # Good-Till-Cancel
        "idempotent_key": event.pld.get(
            "idempotent_key"
        ),  # Pass through for deduplication (AURORA_IDEMPOTENCY_V1)
        "price_ref": order_details.get(
            "price_ref"
        ),  # Pass current market price for min_notional checks
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

    LOG.info(
        f"BRIDGE: Dispatched CMD:OPEN with rid={open_command.rid}, parent_span={event.span_id}"
    )

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
    if hasattr(event, "pld") and event.pld:
        # Only show key fields for market data to avoid spam
        if event.verb == "MARKET_TICK_RECEIVED":
            pld = event.pld
            print(f"   📊 {pld.get('symbol')} bid={pld.get('bid')} ask={pld.get('ask')}")
        elif event.verb in [
            "FEATURES_CALCULATED",
            "RISK_ASSESSMENT_COMPLETED",
            "PORTFOLIO_STATE_UPDATED",
        ]:
            print(f"   📊 {event.verb} for {event.pld.get('symbol', 'unknown')}")
        elif event.verb == "TRADE_INTENT_PROPOSED":
            order_details = event.pld.get("order", {})
            quantity = order_details.get("qty", "None")
            price = order_details.get("price", "None")
            trade_info = f"   🎯 TRADE INTENT: {event.pld.get('side')} {quantity} {event.pld.get('instrument')}"
            print(trade_info)

            # Log formatted trade info to formatted log file (exactly as shown in console)
            # Note: Structured logging handled by AuroraLogAdapter in execution_position/fsm.py
            trade_formatted_logger = logging.getLogger("aurora.trade_formatted")
            trade_formatted_logger.info(trade_info)


def initialize_domains(config: dict[str, Any]) -> FSMCore:
    """Initialize all application domains and wire them up."""
    global fsm, execution_position

    LOG.info("Initializing Aurora Core domains...")

    # 1. Create the central FSMCore instance
    fsm = FSMCore()

    # 2. Initialize EXECUTION POSITION FSM FIRST (before market_data triggers trade intents)
    # This ensures execution_position is ready when on_trade_intent_proposed is called
    execution_position = ExecPosFSM(fsm=fsm)
    LOG.info("✅ Execution position FSM initialized first")

    # 3. Initialize other domains
    # Note: This replay() function is legacy code, may need full config refactoring
    market_data = MarketDataConnector(fsm, config)  # Pass full config
    feature_engineering = FeatureEngineering(fsm, config.get("feature_engineering", {}))
    risk_management = RiskManagement(fsm, config.get("risk_management", {}))
    position_tracking = PositionTracking(fsm, config.get("position_tracking", {}))
    decision_making = DecisionMaking(fsm, config["decision_making"])
    account_balance = AccountConnector(fsm, config["account_balance"])
    account_observer = AccountObserver(fsm)
    snapshot_scheduler = SnapshotScheduler(fsm)

    # 4. Register domains in the FSM core for inter-domain communication if needed
    # NOTE: Temporarily commented out - register_domain not yet implemented in FSMCore
    # fsm.register_domain("market_data", market_data)
    # fsm.register_domain("feature_engineering", feature_engineering)
    # fsm.register_domain("risk_management", risk_management)
    # fsm.register_domain("position_tracking", position_tracking)
    # fsm.register_domain("decision_making", decision_making)
    # fsm.register_domain("account_balance", account_balance)
    # fsm.register_domain("account_observer", account_observer)
    # fsm.register_domain("snapshot_scheduler", snapshot_scheduler)
    # fsm.register_domain("execution_position", execution_position)

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

    # Step 2: Create event listeners
    LOG.info("Setting up event listeners...")
    fsm.listen("EVT:TRADE_INTENT_PROPOSED", on_trade_intent_proposed)

    # Add debug listener for all events (optional, can be removed for production)
    debug_events = [
        "EVT:MARKET_TICK_RECEIVED",
        "EVT:FEATURES_CALCULATED",
        "EVT:RISK_ASSESSMENT_COMPLETED",
        "EVT:PORTFOLIO_STATE_UPDATED",
        "EVT:TRADE_INTENT_PROPOSED",
    ]
    for event_name in debug_events:
        fsm.listen(event_name, debug_event_listener)

    # Step 3: Initialize all domain components
    LOG.info("Initializing domain components...")

    # Account Connector (source of account balance and positions)
    account_balance = AccountConnector(fsm=fsm, config=config)

    # Account Observer (observes trades and sends portfolio updates)
    account_observer = AccountObserver(fsm=fsm, config=config.to_dict())

    # Market Data Connector (source of market ticks)
    # Pass full config dict to access both system.yaml (trading section) and use_testnet
    market_data = MarketDataConnector(fsm=fsm, config=config.to_dict())

    # Feature Engineering (calculates trading features)
    feature_engineering = FeatureEngineering(fsm=fsm, config=config.trading)

    # Risk Management (assesses position risk)
    risk_management = RiskManagement(fsm=fsm, config=config.system)

    # Position Tracking (tracks portfolio state)
    position_tracking = PositionTracking(fsm=fsm, config=config.system)

    # ==========================================
    # DR: DISASTER RECOVERY STATE RESTORATION
    # ==========================================
    LOG.info("--- Starting Disaster Recovery Check ---")

    from apps.reference.dr_loader import find_latest_snapshot, replay_wal_after
    import json

    snapshot_dir_path = str(project_root / "ops" / "snapshots")
    wal_dir_path = str(project_root / "ops" / "wal")

    latest_snapshot_path = find_latest_snapshot(snapshot_dir_path)

    if latest_snapshot_path:
        try:
            LOG.info(f"Found latest snapshot: {latest_snapshot_path.name}")

            # Load snapshot data
            with open(latest_snapshot_path, "r", encoding="utf-8") as f:
                snapshot_data = json.load(f)

            # Restore state from snapshot
            if position_tracking.load_snapshot(snapshot_data):
                LOG.info("✅ Successfully loaded state from snapshot")
                LOG.info(f"   Snapshot timestamp: {snapshot_data.get('timestamp_utc', 'unknown')}")
                LOG.info(
                    f"   Positions restored: {snapshot_data.get('metadata', {}).get('positions_count', 0)}"
                )

                # Replay WAL entries after snapshot
                snapshot_ts = snapshot_data.get("timestamp_utc")
                if snapshot_ts:
                    LOG.info("Replaying WAL entries after snapshot...")
                    replayed_count = replay_wal_after(wal_dir_path, snapshot_ts, position_tracking)
                    LOG.info(f"✅ Replayed {replayed_count} events from WAL")
                else:
                    LOG.warning("Snapshot missing timestamp_utc field, cannot replay WAL")
            else:
                LOG.warning(f"⚠️ Failed to restore state from snapshot: {latest_snapshot_path.name}")
                LOG.info("Starting with empty state.")

        except Exception as e:
            LOG.error(f"Error during disaster recovery: {e}. Starting with empty state.")
            import traceback

            LOG.debug(traceback.format_exc())
    else:
        LOG.warning("No snapshot found. Starting with a clean state.")

    LOG.info("--- Disaster Recovery Check Finished ---")

    # Decision Making (generates trade intents)
    LOG.info(f"DEBUG: config type before to_dict: {type(config)}")
    LOG.info(f"DEBUG: config.to_dict() type: {type(config.to_dict())}")
    LOG.info(f"DEBUG: config.to_dict() keys: {list(config.to_dict().keys())}")
    decision_making = DecisionMaking(fsm=fsm, config=config.to_dict())

    # Execution Position (already initialized in initialize_domains())

    # Register all domains in FSM core for cross-domain access
    # NOTE: Temporarily commented out - register_domain not yet implemented in FSMCore
    # fsm.register_domain('account_balance', account_balance)
    # fsm.register_domain('account_observer', account_observer)
    # fsm.register_domain('market_data', market_data)
    # fsm.register_domain('feature_engineering', feature_engineering)
    # fsm.register_domain('risk_management', risk_management)
    # fsm.register_domain('position_tracking', position_tracking)
    # fsm.register_domain('decision_making', decision_making)
    # fsm.register_domain('execution_position', execution_position)

    # Initialize Snapshot Scheduler (DR - Phase L4)
    LOG.info("Initializing snapshot scheduler (DR)...")
    snapshot_scheduler_config = {
        "interval_sec": 30,  # 30 seconds for testing (production: 300)
        "snapshot_dir": "ops/snapshots",
        "domains": ["position_tracking"],  # Start with position_tracking only
    }
    snapshot_scheduler = SnapshotScheduler(fsm=fsm, config=snapshot_scheduler_config)
    # fsm.register_domain('snapshot_scheduler', snapshot_scheduler)

    # Step 4: Start all components
    LOG.info("Starting account connector...")
    account_balance.start()

    LOG.info("Starting account observer...")
    account_observer.start()

    LOG.info("Starting market data connector...")
    market_data.start()

    LOG.info("Starting feature engineering...")
    feature_engineering.start()

    LOG.info("Starting risk management...")
    risk_management.start()

    LOG.info("Starting position tracking...")
    position_tracking.start()

    LOG.info("Starting decision making...")
    decision_making.start()

    LOG.info("Starting snapshot scheduler (DR)...")
    snapshot_scheduler.start()

    # Step 5: Keep the application running
    LOG.info("Aurora Core is running... Press Ctrl+C to stop.")
    print("\n" + "=" * 60)
    print("🌟 AURORA CORE IS ACTIVE 🌟")
    print("Waiting for market data and trade signals...")
    print("Press Ctrl+C to stop the application.")
    print("=" * 60 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("Shutting down Aurora Core...")
        print("\nShutting down Aurora Core...")

        LOG.info("Shutdown signal received. Stopping all components...")

        # Helper to stop components safely if they exist
        for name in [
            "account_balance",
            "account_observer",
            "market_data",
            "feature_engineering",
            "risk_management",
            "position_tracking",
            "decision_making",
            "snapshot_scheduler",
            "execution_position",
        ]:
            try:
                comp = locals().get(name)
                if comp is not None and hasattr(comp, "stop"):
                    comp.stop()
                    LOG.info(f"{name} stopped.")
            except Exception as e:
                LOG.error(f"Error stopping {name}: {e}")

        LOG.info("All components stopped or shutdown attempted. Exiting.")
        print("Aurora Core shutdown complete.")


if __name__ == "__main__":
    main()
