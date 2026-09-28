# ⚙️ Configuration

All configuration lives in `config/settings.py` as a Python `dataclass`. There is no external config file — all values are code-level defaults that can be modified directly.

---

## How Configuration Works

```python
# config/settings.py
@dataclass
class Settings:
    chunk_size: int = 1000
    chunk_overlap: int = 200
    # ... etc

settings = Settings()  # Module-level singleton
```

```python
# Anywhere in the codebase
from config.settings import settings
print(settings.chunk_size)  # 1000
```

The `Settings` dataclass is instantiated once at module import time. Its `__post_init__` method:
1. Creates all `data/` subdirectories if they don't exist
2. Runs one-time legacy data migration (from flat dirs to `data/`)

---

## All Parameters

### Directories

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_dir` | Project root | Absolute path to the PrivateGPT root directory |
| `data_dir` | `data/` | Root for all runtime data |
| `documents_dir` | `data/documents/` | Permanent copies of uploaded PDFs |
| `index_dir` | `data/faiss_index/` | FAISS index, BM25 index, metadata |
| `sessions_dir` | `data/sessions/` | Per-user chat session JSON files |
| `security_dir` | `data/security/` | `users.json` + `audit.log` |

### Embedding Model

| Parameter | Default | Description |
|-----------|---------|-------------|
| `embedding_model` | `"all-MiniLM-L6-v2"` | Sentence-transformer model name. 384 dimensions, ~80 MB. |

### Document Chunking

| Parameter | Default | Effect |
|-----------|---------|--------|
| `chunk_size` | `1000` | Max characters per chunk. Larger = more context per chunk but fewer chunks. |
| `chunk_overlap` | `200` | Characters shared between adjacent chunks. Prevents sentence-cutting at boundaries. |

**Tuning guidance:**
- **Increase `chunk_size`** (to 1500-2000) if your PDFs have long paragraphs or complex tables
- **Decrease `chunk_size`** (to 500-800) if your PDFs have many short, independent sections
- **Increase `chunk_overlap`** (to 300) if answers are missing context that spans chunk boundaries

### Retrieval

| Parameter | Default | Effect |
|-----------|---------|--------|
| `fetch_k` | `25` | Candidate pool size before reranking. Higher = more recall, slower. |
| `top_k` | `5` | Final chunks sent to LLM (fallback when reranker is unavailable). |
| `neighbor_window` | `1` | ±N adjacent chunks included around each hit. `0` disables expansion. |

**Tuning guidance:**
- **Increase `neighbor_window`** (to 2-3) for long-form documents where context spans multiple chunks
- **Set `neighbor_window = 0`** for FAQs or documents with self-contained sections

### LLM

| Parameter | Default | Effect |
|-----------|---------|--------|
| `default_model` | `"phi3"` | Ollama model used for queries. Can be changed from the sidebar. |
| `llm_temperature` | `0.1` | Controls answer randomness. 0.0 = deterministic, 1.0 = creative. |

**Tuning guidance:**
- Keep temperature at `0.1` for factual document Q&A
- Increase to `0.3-0.5` for summarization or creative tasks

### Contextual Enrichment

| Parameter | Default | Effect |
|-----------|---------|--------|
| `contextual_enrichment` | `True` | Enable background LLM-based chunk enrichment after indexing. |
| `context_model` | `"phi3"` | Ollama model used for generating context sentences. Use a small/fast model. |

**Tuning guidance:**
- Set to `False` if you want maximum indexing speed and don't need enrichment
- Use a smaller model (e.g., `tinyllama:1.1b`) for faster enrichment at lower quality

### Hybrid Search

| Parameter | Default | Effect |
|-----------|---------|--------|
| `hybrid_search` | `True` | Enable FAISS + BM25 fusion. `False` = FAISS-only. |
| `bm25_weight` | `0.4` | Weight of keyword (BM25) results in Reciprocal Rank Fusion. |
| `faiss_weight` | `0.6` | Weight of semantic (FAISS) results in Reciprocal Rank Fusion. |

**Tuning guidance:**
- **Increase `bm25_weight`** (to 0.5-0.7) if your queries contain specific technical terms, codes, or identifiers
- **Increase `faiss_weight`** (to 0.7-0.8) if your queries are natural-language paraphrases

### Reranking

| Parameter | Default | Effect |
|-----------|---------|--------|
| `reranker_model` | `"cross-encoder/ms-marco-MiniLM-L-6-v2"` | Cross-encoder for precision reranking |
| `rerank_candidates` | `40` | How many candidates to feed to the reranker |
| `rerank_top_n` | `4` | How many to keep after reranking |

**Tuning guidance:**
- **Increase `rerank_top_n`** (to 6-8) if answers are missing important context
- **Decrease `rerank_top_n`** (to 2-3) if answers contain too much irrelevant information

### OCR

| Parameter | Default | Effect |
|-----------|---------|--------|
| `ocr_dpi` | `300` | Resolution for rendering scanned pages. Higher = better OCR, slower. |
| `tesseract_path` | `""` | Path to Tesseract binary. Empty = auto-detect common Windows paths. |

**Tuning guidance:**
- **Increase `ocr_dpi`** (to 400-600) for very small text or poor-quality scans
- **Decrease `ocr_dpi`** (to 150-200) for faster processing of standard documents

---

## Derived Paths (Properties)

These are computed from the base settings and cannot be set directly:

| Property | Value | Used By |
|----------|-------|---------|
| `index_faiss_path` | `data/faiss_index/index.faiss` | VectorStoreManager |
| `index_meta_path` | `data/faiss_index/doc_metadata.json` | IngestionPipeline |
| `index_state_path` | `data/faiss_index/index_state.json` | IngestionPipeline |
| `users_file` | `data/security/users.json` | AuthManager |
| `audit_file` | `data/security/audit.log` | AuthManager |
| `bm25_index_path` | `data/faiss_index/bm25_index.pkl` | IngestionPipeline |

---

## Changing Configuration

1. Open `config/settings.py`
2. Modify the default value of any field
3. Restart the app (`start-app.bat`)

**If you change `embedding_model`:** You must also bump the `EMBEDDING_BACKEND` constant in `core/ingestion.py` and rebuild the index. The app will show a migration banner automatically.
