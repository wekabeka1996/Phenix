"""
Phase 13 tests: reconcile.py, wal_archiver.py, latent_embeddings.py.
"""
from __future__ import annotations

import gzip
import json
import pathlib
from typing import List

import pytest

# ── reconcile.py ──────────────────────────────────────────────────────────────
from vfoundation.core.reconcile import (
    PositionReconciler,
    PositionSnapshot,
    ReconcileStatus,
)


class TestPositionReconciler:
    @pytest.fixture()
    def reconciler(self) -> PositionReconciler:
        return PositionReconciler(tolerance=1e-8)

    def _snap(self, symbol: str, qty: float, src: str = "internal") -> PositionSnapshot:
        return PositionSnapshot(symbol=symbol, qty=qty, source=src)

    def test_all_match(self, reconciler: PositionReconciler) -> None:
        """Identical snapshots should produce all MATCH with no mismatches."""
        internal = [self._snap("BTCUSDT", 1.0), self._snap("ETHUSDT", 2.0)]
        external = [self._snap("BTCUSDT", 1.0, "exchange"), self._snap("ETHUSDT", 2.0, "exchange")]
        report = reconciler.reconcile(internal, external)
        assert report.all_match is True
        assert report.match_rate == pytest.approx(1.0)
        assert report.total_symbols == 2

    def test_diverged_detected(self, reconciler: PositionReconciler) -> None:
        """Quantity delta > tolerance should produce DIVERGED mismatch."""
        internal = [self._snap("BTCUSDT", 1.0)]
        external = [self._snap("BTCUSDT", 1.5, "exchange")]
        report = reconciler.reconcile(internal, external)
        assert report.all_match is False
        assert len(report.mismatches) == 1
        assert report.mismatches[0].status == ReconcileStatus.DIVERGED
        assert report.mismatches[0].delta_qty == pytest.approx(-0.5)

    def test_missing_local(self, reconciler: PositionReconciler) -> None:
        """External symbol not in internal should be MISSING_LOCAL."""
        report = reconciler.reconcile(
            internal=[],
            external=[self._snap("SOLUSDT", 5.0, "exchange")],
        )
        assert report.mismatches[0].status == ReconcileStatus.MISSING_LOCAL

    def test_missing_external(self, reconciler: PositionReconciler) -> None:
        """Internal symbol not in external should be MISSING_EXTERNAL."""
        report = reconciler.reconcile(
            internal=[self._snap("SOLUSDT", 5.0)],
            external=[],
        )
        assert report.mismatches[0].status == ReconcileStatus.MISSING_EXTERNAL

    def test_within_tolerance(self, reconciler: PositionReconciler) -> None:
        """Delta within tolerance should count as MATCH."""
        delta = 1e-10  # < tolerance=1e-8
        internal = [self._snap("BTCUSDT", 1.0)]
        external = [self._snap("BTCUSDT", 1.0 + delta, "exchange")]
        report = reconciler.reconcile(internal, external)
        assert report.all_match is True

    def test_empty_inputs(self, reconciler: PositionReconciler) -> None:
        """No symbols → 100% match rate."""
        report = reconciler.reconcile([], [])
        assert report.total_symbols == 0
        assert report.match_rate == pytest.approx(1.0)

    def test_match_rate_partial(self, reconciler: PositionReconciler) -> None:
        """2 matched, 1 diverged → match_rate = 2/3."""
        internal = [
            self._snap("BTC", 1.0), self._snap("ETH", 2.0), self._snap("SOL", 3.0)
        ]
        external = [
            self._snap("BTC", 1.0, "e"), self._snap("ETH", 2.0, "e"), self._snap("SOL", 99.0, "e")
        ]
        report = reconciler.reconcile(internal, external)
        assert report.match_rate == pytest.approx(2 / 3)


# ── wal_archiver.py ───────────────────────────────────────────────────────────
from vfoundation.dataref.wal_archiver import WalArchiver


class TestWalArchiver:
    def test_archives_jsonl_files(self, tmp_path: pathlib.Path) -> None:
        """archive() should produce .gz files in archive_dir."""
        wal_dir = tmp_path / "wal"
        wal_dir.mkdir()
        arch_dir = tmp_path / "archive"
        (wal_dir / "wal_001.jsonl").write_text('{"op":"ASK"}\n', encoding="utf-8")
        archiver = WalArchiver(str(wal_dir), str(arch_dir))
        result = archiver.archive()
        assert result.files_archived == 1
        assert len(list(arch_dir.glob("*.gz"))) == 1

    def test_compressed_content_readable(self, tmp_path: pathlib.Path) -> None:
        """Archived .gz file should contain original content."""
        wal_dir = tmp_path / "wal"
        wal_dir.mkdir()
        arch_dir = tmp_path / "archive"
        content = '{"op":"ASK","rid":"r1"}\n{"op":"DEC","rid":"r1"}\n'
        (wal_dir / "wal_001.jsonl").write_text(content, encoding="utf-8")
        archiver = WalArchiver(str(wal_dir), str(arch_dir))
        archiver.archive(remove_original=False)
        gz_files = list(arch_dir.glob("*.gz"))
        with gzip.open(str(gz_files[0]), "rt", encoding="utf-8") as f:
            restored = f.read()
        assert restored == content

    def test_remove_original(self, tmp_path: pathlib.Path) -> None:
        """remove_original=True should delete source file after archive."""
        wal_dir = tmp_path / "wal"
        wal_dir.mkdir()
        arch_dir = tmp_path / "archive"
        f = wal_dir / "wal_001.jsonl"
        f.write_text('{"op":"ASK"}\n')
        archiver = WalArchiver(str(wal_dir), str(arch_dir))
        archiver.archive(remove_original=True)
        assert not f.exists(), "original WAL file should have been deleted"

    def test_min_size_skip(self, tmp_path: pathlib.Path) -> None:
        """Files below min_size_bytes should be skipped."""
        wal_dir = tmp_path / "wal"
        wal_dir.mkdir()
        arch_dir = tmp_path / "archive"
        (wal_dir / "tiny.jsonl").write_text("{}\n", encoding="utf-8")  # < 1000 bytes
        archiver = WalArchiver(str(wal_dir), str(arch_dir), min_size_bytes=1_000)
        result = archiver.archive()
        assert result.files_archived == 0
        assert result.files_skipped == 1

    def test_empty_wal_dir(self, tmp_path: pathlib.Path) -> None:
        """Archiving empty WAL dir should produce zero results."""
        wal_dir = tmp_path / "wal"
        wal_dir.mkdir()
        arch_dir = tmp_path / "archive"
        archiver = WalArchiver(str(wal_dir), str(arch_dir))
        result = archiver.archive()
        assert result.files_archived == 0
        assert result.compression_ratio == 0.0


# ── latent_embeddings.py ──────────────────────────────────────────────────────
from vfoundation.dataref.latent_embeddings import (
    EmbeddingProvider,
    EmbeddingRecord,
    InMemoryEmbeddingStore,
    StubEmbeddingProvider,
)


class TestEmbeddingRecord:
    def test_basic_record(self) -> None:
        """EmbeddingRecord should store vector and expose dim."""
        record = EmbeddingRecord(rid="r1", model="stub", vector=[0.1, 0.2, 0.3])
        assert record.dim == 3

    def test_empty_vector_raises(self) -> None:
        """Empty vector should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            EmbeddingRecord(rid="r1", model="stub", vector=[])

    def test_fingerprint_is_stable(self) -> None:
        """Same vector → same fingerprint."""
        r = EmbeddingRecord(rid="r1", model="stub", vector=[0.5, 0.5])
        assert r.fingerprint() == r.fingerprint()


class TestStubEmbeddingProvider:
    def test_is_embedding_provider(self) -> None:
        """StubEmbeddingProvider must implement EmbeddingProvider ABC."""
        provider = StubEmbeddingProvider()
        assert isinstance(provider, EmbeddingProvider)

    def test_embed_returns_correct_dim(self) -> None:
        """embed() should return vector with dim matching configuration."""
        provider = StubEmbeddingProvider(dim=16)
        record = provider.embed("test text", "r1")
        assert record.dim == 16

    def test_embed_deterministic(self) -> None:
        """Same text → same vector."""
        provider = StubEmbeddingProvider()
        r1 = provider.embed("hello", "r1")
        r2 = provider.embed("hello", "r2")  # different rid, same text
        assert r1.vector == r2.vector

    def test_dim_0_raises(self) -> None:
        """dim=0 should raise ValueError."""
        with pytest.raises(ValueError):
            StubEmbeddingProvider(dim=0)


class TestInMemoryEmbeddingStore:
    def test_upsert_and_get(self) -> None:
        """upsert then get should return the record."""
        store = InMemoryEmbeddingStore()
        record = EmbeddingRecord(rid="r1", model="stub", vector=[0.1])
        store.upsert(record)
        assert store.get("r1") is record

    def test_get_unknown_rid_returns_none(self) -> None:
        """get() for unknown rid should return None."""
        store = InMemoryEmbeddingStore()
        assert store.get("nonexistent") is None

    def test_len(self) -> None:
        """__len__ should reflect number of records."""
        store = InMemoryEmbeddingStore()
        store.upsert(EmbeddingRecord(rid="r1", model="stub", vector=[0.1]))
        store.upsert(EmbeddingRecord(rid="r2", model="stub", vector=[0.2]))
        assert len(store) == 2

    def test_clear(self) -> None:
        """clear() should remove all records."""
        store = InMemoryEmbeddingStore()
        store.upsert(EmbeddingRecord(rid="r1", model="stub", vector=[0.1]))
        store.clear()
        assert len(store) == 0
