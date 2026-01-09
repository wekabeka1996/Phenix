#!/usr/bin/env python3
"""
Neocortex Domain - Main Entry Point

Shadow Mode Autonomous Learning System
Architecture: vFoundation (AsyncIO + Multiprocessing)
"""

import asyncio
import logging
import sys
from pathlib import Path

from config_models import load_config, NeocortexConfig


from logic.ingest.parser import FeatureParser
from logic.amygdala.valuation import ValuationEngine
from logic.memory.buffer import EpisodicBuffer
from logic.brain.bridge import BrainBridge
from transport.adapter import NeocortexAdapter


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
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=config.system.log_level,
        format=log_format,
        handlers=handlers
    )
    
    # Set transport adapter to DEBUG if needed
    if config.system.log_level == "DEBUG":
        logging.getLogger("transport.adapter").setLevel(logging.DEBUG)
    
    return logging.getLogger("neocortex.main")

from logic.ingest.tailer import WalTailer


# =============================================================================
# MAIN REACTOR (AsyncIO Event Loop)
# =============================================================================

async def main_reactor(config: NeocortexConfig, logger: logging.Logger):
    """
    Main async event loop.
    Phase 6: Unified WAL Tailing (history + live).
    """
    adapter = None
    tailer = None
    tailer_task = None
    
    try:
        logger.info("=" * 80)
        logger.info("NEOCORTEX DOMAIN - PHASE 6 (UNIFIED WAL TAILING)")
        logger.info("=" * 80)
        
        # Create necessary directories
        config.system.data_dir.mkdir(parents=True, exist_ok=True)
        config.system.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Initialize Pipeline Components
        logger.info("Initializing Logic Core...")
        
        # Senses
        parser = FeatureParser(config.ingest)
        logger.info(f"✓ FeatureParser ready (NanStrategy: {config.ingest.nan_strategy})")
        
        # Value System
        amygdala = ValuationEngine()
        logger.info("✓ Amygdala Valuation Engine ready")
        
        # Memory
        buffer = EpisodicBuffer(config.ingest.buffer_size)
        logger.info(f"✓ EpisodicBuffer allocated (Capacity: {config.ingest.buffer_size})")
        
        # Brain Bridge (Process Pool)
        brain_bridge = BrainBridge(
            config=config.neuro,
            max_workers=config.system.brain_workers
        )
        logger.info(f"✓ BrainBridge created (Workers: {config.system.brain_workers})")
        
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
        
        # 3. Start WAL Tailer (if enabled)
        if config.replay.enabled:
            logger.info("Starting WalTailer (Unified Mode)...")
            
            state_path = config.system.data_dir / "tailer_state.json"
            
            tailer = WalTailer(
                config=config.replay,
                handler=adapter.handle_features,
                state_path=state_path,
                wal_dir=config.replay.wal_dir
            )
            tailer_task = asyncio.create_task(tailer.run())
            logger.info(f"✓ WalTailer started (Dir: {config.replay.wal_dir})")
        else:
            logger.info("WAL Tailing disabled")
        
        # 4. Main Loop
        logger.info("")
        logger.info("Phase 6: Pipeline Active. Unified Tailing Ready.")
        logger.info("(Ctrl+C to stop)")
        
        while True:
            await asyncio.sleep(10)
            
            # Heartbeat / Stats
            stats_msg = f"Heartbeat: Buffer={len(buffer)} TrainSteps={adapter._total_train_steps}"
            
            if tailer:
                tailer_stats = tailer.stats
                stats_msg += f" Events={tailer_stats['events_processed']}"
                if tailer.is_tailing:
                    stats_msg += " [LIVE]"
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
                
        # Graceful shutdown
        if adapter is not None:
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
