"""
WAL Tailer

Unified reader for Write-Ahead Log files that handles both:
1. Historical data replay (catching up)
2. Real-time tailing (like `tail -f`)

Key Features:
- Persistent offset tracking (survives restarts)
- File rotation detection (switches to new files)
- Graceful handling of incomplete lines (partial writes)
- Non-blocking async operation

Architecture:
    WAL Files → WalTailer → NeocortexAdapter → EpisodicBuffer → BrainCore
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Callable, Awaitable, Dict, Any, Optional, List
from glob import glob
from dataclasses import dataclass, field

try:
    import aiofiles  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    aiofiles = None

from config_models import ReplayConfig

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _aio_open(path: Path, mode: str):
    """
    Async file open. Prefers aiofiles; falls back to asyncio.to_thread(open).
    """
    if aiofiles is not None:
        async with aiofiles.open(path, mode) as f:  # type: ignore[attr-defined]
            yield f
        return

    f = await asyncio.to_thread(open, path, mode)

    class _AsyncFile:
        def __init__(self, file_obj):
            self._f = file_obj

        async def seek(self, *args):
            return await asyncio.to_thread(self._f.seek, *args)

        async def tell(self):
            return await asyncio.to_thread(self._f.tell)

        async def read(self):
            return await asyncio.to_thread(self._f.read)

        async def write(self, data):
            return await asyncio.to_thread(self._f.write, data)

        async def readline(self):
            return await asyncio.to_thread(self._f.readline)

    try:
        yield _AsyncFile(f)
    finally:
        await asyncio.to_thread(f.close)


@dataclass
class TailerState:
    """Persistent state for WalTailer."""
    offsets: Dict[str, int] = field(default_factory=dict)  # filename -> bytes_read
    last_file: Optional[str] = None  # Last file being tailed


class WalTailer:
    """
    Unified WAL reader that seamlessly processes history and tails for new data.
    
    Behavior:
    1. On startup: Load saved offsets from state file
    2. Process all WAL files from their saved offsets
    3. When reaching EOF of latest file: wait and poll for new data
    4. On file rotation: switch to new file
    5. On shutdown: save offsets to state file
    """
    
    def __init__(
        self,
        config: ReplayConfig,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
        state_path: Path,
        wal_dir: Path
    ):
        """
        Args:
            config: ReplayConfig with filter settings
            handler: Async function to call for each event
            state_path: Path to state JSON file (e.g., data/tailer_state.json)
            wal_dir: Directory containing WAL files
        """
        self.config = config
        self.handler = handler
        self.state_path = state_path
        self.wal_dir = wal_dir
        
        # State
        self._state = TailerState()
        self._running = False
        self._tailing = False  # True when caught up and waiting for new data
        
        # Stats
        self._events_processed = 0
        self._events_filtered = 0
        self._files_processed = 0
        self._incomplete_lines = 0
        
        # Polling interval when tailing
        self._poll_interval = 0.1  # seconds
        
    async def load_state(self) -> bool:
        """Load persisted offsets from state file."""
        try:
            if self.state_path.exists():
                async with _aio_open(self.state_path, "r") as f:
                    data = json.loads(await f.read())
                self._state.offsets = data.get("offsets", {})
                self._state.last_file = data.get("last_file")
                logger.info(f"Loaded tailer state: {len(self._state.offsets)} file offsets")
                return True
            else:
                logger.info("No previous tailer state found, starting fresh")
                return False
        except Exception as e:
            logger.warning(f"Failed to load tailer state: {e}")
            return False
    
    async def save_state(self) -> bool:
        """Persist offsets to state file."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            async with _aio_open(self.state_path, "w") as f:
                await f.write(
                    json.dumps(
                        {"offsets": self._state.offsets, "last_file": self._state.last_file},
                        indent=2,
                    )
                )
            logger.debug(f"Saved tailer state: {len(self._state.offsets)} file offsets")
            return True
        except Exception as e:
            logger.error(f"Failed to save tailer state: {e}")
            return False
    
    async def run(self):
        """
        Main tailing loop.
        
        Processes historical data then continuously tails for new entries.
        """
        if not self.config.enabled:
            logger.info("WalTailer is disabled")
            return
            
        self._running = True
        await self.load_state()
        
        logger.info(f"Starting WalTailer: {self.wal_dir}")
        
        try:
            while self._running:
                # Get sorted list of WAL files
                wal_files = self._get_wal_files()
                
                if not wal_files:
                    # No files yet, wait and retry
                    await asyncio.sleep(self._poll_interval)
                    continue
                
                # Process each file
                for i, file_path in enumerate(wal_files):
                    if not self._running:
                        break
                        
                    is_latest = (i == len(wal_files) - 1)
                    file_name = file_path.name
                    
                    # Get saved offset for this file
                    offset = self._state.offsets.get(file_name, 0)
                    file_size = file_path.stat().st_size
                    
                    # Skip fully processed files (unless it's the latest)
                    if offset >= file_size and not is_latest:
                        continue
                    
                    # Process the file
                    if is_latest:
                        # Tail the latest file
                        await self._tail_file(file_path)
                    else:
                        # Process historical file completely
                        await self._process_file(file_path)
                        self._files_processed += 1
                        
                # Check for new files (rotation)
                await asyncio.sleep(0.01)
                
        except asyncio.CancelledError:
            logger.info("WalTailer cancelled")
            
        finally:
            await self.save_state()
            self._running = False
            logger.info(
                f"WalTailer stopped: {self._events_processed} events, "
                f"{self._files_processed} files, {self._incomplete_lines} incomplete lines"
            )
    
    def _get_wal_files(self) -> List[Path]:
        """Get sorted list of WAL files."""
        pattern = str(self.wal_dir / "*.jsonl")
        files = [Path(f) for f in glob(pattern)]
        
        # Sort by modification time
        files.sort(key=lambda f: f.stat().st_mtime)
        
        return files
    
    async def _process_file(self, file_path: Path):
        """Process a file from saved offset to EOF."""
        file_name = file_path.name
        offset = self._state.offsets.get(file_name, 0)
        
        logger.info(f"Processing: {file_name} (offset={offset})")
        
        try:
            async with _aio_open(file_path, "r") as f:
                await f.seek(offset)
                line_count = 0
                
                while self._running:
                    line = await f.readline()
                    
                    if not line:
                        # EOF reached
                        break
                        
                    # Update offset before processing (in case of crash)
                    new_offset = await f.tell()
                    
                    # Process line
                    await self._process_line(line)
                    line_count += 1
                    
                    # Update state
                    self._state.offsets[file_name] = new_offset
                    self._state.last_file = file_name
                    
                    # Yield periodically
                    if line_count % self.config.batch_size == 0:
                        await asyncio.sleep(0.001)
                        
                        # Progress log
                        if line_count % 10000 == 0:
                            logger.info(f"  {file_name}: {line_count} lines")
                            await self.save_state()  # Periodic checkpoint
                
                logger.info(f"  Completed: {file_name} ({line_count} lines)")
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    
    async def _tail_file(self, file_path: Path):
        """Tail a file, waiting for new data when EOF is reached."""
        file_name = file_path.name
        offset = self._state.offsets.get(file_name, 0)
        
        if not self._tailing:
            logger.info(f"Tailing: {file_name} (offset={offset})")
            self._tailing = True
        
        try:
            async with _aio_open(file_path, "r") as f:
                await f.seek(offset)
                
                while self._running:
                    line = await f.readline()
                    
                    if not line:
                        # Check for file rotation
                        current_files = self._get_wal_files()
                        if current_files and current_files[-1] != file_path:
                            # New file appeared, switch to it
                            logger.info(f"File rotation detected, switching to {current_files[-1].name}")
                            self._tailing = False
                            return
                        
                        # No new data, wait
                        await asyncio.sleep(self._poll_interval)
                        
                        # Check if file was truncated/replaced
                        try:
                            current_size = file_path.stat().st_size
                            if current_size < await f.tell():
                                # File was truncated, reset
                                logger.warning(f"File truncated: {file_name}")
                                await f.seek(0)
                        except FileNotFoundError:
                            # File deleted, exit
                            logger.warning(f"File deleted: {file_name}")
                            return
                            
                        continue
                    
                    # Check for incomplete line (no newline at end)
                    if not line.endswith('\n'):
                        # Partial line, wait for more data
                        await f.seek(offset)  # Go back to start of partial line
                        await asyncio.sleep(self._poll_interval)
                        continue
                    
                    # Process complete line
                    new_offset = await f.tell()
                    await self._process_line(line)
                    
                    # Update state
                    offset = new_offset
                    self._state.offsets[file_name] = offset
                    self._state.last_file = file_name
                    
        except Exception as e:
            logger.error(f"Error tailing {file_path}: {e}")
    
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
            payload = event.get("payload") or event
            
            # Call handler
            await self.handler(payload)
            self._events_processed += 1
            
        except json.JSONDecodeError:
            # Incomplete or malformed JSON
            self._incomplete_lines += 1
            
        except Exception as e:
            logger.debug(f"Error processing line: {e}")
    
    def stop(self):
        """Stop tailing gracefully."""
        self._running = False
        # State is persisted in the async run() finalizer.
        
    @property
    def stats(self) -> Dict[str, Any]:
        """Get tailer statistics."""
        return {
            "events_processed": self._events_processed,
            "events_filtered": self._events_filtered,
            "files_processed": self._files_processed,
            "incomplete_lines": self._incomplete_lines,
            "running": self._running,
            "tailing": self._tailing,
            "offsets": dict(self._state.offsets)
        }
    
    @property
    def is_tailing(self) -> bool:
        """True when caught up with history and tailing live."""
        return self._tailing
