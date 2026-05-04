"""
Latent embedding stubs (Phase 13.3).

Foundation for context-window embeddings for pattern recognition.
Provides abstract EmbeddingProvider, EmbeddingRecord, and an InMemory store.

Real embedding generation (e.g., via OpenAI/Ollama) is deferred to Phase 15.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EmbeddingRecord:
    """Stores a latent embedding for a context window or event sequence."""
    rid: str               # Request ID this embedding represents
    model: str             # Embedding model (e.g., "stub-v0")
    vector: List[float]    # Embedding vector (must be non-empty)
    meta: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.vector:
            raise ValueError("Embedding vector must be non-empty")

    @property
    def dim(self) -> int:
        """Dimensionality of the embedding vector."""
        return len(self.vector)

    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the vector for deduplication."""
        raw = ",".join(f"{v:.6f}" for v in self.vector)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class EmbeddingProvider(ABC):
    """Abstract base class for embedding generation."""

    @abstractmethod
    def embed(self, text: str, rid: str) -> EmbeddingRecord:
        """Generate an embedding record for the given text and request ID."""
        ...


class StubEmbeddingProvider(EmbeddingProvider):
    """
    Stub embedding provider for testing and offline use.

    Generates deterministic zero-valued vectors of configurable dimension.
    ALL vectors are identical (not useful for similarity, only for wiring tests).

    Args:
        dim: Embedding dimension. Default=8 (small for tests).
        model: Model name to tag records with. Default="stub-v0".
    """

    def __init__(self, dim: int = 8, model: str = "stub-v0") -> None:
        if dim <= 0:
            raise ValueError(f"dim must be > 0, got {dim}")
        self.dim = dim
        self.model = model

    def embed(self, text: str, rid: str) -> EmbeddingRecord:
        """Generate a zero-vector embedding (deterministic stub)."""
        # Deterministic: hash text to get a simple float pattern
        digest = hashlib.sha256(text.encode()).hexdigest()
        vector = [float(int(digest[i * 2: i * 2 + 2], 16)) / 255.0 for i in range(self.dim)]
        return EmbeddingRecord(rid=rid, model=self.model, vector=vector)


class InMemoryEmbeddingStore:
    """
    In-memory store for EmbeddingRecord objects.

    Keyed by rid. Supports upsert and similarity-less lookup.
    """

    def __init__(self) -> None:
        self._store: Dict[str, EmbeddingRecord] = {}

    def upsert(self, record: EmbeddingRecord) -> None:
        """Store or overwrite an embedding record."""
        self._store[record.rid] = record

    def get(self, rid: str) -> Optional[EmbeddingRecord]:
        """Retrieve embedding record by rid, or None if not found."""
        return self._store.get(rid)

    def all_rids(self) -> List[str]:
        """Return sorted list of all stored request IDs."""
        return sorted(self._store.keys())

    def clear(self) -> None:
        """Clear all stored embeddings."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
