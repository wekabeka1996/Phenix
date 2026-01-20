"""
WAL Replayer

Reads historical Write-Ahead Log (WAL) files and replays events
to the adapter for training on past data.

Architecture:
    WAL Files (*.jsonl) → WALReplayer → NeocortexAdapter → EpisodicBuffer → BrainCore
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable, Dict, Any
from glob import glob

# Try to use aiofiles for non-blocking I/O
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

from config_models import ReplayConfig

logger = logging.getLogger(__name__)


class WALReplayer:
    """
    Replays historical WAL events for offline training.
    
    Features:
    - Scans directory for *.jsonl files
    - Sorts by modification time
    - Filters by event verb
    - Rate-limited to avoid flooding buffer
    - Async-friendly, non-blocking
    """
    
    def __init__(
        self,
        config: ReplayConfig,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
        base_path: Optional[Path] = None
    ):
        """
        Args:
            config: ReplayConfig with wal_glob, speed_factor, etc.
            handler: Async function to call for each event (e.g., adapter.handle_features)
            base_path: Base path to resolve relative globs
        """
        self.config = config
        self.handler = handler
        self.base_path = base_path or Path.cwd()
        
        # Stats
        self._files_processed = 0
        self._events_replayed = 0
        self._events_filtered = 0
        self._running = False
        self._completed = False
        
    async def run(self):
        """
        Main replay loop.
        
        Scans for WAL files, reads them in order, and replays matching events.
        """
        if not self.config.enabled:
            logger.info("WAL Replay is disabled")
            return
            
        if not self.config.wal_glob:
            logger.warning("WAL Replay enabled but wal_glob is empty")
            return
            
        self._running = True
        logger.info(f"Starting WAL Replay: {self.config.wal_glob}")
        
        try:
            # Find WAL files
            wal_pattern = self.base_path / self.config.wal_glob
            wal_files = sorted(
                glob(str(wal_pattern)),
                key=lambda f: Path(f).name
            )
            
            if not wal_files:
                logger.warning(f"No WAL files found matching: {wal_pattern}")
                self._completed = True
                return
                
            logger.info(f"Found {len(wal_files)} WAL files to replay")
            
            for file_path in wal_files:
                if not self._running:
                    logger.info("WAL Replay stopped")
                    break
                    
                await self._replay_file(Path(file_path))
                self._files_processed += 1
                
            self._completed = True
            logger.info(
                f"WAL Replay completed: {self._files_processed} files, "
                f"{self._events_replayed} events replayed, "
                f"{self._events_filtered} events filtered"
            )
            
        except Exception as e:
            logger.error(f"WAL Replay failed: {e}", exc_info=True)
            raise
            
        finally:
            self._running = False
    
    async def _replay_file(self, file_path: Path):
        """Replay a single WAL file."""
        logger.info(f"Replaying: {file_path.name}")
        
        line_count = 0
        batch_count = 0
        
        try:
            if HAS_AIOFILES:
                async with aiofiles.open(file_path, 'r') as f:
                    async for line in f:
                        await self._process_line(line)
                        line_count += 1
                        batch_count += 1
                        
                        # Yield control every batch_size lines
                        if batch_count >= self.config.batch_size:
                            await asyncio.sleep(0.001)  # Small yield
                            batch_count = 0
                            
                        # Progress logging
                        if line_count % 10000 == 0:
                            logger.info(f"  {file_path.name}: {line_count} lines processed")
            else:
                # Fallback to sync reading with async yields
                with open(file_path, 'r') as f:
                    for line in f:
                        await self._process_line(line)
                        line_count += 1
                        batch_count += 1
                        
                        if batch_count >= self.config.batch_size:
                            await asyncio.sleep(0.001)
                            batch_count = 0
                            
                        if line_count % 10000 == 0:
                            logger.info(f"  {file_path.name}: {line_count} lines processed")
                            
            logger.info(f"  Completed: {file_path.name} ({line_count} lines)")
            
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            
    async def _process_line(self, line: str):
        """Process a single WAL line."""
        line = line.strip()
        if not line:
            return
            
        try:
            event = json.loads(line)
            
            # Filter by verb
            verb = event.get("verb") or event.get("event_type") or event.get("type")
            
            if verb != self.config.filter_verb:
                self._events_filtered += 1
                return
                
            # Extract payload
            # WAL format might be: {"verb": "X", "payload": {...}}
            # Or flat: {"event_type": "X", ...data...}
            payload = event.get("payload") or event
            
            # Call handler
            await self.handler(payload)
            self._events_replayed += 1
            
        except json.JSONDecodeError:
            # Skip malformed lines
            pass
        except Exception as e:
            logger.debug(f"Error processing WAL event: {e}")
    
    def stop(self):
        """Stop the replay gracefully."""
        self._running = False
        
    @property
    def stats(self) -> Dict[str, Any]:
        """Get replay statistics."""
        return {
            "files_processed": self._files_processed,
            "events_replayed": self._events_replayed,
            "events_filtered": self._events_filtered,
            "running": self._running,
            "completed": self._completed
        }
