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

from apps.reference.bootstrap.preflight import check_hybrid_coherence  # NEW IMPORT
from apps.reference.config_loader import ConfigLoader, AuroraConfig
from apps.reference.config_contract import ConfigContractError
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.retry_scheduler import RetryScheduler
# from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import (
#     SnapshotScheduler,
# )

from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)
from apps.reference.domains.data_recorder.recorder import CsvRecorder
# FSMP-ARCH-01: Import both MarketDataConnector and MarketDataProxy
# The actual class used is determined by feature flag at runtime
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.market_data.proxy import MarketDataProxy
from apps.reference.domains.market_data.bar_aggregator import BarAggregator  # BAR-SSOT-002
# TASK32: Strategy plugin allowlist (no dynamic imports)
from apps.reference.domains.strategies.registry import StrategyPluginRegistry, StrategyRuntime
from apps.reference.domains.strategies.plugins.aurora_builtin import AuroraBuiltinPlugin
from apps.reference.domains.strategies.plugins.mean_reversion import MeanReversionPlugin
from apps.reference.domains.strategies.plugins.md_amr import MDAMRPlugin
from apps.reference.domains.strategies.plugins.llm_microstructure import LlmMicrostructurePlugin
from apps.reference.domains.execution_position.order_guardian import OrderGuardian
from apps.reference.domains.shadow_telemetry.main_bridge import (
    LLMIntentIngressBridge,
    ShadowEventTapPublisher,
    register_llm_command_mapper,
)
from vfoundation.core.protocol import truncate_why
from vfoundation.dr.wal_gc import WALGarbageCollector
from vfoundation.dr import wal
from apps.reference.telemetry.alerts import AlertManager
from vfoundation.core.fsm_emit_compat import emit_compat
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
import json
import hashlib
import random
import logging
import sys
import time
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import asyncio

# TASK-EXF-WIRE-STARTUP-09: Startup Guard Imports
from apps.reference.domains.exchange_filters.validator import validate_instruments_on_startup, FilterMismatchError
from apps.reference.adapters.binance_adapter import BinanceAdapter
from typing import Any, Optional
from logging.handlers import RotatingFileHandler
import threading
import concurrent.futures

# Add project root to path for imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


def _run_async_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Run the shared asyncio loop in a dedicated thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


# Import domain classes

# Import telemetry

# Import config loader


# AuroraBridge and global handlers removed (BRIDGE-SUNSET-01).
# TRADE_INTENT_PROPOSED is now handled directly by ExecPosFSM.

# NOTE: JSONFormatter and logging configuration moved to logging_setup.py (CFG-OBS-001)
# Full logging setup is called after config load via setup_logging()


def _perform_alert_checks(alert_manager: AlertManager, wal_dir: Path, config: AuroraConfig) -> None:
    """Perform periodic system health checks and raise alerts if needed."""
    # Check WAL size
    try:
        wal_files = list(wal_dir.glob("*.wal"))
        total_wal_size_mb = sum(
            f.stat().st_size for f in wal_files) / (1024 * 1024)
        alert_manager.check_wal_size(total_wal_size_mb)
    except Exception as e:
        LOG.error(f"Error checking WAL size: {e}")

    # Check circuit breaker status (placeholder - would need actual CB state)
    # For now, just check if we have any active alerts as proxy
    alert_stats = alert_manager.get_alert_stats()
    if alert_stats["active_alerts"] > 5:
        # Assume CB active if many alerts
        alert_manager.check_circuit_breaker(True, 300)

    # Check entropy spike (NEW)
    # Note: entropy_monitor is initialized in initialize_domains()
    # This function is called from guardian_loop which runs after domains are initialized
    try:
        # Use globals().get() to safely access entropy_monitor
        em = globals().get('entropy_monitor')
        if em is not None:
            spike_detected, reason = em.detect_spike()
            if spike_detected:
                alert_manager.trigger_alert(
                    severity="CRITICAL",
                    message=f"System anomaly detected: {reason}",
                    context=em.get_metrics()
                )
                LOG.critical(f"🚨 ENTROPY SPIKE: {reason}")
    except Exception as e:
        LOG.error(f"Error checking entropy: {e}")

    # Check risk gate (placeholder - would need actual risk metrics)
    # This would typically come from risk_management domain
    # alert_manager.check_risk_gate(current_risk_percent)

    LOG.debug(f"Alert checks completed: {alert_stats}")


# Global FSM instance
fsm: FSMCore | None = None
execution_position: ExecPosFSM | None = None

# ============================================================================
# LOGGING SETUP (CFG-OBS-001)
# ============================================================================
# Bootstrap logging: minimal console setup for early startup messages.
# Full config-based logging is set up after config load via setup_logging().
# ============================================================================

# Create logs directory early (needed for early file handlers if any)
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Bootstrap logger: minimal setup before config is loaded
# This will be reconfigured by setup_logging(config) after config load.
_bootstrap_logging_done = False


def _setup_bootstrap_logging() -> None:
    """Minimal logging for startup (before config is loaded)."""
    global _bootstrap_logging_done
    if _bootstrap_logging_done:
        return

    # Bootstrap log level from env (before config is loaded)
    bootstrap_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, bootstrap_level, logging.INFO))

    # Check if already configured (by tests or previous import)
    if any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        _bootstrap_logging_done = True
        return

    # Minimal console handler for startup
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, bootstrap_level, logging.INFO))
    console.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(message)s"))
    root_logger.addHandler(console)
    _bootstrap_logging_done = True


_setup_bootstrap_logging()

LOG = logging.getLogger("AuroraCore")


def _init_order_index(fsm: FSMCore, config: Any) -> None:
    """App-level wiring for order correlation index used by WS client.

    Kept here (composition root) to avoid coupling vfoundation.core to app domains.
    """
    from apps.reference.domains.execution_position.order_index import OrderIndex

    ttl_sec: int | None = None

    # Prefer strict, typed config (YAML -> resolvers -> Pydantic)
    try:
        ttl_raw = config.domains.execution_position.order_index.ttl_sec
        ttl_sec = int(ttl_raw)
    except Exception:
        pass

    # Fallback to dict-style config (legacy bootstrap paths)
    if ttl_sec is None and isinstance(config, dict):
        domains = config.get("domains")
        execpos = domains.get("execution_position") if isinstance(
            domains, dict) else None
        oi_cfg = execpos.get("order_index") if isinstance(
            execpos, dict) else None
        if isinstance(oi_cfg, dict) and "ttl_sec" in oi_cfg:
            ttl_sec = int(oi_cfg["ttl_sec"])

    if ttl_sec is None:
        raise ValueError(
            "OrderIndex wiring fail-closed: missing required config path "
            "domains.execution_position.order_index.ttl_sec"
        )
    if ttl_sec <= 0:
        raise ValueError(
            "OrderIndex wiring fail-closed: invalid domains.execution_position.order_index.ttl_sec "
            f"(must be int > 0, got {ttl_sec})"
        )

    fsm.order_index = OrderIndex(ttl_sec=ttl_sec)  # type: ignore[attr-defined]
    LOG.info(f"✅ OrderIndex wired into FSMCore (ttl_sec={ttl_sec})")


def debug_event_listener(event: Any) -> None:
    """
    Debug listener to see all events flowing through the system.
    """
    print(f"📡 EVENT: {event.op}:{event.verb} from {event.src} - {event.why}")
    if hasattr(event, "pld") and event.pld:
        # Only show key fields for market data to avoid spam
        if event.verb == "MARKET_TICK_RECEIVED":
            pld = event.pld
            print(
                f"   📊 {pld.get('symbol')} bid={pld.get('bid')} ask={pld.get('ask')}"
            )
        elif event.verb in [
            "FEATURES_CALCULATED",
            "RISK_ASSESSMENT_COMPLETED",
            "PORTFOLIO_STATE_UPDATED",
        ]:
            print(f"   📊 {event.verb} for {event.pld.get('symbol', 'unknown')}")
        elif event.verb == "TRADE_INTENT_PROPOSED":
            order_details = event.pld.get("order", {})
            quantity = order_details.get("qty", "None")
            order_details.get("price", "None")
            trade_info = f"   🎯 TRADE INTENT: {event.pld.get('side')} {quantity} {event.pld.get('instrument')}"
            print(trade_info)

            # Log formatted trade info to formatted log file (exactly as shown in console)
            # Note: Structured logging handled by AuroraLogAdapter in execution_position/fsm.py
            trade_formatted_logger = logging.getLogger(
                "aurora.trade_formatted")
            trade_formatted_logger.info(trade_info)


def initialize_domains(config: dict[str, Any]) -> FSMCore:
    """Initialize all application domains and wire them up."""
    global fsm, execution_position

    LOG.info("Initializing Aurora Core domains...")

    # 1. Create the central FSMCore instance
    fsm = FSMCore()
    _init_order_index(fsm, config)

    # 2. Initialize EXECUTION POSITION FSM FIRST (before market_data triggers trade intents)
    # This ensures execution_position is ready when on_trade_intent_proposed is called
    config_dict = config
    execution_position = ExecPosFSM(config=config_dict, fsm=fsm)
    LOG.info("✅ Execution position FSM initialized first")

    # 3. Initialize other domains
    # Note: This replay() function is legacy code, may need full config refactoring
    market_data = MarketDataConnector(fsm, config_dict)  # Pass full config
    feature_engineering = FeatureEngineering(
        fsm, config_dict.get("trading", {}))
    risk_management = RiskManagement(fsm, config_dict.get("system", {}))
    position_tracking = PositionTracking(fsm, config_dict.get("system", {}))
    # NOTE: Legacy unused initialization (line 1718 is the actual one used)
    decision_making = DecisionMaking(fsm, config_dict.get("trading", {}))
    account_balance = AccountConnector(fsm, config_dict)
    # account_observer = AccountObserver(fsm, config_dict) (Deleted: TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
    # RegimeDetector: Analyzes market features to detect trading regimes
    # Emits EVT:REGIME_DETECTED for decision_making to use
    regime_detector = RegimeDetector(config_dict, fsm)
    # snapshot_scheduler = SnapshotScheduler(fsm, config_dict)  # Moved to main()

    # 4. Register domains in the FSM core for inter-domain communication if needed
    fsm.register_domain("market_data", market_data)
    fsm.register_domain("feature_engineering", feature_engineering)
    fsm.register_domain("risk_management", risk_management)
    fsm.register_domain("position_tracking", position_tracking)
    fsm.register_domain("decision_making", decision_making)
    fsm.register_domain("account_balance", account_balance)
    # fsm.register_domain("account_observer", account_observer) (Deleted: TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
    fsm.register_domain("regime_detector", regime_detector)
    # fsm.register_domain("snapshot_scheduler", snapshot_scheduler)  # Moved to main()
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

    # Step 1.5: Setup full logging from observability.yaml (CFG-OBS-001)
    from apps.reference.logging_setup import setup_logging
    setup_logging(config, logs_dir=logs_dir)

    # PHASE 2: METADATA ACTIVATION - Log config versions at startup (PURGE-DIRTY-DOZEN)
    sys_ver = getattr(config.system_meta,
                      'system_config_version', None) or 'N/A'
    regime_ver = getattr(config.system_meta,
                         'regime_config_version', None) or 'N/A'
    LOG.info(f"📋 Config Versions: system={sys_ver}, regime={regime_ver}")
    LOG.info(f"📋 Trading Mode: {config.trading_mode}")

    # TASK-EXF-WIRE-STARTUP-09: Validate Instruments vs Exchange
    if config.system.validate_instruments_on_startup:
        async def _startup_validation():
            LOG.info("🛡️ STARTUP GUARD: Validating exchange filters...")

            # Use testnet if executing in testnet (Hybrid or Pure Testnet)
            is_testnet = (
                config.trading_mode == "testnet" or
                config.trading_mode == "hybrid_live_data_testnet_exec"
            )

            # Force-disable warn_only in LIVE/PRODUCTION to ensure safety
            # If we are in live/production, we MUST crash on filter mismatch.
            warn_only = config.system.warn_only_filters
            if config.trading_mode in ("live", "production") and warn_only:
                LOG.warning(
                    "⚠️ SECURITY: warn_only_filters=True ignored in LIVE/PROD mode. Enforcing FAIL-CLOSED.")
                warn_only = False

            api_cfg = config.binance_api.testnet if is_testnet else config.binance_api.live

            # Create temporary adapter for validation
            adapter = BinanceAdapter(
                api_key=api_cfg.api_key or "",
                api_secret=api_cfg.api_secret or "",
                testnet=is_testnet,
                logger=LOG
            )

            # Convert Pydantic models back to raw dicts for validator consumption
            instruments_raw = {
                k: v.model_dump() for k, v in config.instruments.items()
            }

            try:
                await validate_instruments_on_startup(
                    adapter=adapter,
                    instruments_config={"instruments": instruments_raw},
                    mode="testnet" if is_testnet else "live",
                    warn_only=warn_only
                )
            except FilterMismatchError as e:
                LOG.critical(
                    f"🛑 STARTUP BLOCKED: Exchange Filter Mismatch!\n{e}")
                sys.exit(1)
            except Exception as e:
                LOG.critical(f"🛑 STARTUP BLOCKED: Validation error: {e}")
                sys.exit(1)
            finally:
                # Cleanup adapter resources if possible
                if hasattr(adapter, "close"):
                    await adapter.close()

        # Run validation in temporary loop
        try:
            asyncio.run(_startup_validation())
        except SystemExit:
            raise
        except Exception as e:
            LOG.critical(f"Async loop error during filter validation: {e}")
            sys.exit(1)

    # Initialize WAL Garbage Collector
    wal_dir = project_root / "ops" / "wal"
    wal_gc = WALGarbageCollector(
        wal_dir=wal_dir,
        retention_days=7,
        max_file_size_mb=100,
        logger=LOG
    )
    wal_gc_thread = wal_gc.start_background_gc(
        interval_sec=3600)  # Run every hour
    LOG.info("✅ WAL Garbage Collector initialized")

    # Initialize Multi-TF Feature Aggregation Scheduler
    from threading import Thread
    import time as time_module

    # Initialize Alert Manager
    alert_manager = AlertManager(config=config, logger=LOG)
    LOG.info("✅ Alert Manager initialized")

    # Initialize EntropyMonitor for system anomaly detection
    from vfoundation.obs.entropy_monitor import EntropyMonitor
    entropy_monitor = EntropyMonitor(
        window_sec=60,  # 1-minute sliding window
        volume_threshold=100,  # Alert if >100 events/min
        error_rate_threshold=0.5  # Alert if >50% errors
    )
    LOG.info("✅ EntropyMonitor initialized")

    # FSMP-P3-T01: Pre-flight check for hybrid coherence
    is_coherent, reasons = check_hybrid_coherence(config)
    if not is_coherent:
        LOG.critical(
            f"🚨 CRITICAL: Hybrid mode is incoherent. Trading will be deferred. Reasons: {'; '.join(reasons)}"
        )
        # In a real scenario, this would trigger a system-wide deferral or shutdown.
        # For now, we just log and continue, assuming downstream components will handle deferral.
        # TODO: Implement a global deferral mechanism or graceful shutdown here.

    # Step 2: Initialize FSM Core
    LOG.info("Initializing FSM Core...")
    global fsm
    fsm = FSMCore()
    _init_order_index(fsm, config)

    shadow_event_tap_publisher: ShadowEventTapPublisher | None = None
    llm_intent_ingress_bridge: LLMIntentIngressBridge | None = None

    # Wrap FSMCore.emit to track events with EntropyMonitor
    original_emit = fsm.emit

    def emit_with_monitoring(event_name: str, payload: dict, why: str, data_ref=None):
        """Emit with entropy monitoring"""
        why_short = truncate_why(str(why), 80) or str(event_name)

        # Track event for anomaly detection
        from vfoundation.core.protocol import Message
        tracking_msg = Message(
            op=event_name.split(":")[0] if ":" in event_name else "EVT",
            verb=event_name.split(":")[1] if ":" in event_name else event_name,
            src="fsm_core",
            dst="any",
            pld=payload,
            why=why_short
        )
        entropy_monitor.track_event(tracking_msg)

        # Shadow telemetry mirror (best-effort; fail-closed only when explicitly configured).
        if shadow_event_tap_publisher is not None:
            try:
                shadow_event_tap_publisher.publish(
                    event_name=event_name,
                    payload=payload if isinstance(payload, dict) else {},
                    why=why_short,
                )
            except Exception as tap_exc:
                LOG.error(
                    "Shadow telemetry tap publish failed: %s", tap_exc, exc_info=True
                )

        # Call original emit
        return original_emit(event_name, payload, why_short, data_ref)

    fsm.emit = emit_with_monitoring
    LOG.info("✅ FSMCore initialized with EntropyMonitor tracking")

    # Shadow telemetry bridges (additive-only, config-gated).
    try:
        shadow_cfg = getattr(
            getattr(config, "domains", None), "shadow_telemetry", None)
        if shadow_cfg is not None and bool(getattr(shadow_cfg, "enabled", False)):
            shadow_log = LOG.getChild("shadow_telemetry")
            shadow_event_tap_publisher = ShadowEventTapPublisher(
                cfg=shadow_cfg,
                logger=shadow_log,
            )
            shadow_event_tap_publisher.start()

            llm_intent_ingress_bridge = LLMIntentIngressBridge(
                fsm=fsm,
                config=config,
                logger=shadow_log,
            )
            llm_intent_ingress_bridge.start()
            register_llm_command_mapper(fsm=fsm, logger=shadow_log)

            LOG.info(
                "✅ Shadow telemetry bridges started (tap=%s, ingress=%s)",
                shadow_cfg.ingest.ipc_endpoint,
                shadow_cfg.egress_to_main.ipc_commands_endpoint,
            )
        else:
            LOG.info("ℹ️ Shadow telemetry bridges disabled by config")
    except Exception as shadow_exc:
        LOG.error("Failed to initialize shadow telemetry bridges: %s",
                  shadow_exc, exc_info=True)

    # Step 2: Create event listeners
    LOG.info("Setting up event listeners...")
    # AuroraBridge removed (BRIDGE-SUNSET-01).
    # TRADE_INTENT_PROPOSED is now handled directly by ExecPosFSM.
    # bridge = AuroraBridge(fsm=fsm, config=config, logger=LOG)

    # P2 FIX: Gate debug listener with environment variable to avoid hot-path prints in production
    # Set AURORA_DEBUG_EVENTS=1 to enable debug event logging
    if os.environ.get("AURORA_DEBUG_EVENTS", "0") == "1":
        debug_events = [
            "EVT:MARKET_TICK_RECEIVED",
            "EVT:FEATURES_CALCULATED",
            "EVT:RISK_ASSESSMENT_COMPLETED",
            "EVT:PORTFOLIO_STATE_UPDATED",
            "EVT:TRADE_INTENT_PROPOSED",
        ]
        for event_name in debug_events:
            fsm.listen(event_name, debug_event_listener)
        LOG.info("🐛 Debug event listener ENABLED (AURORA_DEBUG_EVENTS=1)")
    else:
        LOG.debug(
            "Debug event listener DISABLED (set AURORA_DEBUG_EVENTS=1 to enable)")

    # Step 3: Initialize all domain components
    LOG.info("Initializing domain components...")

    # Account Connector (source of account balance and positions)
    account_balance = AccountConnector(fsm=fsm, config=config)

    # Account Observer (observes trades and sends portfolio updates)
    # FSMP-P3-T01: AccountObserver removed (Legacy Spot code).
    # risk_portfolio_source logic preserved if needed for other components but observer init removed.

    # account_observer = AccountObserver(
    #     fsm=fsm, config=config, environment=risk_portfolio_source)

    # FSMP-ARCH-01: Market Data Connector with Multiprocessing Feature Flag
    if config.trading.market_data is None:
        raise ConfigContractError(
            path="trading.market_data",
            why="Missing required config (market_data).",
        )
    use_multiprocessing = bool(config.trading.market_data.use_multiprocessing)

    if use_multiprocessing:
        LOG.info("🚀 Using MarketDataProxy (multiprocessing mode)")
        market_data = MarketDataProxy(fsm=fsm, config=config)
    else:
        LOG.info("📊 Using MarketDataConnector (legacy single-process mode)")
        market_data = MarketDataConnector(fsm=fsm, config=config)

    # Feature Engineering (calculates trading features)
    feature_engineering = FeatureEngineering(
        fsm=fsm, config=config)

    # ==========================================
    # BAR-SSOT-002: BarAggregator as passive observer
    # ==========================================
    bar_aggregator = None
    bar_config = getattr(config.trading.market_data, 'bar_aggregator', None)

    if bar_config is None:
        # CLOSEOUT-BASELINE-001: Explicit why for missing config
        LOG.info(
            "ℹ️ BarAggregator disabled",
            extra={"why": "bar_agg_disabled_missing_config",
                   "reason": "config.trading.market_data.bar_aggregator not defined"}
        )
    elif not bar_config.enabled:
        # CLOSEOUT-BASELINE-001: Explicit why for disabled flag
        LOG.info(
            "ℹ️ BarAggregator disabled",
            extra={"why": "bar_agg_disabled_config",
                   "reason": "bar_aggregator.enabled=false"}
        )
    else:
        # Enabled: validate timeframes and wire
        timeframes = bar_config.timeframes_sec
        if not timeframes:
            LOG.warning(
                "⚠️ BarAggregator enabled but timeframes_sec empty, using defaults [60, 300]",
                extra={"why": "bar_agg_timeframes_default"}
            )
            timeframes = [60, 300]
        bar_aggregator = BarAggregator(
            timeframes_sec=timeframes, emit_fn=fsm.emit)
        fsm.listen("EVT:MARKET_TICK_RECEIVED", bar_aggregator.on_market_tick)
        LOG.info(
            f"✅ BarAggregator enabled",
            extra={"why": "bar_agg_enabled", "timeframes_sec": timeframes}
        )

    # Risk Management (assesses position risk)
    # Task 18: Pass AuroraConfig object directly (Resolves domain_configuration internally via DomainConfigResolver)
    risk_management = RiskManagement(fsm=fsm, config=config)

    # Position Tracking (tracks portfolio state)
    position_tracking = PositionTracking(fsm=fsm, config=config)

    # Execution Position (handles order execution on testnet)
    global execution_position
    execution_position = ExecPosFSM(config=config, fsm=fsm)
    LOG.info("✅ Execution position FSM initialized")

    # ==========================================
    # DR: DISASTER RECOVERY STATE RESTORATION
    # ==========================================
    LOG.info("--- Starting Disaster Recovery Check ---")

    # Initialize components needed for DR (execution_position already initialized in initialize_domains)
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
                LOG.info(
                    f"   Snapshot timestamp: {snapshot_data.get('timestamp_utc', 'unknown')}"
                )
                LOG.info(
                    f"   Positions restored: {snapshot_data.get('metadata', {}).get('positions_count', 0)}"
                )

                # Replay WAL entries after snapshot
                snapshot_ts = snapshot_data.get("timestamp_utc")
                if snapshot_ts:
                    LOG.info("Replaying WAL entries after snapshot...")
                    replayed_count = replay_wal_after(
                        wal_dir_path, snapshot_ts, position_tracking
                    )
                    LOG.info(f"✅ Replayed {replayed_count} events from WAL")

                # ==========================================
                # FSM HYDRATION FROM SNAPSHOT
                # ==========================================
                LOG.info("Hydrating FSMs from restored positions...")
                restored_positions = position_tracking.get_positions()
                hydrated_count = 0
                for symbol, position_data in restored_positions.items():
                    # Reformat data for hydrate method
                    hydrate_data = {
                        "symbol": symbol,
                        "qty": position_data["quantity"],
                        "entry_price": position_data["avg_price"],
                        "side": "BUY" if position_data["quantity"] > 0 else "SELL",
                    }
                    execution_position.hydrate(hydrate_data)
                    hydrated_count += 1
                LOG.info(f"✅ Hydrated {hydrated_count} FSMs.")
                # ==========================================

            else:
                LOG.warning(
                    f"⚠️ Failed to restore state from snapshot: {latest_snapshot_path.name}"
                )
                LOG.info("Starting with empty state.")

        except Exception as e:
            LOG.error(
                f"Error during disaster recovery: {e}. Starting with empty state."
            )
            import traceback

            LOG.debug(traceback.format_exc())
    else:
        LOG.warning("No snapshot found. Starting with a clean state.")

    LOG.info("--- Disaster Recovery Check Finished ---")

    # ==========================================
    # SYNC OPEN ORDERS AND POSITIONS WITH BINANCE
    # ==========================================
    guardian_loop: Optional[asyncio.AbstractEventLoop] = None
    guardian_loop_thread: Optional[threading.Thread] = None

    LOG.info("--- Starting Order/Position Synchronization ---")
    guardian_loop = asyncio.new_event_loop()
    guardian_loop_thread = threading.Thread(
        target=_run_async_loop,
        args=(guardian_loop,),
        name="AuroraAsyncLoop",
        daemon=True,
    )
    execution_position.set_async_loop(guardian_loop)
    guardian_loop_thread.start()

    # ==========================================
    # TASK47c-P3: LEVERAGE BOOTSTRAP (ACTIVE LEVERAGE MANAGEMENT)
    # ==========================================
    # Sync margin mode and leverage with exchange BEFORE trading starts.
    # Failed symbols will be blocked from trading (fail-closed).
    blocked_symbols: set = set()
    try:
        LOG.info("--- Starting Leverage Bootstrap ---")
        future = asyncio.run_coroutine_threadsafe(
            execution_position.run_leverage_bootstrap(),
            guardian_loop
        )
        # 30s timeout for all symbols
        blocked_symbols = future.result(timeout=30.0)
        if blocked_symbols:
            LOG.warning(
                f"TASK47c-P3: Symbols blocked from trading due to leverage sync failure: {blocked_symbols}")
        else:
            LOG.info("TASK47c-P3: Leverage bootstrap completed successfully")
    except Exception as e:
        LOG.error(
            f"TASK47c-P3: Leverage bootstrap failed with exception: {e}. Trading MAY proceed with default settings.")

    # ==========================================
    # IN-FLIGHT RECONCILER (TRUTH DOMAIN REPAIR)
    # ==========================================
    try:
        from apps.reference.domains.inflight_reconcile.reconciler import InFlightReconciler, InFlightStatus
        from apps.reference.domains.inflight_reconcile.config import InFlightConfig

        domains_dict = {}
        try:
            if getattr(config, "domains", None) is not None and hasattr(config.domains, "model_dump"):
                # type: ignore[assignment]
                domains_dict = config.domains.model_dump()
        except Exception:
            domains_dict = {}

        inflight_cfg = InFlightConfig.from_ssot(domains_dict)
        inflight_reconciler = InFlightReconciler(
            config=inflight_cfg, adapter=getattr(execution_position, "adapter", None))

        # Bind ACK/FILL events so the reconciler can track orders without touching execution code.
        def _inflight_on_order_ack(event: "Message") -> None:
            pld = event.pld or {}
            rid = str(pld.get("rid") or event.rid or pld.get(
                "clientOrderId") or pld.get("orderId") or "")
            symbol = pld.get("symbol")
            if not rid or not symbol:
                return
            client_order_id = pld.get(
                "clientOrderId") or pld.get("client_order_id")
            exchange_order_id = str(pld.get("orderId")) if pld.get(
                "orderId") is not None else None
            if not inflight_reconciler.update_order_id(
                rid=rid,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
            ):
                inflight_reconciler.register(
                    rid=rid,
                    symbol=str(symbol),
                    client_order_id=client_order_id,
                    exchange_order_id=exchange_order_id,
                )

        def _inflight_on_order_fill(event: "Message") -> None:
            pld = event.pld or {}
            rid = str(pld.get("rid") or event.rid or pld.get(
                "clientOrderId") or pld.get("orderId") or "")
            if not rid:
                return
            inflight_reconciler.mark_terminal(
                rid=rid,
                status=InFlightStatus.FILLED,
                reason="EVT:ORDER_FILL received",
            )
            inflight_reconciler.clear(rid)

        fsm.listen("EVT:ORDER_ACK", _inflight_on_order_ack)
        fsm.listen("EVT:ORDER_FILL", _inflight_on_order_fill)

        if guardian_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                inflight_reconciler.run_forever(), guardian_loop)
            LOG.info("✅ InFlightReconciler started")
        else:
            LOG.warning(
                "⚠️ InFlightReconciler not started: async loop is not running")
    except Exception as e:
        LOG.warning(f"⚠️ InFlightReconciler disabled (init failed): {e}")

    # RetryScheduler binding restored (PHASE2-DEAD-DEFER-FIX)
    retry_scheduler = None
    try:
        from apps.reference.retry_scheduler import RetryScheduler

        # Config for retry scheduler (use arming config if available)
        try:
            arming_cfg = config.domains.decision_making.arming
            max_attempts = int(getattr(arming_cfg, 'max_attempts', 5))
            retry_backoff_ms = int(
                getattr(arming_cfg, 'retry_backoff_ms', 500))
        except AttributeError:
            max_attempts = 5
            retry_backoff_ms = 500

        retry_scheduler = RetryScheduler(
            fsm=fsm,
            logger=LOG.getChild("RetryScheduler"),
            default_max_attempts=max_attempts,
            min_retry_delay_ms=retry_backoff_ms,
            backoff_factor=2.0,
            jitter_ms=100,
        )

        if guardian_loop is not None and guardian_loop.is_running():
            retry_scheduler.bind_loop(guardian_loop)

            # Listen to EVT:INTENT_DEFERRED and register with scheduler
            def on_intent_deferred(msg):
                """Handler for EVT:INTENT_DEFERRED — forwards to RetryScheduler."""
                try:
                    retry_scheduler.register_deferred(msg.pld)
                except Exception as e:
                    LOG.warning(
                        f"RetryScheduler.register_deferred failed: {e}")

            fsm.listen("EVT:INTENT_DEFERRED", on_intent_deferred)
            LOG.info("✅ RetryScheduler bound (max_attempts=%d, backoff_ms=%d)",
                     max_attempts, retry_backoff_ms)
        else:
            LOG.warning(
                "⚠️ RetryScheduler not bound: async loop is not running")
    except Exception as e:
        LOG.warning(f"⚠️ RetryScheduler disabled (init failed): {e}")

    try:
        sync_fn = getattr(
            execution_position,
            "sync_open_orders_and_positions",
            None,
        )
        if callable(sync_fn):
            sync_future = asyncio.run_coroutine_threadsafe(
                sync_fn(),
                guardian_loop,
            )
            sync_future.result()
        else:
            LOG.info(
                "ExecutionPosition has no sync_open_orders_and_positions(); skipping initial sync"
            )

        LOG.info("Starting OrderGuardian...")
        guardian_start_future = asyncio.run_coroutine_threadsafe(
            execution_position.start_order_guardian(),
            guardian_loop,
        )
        guardian_start_future.result()

        LOG.info("✅ Order/Position synchronization complete")
        LOG.info("✅ OrderGuardian started")
    except Exception as e:
        LOG.error(
            f"❌ Error during order/position sync or OrderGuardian startup: {e}")
        import traceback
        LOG.debug(traceback.format_exc())
    else:
        LOG.debug("OrderGuardian background loop thread running")
    LOG.info("--- Order/Position Synchronization Finished ---")
    LOG.info("--- Order/Position Synchronization Finished ---")

    # Decision Making (generates trade intents) - execution_position already initialized in initialize_domains()
    # CFG-DOMAINS-STEP-02-FIX: Pass AuroraConfig (not dict) to DecisionMaking
    decision_making = DecisionMaking(fsm=fsm, config=config)

    # TASK32: Strategy plugins (allowlist registry) wired in composition root
    strategy_plugins = StrategyPluginRegistry()
    strategy_plugins.register(AuroraBuiltinPlugin())
    strategy_plugins.register(MeanReversionPlugin())
    strategy_plugins.register(MDAMRPlugin())
    # sentinel: bridge-driven via shadow_telemetry
    strategy_plugins.register(LlmMicrostructurePlugin())
    StrategyRuntime(fsm=fsm, config=config, registry=strategy_plugins).start()

    # RegimeDetector: Analyzes market features to detect trading regimes (TREND_UP, TREND_DOWN, etc.)
    # Emits EVT:REGIME_DETECTED which decision_making uses for regime-aware sizing
    regime_detector = RegimeDetector(config=config, fsm=fsm)
    LOG.info("✅ RegimeDetector initialized and subscribed to EVT:FEATURES_CALCULATED")

    # DATA-RECORDER-01: Unified Backtest Recorder
    # Captures [Bar + Features + Regime] into CSVs for offline analysis.
    csv_recorder = CsvRecorder(fsm=fsm, config=config)
    csv_recorder.start()
    LOG.info("✅ CsvRecorder initialized and started")

    # FEATURE-MIRROR: Write live feature snapshots to JSONL
    # for standalone Alpha Search domain consumption
    try:
        from apps.reference.domains.alpha_search.runtime.feature_mirror_writer import FeatureMirrorWriter
        feature_mirror = FeatureMirrorWriter(
            event_bus=fsm,
            symbols=list(config.instruments.keys()
                         ) if config.instruments else None,
        )
        LOG.info(
            "FeatureMirrorWriter activated (feeds Alpha Search standalone domain)")
    except ImportError as e:
        LOG.debug(f"FeatureMirrorWriter not available: {e}")
    except Exception as e:
        LOG.warning(f"FeatureMirrorWriter init failed: {e}")

    # P2 CLEANUP: register_domain calls are now done in initialize_domains()
    # These commented lines preserved for historical reference only:
    # Domain registration moved to initialize_domains() at lines 906-916

    # Initialize Snapshot Scheduler (DR - Phase L4)
    LOG.info("Initializing snapshot scheduler (DR)...")
    snapshot_scheduler_config = {
        "interval_sec": 30,  # 30 seconds for testing (production: 300)
        "snapshot_dir": "ops/snapshots",
        "domains": ["position_tracking"],  # Start with position_tracking only
    }
    # snapshot_scheduler = SnapshotScheduler(
    #     fsm=fsm, config=snapshot_scheduler_config)
    snapshot_scheduler = None  # Temporarily disabled

    # Step 4: Start all components
    LOG.info("Starting account connector...")
    account_balance.start()

    LOG.info("Starting account observer - SKIPPED (Deleted)")
    # account_observer.start()

    LOG.info("Starting market data connector...")
    # MarketDataConnector requires async loop - use guardian_loop
    if guardian_loop is not None and guardian_loop.is_running():
        try:
            market_data_future = asyncio.run_coroutine_threadsafe(
                market_data.start_async(),
                guardian_loop,
            )
            market_data_future.result(timeout=10)  # Wait up to 10s for startup
            LOG.info("✅ MarketDataConnector started via async loop")
        except Exception as e:
            LOG.error(f"Failed to start MarketDataConnector: {e}")
    else:
        LOG.warning(
            "⚠️ No async loop available for MarketDataConnector - market data will not be available")

    LOG.info("Starting feature engineering...")
    feature_engineering.start()

    LOG.info("Starting risk management...")
    risk_management.start()

    LOG.info("Starting position tracking...")
    position_tracking.start()

    LOG.info("Starting decision making...")
    decision_making.start()

    LOG.info("Starting regime detector...")
    try:
        if hasattr(regime_detector, "start"):
            regime_detector.start()
            LOG.info("✅ RegimeDetector started")
        else:
            LOG.info("ℹ️ RegimeDetector has no start() method (purely reactive)")
    except Exception as e:
        LOG.error(f"Failed to start RegimeDetector: {e}")

    LOG.info("Starting snapshot scheduler (DR)...")
    # snapshot_scheduler.start()
    LOG.info("Snapshot scheduler temporarily disabled")

    # Step 5: Keep the application running
    LOG.info("Aurora Core is running... Press Ctrl+C to stop.")
    print("\n" + "=" * 60)
    print("🌟 AURORA CORE IS ACTIVE 🌟")
    print("Waiting for market data and trade signals...")
    print("Press Ctrl+C to stop the application.")
    print("=" * 60 + "\n")

    # Alert monitoring state
    last_alert_check = time.time()
    alert_check_interval = 60  # Check every 60 seconds

    try:
        while True:
            current_time = time.time()

            # Periodic alert checks
            if current_time - last_alert_check >= alert_check_interval:
                try:
                    _perform_alert_checks(
                        alert_manager, wal_dir, config)
                except Exception as e:
                    LOG.error(f"Error during alert checks: {e}")
                last_alert_check = current_time

            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("Shutting down Aurora Core...")
        print("\nShutting down Aurora Core...")

        LOG.info("Shutdown signal received. Stopping all components...")

        if guardian_loop is not None:
            try:
                if guardian_loop.is_running():
                    guardian_loop.call_soon_threadsafe(guardian_loop.stop)
                if guardian_loop_thread is not None:
                    guardian_loop_thread.join(timeout=5)
            except Exception as loop_exc:
                LOG.error(f"Error stopping guardian asyncio loop: {loop_exc}")
            finally:
                try:
                    guardian_loop.close()
                except Exception:
                    pass

        # Helper to stop components safely if they exist
        for name in [
            "llm_intent_ingress_bridge",
            "shadow_event_tap_publisher",
            "account_balance",
            # "account_observer", (Deleted)
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

        # Stop WAL GC
        try:
            wal_gc.stop()
            wal_gc_thread.join(timeout=5)
            LOG.info("WAL GC stopped.")
        except Exception as e:
            LOG.error(f"Error stopping WAL GC: {e}")

        LOG.info("All components stopped or shutdown attempted. Exiting.")
        print("Aurora Core shutdown complete.")


if __name__ == "__main__":
    main()
