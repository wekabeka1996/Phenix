#!/usr/bin/env python3
"""
Neocortex Domain - Main Entry Point

Shadow Mode Autonomous Learning System
Architecture: vFoundation (AsyncIO + Multiprocessing)
"""

from apps.reference.domains.neocortex.logic.ingest.tailer import WalTailer
from apps.reference.domains.neocortex.logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig
import asyncio
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from apps.reference.domains.neocortex.config_models import load_config, NeocortexConfig


from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.logic.brain.bridge import BrainBridge
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging(config: NeocortexConfig):
    """Configure logging based on system config."""
    log_format = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'

    handlers = [logging.StreamHandler(sys.stdout)]

    if config.system.log_to_file:
        config.system.data_dir.mkdir(parents=True, exist_ok=True)
        log_file = config.system.data_dir / "neocortex.log"
        handlers.append(
            RotatingFileHandler(
                log_file,
                maxBytes=20 * 1024 * 1024,
                backupCount=100,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=config.system.log_level,
        format=log_format,
        handlers=handlers
    )

    # Set transport adapter to DEBUG if needed
    if config.system.log_level == "DEBUG":
        logging.getLogger("transport.adapter").setLevel(logging.DEBUG)

    return logging.getLogger("neocortex.main")


# =============================================================================
# MAIN REACTOR (AsyncIO Event Loop)
# =============================================================================

async def main_reactor(config: NeocortexConfig, logger: logging.Logger):
    """
    Main async event loop.
    Supports both Phase 6 (WAL Tailing) and Phase 7 (Multi-Source Ingestion).
    """
    adapter = None
    tailer = None
    tailer_task = None

    # Determine active phase
    is_phase7 = config.replay.enabled and config.replay.is_phase7
    phase_name = "PHASE 7 (MULTI-SOURCE INGESTION)" if is_phase7 else "PHASE 6 (UNIFIED WAL TAILING)"

    try:
        logger.info("=" * 80)
        logger.info(f"NEOCORTEX DOMAIN - {phase_name}")
        logger.info("=" * 80)

        # Create necessary directories
        config.system.data_dir.mkdir(parents=True, exist_ok=True)
        config.system.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 1. Initialize Pipeline Components
        logger.info("Initializing Logic Core...")

        # Senses
        parser = FeatureParser(config.ingest)
        logger.info(
            f"✓ FeatureParser ready (NanStrategy: {config.ingest.nan_strategy})")

        # Value System
        amygdala = ValuationEngine()
        logger.info("✓ Amygdala Valuation Engine ready")

        # Memory
        buffer = EpisodicBuffer(config.ingest.buffer_size)
        logger.info(
            f"✓ EpisodicBuffer allocated (Capacity: {config.ingest.buffer_size})")

        # Brain Bridge (Process Pool)
        brain_bridge = BrainBridge(
            config=config.neuro,
            max_workers=config.system.brain_workers,
            rng_seed=config.system.rng_seed,
        )
        logger.info(
            f"✓ BrainBridge created (Workers: {config.system.brain_workers})")

        # Transport Adapter
        adapter = NeocortexAdapter(
            config=config,
            parser=parser,
            amygdala=amygdala,
            buffer=buffer,
            brain_bridge=brain_bridge
        )
        logger.info("✓ NeocortexAdapter wired up")

        logger.info("=" * 80)

        # 2. Start Brain Bridge
        logger.info("Starting BrainBridge worker processes...")
        await adapter.start()

        # 3. Start Tailer (Phase 6 or Phase 7)
        if config.replay.enabled:
            state_path = config.system.data_dir / "tailer_state.json"

            if is_phase7:
                # === PHASE 7: Multi-Source Ingestion ===
                logger.info("Starting MultiTailer (Phase 7 Multi-Source)...")

                multi_config = MultiSourceConfig(
                    enabled=True,
                    features_dir=config.replay.features_dir,
                    orders_file=config.replay.orders_file,
                    core_log=config.replay.core_log,
                    symbols=config.replay.symbols or [
                        "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"],
                    batch_size=config.replay.batch_size,
                    poll_interval=config.replay.poll_interval,
                    max_feature_lines_total_per_cycle=config.replay.max_feature_lines_total_per_cycle,
                    max_feature_lines_per_symbol_per_cycle=config.replay.max_feature_lines_per_symbol_per_cycle,
                    max_order_lines_per_cycle=config.replay.max_order_lines_per_cycle,
                    max_core_lines_per_cycle=config.replay.max_core_lines_per_cycle,
                )

                tailer = MultiTailer(
                    config=multi_config,
                    feature_handler=adapter.handle_features,
                    episode_handler=adapter.add_completed_episode if hasattr(
                        adapter, 'add_completed_episode') else None,
                    state_path=config.system.data_dir / "multi_tailer_state.json",
                    run_mode=config.system.run_mode
                )
                tailer_task = asyncio.create_task(tailer.run())

                logger.info(f"✓ MultiTailer started")
                logger.info(f"  Features: {config.replay.features_dir}")
                logger.info(f"  Orders: {config.replay.orders_file}")
                logger.info(f"  Core: {config.replay.core_log}")
                logger.info(f"  Symbols: {multi_config.symbols}")
            else:
                # === PHASE 6: WAL Tailing (Legacy) ===
                logger.info("Starting WalTailer (Phase 6 Unified Mode)...")

                tailer = WalTailer(
                    config=config.replay,
                    handler=adapter.handle_features,
                    state_path=state_path,
                    wal_dir=config.replay.wal_dir
                )
                tailer_task = asyncio.create_task(tailer.run())
                logger.info(
                    f"✓ WalTailer started (Dir: {config.replay.wal_dir})")
        else:
            logger.info("Data ingestion disabled (replay.enabled=False)")

        # 4. Main Loop
        logger.info("")
        logger.info(f"{phase_name}: Pipeline Active.")
        logger.info("(Ctrl+C to stop)")

        while True:
            await asyncio.sleep(10)

            # Heartbeat / Stats
            stats_msg = f"Heartbeat: Buffer={len(buffer)} TrainSteps={adapter._total_train_steps}"

            if tailer:
                tailer_stats = tailer.stats
                # MultiTailer uses 'features_processed', WalTailer uses 'events_processed'
                events = tailer_stats.get('events_processed') or tailer_stats.get(
                    'features_processed', 0)
                stats_msg += f" Events={events}"

                # Check tailing status (property name differs between tailers)
                if hasattr(tailer, 'is_tailing') and tailer.is_tailing:
                    stats_msg += " [LIVE]"
                elif tailer_stats.get('running', False):
                    stats_msg += " [RUNNING]"
                else:
                    stats_msg += " [CATCHING UP]"

            logger.debug(stats_msg)

    except asyncio.CancelledError:
        logger.info("Reactor received cancellation signal")

    finally:
        # Stop tailer
        if tailer:
            tailer.stop()
        if tailer_task and not tailer_task.done():
            tailer_task.cancel()
            try:
                await tailer_task
            except asyncio.CancelledError:
                pass

        # Graceful async shutdown (with final checkpoint)
        if adapter is not None:
            try:
                await adapter.shutdown_async()
            except Exception as e:
                logger.error(
                    f"Async shutdown failed, falling back to sync: {e}")
                adapter.shutdown()
        logger.info("Reactor shutdown complete")


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """Application entry point with error handling."""
    logger = None

    try:
        # 1. Load configuration (fail-closed: exits on error)
        config_dir = Path(__file__).parent / "config"
        print(f"Loading configuration from: {config_dir}")

        config = load_config(config_dir)
        print("✓ Configuration validation passed")

        # 2. Setup logging
        logger = setup_logging(config)

        # 3. Enter reactor
        await main_reactor(config, logger)

    except FileNotFoundError as e:
        print(f"❌ Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        if logger:
            logger.exception(f"Fatal error: {e}")
        else:
            print(f"❌ Fatal Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
        sys.exit(1)

    finally:
        if logger:
            logger.info("Neocortex domain shutdown complete")


def run():
    """Wrapper for asyncio.run with graceful KeyboardInterrupt handling."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠ Received KeyboardInterrupt - shutting down gracefully...")
        sys.exit(0)


if __name__ == "__main__":
    run()
