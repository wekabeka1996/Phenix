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
"""

from apps.reference.bootstrap.preflight import check_hybrid_coherence  # NEW IMPORT
from apps.reference.bootstrap.async_runtime import AsyncLoopRuntime
from apps.reference.bootstrap.backtest_runner import resolve_backtest_max_ticks
from apps.reference.bootstrap.domain_builder import build_live_domains
from apps.reference.config_loader import ConfigLoader, AuroraConfig
from apps.reference.config_contract import ConfigContractError
from apps.reference.domains.execution_position.fsm import ExecPosFSM
# from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import (
#     SnapshotScheduler,
# )

from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.core.time.clock import MockClock, set_clock, reset_clock
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
from backtest_engine.engine import BacktestEngine
from vfoundation.dr.wal_gc import WALGarbageCollector
from apps.reference.telemetry.alerts import AlertManager
from vfoundation.core import FSMCore
from vfoundation.core.schema_registry import init_global_registry
from vfoundation.core.protocol import Message
from vfoundation.core.protocol import Message
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import asyncio

# TASK-EXF-WIRE-STARTUP-09: Startup Guard Imports
from apps.reference.domains.exchange_filters.validator import validate_instruments_on_startup, FilterMismatchError
from apps.reference.adapters.binance_adapter import BinanceAdapter
from typing import Any, Optional
import threading

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
    
    # SSOT: bootstrap logger defaults to INFO (no ad-hoc env override here).
    bootstrap_level = "INFO"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, bootstrap_level, logging.INFO))
    
    # Check if already configured (by tests or previous import)
    if any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        _bootstrap_logging_done = True
        return
    
    # Minimal console handler for startup
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, bootstrap_level, logging.INFO))
    console.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(message)s"))
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
        execpos = domains.get("execution_position") if isinstance(domains, dict) else None
        oi_cfg = execpos.get("order_index") if isinstance(execpos, dict) else None
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
    
    # Initialize message schema registry for payload validation
    init_global_registry(str(project_root))

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


def run_backtest_simulation(config: AuroraConfig, *, return_result: bool = False) -> None:
    """
    Run the application in BACKTEST mode.
    
    This replaces the standard main loop with a simulation loop driven by BacktestEngine.
    It initializes a subset of domains (FeatureEngineering, DecisionMaking, etc.) 
    and wires them to a MockBroker and LocalBus (FSMCore).
    
    Args:
        config: Aurora configuration
        return_result: If True, return (BacktestResult, report_data) instead of None.
                       Used by Optuna integration for optimization.
    """
    LOG.info("="*60)
    LOG.info("🚀 STARTING AURORA CORE IN BACKTEST MODE")
    LOG.info("="*60)

    # Stable run id for artifacts (report + order log)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # WAL Isolation: Redirect to ops/wal/backtest/<run_id>
    # This prevents pollution of live WAL and avoids performance hits on fsync for live logs.
    try:
        from vfoundation.dr import wal
        bt_wal_dir = project_root / "ops" / "wal" / "backtest" / run_id
        bt_wal_dir.mkdir(parents=True, exist_ok=True)
        wal.set_wal_dir(bt_wal_dir)
        LOG.info(f"🛡️ WAL Isolated for Backtest: {bt_wal_dir}")
    except Exception as e:
        LOG.warning(f"Failed to isolate WAL for backtest: {e}")

    bt_cfg = getattr(getattr(config, "trading", None), "backtest", None)
    backtest_mode = str(getattr(bt_cfg, "backtest_mode", "strict")).strip().lower()
    if backtest_mode not in ("strict", "relaxed"):
        raise ValueError(f"Invalid trading.backtest.backtest_mode={backtest_mode!r} (expected strict|relaxed)")
    LOG.info(f"Backtest mode: {backtest_mode}")

    if backtest_mode == "relaxed":
        # Explicit, opt-in relaxations.
        try:
            fe = getattr(config.domains, "feature_engineering", None)
            warm = getattr(fe, "warmup", None) if fe is not None else None
            if warm is not None:
                warm.enforcement_mode = "warn_only"
            else:
                from apps.reference.config_models import WarmupEnforcementConfig

                if fe is not None:
                    fe.warmup = WarmupEnforcementConfig(enforcement_mode="warn_only")
            LOG.warning("BACKTEST RELAXED: warmup.enforcement_mode=warn_only (explicit override)")
        except Exception as e:
            LOG.warning(f"BACKTEST RELAXED override failed (warmup): {e}")

        try:
            fe = getattr(config.domains, "feature_engineering", None)
            ms_cfg = getattr(fe, "macro_sync", None) if fe is not None else None
            if ms_cfg is not None and hasattr(ms_cfg, "enabled"):
                ms_cfg.enabled = False
                LOG.warning("BACKTEST RELAXED: macro_sync.enabled=False (explicit override)")
            else:
                LOG.warning("BACKTEST RELAXED: macro_sync config not present")
        except Exception as e:
            LOG.warning(f"BACKTEST RELAXED override failed (macro_sync): {e}")
    else:
        LOG.info("BACKTEST STRICT: no implicit relaxations applied")
    
    # Initialize message schema registry for payload validation
    init_global_registry(str(project_root))

    # 1. Initialize Core Event Bus
    fsm = FSMCore()
    # FIX-BACKTEST-ORDER-IN-FLIGHT: Skip order_index for backtest.
    # The order-in-flight guard prevents duplicate ENTRY orders in live trading.
    # In backtest, orders never receive FILL/CANCEL feedback, so they never become terminal,
    # causing ALL subsequent intents to be blocked with NRR-ORDER-IN-FLIGHT.
    # Solution: Don't initialize order_index for backtest - the guard check will be skipped
    # because `hasattr(self.fsm, "order_index") and self.fsm.order_index` returns False.
    # _init_order_index(fsm, config)  # DISABLED FOR BACKTEST

    # 1b. Start dedicated asyncio loop for async domains (ExecPosFSM order execution, watchdog, etc.)
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=_run_async_loop, args=(loop,), daemon=True)
    loop_thread.start()

    # Backtest timebase: prevent stale-feature gates by running domains on simulated time.
    # LiveClock (wall time) makes all 2023 events look stale in 2026.
    bt_clock = MockClock(start_ms=0)
    
    # CRITICAL: Wire MockClock globally so all guards (ExposureGuard, cooldowns, staleness checks)
    # use simulated time instead of wall-clock. Without this, historical data from 2023 
    # appears "stale" when checked against 2026 wall-clock.
    set_clock(bt_clock)
    LOG.info("🕐 MockClock wired globally via set_clock() for backtest timebase")

    # Backtest-only: redirect OrderLoggerV1 to a run-specific file so reports can join rid<->order_id
    # without mixing sessions (logs/order_log_v1.jsonl is global & accumulative).
    order_log_path = None
    try:
        from apps.reference.telemetry.order_logger import order_logger as order_logger_proxy

        order_log_path = project_root / "logs" / "backtests" / f"order_log_{run_id}.jsonl"
        order_log_path.parent.mkdir(parents=True, exist_ok=True)
        order_logger_proxy.log_file = order_log_path
        LOG.info(f"🧾 Backtest OrderLogger file: {order_log_path}")
    except Exception as e:
        LOG.warning(f"Backtest OrderLogger redirection failed: {e}")
        order_log_path = None

    # --- Backtest telemetry: capture regimes & feature readiness ---
    regime_events: list[dict] = []
    regime_log: list[dict] = []
    last_regime_by_symbol: dict[str, dict] = {}
    regime_counts_by_symbol: dict[str, dict[str, int]] = {}
    features_counts_by_tf: dict[int, int] = {}
    features_full_ready_by_tf: dict[int, int] = {}
    trade_intents: list[dict] = []
    intent_log: list[dict] = []
    process_strategy_count = 0
    process_strategy_enqueued_count = 0
    bar_count = 0
    decision_clock_counts: dict[tuple[str, int, int], int] = {}
    decision_clock_violations = 0
    blocked_reason_counts: dict[str, int] = {}

    def _advance_clock_from_ts(ts_ms: int) -> None:
        try:
            bt_clock.set_time_ms(int(ts_ms))
        except Exception:
            pass

    def _on_regime(event: Message) -> None:
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        symbol = pld.get("symbol")
        regime = pld.get("regime")
        if not symbol or not regime:
            return
        regime_events.append(pld)
        last_regime_by_symbol[str(symbol)] = pld
        bucket = regime_counts_by_symbol.setdefault(str(symbol), {})
        norm = str(regime).upper().strip()
        bucket[norm] = int(bucket.get(norm, 0)) + 1
        ts_ms = pld.get("ts") or pld.get("ts_ms") or pld.get("timestamp_ms")
        try:
            ts_i = int(ts_ms)
        except Exception:
            ts_i = None
        regime_log.append(
            {
                "symbol": str(symbol),
                "regime": norm,
                "ts_ms": ts_i,
            }
        )

    def _on_features(event: Message) -> None:
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        ts_ms = pld.get("ts")
        if ts_ms is not None:
            _advance_clock_from_ts(int(ts_ms))
        tf_sec = pld.get("tf_sec")
        try:
            tf_i = int(tf_sec)
        except Exception:
            return
        features_counts_by_tf[tf_i] = int(features_counts_by_tf.get(tf_i, 0)) + 1
        warmup = pld.get("warmup") if isinstance(pld.get("warmup"), dict) else {}
        if bool(warmup.get("full_ready")):
            features_full_ready_by_tf[tf_i] = int(features_full_ready_by_tf.get(tf_i, 0)) + 1

    def _on_trade_intent(event: Message) -> None:
        # Capture strategy_id + rid in backtest report.
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        rid = pld.get("rid")
        if not isinstance(rid, str) or not rid:
            return
        # Add simulated emit time (MockClock) so we can join to order creation/fills deterministically.
        stamped = dict(pld)
        stamped["emitted_ts_ms"] = int(bt_clock.now_ms())
        try:
            stamped["emitted_iso_utc"] = datetime.fromtimestamp(int(bt_clock.now_ms()) / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            stamped["emitted_iso_utc"] = None

        # Attach last known market regime for this symbol (from RegimeDetector stream).
        # This is crucial for strategies whose why-chain does not include "regime:*" (e.g. Aurora).
        try:
            sym = stamped.get("instrument") or stamped.get("symbol")
            if isinstance(sym, str) and sym:
                last = last_regime_by_symbol.get(sym)
                if isinstance(last, dict):
                    stamped["market_regime"] = last.get("regime")
                    stamped["market_regime_confidence"] = last.get("confidence")
                    stamped["market_regime_ts_ms"] = last.get("ts") or last.get("last_update_ts_ms")
        except Exception:
            pass

        stamped["intent_status"] = "PROPOSED"
        trade_intents.append(stamped)
        intent_log.append(stamped)

    def _on_trade_intent_rejected(event: Message) -> None:
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        stamped = dict(pld)
        stamped["intent_status"] = "REJECTED"
        stamped["emitted_ts_ms"] = int(bt_clock.now_ms())
        intent_log.append(stamped)
        reason = str(stamped.get("reason_code", "UNKNOWN")).upper().strip() or "UNKNOWN"
        blocked_reason_counts[reason] = int(blocked_reason_counts.get(reason, 0)) + 1

    def _on_process_strategy_blocked(event: Message) -> None:
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        reason = str(pld.get("reason_code", "UNKNOWN")).upper().strip() or "UNKNOWN"
        blocked_reason_counts[reason] = int(blocked_reason_counts.get(reason, 0)) + 1

    def _decision_key_from_payload(pld: dict) -> Optional[tuple[str, int, int]]:
        if not isinstance(pld, dict):
            return None
        symbol = pld.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            return None
        tf_raw = pld.get("tf_sec")
        bar_close_ts_raw = pld.get("bar_close_ts")
        if bar_close_ts_raw is None:
            bar = pld.get("bar")
            if isinstance(bar, dict):
                bar_close_ts_raw = bar.get("end_ts_ms")
        try:
            tf_sec = int(tf_raw)
            bar_close_ts = int(bar_close_ts_raw)
        except Exception:
            return None
        return (symbol, tf_sec, bar_close_ts)

    def _on_bar_closed(event: Message) -> None:
        nonlocal bar_count
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        key = _decision_key_from_payload(pld)
        if key is not None:
            bar_count += 1

    def _on_process_strategy(event: Message) -> None:
        nonlocal process_strategy_count, decision_clock_violations
        pld = event.get("pld", {}) if isinstance(event, dict) else getattr(event, "pld", {})
        if not isinstance(pld, dict):
            return
        key = _decision_key_from_payload(pld)
        if key is None:
            return
        process_strategy_count += 1
        cnt = int(decision_clock_counts.get(key, 0)) + 1
        decision_clock_counts[key] = cnt
        if cnt > 1:
            decision_clock_violations += 1
            LOG.error(f"DOUBLE_DECISION_CLOCK: duplicate CMD:PROCESS_STRATEGY for key={key} count={cnt}")

    fsm.listen("EVT:REGIME_DETECTED", _on_regime)
    fsm.listen("EVT:FEATURES_CALCULATED", _on_features)
    fsm.listen("EVT:TRADE_INTENT_PROPOSED", _on_trade_intent)
    fsm.listen("EVT:TRADE_INTENT_REJECTED", _on_trade_intent_rejected)
    fsm.listen("EVT:PROCESS_STRATEGY_BLOCKED", _on_process_strategy_blocked)
    fsm.listen("EVT:BAR_CLOSED", _on_bar_closed)
    fsm.listen("CMD:PROCESS_STRATEGY", _on_process_strategy)

    # Lightweight enqueue telemetry for decision clock debugging.
    original_emit = fsm.emit

    def emit_with_decision_clock(event_name: str, payload: dict = None, why: str = "", data_ref=None):
        nonlocal process_strategy_enqueued_count
        if event_name == "CMD:PROCESS_STRATEGY":
            key = _decision_key_from_payload(payload if isinstance(payload, dict) else {})
            if key is not None:
                process_strategy_enqueued_count += 1
        return original_emit(event_name, payload, why, data_ref)

    fsm.emit = emit_with_decision_clock
    
    # 2. Initialize Backtest Engine (The Driver)
    
    start_date = datetime(2024, 1, 1).date() # Fallback (inclusive day semantics)
    end_date = datetime(2024, 1, 7).date()   # Fallback (inclusive day semantics)
    initial_balance = 10000.0         # Fallback
    profit_withdrawal_roi_pct = None
    profit_withdrawal_enabled = None

    # Read from config.trading.backtest if available
    if config.trading.backtest:
        try:
            start_date = datetime.strptime(config.trading.backtest.start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(config.trading.backtest.end_date, "%Y-%m-%d").date()
            initial_balance = config.trading.backtest.initial_balance
            profit_withdrawal_enabled = getattr(config.trading.backtest, "profit_withdrawal_enabled", None)
            profit_withdrawal_roi_pct = getattr(config.trading.backtest, "profit_withdrawal_roi_pct", None)
            LOG.info(f"Loaded backtest configuration: {start_date} -> {end_date}, Balance: {initial_balance}")
        except ValueError as e:
            LOG.error(f"Invalid date format in config.trading.backtest: {e}")
            sys.exit(1)

    # Symbols to test
    symbols = list(getattr(config.trading, "symbols_to_track", []) or [])
    if not symbols:
        symbols = list(config.instruments.keys()) if config.instruments else ["BTCUSDT", "ETHUSDT"]
    
    # Clock advance callback: updates global MockClock before each bar is processed
    def _advance_global_clock(ts_ms: int) -> None:
        """Advance the global MockClock to the given timestamp."""
        try:
            bt_clock.set_time_ms(ts_ms)
        except Exception:
            pass
    
    engine = BacktestEngine(
        start_date=start_date,
        end_date=end_date,
        symbol_list=symbols,
        timeframe="5m", # Configurable?
        initial_balance=initial_balance,
        profit_withdrawal_enabled=profit_withdrawal_enabled,
        profit_withdrawal_roi_pct=profit_withdrawal_roi_pct,
        event_bus=fsm,
        clock_advance_fn=_advance_global_clock  # Wire clock sync
    )

    from backtest_engine.wrappers import BacktestExecPosFSM
    
    # 3. Initialize Domains (Subset)
    LOG.info("Initializing Backtest Domains...")
    
    # Feature Engineering (Calculates indicators)
    # Task 18: FeatureEngineering requires AuroraConfig object
    feature_engineering = FeatureEngineering(fsm, config)
    fsm.register_domain("feature_engineering", feature_engineering)
    
    # PILLAR-WARMUP: Wire multi-TF resampler for pillar warmup.
    # FE already has _pillar_timeframe_to_label = {900: 'm15', 14400: 'h4', 86400: 'd1'}
    # Resampler aggregates 5m bars → HTF bars → emits EVT:BAR_CLOSED → FE updates pillar state.
    pillar_tf_map = getattr(feature_engineering, "_pillar_timeframe_to_label", {})
    if pillar_tf_map:
        try:
            from backtest_engine.backtest_bar_resampler import BacktestBarResampler
            pillar_tfs = sorted(pillar_tf_map.keys())
            engine._bar_resampler = BacktestBarResampler(
                emit_fn=fsm.emit,
                pillar_timeframes_sec=pillar_tfs,
            )
            LOG.info(
                f"✅ BacktestBarResampler wired: pillar_tfs={pillar_tfs} "
                f"(labels={list(pillar_tf_map.values())})"
            )
        except Exception as e:
            LOG.warning(f"⚠️ BacktestBarResampler not available: {e}")
    else:
        LOG.info("ℹ️ No pillar timeframes configured — HTF resampler skipped")
    
    # Regime Detector
    # Task 18: RegimeDetector requires AuroraConfig object
    regime_detector = RegimeDetector(config, fsm, clock=bt_clock)
    fsm.register_domain("regime_detector", regime_detector)
    
    # Risk Management
    # Task 18: RiskManagement requires AuroraConfig object
    risk_management = RiskManagement(fsm, config)
    fsm.register_domain("risk_management", risk_management)
    
    # Position Tracking (Portfolio State SSOT)
    # Backtest uses BacktestEngine as the authoritative portfolio emitter.
    # Reason: PositionTracking is truth-first and expects initial account sync / DR replay.
    # In backtest there is no live account sync, so disabling engine portfolio emission
    # would deadlock DecisionMaking with NRR-PORTFOLIO-UNKNOWN.
    LOG.info("ℹ️ Backtest: BacktestEngine will emit EVT:PORTFOLIO_STATE_UPDATED (no PositionTracking domain)")
    
    # Decision Making (Strategy Logic)
    # Task 18: DecisionMaking requires AuroraConfig object
    decision_making = DecisionMaking(fsm, config, clock=bt_clock)
    fsm.register_domain("decision_making", decision_making)
    
    # Execution Position (The Trader)
    exec_pos = BacktestExecPosFSM(config=config, fsm=fsm, shadow_mode=False)
    exec_pos.set_async_loop(loop)
    # Ensure BacktestEngine uses the same broker instance created by ExecPosFSM
    if exec_pos.adapter is not None:
        engine.broker = exec_pos.adapter
    # DET-BT-15: Wire ExecPosFSM for tick-barrier synchronization
    engine.execpos_fsm = exec_pos
    fsm.register_domain("execution_position", exec_pos)
    
    # 3b. Initialize Aurora Strategy Handler (processes CMD:PROCESS_STRATEGY)
    # This is CRITICAL - without this, no signals will be generated!
    try:
        from apps.reference.domains.strategies.plugins.aurora_builtin import AuroraBuiltinPlugin
        aurora_plugin = AuroraBuiltinPlugin()
        # DET-BT-COOLDOWN-FIX: Pass bt_clock.monotonic for deterministic cooldowns/holds
        aurora_handler = aurora_plugin.create_handler(
            fsm=fsm, config=config, monotonic_fn=bt_clock.monotonic
        )
        aurora_handler.register()
        LOG.info("✅ Aurora Strategy Handler registered for Backtest.")
    except Exception as e:
        LOG.error(f"Failed to register Aurora Strategy Handler: {e}")
        import traceback
        traceback.print_exc()
    
    # 3c. Initialize Mean Reversion Strategy Handler
    # FIX-BACKTEST-MR: Mean Reversion was not registered, so BTC (assigned to MR) couldn't trade!
    try:
        from apps.reference.domains.strategies.plugins.mean_reversion import MeanReversionPlugin
        mr_plugin = MeanReversionPlugin()
        mr_handler = mr_plugin.create_handler(fsm=fsm, config=config)
        mr_handler.register()
        LOG.info("✅ Mean Reversion Strategy Handler registered for Backtest.")
    except Exception as e:
        LOG.error(f"Failed to register Mean Reversion Strategy Handler: {e}")
        import traceback
        traceback.print_exc()
    
    LOG.info("✅ Domains initialized and wired for Backtest.")

    # 3d. Initialize AlphaSearch Backtest Plugin (Shadow Advisor)
    # ALPHA-SEARCH: Wire plugin to enable virtual trading and ensemble learning
    alpha_plugin = None
    try:
        from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
        from apps.reference.domains.alpha_search.config_models import load_alpha_search_config

        _as_config_path = project_root / "config" / "alpha_search.yaml"
        _as_config = load_alpha_search_config(str(_as_config_path))
        alpha_plugin = AlphaSearchBacktestPlugin(
            event_bus=fsm,
            config=_as_config,
        )
        LOG.info(
            f"✅ AlphaSearch Plugin registered (shadow={_as_config.shadow_mode}, "
            f"providers={list(alpha_plugin.providers.keys())})"
        )
    except Exception as e:
        LOG.warning(f"⚠️ AlphaSearch Plugin disabled (init failed): {e}")
        alpha_plugin = None
    
    # 4. Run Simulation
    try:
        max_ticks = resolve_backtest_max_ticks(config)
        if max_ticks is not None:
            LOG.info(f"⏱️ Backtest max_ticks={max_ticks} (from config.trading.backtest.max_ticks)")

        results = engine.run(max_ticks=max_ticks)

        if decision_clock_violations > 0:
            raise RuntimeError(
                f"double decision clock detected: violations={decision_clock_violations}, "
                "expected max 1 CMD:PROCESS_STRATEGY per closed bar key"
            )

        # --- Regime summary (console) ---
        if last_regime_by_symbol:
            print("\n" + "=" * 60)
            print("🧭 REGIME SUMMARY (last known per symbol)")
            print("=" * 60)
            # Show up to 10 symbols for readability
            for sym in sorted(last_regime_by_symbol.keys())[:10]:
                last = last_regime_by_symbol[sym]
                print(
                    f"{sym}: {last.get('regime')} conf={last.get('confidence')} "
                    f"warmup_full_ready={bool((last.get('warmup') or {}).get('full_ready'))}"
                )
            if len(last_regime_by_symbol) > 10:
                print(f"... ({len(last_regime_by_symbol) - 10} more symbols)")
            print("=" * 60 + "\n")
        else:
            print("\n[WARN] No EVT:REGIME_DETECTED captured during backtest. Likely no bar-features emitted (check FEATURES_CALCULATED tf_sec=300 counters).")
        
        # --- Reporting ---
        
        # 1. Console Output
        print("\n" + "="*60)
        print(f"🏁 BACKTEST RESULTS ({start_date} to {end_date})")
        print("="*60)
        print(f"💰 PnL:           {results.total_pnl: >10.2f} USDT")
        print(f"📈 ROI:           {results.roi_pct: >10.2f} %")
        print(f"📉 Max Drawdown:  {results.max_drawdown*100: >10.2f} %")
        print(f"🎲 Win Rate:      {results.win_rate*100: >10.1f} %")
        print(f"🔢 Total Trades:  {results.total_trades: >10}")
        withdrawals_total = float(getattr(results, "withdrawals_total", 0.0) or 0.0)
        if withdrawals_total > 0:
            print(f"🏦 Withdrawn:     {withdrawals_total: >10.2f} USDT")
            print(f"💵 End Balance:   {results.end_balance: >10.2f} USDT (on-account)")
            print(f"💼 End Gross:     {float(getattr(results, 'end_balance_gross', results.end_balance) or 0.0): >10.2f} USDT")
            print(f"📊 ROI (cash):    {float(getattr(results, 'roi_on_account_pct', 0.0) or 0.0): >10.2f} %")
            print(f"📉 DD (cash):     {float(getattr(results, 'max_drawdown_on_account', 0.0) or 0.0)*100: >10.2f} %")
        else:
            print(f"💵 End Balance:   {results.end_balance: >10.2f} USDT")
        print("="*60 + "\n")

        # 2. JSON Report
        from backtest_engine.reporting import build_backtest_report, save_backtest_run_bundle

        report_data = build_backtest_report(
            run_id=run_id,
            config=config,
            results=results,
            engine=engine,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            timeframe="5m",
            initial_balance=float(initial_balance),
            regimes={
                "events_total": int(len(regime_events)),
                "regime_log": regime_log,
                "last_by_symbol": last_regime_by_symbol,
                "counts_by_symbol": regime_counts_by_symbol,
            },
            features={
                "counts_by_tf_sec": {str(k): int(v) for k, v in features_counts_by_tf.items()},
                "full_ready_counts_by_tf_sec": {str(k): int(v) for k, v in features_full_ready_by_tf.items()},
            },
            trade_intents=intent_log or trade_intents,
            order_log_path=str(order_log_path) if order_log_path is not None else None,
            pipeline={
                "bar_count": int(bar_count),
                "features_emitted_count": int(sum(features_counts_by_tf.values())),
                "regime_detected_count": int(len(regime_events)),
                "process_strategy_enqueued_count": int(process_strategy_enqueued_count),
                "process_strategy_executed_count": int(process_strategy_count),
                "process_strategy_count": int(process_strategy_count),
                "decision_clock_violations": int(decision_clock_violations),
                "blocked_reason_counts": {str(k): int(v) for k, v in blocked_reason_counts.items()},
            },
        )
        
        # Inject Alpha Search Summary (since it's a standalone plugin)
        try:
            if alpha_plugin is not None:
                report_data["alpha_search"] = alpha_plugin.get_summary()
                LOG.info("✅ Alpha Search summary injected into report")
        except Exception as e:
            LOG.warning(f"Failed to inject Alpha summary: {e}")
        
        reports_dir = project_root / "reports" / "backtests"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Reproducible run bundle (fail-closed on missing declared config YAMLs)
        bundle_dir = save_backtest_run_bundle(
            run_id=run_id,
            report=report_data,
            config=config,
            reports_root=reports_dir,
        )
        LOG.info(f"📦 Backtest run bundle saved to: {bundle_dir}")
        
        # Filename: backtest_{iso_timestamp}.json
        report_path = reports_dir / f"backtest_{run_id}.json"
        
        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
            
        LOG.info(f"✅ Report saved to: {report_path}")

    except Exception as e:
        LOG.error(f"❌ Backtest failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Restore global clock to LiveClock for any subsequent code
        try:
            reset_clock()
            LOG.info("🕐 Clock reset to LiveClock after backtest")
        except Exception:
            pass
            
        try:
            if hasattr(exec_pos, "watchdog") and exec_pos.watchdog is not None:
                exec_pos.watchdog.stop()
        except Exception:
            pass

        try:
            async def _shutdown_asyncio_loop() -> None:
                tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            asyncio.run_coroutine_threadsafe(_shutdown_asyncio_loop(), loop).result(timeout=2.0)
        except Exception:
            pass

        try:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()
        except Exception:
            pass

    # OPTUNA-HOOK-01: Return results for optimization
    if return_result:
        return results, report_data


def main() -> None:
    """Main application entry point."""
    LOG.info("Starting Aurora Core...")

    # Step 1: Load configuration
    LOG.info("Loading configuration...")
    # ConfigLoader accepts config_dir parameter (path to aurora configs)
    config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
    config = config_loader.load_config()
    LOG.info("Configuration loaded successfully")

    # BACKTEST OVERRIDE: keep more rotated log files for longer runs.
    # RotatingFileHandler keeps: <current> + backupCount files.
    if config.trading_mode == "backtest":
        try:
            obs_logging = config.observability.logging
            desired_backup_count = 50

            obs_logging.rotation.backup_count = desired_backup_count
            obs_logging.core.backup_count = desired_backup_count
            obs_logging.event_chain.backup_count = desired_backup_count
            for domain_cfg in obs_logging.domains.values():
                domain_cfg.backup_count = desired_backup_count

            LOG.warning(
                "BACKTEST OVERRIDE: observability.logging.*.backup_count=50 "
                "(rotation/core/event_chain/domains)"
            )
        except Exception as e:
            LOG.warning(f"BACKTEST OVERRIDE failed (logging backup_count=50): {e}")

    # Step 1.5: Setup full logging from observability.yaml (CFG-OBS-001)
    from apps.reference.logging_setup import setup_logging
    setup_logging(config, logs_dir=logs_dir)

    # PHASE 2: METADATA ACTIVATION - Log config versions at startup (PURGE-DIRTY-DOZEN)
    sys_ver = getattr(config.system_meta, 'system_config_version', None) or 'N/A'
    regime_ver = getattr(config.system_meta, 'regime_config_version', None) or 'N/A'
    LOG.info(f"📋 Config Versions: system={sys_ver}, regime={regime_ver}")
    LOG.info(f"📋 Trading Mode: {config.trading_mode}")

    # TASK: BACKTEST MODE INTERCEPTION
    if config.trading_mode == "backtest":
        run_backtest_simulation(config)
        return # Exit main after backtest finishes


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
                LOG.warning("⚠️ SECURITY: warn_only_filters=True ignored in LIVE/PROD mode. Enforcing FAIL-CLOSED.")
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
                LOG.critical(f"🛑 STARTUP BLOCKED: Exchange Filter Mismatch!\n{e}")
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
    
    # Wrap FSMCore.emit to track events with EntropyMonitor
    original_emit = fsm.emit
    def emit_with_monitoring(event_name: str, payload: dict, why: str, data_ref=None):
        """Emit with entropy monitoring"""
        # Track event for anomaly detection
        from vfoundation.core.protocol import Message
        tracking_msg = Message(
            op=event_name.split(":")[0] if ":" in event_name else "EVT",
            verb=event_name.split(":")[1] if ":" in event_name else event_name,
            src="fsm_core",
            dst="any",
            pld=payload,
            why=why
        )
        entropy_monitor.track_event(tracking_msg)
        
        # Call original emit
        return original_emit(event_name, payload, why, data_ref)
    
    fsm.emit = emit_with_monitoring
    LOG.info("✅ FSMCore initialized with EntropyMonitor tracking")

    # Step 2: Create event listeners
    LOG.info("Setting up event listeners...")
    # AuroraBridge removed (BRIDGE-SUNSET-01).
    # TRADE_INTENT_PROPOSED is now handled directly by ExecPosFSM.
    # bridge = AuroraBridge(fsm=fsm, config=config, logger=LOG)


    # Step 3: Initialize domains via composition root
    LOG.info("Initializing domain components via DomainBuilder...")
    domains = build_live_domains(
        config=config,
        fsm=fsm,
        logger=LOG,
        debug_event_listener=debug_event_listener,
    )
    account_balance = domains.account_balance
    market_data = domains.market_data
    feature_engineering = domains.feature_engineering
    risk_management = domains.risk_management
    position_tracking = domains.position_tracking
    decision_making = domains.decision_making
    regime_detector = domains.regime_detector
    csv_recorder = domains.csv_recorder
    bar_aggregator = domains.bar_aggregator

    global execution_position
    execution_position = domains.execution_position
    LOG.info("✅ DomainBuilder completed")

    # ==========================================
    # DR: DISASTER RECOVERY STATE RESTORATION
    # ==========================================
    LOG.info("--- Starting Disaster Recovery Check ---")

    # Initialize components needed for DR (execution_position already initialized in initialize_domains)
    from vfoundation.dr.dr_loader import find_latest_snapshot, replay_wal_after

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
    guardian_runtime: Optional[AsyncLoopRuntime] = None
    guardian_loop: Optional[asyncio.AbstractEventLoop] = None
    guardian_loop_thread: Optional[threading.Thread] = None

    LOG.info("--- Starting Order/Position Synchronization ---")
    guardian_runtime = AsyncLoopRuntime(name="AuroraAsyncLoop")
    guardian_loop = guardian_runtime.start()
    guardian_loop_thread = guardian_runtime.thread
    execution_position.set_async_loop(guardian_loop)

    # ==========================================
    # TASK47c-P3: LEVERAGE BOOTSTRAP (ACTIVE LEVERAGE MANAGEMENT)
    # ==========================================
    # Sync margin mode and leverage with exchange BEFORE trading starts.
    # Failed symbols will be blocked from trading (fail-closed).
    blocked_symbols: set = set()
    try:
        LOG.info("--- Starting Leverage Bootstrap ---")
        blocked_symbols = guardian_runtime.run(
            execution_position.run_leverage_bootstrap(),
            timeout=30.0,
        )  # 30s timeout for all symbols
        if blocked_symbols:
            LOG.warning(f"TASK47c-P3: Symbols blocked from trading due to leverage sync failure: {blocked_symbols}")
        else:
            LOG.info("TASK47c-P3: Leverage bootstrap completed successfully")
    except Exception as e:
        LOG.error(f"TASK47c-P3: Leverage bootstrap failed with exception: {e}. Trading MAY proceed with default settings.")

    # ==========================================
    # IN-FLIGHT RECONCILER (TRUTH DOMAIN REPAIR)
    # ==========================================
    try:
        from apps.reference.domains.inflight_reconcile.reconciler import InFlightReconciler, InFlightStatus
        from apps.reference.domains.inflight_reconcile.config import InFlightConfig

        domains_dict = {}
        try:
            if getattr(config, "domains", None) is not None and hasattr(config.domains, "model_dump"):
                domains_dict = config.domains.model_dump()  # type: ignore[assignment]
        except Exception:
            domains_dict = {}

        inflight_cfg = InFlightConfig.from_ssot(domains_dict)
        inflight_reconciler = InFlightReconciler(config=inflight_cfg, adapter=getattr(execution_position, "adapter", None))

        # Bind ACK/FILL events so the reconciler can track orders without touching execution code.
        def _inflight_on_order_ack(event: "Message") -> None:
            pld = event.pld or {}
            rid = str(pld.get("rid") or event.rid or pld.get("clientOrderId") or pld.get("orderId") or "")
            symbol = pld.get("symbol")
            if not rid or not symbol:
                return
            client_order_id = pld.get("clientOrderId") or pld.get("client_order_id")
            exchange_order_id = str(pld.get("orderId")) if pld.get("orderId") is not None else None
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
            rid = str(pld.get("rid") or event.rid or pld.get("clientOrderId") or pld.get("orderId") or "")
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

        if guardian_runtime is not None and guardian_loop is not None and guardian_loop.is_running():
            guardian_runtime.submit(inflight_reconciler.run_forever())
            LOG.info("✅ InFlightReconciler started")
        else:
            LOG.warning("⚠️ InFlightReconciler not started: async loop is not running")
    except Exception as e:
        LOG.warning(f"⚠️ InFlightReconciler disabled (init failed): {e}")

    # RetryScheduler binding restored (PHASE2-DEAD-DEFER-FIX)
    retry_scheduler = None
    try:
        from vfoundation.core.retry_scheduler import RetryScheduler
        
        # Config for retry scheduler (use arming config if available)
        try:
            arming_cfg = config.domains.decision_making.arming
            max_attempts = int(getattr(arming_cfg, 'max_attempts', 5))
            retry_backoff_ms = int(getattr(arming_cfg, 'retry_backoff_ms', 500))
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
                    LOG.warning(f"RetryScheduler.register_deferred failed: {e}")
            
            fsm.listen("EVT:INTENT_DEFERRED", on_intent_deferred)
            LOG.info("✅ RetryScheduler bound (max_attempts=%d, backoff_ms=%d)", max_attempts, retry_backoff_ms)
        else:
            LOG.warning("⚠️ RetryScheduler not bound: async loop is not running")
    except Exception as e:
        LOG.warning(f"⚠️ RetryScheduler disabled (init failed): {e}")

    try:
        sync_fn = getattr(
            execution_position,
            "sync_open_orders_and_positions",
            None,
        )
        if callable(sync_fn):
            guardian_runtime.run(sync_fn())
        else:
            LOG.info(
                "ExecutionPosition has no sync_open_orders_and_positions(); skipping initial sync"
            )

        LOG.info("Starting OrderGuardian...")
        guardian_runtime.run(execution_position.start_order_guardian())

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

    # TASK32: Strategy plugins (allowlist registry) wired in composition root
    strategy_plugins = StrategyPluginRegistry()
    strategy_plugins.register(AuroraBuiltinPlugin())
    strategy_plugins.register(MeanReversionPlugin())
    StrategyRuntime(fsm=fsm, config=config, registry=strategy_plugins).start()
    LOG.info("✅ RegimeDetector initialized and subscribed to EVT:FEATURES_CALCULATED")

    # ==========================================
    # ALPHA-SEARCH: Shadow Alpha Plugin (always-on, all trading modes)
    # ==========================================
    try:
        from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
        from apps.reference.domains.alpha_search.config_models import load_alpha_search_config

        _as_config_path = project_root / "config" / "alpha_search.yaml"
        _as_config = load_alpha_search_config(str(_as_config_path))
        alpha_plugin = AlphaSearchBacktestPlugin(
            event_bus=fsm,
            config=_as_config,
        )
        LOG.info(
            f"✅ AlphaSearch Plugin registered (shadow={_as_config.shadow_mode}, "
            f"providers={list(alpha_plugin.providers.keys())})"
        )
    except Exception as e:
        LOG.warning(f"⚠️ AlphaSearch Plugin disabled (init failed): {e}")

    # DATA-RECORDER-01: Unified backtest recorder (initialized by DomainBuilder).
    csv_recorder.start()
    LOG.info("✅ CsvRecorder initialized and started")


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
    if guardian_runtime is not None and guardian_loop is not None and guardian_loop.is_running():
        try:
            guardian_runtime.run(market_data.start_async(), timeout=10)  # Wait up to 10s for startup
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

            # Periodic house-keeping
            if decision_making is not None and hasattr(decision_making, "handle_tick"):
                try:
                    decision_making.handle_tick()
                except Exception as e:
                    LOG.error(f"Error in decision_making.handle_tick: {e}")

            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("Shutting down Aurora Core...")
        print("\nShutting down Aurora Core...")

        LOG.info("Shutdown signal received. Stopping all components...")

        if guardian_runtime is not None:
            try:
                guardian_runtime.stop(timeout=5.0)
            except Exception as loop_exc:
                LOG.error(f"Error stopping guardian asyncio loop: {loop_exc}")

        # Helper to stop components safely if they exist
        for name in [
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
