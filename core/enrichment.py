"""
core/enrichment.py — BackgroundEnricher

Progressive enhancement: enriches indexed chunks with LLM-generated context
sentences in a background daemon thread.  The system is immediately queryable
after ingestion; answer quality improves silently as enrichment completes.

Design decisions:
  - Daemon thread: dies automatically when Streamlit stops
  - Per-chunk progress: UI can poll enricher.status for the badge
  - Fault-tolerant: failed chunks keep their original content, never block user
  - Junk page filtering now happens at extraction time (PDFProcessor)
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from config.settings import Settings
    from core.embeddings import EmbeddingsManager
    from core.vector_store import VectorStoreManager


class BackgroundEnricher:
    """
    Background thread that enriches chunks with LLM-generated context.

    Progressive enhancement: system is queryable immediately,
    quality improves silently in the background.

    Usage::

        enricher = BackgroundEnricher(settings, embeddings, vsm)
        enricher.start(chunks)   # non-blocking

        # Poll status from UI:
        status = enricher.status  # {running: bool, total: int, done: int}
    """

    CONTEXT_PROMPT = """\
You are a document indexing assistant. Given a chunk of text from \
"{filename}" (page {page}), write a concise 1-2 sentence context \
that explains what document this is from and what this specific \
section covers. This context will be prepended to the chunk for search.

Chunk:
{chunk_text}

Context (1-2 sentences only):"""

    BATCH_SIZE = 5  # chunks per Ollama call batch

    def __init__(
        self,
        settings: "Settings",
        embeddings: "EmbeddingsManager",
        vsm: "VectorStoreManager",
    ) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._vsm = vsm
        self._thread: threading.Thread | None = None
        self._progress: dict = {"total": 0, "done": 0, "running": False}
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self, chunks: List) -> None:
        """Launch background enrichment (non-blocking)."""
        with self._lock:
            self._progress = {"total": len(chunks), "done": 0, "running": True}
        self._thread = threading.Thread(
            target=self._enrich_loop,
            args=(chunks,),
            daemon=True,
            name="BackgroundEnricher",
        )
        self._thread.start()

    @property
    def status(self) -> dict:
        """For UI status badge: {running, total, done}."""
        with self._lock:
            return dict(self._progress)

    # ── Internal ───────────────────────────────────────────────────────────

    def _enrich_loop(self, chunks: List) -> None:
        """Process chunks in batches, re-embed enriched text, update index."""
        try:
            from core.ssl_patch import patch_ssl_for_hf  # noqa: PLC0415
            patch_ssl_for_hf()
            from langchain_ollama import OllamaLLM  # noqa: PLC0415

            llm = OllamaLLM(
                model=self._settings.context_model,
                temperature=0.0,
            )

            enriched_chunks: List = []

            for batch in self._batched(chunks, self.BATCH_SIZE):
                for chunk in batch:
                    # Skip very short chunks (likely noise)
                    if len(chunk.page_content.strip()) < 50:
                        with self._lock:
                            self._progress["done"] += 1
                        continue

                    try:
                        context = llm.invoke(
                            self.CONTEXT_PROMPT.format(
                                filename=chunk.metadata.get("source_file", "unknown"),
                                page=chunk.metadata.get("page", "?"),
                                chunk_text=chunk.page_content[:500],
                            )
                        )
                        chunk.page_content = (
                            f"[Context: {context.strip()}]\n{chunk.page_content}"
                        )
                        chunk.metadata["enriched"] = True
                    except Exception:  # noqa: BLE001
                        pass  # Keep original content — never raise

                    enriched_chunks.append(chunk)

                    with self._lock:
                        self._progress["done"] += 1

            # Re-build both indexes with enriched chunks
            if enriched_chunks:
                self._rebuild_indexes(enriched_chunks)

        except Exception:  # noqa: BLE001
            pass  # Enrichment thread must never crash the parent process
        finally:
            with self._lock:
                self._progress["running"] = False

    def _rebuild_indexes(self, chunks: List) -> None:
        """Replace FAISS + BM25 indexes with enriched versions."""
        try:
            from langchain_community.vectorstores import FAISS  # noqa: PLC0415

            idx_dir = str(self._settings.index_dir)

            # Load existing index and update with enriched documents
            faiss_file = self._settings.index_dir / "index.faiss"
            if faiss_file.exists():
                db = FAISS.load_local(
                    idx_dir,
                    self._embeddings,
                    allow_dangerous_deserialization=True,
                )
                # Re-build from enriched chunks (full replace for quality)
                new_db = FAISS.from_documents(chunks, self._embeddings)
                db.merge_from(new_db)
            else:
                db = FAISS.from_documents(chunks, self._embeddings)

            db.save_local(idx_dir)

            # Rebuild BM25 index
            try:
                from rank_bm25 import BM25Okapi  # noqa
                import pickle

                corpus = [doc.page_content for doc in chunks]
                tokenized = [text.lower().split() for text in corpus]
                bm25 = BM25Okapi(tokenized)

                with open(self._settings.bm25_index_path, "wb") as f:
                    pickle.dump({"bm25": bm25, "docs": chunks}, f)
            except ImportError:
                pass  # BM25 optional

            # Reload in VectorStoreManager
            self._vsm.mark_dirty()

        except Exception:  # noqa: BLE001
            pass  # Never raise from enrichment background thread

    @staticmethod
    def _batched(iterable, n: int):
        """Yield successive n-sized batches from iterable."""
        from itertools import islice
        it = iter(iterable)
        while batch := list(islice(it, n)):
            yield batch
