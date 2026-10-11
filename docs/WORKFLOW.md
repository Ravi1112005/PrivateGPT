# 🔄 Workflow

This document traces every major workflow through the system, from the user's action in the Electron UI to the final output. Each step references the exact source file and method responsible.

---

## 0. Application Startup Workflow

**Trigger:** User runs `start-app.bat` or launches the installed application.

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ start-   │──▶│ FastAPI   │──▶│ Singleton│──▶│ Electron │──▶│ Wait for │
│ app.bat  │   │ Backend   │   │ Loading  │   │ Window   │   │ Backend  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                                   │
                                                              ┌────▼────┐
                                                              │ Renderer│
                                                              │ Ready   │
                                                              └─────────┘
```

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Launch script** | `start-app.bat` | Checks Python venv exists, installs Electron if needed, starts FastAPI backend via uvicorn on port 8765. |
| 2. **Backend startup** | `backend/server.py` (module level) | Loads embedding model (from local cache if available), initializes singletons: `EmbeddingsManager`, `VectorStoreManager`, `OllamaManager`, `SessionManager`, `IngestionPipeline`, `RAGGraphEngine`. |
| 3. **Model loading** | `backend/server.py` line 63 | Checks if `embedding_model_path/config.json` exists → loads from local disk (fast) or HuggingFace (first run). |
| 4. **Electron launch** | `electron/main.js` → `startBackend()` | Checks if backend is already running (dev mode). If not, spawns Python as child process. |
| 5. **Window creation** | `electron/main.js` → `createWindow()` | Creates frameless BrowserWindow (1400×900, min 1000×700) with custom dark background. |
| 6. **Backend wait** | `electron/main.js` → `waitForBackend()` | Polls `GET /api/info` up to 30 times (1s interval). Sends `backend-ready` or `backend-error` event to renderer. |
| 7. **Renderer init** | `electron/renderer/app.js` | Receives `backend-ready` event, fetches `/api/info` for app state, renders the UI. |

---

## 1. Document Ingestion Workflow

**Trigger:** User selects PDFs in the Documents view and clicks "Index documents".

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────┐
│ File     │───▶│ PDFProcessor │───▶│   Chunker    │───▶│  FAISS   │───▶│  BM25    │
│ Picker   │    │ (3-tier)     │    │ (Recursive)  │    │  Index   │    │  Index   │
└──────────┘    └──────────────┘    └──────────────┘    └──────────┘    └──────────┘
                       │                                                      │
                       ▼                                                      ▼
                ┌──────────────┐                                     ┌──────────────┐
                │ Background   │                                     │ mark_dirty() │
                │ Enricher     │────────────────────────────────────▶│ (hot reload) │
                └──────────────┘                                     └──────────────┘
```

### Step-by-step

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **File selection** | `electron/main.js` → `select-files` IPC | Native file dialog opens with PDF filter. Returns array of file paths. |
| 2. **Upload** | `backend/server.py` → `POST /api/documents/upload` | Files are sent as multipart form data to FastAPI. Written to OS temp dir. |
| 3. **Permanent copy** | `core/ingestion.py` → `_ensure_permanent_copy()` | PDF is copied to `data/documents/` for persistence. |
| 4. **Hash check** | `core/ingestion.py` → `_file_hash()` | SHA-256 hash is compared against stored metadata. If unchanged, file is skipped (idempotent). |
| 5. **PDF extraction** | `core/pdf_processor.py` → `extract()` | 3-tier extraction runs per page (see below). |
| 6. **Text cleaning** | `core/pdf_processor.py` → `_clean_text()` | Headers, footers, page numbers, and boilerplate are stripped. |
| 7. **Chunking** | `core/ingestion.py` → `_run()` | `RecursiveCharacterTextSplitter` splits into 1000-char chunks with 200-char overlap. Each chunk gets a sequential `chunk_index` in metadata. |
| 8. **FAISS indexing** | `core/ingestion.py` → `_run()` | Chunks are embedded via `EmbeddingsManager` (all-MiniLM-L6-v2) and stored in FAISS. |
| 9. **BM25 indexing** | `core/ingestion.py` → `_run()` | Parallel keyword index built with `rank_bm25.BM25Okapi`. |
| 10. **Hot reload** | `core/vector_store.py` → `mark_dirty()` | Signals `VectorStoreManager` to reload from disk on next query. |
| 11. **Enrichment** | `core/enrichment.py` → `BackgroundEnricher.start()` | Daemon thread starts enriching chunks with LLM-generated context (non-blocking). |
| 12. **Response** | `backend/server.py` | Returns JSON: `{ingested, skipped, errors, total_chunks, total_docs}`. |

### PDF Extraction — 3-Tier Strategy

```
                    ┌─────────────────┐
                    │   PDF Page N    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
              ┌─────│ Has tables?     │─────┐
              │ YES └─────────────────┘ NO  │
              │                             │
    ┌─────────▼─────────┐         ┌─────────▼─────────┐
    │ Tier 2: Extract   │         │                   │
    │ tables → Markdown │         │                   │
    └───────────────────┘         │                   │
                                  │                   │
                         ┌────────▼────────┐          │
                   ┌─────│ Has text ≥30ch? │─────┐    │
                   │ YES └─────────────────┘ NO  │    │
                   │                             │    │
         ┌─────────▼─────────┐         ┌─────────▼────▼──┐
         │ Tier 1: PyMuPDF   │         │ Tier 3: OCR    │
         │ text extraction   │         │ (pytesseract)  │
         └───────────────────┘         └────────────────┘
```

| Tier | When | Method | Content Type |
|------|------|--------|-------------|
| **1. Text** | Page has ≥30 chars of selectable text | `page.get_text("text")` | `"text"` |
| **2. Tables** | `page.find_tables()` detects table structures | Extract → Markdown format | `"table"` |
| **3. OCR** | Page has <30 chars AND no tables (scanned/image) | Render to 300 DPI → `pytesseract.image_to_string()` | `"ocr"` |

---

## 2. Query (RAG) Workflow

**Trigger:** User types a question in the Chat view and sends it.

```
┌──────────┐   ┌───────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Question │──▶│ Hybrid    │──▶│ Neighbor │──▶│ Rerank   │──▶│ Prompt   │──▶│ Ollama   │
│ (user)   │   │ Search    │   │ Expand   │   │ (cross-  │   │ Template │   │ Stream   │
│          │   │ FAISS+BM25│   │ (±1 adj) │   │ encoder) │   │          │   │ Tokens   │
└──────────┘   └───────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

### Phase 1: Retrieval (fast, ~0.5s)

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Request** | `electron/renderer/app.js` | Sends `POST /api/chat/stream` with `ChatRequest` body (question, model, session_id, filter_files). |
| 2. **Hybrid search** | `core/vector_store.py` → `search_with_neighbors()` | FAISS (dense, semantic) + BM25 (sparse, keyword) search in parallel. |
| 3. **RRF fusion** | `core/vector_store.py` → `_rrf_fuse()` | Reciprocal Rank Fusion merges both result lists with configurable weights (60% FAISS, 40% BM25). |
| 4. **Neighbor expansion** | `core/vector_store.py` → `_expand_neighbors()` | For each hit, ±1 adjacent chunks from the same document are included. Uses `chunk_index` metadata and binary search over the chunk registry. |
| 5. **File filtering** | `core/graph/engine.py` → `retrieve()` | Only chunks from selected documents are kept. |
| 6. **Cross-encoder reranking** | `core/graph/engine.py` → `retrieve()` | `ms-marco-MiniLM-L-6-v2` scores each (query, chunk) pair with deep attention. Top 4 kept. |
| 7. **SSE: source chips** | `backend/server.py` → SSE `sources` event | Source file/page badges are sent immediately — user sees retrieval results while generation starts. |

### Phase 2: Generation (streaming, ~5-70s)

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 8. **Prompt assembly** | `core/graph/nodes.py` → `_PROMPT_TEMPLATE` | Context chunks formatted with source attribution, injected into a strict grounding prompt. |
| 9. **Streaming** | `core/graph/engine.py` → `stream_answer()` | `OllamaLLM.stream()` yields tokens one-by-one. |
| 10. **SSE delivery** | `backend/server.py` → SSE `token` events | Each token is sent as an SSE event to the renderer. |
| 11. **Live render** | `electron/renderer/app.js` | Each token is appended to the answer display in real-time. |
| 12. **Session save** | `sessions/manager.py` → `add_message()` | Full answer, sources, and metrics are persisted to the session JSON. |
| 13. **Completion** | `backend/server.py` → SSE `done` event | Final metrics (latency, retrieval time, chunks, model) sent to frontend. |

### Full Graph (non-streaming fallback)

When the full LangGraph is invoked (e.g., via `POST /api/chat`), it executes all 6 nodes:

```
__start__  →  retrieve  →  rerank  →  check_retrieval  ─┬─ (ok)  → generate → validate → finalize
                                                          └─ (fail) → finalize
```

The `validate` node performs a zero-latency heuristic grounding check: it verifies that the answer references content from the source chunks (≥20% chunk overlap required).

---

## 3. Background Enrichment Workflow

**Trigger:** Automatically after successful document indexing (if `contextual_enrichment = True`).

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Ingestion│──▶│ Daemon   │──▶│ LLM Gen  │──▶│ Re-index │
│ Complete │   │ Thread   │   │ Context  │   │ FAISS+   │
│          │   │ Start    │   │ per chunk│   │ BM25     │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
                    │                              │
                    ▼                              ▼
              ┌──────────┐                  ┌──────────┐
              │ Status   │                  │mark_dirty│
              │ Polling  │                  │(hot swap)│
              └──────────┘                  └──────────┘
```

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Launch** | `core/enrichment.py` → `BackgroundEnricher.start()` | A Python daemon thread starts (dies when FastAPI backend stops). |
| 2. **Per-chunk enrichment** | `core/enrichment.py` → `_enrich_loop()` | For each chunk, the LLM (phi3) generates a 1-2 sentence context summary: *"This chunk is from document X, page Y, discussing Z."* |
| 3. **Prepend context** | `core/enrichment.py` → `_enrich_loop()` | Context is prepended as `[Context: ...]` to the chunk text. |
| 4. **Re-index** | `core/enrichment.py` → `_rebuild_indexes()` | Enriched chunks are re-embedded and stored in FAISS + BM25. |
| 5. **Hot swap** | `core/vector_store.py` → `mark_dirty()` | Next query automatically uses the enriched index. |
| 6. **Status polling** | `core/enrichment.py` → `enricher.status` property | Frontend can poll enrichment progress: `{running, total, done}`. |

**Key property:** The system is immediately queryable after ingestion. Enrichment improves quality progressively in the background.

---

## 4. Session Management Workflow

**Trigger:** User interacts with chat sessions.

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Create   │──▶│ Chat     │──▶│ Messages │──▶│ Persist  │
│ Session  │   │ (query)  │   │ Added    │   │ to JSON  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
```

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Create session** | `backend/server.py` → `POST /api/sessions` | Creates a new session with the OS username and auto-generated label. Returns session JSON with unique 8-char ID. |
| 2. **List sessions** | `backend/server.py` → `GET /api/sessions` | Returns all sessions for the current OS user, sorted by modification date (newest first). |
| 3. **Chat message** | `backend/server.py` → `POST /api/chat/stream` | User and assistant messages are appended to the session JSON with timestamps, sources, and metrics. |
| 4. **Rename session** | `backend/server.py` → `PATCH /api/sessions/{id}` | Updates the session label. |
| 5. **Load session** | `backend/server.py` → `GET /api/sessions/{id}` | Returns full session data including all messages. |
| 6. **Export session** | `backend/server.py` → `GET /api/sessions/{id}/export` | Generates formatted text transcript with source citations. |
| 7. **Delete session** | `backend/server.py` → `DELETE /api/sessions/{id}` | Permanently removes the session JSON file. |

---

## 5. Model Management Workflow

**Trigger:** User navigates to the Models view.

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **List models** | `backend/server.py` → `GET /api/ollama/models` | HTTP GET to Ollama's `/api/tags` endpoint. Returns models with param count, quantization, family. |
| 2. **Recommended models** | `backend/server.py` → `GET /api/ollama/recommended` | Returns curated model list with availability flags (cross-referenced against local models). |
| 3. **Pull model** | `backend/server.py` → `POST /api/ollama/pull` or `POST /api/ollama/pull/sync` | Streaming HTTP POST to Ollama's `/api/pull`. Progress streamed back via SSE. |
| 4. **Delete model** | `backend/server.py` → `DELETE /api/ollama/models/{name}` | HTTP DELETE to Ollama's `/api/delete`. |
| 5. **Server start** | `backend/server.py` → `POST /api/ollama/start` | `subprocess.Popen(["ollama", "serve"])` with platform-specific flags. Polls health endpoint for 10s. |
| 6. **Status check** | `backend/server.py` → `GET /api/ollama/status` | Returns `{running, url, models, model_count}` for UI status display. |

---

## 6. CI/CD Workflow

**Trigger:** Push or pull request to `main` branch on GitHub.

```
Push to main → GitHub Actions
├── CI: Test Job
│   ├── Checkout code
│   ├── Setup Python 3.12
│   ├── pip install requirements + pytest
│   └── pytest tests/test_backend.py
│
└── CD: Build Job (only on push to main, after tests pass)
    ├── Checkout code
    ├── Setup Node.js 25.2.1
    ├── npm ci (electron/)
    ├── npm run build (electron-builder → NSIS installer)
    └── Upload PrivateGPT-Setup.exe as artifact
```

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Test trigger** | `.github/workflows/ci-cd.yml` → `test` job | Runs on every push and PR to `main`. Uses `windows-latest` runner. |
| 2. **Test execution** | `tests/test_backend.py` | Tests: API info endpoint, Ollama status, document listing, session CRUD (create, list, delete). |
| 3. **Build trigger** | `.github/workflows/ci-cd.yml` → `build` job | Runs only on push to `main` (not PRs), after `test` job passes. |
| 4. **Electron build** | `electron/package.json` → `npm run build` | electron-builder produces NSIS installer. Bundles backend, core, config, sessions, requirements, and setup scripts. |
| 5. **Artifact upload** | `.github/workflows/ci-cd.yml` | Uploads `electron/dist/*.exe` as downloadable artifact named `PrivateGPT-Setup`. |

---

## 7. Installer Workflow

**Trigger:** User runs the `PrivateGPT-Setup.exe` installer built by electron-builder.

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **NSIS install** | `electron/installer.nsh` → `customInstall` | After extracting files, runs `setup_env.bat` from the install directory. |
| 2. **Python venv** | `setup_env.bat` | Creates Python virtual environment if not present. |
| 3. **Pip install** | `setup_env.bat` | Installs all Python dependencies from `requirements.txt`. |
| 4. **Embedding download** | `setup_env.bat` → `download_embeddings.py` | Pre-downloads the embedding model for offline operation. |
| 5. **Ollama check** | `setup_env.bat` | Checks if Ollama is installed. If not, downloads and silently installs it. |
| 6. **Uninstall** | `electron/installer.nsh` → `customUnInstall` | Removes the Python virtual environment directory. |
