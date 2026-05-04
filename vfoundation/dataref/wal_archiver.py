"""
WAL archiver (Phase 13.2).

Provides WAL file archiving: rotates active JSONL files into compressed
archives for long-term storage. Configurable retention, chunk sizes.

No hardcoded paths or sizes — all supplied as parameters.
"""
from __future__ import annotations

import gzip
import os
import pathlib
import shutil
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ArchiveResult:
    """Result of a WAL archive operation."""
    files_archived: int
    files_skipped: int
    total_bytes_original: int
    total_bytes_compressed: int
    archive_dir: str

    @property
    def compression_ratio(self) -> float:
        """Bytes saved as fraction of original (0.0 if nothing archived)."""
        if self.total_bytes_original <= 0:
            return 0.0
        return 1.0 - (self.total_bytes_compressed / self.total_bytes_original)


class WalArchiver:
    """
    Archives WAL JSONL files by gzip-compressing them into an archive directory.

    Args:
        wal_dir: Directory containing active WAL JSONL files.
        archive_dir: Directory to store compressed archives.
        min_size_bytes: Only archive files at least this large. Default=0 (all files).
    """

    def __init__(
        self,
        wal_dir: str,
        archive_dir: str,
        min_size_bytes: int = 0,
    ) -> None:
        self.wal_dir = pathlib.Path(wal_dir)
        self.archive_dir = pathlib.Path(archive_dir)
        self.min_size_bytes = min_size_bytes

    def archive(self, pattern: str = "*.jsonl", remove_original: bool = True) -> ArchiveResult:
        """
        Archive WAL files matching pattern.

        Args:
            pattern: Glob pattern for WAL files to archive. Default="*.jsonl".
            remove_original: Delete source file after successful archive. Default=True.

        Returns:
            ArchiveResult with counts and compression statistics.
        """
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        files_archived = 0
        files_skipped = 0
        total_original = 0
        total_compressed = 0

        for wal_file in sorted(self.wal_dir.glob(pattern)):
            file_size = wal_file.stat().st_size
            if file_size < self.min_size_bytes:
                files_skipped += 1
                continue

            archive_path = self.archive_dir / (wal_file.name + ".gz")
            with wal_file.open("rb") as f_in:
                with gzip.open(str(archive_path), "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            compressed_size = archive_path.stat().st_size
            total_original += file_size
            total_compressed += compressed_size
            files_archived += 1

            if remove_original:
                wal_file.unlink()

        return ArchiveResult(
            files_archived=files_archived,
            files_skipped=files_skipped,
            total_bytes_original=total_original,
            total_bytes_compressed=total_compressed,
            archive_dir=str(self.archive_dir),
        )

    def list_archives(self) -> List[pathlib.Path]:
        """Return sorted list of .gz files in archive_dir."""
        if not self.archive_dir.exists():
            return []
        return sorted(self.archive_dir.glob("*.gz"))
