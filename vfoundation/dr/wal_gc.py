from pathlib import Path
import time
from threading import Thread, Event
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from vfoundation.dataref.wal_archiver import WalArchiver


class WALGarbageCollector:
    """
    Manages WAL file lifecycle: rotation, cleanup, archival.
    Runs as background daemon thread.
    """

    def __init__(
        self,
        wal_dir: Path,
        retention_days: int = 7,
        max_file_size_mb: int = 100,
        logger: Optional[logging.Logger] = None,
        archiver: Optional["WalArchiver"] = None,
    ):
        self.wal_dir = Path(wal_dir)
        self.retention_days = retention_days
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = Event()
        self.archiver = archiver

    def start_background_gc(self, interval_sec: int = 3600) -> Thread:
        """Start GC thread (runs every 1 hour by default)."""
        thread = Thread(
            target=self._gc_loop,
            args=(interval_sec,),
            daemon=True,
            name="WAL-GC"
        )
        thread.start()
        return thread

    def _gc_loop(self, interval_sec: int):
        """Background GC loop."""
        while not self._stop_event.is_set():
            try:
                self.cleanup_old_wals()
                self.rotate_current_wal()
            except Exception as e:
                self.logger.error(f"GC error: {e}")

            self._stop_event.wait(interval_sec)

    def cleanup_old_wals(self) -> int:
        """Remove WAL files older than retention_days."""
        cutoff_ts = time.time() - (self.retention_days * 86400)
        removed = 0

        for wal_file in self.wal_dir.glob("*.jsonl"):
            # Skip current WAL (today's file)
            today = time.strftime("%Y-%m-%d")
            if wal_file.name.startswith(today):
                continue

            file_mtime = wal_file.stat().st_mtime
            if file_mtime < cutoff_ts:
                try:
                    if self.archiver:
                        self.archiver.archive(
                            pattern=wal_file.name, remove_original=False,
                        )
                    wal_file.unlink()
                    removed += 1
                    self.logger.info(f"GC: Removed WAL {wal_file.name}")
                except Exception as e:
                    self.logger.error(f"Failed to remove {wal_file}: {e}")

        return removed

    def rotate_current_wal(self) -> bool:
        """Rotate WAL file when size exceeds max."""
        today = time.strftime("%Y-%m-%d")
        current_wal = self.wal_dir / f"{today}.jsonl"

        if not current_wal.exists():
            return False

        file_size = current_wal.stat().st_size
        if file_size > self.max_file_size_bytes:
            try:
                ts = int(time.time())
                new_name = self.wal_dir / f"{today}_{ts}.jsonl"
                current_wal.rename(new_name)
                self.logger.info(
                    f"GC: Rotated WAL (size was {file_size} bytes)")
                return True
            except Exception as e:
                self.logger.error(f"Failed to rotate WAL: {e}")

        return False

    def stop(self):
        """Stop background GC."""
        self._stop_event.set()

    def get_stats(self) -> dict:
        """Return WAL directory stats."""
        total_size = sum(
            f.stat().st_size for f in self.wal_dir.glob("*.jsonl"))
        file_count = len(list(self.wal_dir.glob("*.jsonl")))
        return {
            'total_size_mb': total_size / (1024 * 1024),
            'file_count': file_count,
        }
