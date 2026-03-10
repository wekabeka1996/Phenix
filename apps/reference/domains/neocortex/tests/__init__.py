#!/usr/bin/env python3
"""
Neocortex Persistence Verification Test

Tests that:
1. Shadow intent JSONL is created
2. Checkpoints are saved after train steps
3. Paths are correctly resolved
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add parent dirs to path

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.logic.brain.bridge import BrainBridge
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run persistence verification."""
    logger.info("=" * 80)
    logger.info("NEOCORTEX PERSISTENCE VERIFICATION TEST")
    logger.info("=" * 80)
    
    # 1. Load config
    config_dir = Path(__file__).parent.parent / "config"
    logger.info(f"Loading config from {config_dir}")
    config = load_config(config_dir)
    
    # 2. Initialize components
    parser = FeatureParser(config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(capacity=config.ingest.buffer_size)
    
    # 3. Initialize BrainBridge (with worker)
    logger.info("Initializing BrainBridge...")
    bridge = BrainBridge(
        config=config.neuro,
        max_workers=1,
        rng_seed=config.system.rng_seed
    )
    await bridge.start()
    
    # 4. Initialize Adapter
    logger.info("Initializing NeocortexAdapter...")
    adapter = NeocortexAdapter(
        config=config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=bridge,
        event_emitter=None,
        fsm_core=None
    )
    
    # 5. Send dummy observations to trigger training
    logger.info("Sending 100 dummy observations to trigger training...")
    
    import numpy as np
    for i in range(100):
        dummy_payload = {
            "symbol": "TEST",
            "timestamp": 1000 + i,
        }
        # Add all required features
        for feat in config.ingest.feature_list:
            dummy_payload[feat] = float(i % 10 + np.random.randn() * 0.1)
        
        await adapter.handle_features(dummy_payload)
        
        if (i + 1) % 20 == 0:
            logger.info(f"  Sent {i + 1}/100 observations...")
    
    # 6. Wait for async tasks
    logger.info("Waiting 5 seconds for async tasks to complete...")
    await asyncio.sleep(5)
    
    # 7. Check results
    logger.info("=" * 80)
    logger.info("VERIFICATION RESULTS:")
    logger.info("=" * 80)
    
    # Check shadow intent JSONL
    shadow_log = config.system.data_dir / "shadow_intents.jsonl"
    if shadow_log.exists():
        line_count = len(shadow_log.read_text().strip().split('\n'))
        logger.info(f"✅ Shadow intent JSONL exists: {shadow_log}")
        logger.info(f"   Lines in file: {line_count}")
    else:
        logger.error(f"❌ Shadow intent JSONL NOT FOUND: {shadow_log}")
    
    # Check checkpoints
    checkpoint_dir = config.system.checkpoint_dir
    checkpoints = list(checkpoint_dir.glob("*.pt"))
    if checkpoints:
        logger.info(f"✅ Checkpoints found in {checkpoint_dir}:")
        for cp in checkpoints:
            logger.info(f"   - {cp.name}")
    else:
        logger.warning(f"⚠️  NO checkpoints found in {checkpoint_dir}")
        logger.warning(f"   (This is expected if training steps < {config.neuro.checkpoint_every_n_steps})")
    
    # Check data directory
    data_dir = config.system.data_dir
    logger.info(f"\n📁 Data directory contents ({data_dir}):")
    if data_dir.exists():
        for item in sorted(data_dir.iterdir()):
            size = item.stat().st_size if item.is_file() else "DIR"
            logger.info(f"   {item.name}: {size}")
    else:
        logger.error(f"❌ Data directory does not exist: {data_dir}")
    
    # 8. Shutdown
    logger.info("\nShutting down...")
    bridge.shutdown()
    
    logger.info("=" * 80)
    logger.info("TEST COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())



