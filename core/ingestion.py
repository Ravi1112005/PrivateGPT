"""
core/ingestion.py — IngestionPipeline

Handles the full PDF → chunks → embeddings → FAISS index pipeline.

Key behaviours:
  - Uses PDFProcessor for robust multi-format PDF extraction (text, tables, OCR)
  - Copies uploaded PDFs to data/documents/ permanently (not temp paths)
  - Skips files whose SHA-256 hash hasn't changed (idempotent)
  - Assigns sequential chunk_index metadata for neighbor expansion
  - Calls vsm.mark_dirty() after updating the index so queries auto-reload
  - Bumped EMBEDDING_BACKEND triggers automatic full re-index on upgrade
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from core.embeddings import EmbeddingsManager
    from core.vector_store import VectorStoreManager


ProgressCallback = Callable[[int, int, str], None]


class IngestionPipeline:
    """
    Orchestrates PDF ingestion into the shared FAISS vector index.

    Usage::

        pipeline = IngestionPipeline(settings, embeddings_mgr, vector_store_mgr)
        result = pipeline.ingest(["/tmp/upload.pdf"], progress_callback=my_cb)
    """

    EMBEDDING_BACKEND = "v4-robust-pdf"

    def __init__(
        self,
        settings,          # config.Settings
        embeddings: "EmbeddingsManager",
        vsm: "VectorStoreManager",
    ) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._vsm = vsm
        self.enricher = None  # BackgroundEnricher instance (set after ingestion)

    # ── Public API ─────────────────────────────────────────────────────────

    def ingest(
        self,
        pdf_paths: List[str],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict:
        """
        Ingest one or more PDFs into the shared FAISS index.

        Returns a summary dict::

            {
                "ingested":    ["doc1.pdf"],
                "skipped":     ["doc2.pdf"],
                "errors":      [{"file": "bad.pdf", "error": "..."}],
                "total_chunks": 9120,
                "total_docs":   3,
            }
        """
        metadata  = self._load_metadata()
        state     = self._load_state()
        backend   = state.get("embedding_backend")

        # If the embedding backend changed, wipe the old index and re-index everything
        if metadata and backend not in (None, self.EMBEDDING_BACKEND):
            tracked = [v["path"] for v in metadata.values() if Path(v["path"]).exists()]
            all_paths = list(dict.fromkeys(tracked + [str(p) for p in pdf_paths]))
            self._wipe_index()
            return self._run(all_paths, {}, progress_callback)

        return self._run([str(p) for p in pdf_paths], metadata, progress_callback)

    def rebuild(self, progress_callback: Optional[ProgressCallback] = None) -> Dict:
        """Re-index all tracked documents from scratch (used after deletions)."""
        metadata = self._load_metadata()
        if not metadata:
            return {"ingested": [], "skipped": [], "errors": [],
                    "total_chunks": 0, "total_docs": 0}

        pdf_paths = [v["path"] for v in metadata.values() if Path(v["path"]).exists()]
        self._wipe_index()
        return self._run(pdf_paths, {}, progress_callback)

    def remove(self, filename: str) -> bool:
        """
        Remove a document from the metadata registry and its permanent copy.
        NOTE: FAISS doesn't support partial deletion — call rebuild() after.
        """
        metadata = self._load_metadata()
        if filename not in metadata:
            return False

        perm = self._settings.documents_dir / filename
        if perm.exists():
            perm.unlink(missing_ok=True)

        del metadata[filename]
        self._save_metadata(metadata)
        return True

    def list_documents(self) -> List[Dict]:
        """Return indexed documents with summary metadata."""
        meta = self._load_metadata()
        return [
            {
                "name":       k,
                "pages":      v.get("pages", 0),
                "chunks":     v.get("chunks", 0),
                "indexed_at": v.get("indexed_at", ""),
            }
            for k, v in meta.items()
        ]

    # ── Internal ───────────────────────────────────────────────────────────

    def _run(
        self,
        pdf_paths: List[str],
        metadata: Dict,
        progress_callback: Optional[ProgressCallback],
    ) -> Dict:
        from langchain_community.vectorstores import FAISS                     # noqa
        from langchain_text_splitters import RecursiveCharacterTextSplitter    # noqa
        from core.pdf_processor import PDFProcessor                           # noqa

        # O(n) pure string scan — no model calls during splitting
        chunker = RecursiveCharacterTextSplitter(
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""],
        )

        # Robust PDF extraction (handles text, tables, OCR)
        pdf_processor = PDFProcessor(
            ocr_dpi=self._settings.ocr_dpi,
            tesseract_path=self._settings.tesseract_path,
        )

        new_docs: List = []
        ingested:  List[str] = []
        skipped:   List[str] = []
        errors:    List[Dict] = []

        for i, raw_path in enumerate(pdf_paths):
            src = Path(raw_path)
            name = src.name

            if progress_callback:
                progress_callback(i, len(pdf_paths), f"Processing {name}…")

            try:
                # Copy to permanent store
                perm = self._ensure_permanent_copy(src)
                fhash = self._file_hash(perm)

                # Skip unchanged documents
                if name in metadata and metadata[name]["hash"] == fhash:
                    skipped.append(name)
                    continue

                # Extract pages using robust PDFProcessor
                pages = pdf_processor.extract(str(perm))

                if not pages:
                    errors.append({"file": name, "error": "No extractable content found"})
                    continue

                # Chunk the extracted pages
                chunks = chunker.split_documents(pages)

                # Assign sequential chunk_index for neighbor expansion
                for idx, chunk in enumerate(chunks):
                    chunk.metadata["source_file"] = name
                    chunk.metadata["chunk_index"] = idx
                    # Ensure page is 1-indexed (PDFProcessor already does this)
                    if "page" not in chunk.metadata:
                        chunk.metadata["page"] = "?"

                new_docs.extend(chunks)
                metadata[name] = {
                    "hash":       fhash,
                    "pages":      len(pages),
                    "chunks":     len(chunks),
                    "indexed_at": datetime.now().isoformat(),
                    "path":       str(perm),
                }
                ingested.append(name)

            except Exception as exc:  # noqa: BLE001
                errors.append({"file": name, "error": str(exc)})

        # Build / extend FAISS index
        all_indexed_docs: List = []
        if new_docs:
            if progress_callback:
                progress_callback(len(pdf_paths), len(pdf_paths), "Building vector index…")

            idx_dir = str(self._settings.index_dir)
            faiss_file = self._settings.index_faiss_path

            if faiss_file.exists():
                db = FAISS.load_local(
                    idx_dir, self._embeddings, allow_dangerous_deserialization=True
                )
                db.add_documents(new_docs)
            else:
                db = FAISS.from_documents(new_docs, self._embeddings)

            db.save_local(idx_dir)

            # Collect all indexed docs for BM25 (existing + new)
            all_indexed_docs = list(db.docstore._dict.values())

            # Build BM25 index alongside FAISS
            try:
                from rank_bm25 import BM25Okapi  # noqa
                import pickle

                corpus = [doc.page_content for doc in all_indexed_docs]
                tokenized = [text.lower().split() for text in corpus]
                bm25 = BM25Okapi(tokenized)

                with open(self._settings.bm25_index_path, "wb") as f:
                    pickle.dump({"bm25": bm25, "docs": all_indexed_docs}, f)
            except ImportError:
                pass  # rank_bm25 not installed — fall back to FAISS-only

            # Signal VectorStoreManager that the on-disk index has changed
            self._vsm.mark_dirty()

        self._save_metadata(metadata)
        self._save_state()

        result = {
            "ingested":     ingested,
            "skipped":      skipped,
            "errors":       errors,
            "total_chunks": sum(v["chunks"] for v in metadata.values()),
            "total_docs":   len(metadata),
        }

        # Launch background enrichment (non-blocking) if enabled and docs were indexed
        if ingested and self._settings.contextual_enrichment and all_indexed_docs:
            try:
                from core.enrichment import BackgroundEnricher  # noqa
                self.enricher = BackgroundEnricher(
                    self._settings, self._embeddings, self._vsm
                )
                self.enricher.start(new_docs)
            except Exception:  # noqa: BLE001
                pass  # Enrichment is optional — never block the user

        return result

    def _wipe_index(self) -> None:
        idx_dir = self._settings.index_dir
        if idx_dir.exists():
            shutil.rmtree(idx_dir)
        idx_dir.mkdir(parents=True, exist_ok=True)
        self._save_metadata({})
        self._vsm.mark_dirty()

    def _ensure_permanent_copy(self, src: Path) -> Path:
        dst = self._settings.documents_dir / src.name
        if not dst.exists() or self._file_hash(src) != self._file_hash(dst):
            shutil.copy2(src, dst)
        return dst

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── Metadata helpers ───────────────────────────────────────────────────

    def _load_metadata(self) -> Dict:
        p = self._settings.index_meta_path
        if p.exists():
            with open(p) as fh:
                return json.load(fh)
        return {}

    def _save_metadata(self, meta: Dict) -> None:
        self._settings.index_dir.mkdir(parents=True, exist_ok=True)
        with open(self._settings.index_meta_path, "w") as fh:
            json.dump(meta, fh, indent=2)

    def _load_state(self) -> Dict:
        p = self._settings.index_state_path
        if p.exists():
            with open(p) as fh:
                return json.load(fh)
        return {}

    def _save_state(self) -> None:
        with open(self._settings.index_state_path, "w") as fh:
            json.dump(
                {"embedding_backend": self.EMBEDDING_BACKEND,
                 "updated_at": datetime.now().isoformat()},
                fh, indent=2,
            )
