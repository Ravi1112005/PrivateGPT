"""
config/settings.py — Central application configuration.

Single source of truth for all paths, model names, and tunable parameters.
Automatically migrates legacy flat-directory data to the new data/ structure.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Project root is two levels above this file (config/settings.py → config/ → root)
BASE_DIR: Path = Path(__file__).parent.parent


@dataclass
class Settings:
    """
    Immutable application settings.

    All paths are absolute so the app works regardless of the working directory
    that streamlit is launched from.
    """

    # ── Directories ────────────────────────────────────────────────────────
    base_dir: Path = field(default_factory=lambda: BASE_DIR)
    data_dir: Path = field(default_factory=lambda: BASE_DIR / "data")

    # Runtime data sub-directories (inside data/)
    documents_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "documents")
    index_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "faiss_index")
    sessions_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "sessions")
    security_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "security")

    # ── Embedding model ────────────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Document chunking ──────────────────────────────────────────────────
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # ── Retrieval ──────────────────────────────────────────────────────────
    fetch_k: int = 25          # Wide candidate pool before filtering
    top_k: int = 5             # Final chunks sent to LLM
    neighbor_window: int = 1   # ±N adjacent chunks to include around each hit

    # ── LLM ───────────────────────────────────────────────────────────────
    default_model: str = "phi3"
    llm_temperature: float = 0.1

    # ── Contextual Enrichment ─────────────────────────────────────────────
    contextual_enrichment: bool = True
    context_model: str = "phi3"          # Small/fast Ollama model for context gen

    # ── Hybrid Search ─────────────────────────────────────────────────────
    hybrid_search: bool = True
    bm25_weight: float = 0.4
    faiss_weight: float = 0.6

    # ── Reranking ─────────────────────────────────────────────────────────
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidates: int = 40          # Candidates fed to reranker
    rerank_top_n: int = 4                # Final chunks after reranking

    # ── OCR ───────────────────────────────────────────────────────────────
    ocr_dpi: int = 300                   # DPI for rendering scanned pages
    tesseract_path: str = ""             # Custom Tesseract binary path (auto-detect if empty)

    def __post_init__(self):
        """Create directories and run one-time data migration."""
        for d in (
            self.data_dir,
            self.documents_dir,
            self.index_dir,
            self.sessions_dir,
            self.security_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        self._migrate_legacy_data()

    def _migrate_legacy_data(self):
        """
        One-time migration: copy data from legacy flat dirs to data/.

        Legacy locations          →  New locations
        ──────────────────────────────────────────────────────
        faiss_index/              →  data/faiss_index/
        sessions_data/            →  data/sessions/
        documents/                →  data/documents/
        security/users.json       →  data/security/users.json
        security/audit.log        →  data/security/audit.log
        """
        # Directory migrations
        legacy_map = {
            self.base_dir / "faiss_index":   self.index_dir,
            self.base_dir / "sessions_data": self.sessions_dir,
            self.base_dir / "documents":     self.documents_dir,
        }
        for src, dst in legacy_map.items():
            if src.exists() and src != dst:
                for item in src.iterdir():
                    target = dst / item.name
                    if not target.exists():
                        shutil.copy2(item, target)

        # Security data files (only data files, not auth.py code)
        for fname in ("users.json", "audit.log"):
            src = self.base_dir / "security" / fname
            dst = self.security_dir / fname
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

    # ── Derived paths ──────────────────────────────────────────────────────

    @property
    def index_faiss_path(self) -> Path:
        return self.index_dir / "index.faiss"

    @property
    def index_meta_path(self) -> Path:
        return self.index_dir / "doc_metadata.json"

    @property
    def index_state_path(self) -> Path:
        return self.index_dir / "index_state.json"

    @property
    def users_file(self) -> Path:
        return self.security_dir / "users.json"

    @property
    def audit_file(self) -> Path:
        return self.security_dir / "audit.log"

    @property
    def bm25_index_path(self) -> Path:
        return self.index_dir / "bm25_index.pkl"

    def index_exists(self) -> bool:
        """True when a valid FAISS index is present on disk."""
        return self.index_faiss_path.exists()


# Module-level singleton — import this everywhere.
settings = Settings()
