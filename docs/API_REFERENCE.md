# 📖 API Reference

Class-level documentation for all core modules. Each section maps to a source file.

---

## `core/pdf_processor.py` — PDFProcessor

**Purpose:** Robust multi-strategy PDF extraction. Handles digital text, tables, scanned images, and mixed-content documents.

### Constructor

```python
PDFProcessor(ocr_dpi: int = 300, tesseract_path: str = "")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ocr_dpi` | `int` | `300` | DPI for rendering scanned pages before OCR. Higher = better quality, slower. |
| `tesseract_path` | `str` | `""` | Custom path to Tesseract binary. Empty = auto-detect. |

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `extract` | `(pdf_path: str) → List[Document]` | List of LangChain Documents | Extracts all pages using the 3-tier strategy. Each Document has `page_content` (cleaned text or Markdown table) and `metadata` (`source_file`, `page`, `content_type`). |

### Content Types in Metadata

| `content_type` | Source | Description |
|----------------|--------|-------------|
| `"text"` | Tier 1 (PyMuPDF) | Digital selectable text |
| `"table"` | Tier 2 (find_tables) | Structured table → Markdown format |
| `"ocr"` | Tier 3 (pytesseract) | OCR'd text from scanned/image page |

---

## `core/embeddings.py` — EmbeddingsManager

**Purpose:** Semantic text embeddings via sentence-transformers. Implements LangChain's `Embeddings` interface.

### Constructor

```python
EmbeddingsManager(model_name: str = "all-MiniLM-L6-v2")
```

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `preload` | `() → None` | — | Eagerly loads the model into RAM (call at startup). |
| `embed_query` | `(text: str) → List[float]` | 384-dim vector | Embed a single query (~8ms on CPU). |
| `embed_documents` | `(texts: List[str]) → List[List[float]]` | List of 384-dim vectors | Batch-embed documents (~50ms for 64 chunks). |

---

## `core/ingestion.py` — IngestionPipeline

**Purpose:** Orchestrates the full PDF → chunks → FAISS index pipeline.

### Constructor

```python
IngestionPipeline(settings, embeddings: EmbeddingsManager, vsm: VectorStoreManager)
```

### Class Attribute

| Attribute | Value | Description |
|-----------|-------|-------------|
| `EMBEDDING_BACKEND` | `"v4-robust-pdf"` | Version tag. Change triggers automatic full re-index. |

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `ingest` | `(pdf_paths, progress_callback?) → dict` | `{ingested, skipped, errors, total_chunks, total_docs}` | Index new PDFs. Skips unchanged files (SHA-256 hash check). |
| `rebuild` | `(progress_callback?) → dict` | Same as `ingest` | Wipe and re-index all tracked documents. |
| `remove` | `(filename: str) → bool` | Success flag | Remove a document from metadata + disk. Requires `rebuild()` after. |
| `list_documents` | `() → List[dict]` | `[{name, pages, chunks, indexed_at}]` | List all indexed documents. |

### Instance Attribute

| Attribute | Type | Description |
|-----------|------|-------------|
| `enricher` | `BackgroundEnricher \| None` | Reference to the background enricher (set after ingestion). |

---

## `core/vector_store.py` — VectorStoreManager

**Purpose:** In-memory FAISS + BM25 wrapper with hybrid search and neighbor chunk expansion.

### Constructor

```python
VectorStoreManager(index_dir: Path, embeddings: EmbeddingsManager)
```

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `search` | `(query, k=25) → List[Document]` | Top-k documents | Pure FAISS similarity search. |
| `hybrid_search` | `(query, k=40, bm25_weight=0.4, faiss_weight=0.6) → List[Document]` | Fused results | FAISS + BM25 with Reciprocal Rank Fusion. |
| `search_with_neighbors` | `(query, k=40, neighbor_window=1, ...) → List[Document]` | Expanded results | Hybrid search + ±N adjacent chunk expansion. |
| `mark_dirty` | `() → None` | — | Signal that on-disk index changed. Next search reloads. |
| `is_ready` | `() → bool` | — | True if `index.faiss` exists on disk. |

### Thread Safety

All public methods are thread-safe. Internal state is protected by `threading.Lock`.

---

## `core/enrichment.py` — BackgroundEnricher

**Purpose:** Progressive chunk enrichment via LLM-generated context sentences. Runs as a daemon thread.

### Constructor

```python
BackgroundEnricher(settings, embeddings: EmbeddingsManager, vsm: VectorStoreManager)
```

### Public Methods / Properties

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `start` | `(chunks: List[Document]) → None` | — | Launch background enrichment (non-blocking). |
| `status` | Property → `dict` | `{running: bool, total: int, done: int}` | For UI status badge polling. |

---

## `core/graph/engine.py` — RAGGraphEngine

**Purpose:** Drop-in replacement for the legacy QueryEngine. Exposes the same public API.

### Constructor

```python
RAGGraphEngine(vsm: VectorStoreManager, settings: Settings)
```

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `retrieve` | `(question, filter_files?) → (source_docs, context, prompt_text)` | Tuple | Phase 1: Retrieve + rerank. Used for immediate source chip display. |
| `stream_answer` | `(prompt_text, model) → Generator[str]` | Token generator | Phase 2: Stream tokens from Ollama. Returned over SSE. |
| `query` | `(question, model, filter_files?) → dict` | `{answer, sources, metrics, context}` | Full graph invocation (non-streaming). Used for session export. |

---

## `core/ollama_manager.py` — OllamaManager

**Purpose:** Manages the local Ollama server lifecycle and model inventory.

### Constructor

```python
OllamaManager(base_url: str = "http://localhost:11434")
```

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `is_running` | `() → bool` | — | Ping Ollama's health endpoint. |
| `get_status` | `() → dict` | `{running, url, models, model_count}` | Full status for UI status bar. |
| `start` | `() → (bool, str)` | Success + message | Start Ollama server via subprocess. |
| `list_models` | `() → List[str]` | Model names | List locally downloaded models. |
| `pull` | `(model_name, stream_callback?) → (bool, str)` | Success + message | Download a model with streaming progress. |
| `delete` | `(model_name) → (bool, str)` | Success + message | Remove a local model. |
| `get_info` | `(model_name) → dict \| None` | Model details | Get param count, quantization, family. |

---

## `security/auth.py` — AuthManager

**Purpose:** Local user authentication with PBKDF2-HMAC-SHA256 and audit logging.

### Constructor

```python
AuthManager(security_dir: Path)
```

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `setup_default_admin` | `() → None` | — | Creates `admin/admin123` if no users exist. |
| `authenticate` | `(username, password) → (bool, str)` | `(True, role)` or `(False, error)` | Verify credentials. |
| `register` | `(username, password, role="user") → (bool, str)` | Success + message | Create a new user account. |
| `change_password` | `(username, old_pass, new_pass) → (bool, str)` | Success + message | Update password. |
| `delete` | `(username) → (bool, str)` | Success + message | Remove user (protects last admin). |
| `list_users` | `() → List[dict]` | `[{username, role, created_at, last_login}]` | All registered users. |
| `read_audit_log` | `(lines=200) → str` | Log text | Last N lines of the audit log. |

---

## `sessions/manager.py` — SessionManager

**Purpose:** Per-user chat session persistence as JSON files.

### Constructor

```python
SessionManager(sessions_dir: Path)
```

### Public Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `create` | `(username, label?) → dict` | Session dict | Create a new chat session. |
| `load` | `(session_id) → dict \| None` | Session data | Load a session by ID. |
| `list_for_user` | `(username) → List[dict]` | Session summaries | All sessions for a user, sorted by date. |
| `add_message` | `(session_id, role, content, metadata?) → None` | — | Append a message to a session. |
| `delete` | `(session_id) → bool` | Success | Permanently remove a session. |
| `export_txt` | `(session_id) → str` | Formatted text | Export session as human-readable transcript. |

---

## `config/settings.py` — Settings

**Purpose:** Central configuration dataclass. Single source of truth for all paths and tunable parameters.

### All Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_dir` | `Path` | Project root | Base directory for all relative paths |
| `data_dir` | `Path` | `data/` | Root for all runtime data |
| `documents_dir` | `Path` | `data/documents/` | Permanent PDF storage |
| `index_dir` | `Path` | `data/faiss_index/` | FAISS + BM25 indexes |
| `sessions_dir` | `Path` | `data/sessions/` | Chat session JSON files |
| `security_dir` | `Path` | `data/security/` | Auth data |
| `embedding_model` | `str` | `"all-MiniLM-L6-v2"` | Sentence-transformer model name |
| `chunk_size` | `int` | `1000` | Max characters per chunk |
| `chunk_overlap` | `int` | `200` | Overlap between adjacent chunks |
| `fetch_k` | `int` | `25` | Wide candidate pool before filtering |
| `top_k` | `int` | `5` | Final chunks sent to LLM |
| `neighbor_window` | `int` | `1` | ±N adjacent chunks to include |
| `default_model` | `str` | `"phi3"` | Default Ollama model |
| `llm_temperature` | `float` | `0.1` | Generation temperature |
| `contextual_enrichment` | `bool` | `True` | Enable background chunk enrichment |
| `context_model` | `str` | `"phi3"` | Ollama model for enrichment |
| `hybrid_search` | `bool` | `True` | Enable FAISS + BM25 hybrid search |
| `bm25_weight` | `float` | `0.4` | BM25 weight in RRF fusion |
| `faiss_weight` | `float` | `0.6` | FAISS weight in RRF fusion |
| `reranker_model` | `str` | `"cross-encoder/ms-marco-MiniLM-L-6-v2"` | Cross-encoder model |
| `rerank_candidates` | `int` | `40` | Candidates fed to reranker |
| `rerank_top_n` | `int` | `4` | Final chunks after reranking |
| `ocr_dpi` | `int` | `300` | DPI for scanned page rendering |
| `tesseract_path` | `str` | `""` | Custom Tesseract binary path |
