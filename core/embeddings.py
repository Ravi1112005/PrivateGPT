"""
core/embeddings.py — EmbeddingsManager

Loads the sentence-transformer model ONCE and keeps it in memory.
The Streamlit @st.cache_resource wrapper in app.py ensures a single
instance is shared across all reruns and users.

Performance impact:
  Before: ~10s model load on every query
  After : ~0ms (model already warm in RAM)
"""

from __future__ import annotations

from typing import List, Optional

from langchain_core.embeddings import Embeddings


class EmbeddingsManager(Embeddings):
    """
    Semantic embeddings backed by sentence-transformers.

    Designed to be instantiated once (via @st.cache_resource) and reused
    for the lifetime of the Streamlit server process.

    Model: all-MiniLM-L6-v2
    - 384 dimensions
    - ~80 MB download (cached locally after first run, then fully offline)
    - Fast CPU inference (~8 ms per query, ~50 ms per batch of 64 chunks)
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Optional[object] = None

    # ── Model lifecycle ────────────────────────────────────────────────────

    def preload(self) -> None:
        """Eagerly load the model into memory (call once at startup)."""
        self._get_model()

    def _get_model(self):
        """Lazy-load on first access; subsequent calls return cached model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            self._model = SentenceTransformer(self.model_name)
        return self._model

    # ── Embeddings interface ───────────────────────────────────────────────

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string (~8 ms on CPU)."""
        model = self._get_model()
        vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Batch-embed a list of document chunks.

        Significantly faster than calling embed_query() in a loop because
        sentence-transformers processes all texts in a single forward pass.
        """
        model = self._get_model()
        vecs = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        return vecs.tolist()

    # ── Convenience ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        loaded = "loaded" if self._model is not None else "not loaded"
        return f"EmbeddingsManager(model={self.model_name!r}, status={loaded})"
