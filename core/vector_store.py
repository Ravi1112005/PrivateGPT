"""
core/vector_store.py — VectorStoreManager

Loads the FAISS index ONCE and keeps it in memory.
The Streamlit @st.cache_resource wrapper in app.py ensures a single
instance is shared across all reruns and users.

Performance impact:
  Before: ~4s FAISS deserialization on every query
  After : ~0ms (index already in RAM)

Invalidation:
  Call mark_dirty() after the on-disk index is updated (e.g. after ingestion).
  The next search() call will transparently reload from disk.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.embeddings import EmbeddingsManager


class VectorStoreManager:
    """
    In-memory wrapper around a FAISS vector store.

    Thread-safe: uses a lock when reloading so concurrent queries don't
    trigger multiple simultaneous disk reads.
    """

    def __init__(self, index_dir: Path, embeddings: "EmbeddingsManager") -> None:
        self._index_dir = index_dir
        self._embeddings = embeddings
        self._db = None          # Loaded FAISS instance (None = not yet loaded)
        self._dirty = False      # True = reload from disk before next search
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 25) -> List:
        """
        Embed query and return the top-k most similar document chunks.

        Automatically reloads from disk when mark_dirty() has been called.
        Returns an empty list if no index exists yet.
        """
        with self._lock:
            self._ensure_loaded()
            if self._db is None:
                return []
            return self._db.similarity_search(query, k=k)

    def mark_dirty(self) -> None:
        """
        Signal that the on-disk index has changed.
        The next search() call will reload from disk.
        Called by IngestionPipeline after saving a new/updated index.
        """
        with self._lock:
            self._dirty = True
            self._db = None

    def is_ready(self) -> bool:
        """Return True if a valid FAISS index exists on disk."""
        return (self._index_dir / "index.faiss").exists()

    # ── Internal ───────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Load (or reload) the FAISS index from disk if needed."""
        if self._db is not None and not self._dirty:
            return  # Already warm — fast path

        faiss_file = self._index_dir / "index.faiss"
        if not faiss_file.exists():
            self._db = None
            self._dirty = False
            return

        from langchain_community.vectorstores import FAISS  # noqa: PLC0415
        self._db = FAISS.load_local(
            str(self._index_dir),
            self._embeddings,
            allow_dangerous_deserialization=True,
        )
        self._dirty = False

    def __repr__(self) -> str:
        ready = "ready" if self.is_ready() else "no index"
        return f"VectorStoreManager(index={self._index_dir}, status={ready})"
