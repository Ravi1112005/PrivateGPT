"""
core/vector_store.py — VectorStoreManager

Loads the FAISS index ONCE and keeps it in memory.
The Streamlit @st.cache_resource wrapper in app.py ensures a single
instance is shared across all reruns and users.

Features:
  - Hybrid search: FAISS (dense) + BM25 (sparse) via Reciprocal Rank Fusion
  - Neighbor chunk expansion: includes ±N adjacent chunks for context continuity
  - Lazy loading with thread-safe invalidation

Performance impact:
  Before: ~4s FAISS deserialization on every query
  After : ~0ms (index already in RAM)

Invalidation:
  Call mark_dirty() after the on-disk index is updated (e.g. after ingestion).
  The next search() call will transparently reload from disk.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from core.embeddings import EmbeddingsManager


class VectorStoreManager:
    """
    In-memory wrapper around a FAISS vector store with hybrid search
    and neighbor chunk expansion.

    Thread-safe: uses a lock when reloading so concurrent queries don't
    trigger multiple simultaneous disk reads.
    """

    def __init__(self, index_dir: Path, embeddings: "EmbeddingsManager") -> None:
        self._index_dir = index_dir
        self._embeddings = embeddings
        self._db = None          # Loaded FAISS instance (None = not yet loaded)
        self._dirty = False      # True = reload from disk before next search
        self._lock = threading.Lock()
        self._bm25_data = None   # {bm25: BM25Okapi, docs: list} — lazy-loaded

        # Chunk registry for neighbor expansion:
        #   source_file → sorted list of (chunk_index, Document)
        self._chunk_registry: Dict[str, List[Tuple[int, object]]] = {}

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

    def hybrid_search(
        self,
        query: str,
        k: int = 40,
        bm25_weight: float = 0.4,
        faiss_weight: float = 0.6,
    ) -> List:
        """
        Hybrid retrieval: FAISS (semantic) + BM25 (keyword),
        fused via Reciprocal Rank Fusion.

        Falls back to pure FAISS search when BM25 index is unavailable.
        """
        with self._lock:
            self._ensure_loaded()
            if self._db is None:
                return []

            # Dense retrieval (FAISS)
            faiss_results = self._db.similarity_search(query, k=k)

            # Sparse retrieval (BM25)
            bm25_results = self._bm25_search_unlocked(query, k=k)

            if not bm25_results:
                # BM25 unavailable — fall back to pure FAISS
                return faiss_results

            # Reciprocal Rank Fusion
            return self._rrf_fuse(faiss_results, bm25_results, faiss_weight, bm25_weight, k=k)

    def search_with_neighbors(
        self,
        query: str,
        k: int = 40,
        neighbor_window: int = 1,
        bm25_weight: float = 0.4,
        faiss_weight: float = 0.6,
    ) -> List:
        """
        Hybrid search with neighbor chunk expansion.

        After finding the top-k chunks, expands each by including
        ±neighbor_window adjacent chunks from the same source document.
        This provides better context continuity for tables and paragraphs
        that span chunk boundaries.

        Parameters
        ----------
        query : str
            Search query.
        k : int
            Number of initial candidates (before expansion).
        neighbor_window : int
            Number of chunks to include on each side (±N).
        bm25_weight, faiss_weight : float
            Weights for hybrid search fusion.

        Returns
        -------
        list of Document
            Expanded, deduplicated list of documents, ordered by:
            1. Original rank of the anchor chunk
            2. Chunk index (neighbors in document order)
        """
        # Get initial candidates via hybrid search
        candidates = self.hybrid_search(
            query, k=k, bm25_weight=bm25_weight, faiss_weight=faiss_weight
        )

        if not candidates or neighbor_window <= 0:
            return candidates

        with self._lock:
            return self._expand_neighbors(candidates, neighbor_window)

    def mark_dirty(self) -> None:
        """
        Signal that the on-disk index has changed.
        The next search() call will reload from disk.
        Called by IngestionPipeline after saving a new/updated index.
        """
        with self._lock:
            self._dirty = True
            self._db = None
            self._bm25_data = None          # Invalidate BM25 cache
            self._chunk_registry = {}       # Invalidate neighbor registry

    def is_ready(self) -> bool:
        """Return True if a valid FAISS index exists on disk."""
        return (self._index_dir / "index.faiss").exists()

    # ── Neighbor expansion ─────────────────────────────────────────────────

    def _expand_neighbors(self, candidates: List, window: int) -> List:
        """
        Expand each candidate chunk by including ±window adjacent chunks
        from the same source document.

        Must be called while holding self._lock.
        """
        self._ensure_chunk_registry()

        seen: Set[str] = set()
        expanded: List = []

        for doc in candidates:
            source = doc.metadata.get("source_file", "")
            chunk_idx = doc.metadata.get("chunk_index")

            # If no chunk_index metadata, include as-is
            if chunk_idx is None or source not in self._chunk_registry:
                key = self._doc_key(doc)
                if key not in seen:
                    seen.add(key)
                    expanded.append(doc)
                continue

            registry = self._chunk_registry[source]

            # Find the position of this chunk in the sorted registry
            pos = self._find_position(registry, chunk_idx)

            # Expand ±window around this position
            start = max(0, pos - window)
            end = min(len(registry), pos + window + 1)

            for i in range(start, end):
                neighbor_idx, neighbor_doc = registry[i]
                key = f"{source}:{neighbor_idx}"
                if key not in seen:
                    seen.add(key)
                    expanded.append(neighbor_doc)

        return expanded

    def _ensure_chunk_registry(self) -> None:
        """
        Build the chunk registry from the FAISS docstore.

        Maps source_file → sorted list of (chunk_index, Document).
        Must be called while holding self._lock.
        """
        if self._chunk_registry:
            return  # Already built

        if self._db is None:
            return

        registry: Dict[str, List[Tuple[int, object]]] = defaultdict(list)

        for doc in self._db.docstore._dict.values():
            source = doc.metadata.get("source_file", "")
            chunk_idx = doc.metadata.get("chunk_index")
            if source and chunk_idx is not None:
                registry[source].append((chunk_idx, doc))

        # Sort each file's chunks by index
        for source in registry:
            registry[source].sort(key=lambda x: x[0])

        self._chunk_registry = dict(registry)

    @staticmethod
    def _find_position(registry: List[Tuple[int, object]], chunk_idx: int) -> int:
        """Binary search for chunk_index in the sorted registry."""
        lo, hi = 0, len(registry) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if registry[mid][0] == chunk_idx:
                return mid
            elif registry[mid][0] < chunk_idx:
                lo = mid + 1
            else:
                hi = mid - 1
        return lo  # Closest position if exact match not found

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
        self._chunk_registry = {}  # Reset registry on reload

    def _bm25_search_unlocked(self, query: str, k: int) -> List:
        """
        Keyword search via BM25.  Must be called while holding self._lock.
        Returns empty list if BM25 index is unavailable.
        """
        if self._bm25_data is None:
            bm25_path = self._index_dir / "bm25_index.pkl"
            if not bm25_path.exists():
                return []
            try:
                import pickle
                with open(bm25_path, "rb") as f:
                    self._bm25_data = pickle.load(f)  # {bm25, docs}
            except Exception:  # noqa: BLE001
                return []

        try:
            bm25 = self._bm25_data["bm25"]
            docs = self._bm25_data["docs"]
            scores = bm25.get_scores(query.lower().split())
            top_indices = scores.argsort()[-k:][::-1]
            return [docs[i] for i in top_indices if scores[i] > 0]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _rrf_fuse(list_a: List, list_b: List,
                  weight_a: float, weight_b: float,
                  k: int = 60) -> List:
        """
        Reciprocal Rank Fusion — merge two ranked result lists.

        Uses document content as identity key (stable across different
        Python object identities after reload).
        """
        scores: dict = {}
        doc_map: dict = {}

        def _doc_key(doc) -> str:
            """Stable key: first 200 chars of content + source + page."""
            return (
                doc.page_content[:200]
                + str(doc.metadata.get("source_file", ""))
                + str(doc.metadata.get("page", ""))
            )

        for rank, doc in enumerate(list_a):
            key = _doc_key(doc)
            scores[key] = scores.get(key, 0.0) + weight_a / (rank + 60)
            doc_map[key] = doc

        for rank, doc in enumerate(list_b):
            key = _doc_key(doc)
            scores[key] = scores.get(key, 0.0) + weight_b / (rank + 60)
            doc_map.setdefault(key, doc)

        sorted_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [doc_map[key] for key in sorted_keys[:k]]

    @staticmethod
    def _doc_key(doc) -> str:
        """Stable identity key for deduplication."""
        return (
            doc.page_content[:200]
            + str(doc.metadata.get("source_file", ""))
            + str(doc.metadata.get("page", ""))
        )

    def __repr__(self) -> str:
        ready = "ready" if self.is_ready() else "no index"
        return f"VectorStoreManager(index={self._index_dir}, status={ready})"
