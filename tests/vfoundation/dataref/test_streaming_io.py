"""
Phase 10.4: Tests for vfoundation.dataref.streaming_io.read_chunks().
Tests: normal read, custom chunk size, empty file, non-existent file.
"""
from __future__ import annotations

import pathlib

import pytest

from vfoundation.dataref.streaming_io import read_chunks


class TestReadChunks:
    """Tests for the read_chunks() streaming generator."""

    def test_reads_file_content(self, tmp_path: pathlib.Path) -> None:
        """read_chunks should yield all bytes from a file."""
        file = tmp_path / "test.bin"
        data = b"hello world " * 100
        file.write_bytes(data)
        chunks = list(read_chunks(str(file)))
        assert b"".join(chunks) == data, "expected all file bytes to be read"

    def test_yields_chunks_of_correct_size(self, tmp_path: pathlib.Path) -> None:
        """read_chunks with custom size should yield chunks <= size bytes."""
        chunk_size = 16
        file = tmp_path / "sized.bin"
        file.write_bytes(b"x" * 100)
        chunks = list(read_chunks(str(file), size=chunk_size))
        for chunk in chunks[:-1]:
            assert len(chunk) == chunk_size, (
                f"expected intermediate chunk of {chunk_size} bytes, got {len(chunk)}"
            )
        # Last chunk may be smaller
        assert len(chunks[-1]) > 0

    def test_empty_file_yields_no_chunks(self, tmp_path: pathlib.Path) -> None:
        """read_chunks on empty file should yield nothing."""
        file = tmp_path / "empty.bin"
        file.write_bytes(b"")
        chunks = list(read_chunks(str(file)))
        assert chunks == [], f"expected no chunks for empty file, got {len(chunks)} chunks"

    def test_missing_file_raises(self, tmp_path: pathlib.Path) -> None:
        """read_chunks on non-existent file should raise FileNotFoundError."""
        missing = str(tmp_path / "nonexistent.bin")
        with pytest.raises(FileNotFoundError):
            list(read_chunks(missing))

    def test_single_chunk_small_file(self, tmp_path: pathlib.Path) -> None:
        """File smaller than chunk_size should be returned in one chunk."""
        file = tmp_path / "small.bin"
        data = b"abc"
        file.write_bytes(data)
        chunks = list(read_chunks(str(file), size=8192))
        assert len(chunks) == 1
        assert chunks[0] == data
