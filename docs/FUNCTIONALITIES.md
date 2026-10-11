# ⚙️ Functionalities

A complete inventory of every feature in PrivateGPT v2.0, organized by functional area.

---

## 🖥️ Desktop Application (Electron)

| Feature | Description | Source |
|---------|-------------|--------|
| **Custom Title Bar** | Frameless window with custom minimize, maximize, and close buttons | `electron/main.js` → `createWindow()` |
| **Backend Auto-Launch** | FastAPI backend spawned as child process on app start | `electron/main.js` → `startBackend()` |
| **Backend Health Check** | Waits up to 30 seconds for backend to be ready before signaling renderer | `electron/main.js` → `waitForBackend()` |
| **Native File Picker** | OS-native file dialog for PDF selection (multi-select enabled) | `electron/main.js` → `select-files` IPC |
| **Secure IPC Bridge** | `contextBridge` exposes minimal API — no `nodeIntegration` in renderer | `electron/preload.js` |
| **Dark Theme** | GitHub-inspired dark color palette with glassmorphism elements | `electron/renderer/styles.css` |
| **SPA Routing** | Single-page app with client-side navigation between all views | `electron/renderer/app.js` |
| **Backend Reuse** | Detects if backend is already running (dev mode) and skips launch | `electron/main.js` → `isBackendAlreadyRunning()` |

---

## 💬 Chat

| Feature | Description | Source |
|---------|-------------|--------|
| **Streaming Answers** | Tokens appear one-by-one via SSE — no blank wait | `backend/server.py` → `/api/chat/stream` |
| **Source Citations** | Source file + page badges shown immediately after retrieval completes | `backend/server.py` → SSE `sources` event |
| **Performance Metrics** | Total latency, retrieval time, chunk count, model name | `backend/server.py` → SSE `done` event |
| **Conversation Memory** | Full message history persisted per session via backend API | `sessions/manager.py` → `add_message()` |
| **New Chat** | Start a fresh conversation (creates a new session via REST) | `backend/server.py` → `POST /api/sessions` |
| **Document Filter** | Query only search selected documents (passed as `filter_files`) | `core/graph/engine.py` → `retrieve()` |
| **Model Selection** | Switch active LLM model per query | `backend/server.py` → `ChatRequest.model` |
| **Error Handling** | Generation errors caught and displayed inline in the stream | `backend/server.py` → SSE error handling |

---

## 📄 Documents

| Feature | Description | Source |
|---------|-------------|--------|
| **Multi-file Upload** | Upload multiple PDFs via native file picker or REST API | `backend/server.py` → `POST /api/documents/upload` |
| **Idempotent Indexing** | SHA-256 hash check — unchanged files are skipped automatically | `core/ingestion.py` → `_file_hash()` |
| **3-Tier PDF Extraction** | Handles digital text, tables (→ Markdown), and scanned pages (OCR) | `core/pdf_processor.py` → `extract()` |
| **Text Cleaning** | Removes headers, footers, page numbers, boilerplate, junk pages | `core/pdf_processor.py` → `_clean_text()` |
| **Document List** | Shows all indexed docs with page count, chunk count, indexed date | `backend/server.py` → `GET /api/documents` |
| **Delete Document** | Remove from metadata + permanent storage (requires rebuild) | `backend/server.py` → `DELETE /api/documents/{filename}` |
| **Full Rebuild** | Re-index all documents from scratch with current settings | `backend/server.py` → `POST /api/documents/rebuild` |
| **Permanent Storage** | PDFs copied to `data/documents/` for persistence across sessions | `core/ingestion.py` → `_ensure_permanent_copy()` |
| **Migration Banner** | Automatic full re-index when embedding backend version changes | `core/ingestion.py` → `EMBEDDING_BACKEND` |

---

## 🤖 Models

| Feature | Description | Source |
|---------|-------------|--------|
| **Downloaded Models** | List all locally available Ollama models with param count + quantization | `backend/server.py` → `GET /api/ollama/models` |
| **Recommended Models** | Curated list with RAM requirements, descriptions, and availability flags | `backend/server.py` → `GET /api/ollama/recommended` |
| **Pull Model (Sync)** | Download models synchronously | `backend/server.py` → `POST /api/ollama/pull/sync` |
| **Pull Model (Stream)** | Download models with SSE streaming progress | `backend/server.py` → `POST /api/ollama/pull` |
| **Delete Model** | Remove locally downloaded models to free disk space | `backend/server.py` → `DELETE /api/ollama/models/{name}` |
| **Model Info** | Show parameter size, quantization level, model family | `core/ollama_manager.py` → `get_info()` |
| **Availability Check** | Check if a specific model is already pulled locally | `core/ollama_manager.py` → `is_available()` |
| **Server Management** | Start Ollama server from the app if not running | `backend/server.py` → `POST /api/ollama/start` |

---

## 🕘 History

| Feature | Description | Source |
|---------|-------------|--------|
| **Session List** | All past chat sessions for the current OS user, sorted by date | `backend/server.py` → `GET /api/sessions` |
| **Load Session** | Restore a previous conversation by session ID | `backend/server.py` → `GET /api/sessions/{id}` |
| **Rename Session** | Change the label of an existing session | `backend/server.py` → `PATCH /api/sessions/{id}` |
| **Export to TXT** | Download a formatted text transcript of any session | `backend/server.py` → `GET /api/sessions/{id}/export` |
| **Delete Session** | Permanently remove a chat session | `backend/server.py` → `DELETE /api/sessions/{id}` |

---

## Core Engine Features (Non-UI)

| Feature | Description | Source |
|---------|-------------|--------|
| **Hybrid Search** | FAISS (semantic) + BM25 (keyword) fused via Reciprocal Rank Fusion | `core/vector_store.py` → `hybrid_search()` |
| **Neighbor Expansion** | ±1 adjacent chunks included for context continuity | `core/vector_store.py` → `search_with_neighbors()` |
| **Cross-Encoder Reranking** | `ms-marco-MiniLM-L-6-v2` scores all candidates, keeps top 4 | `core/graph/nodes.py` → `make_rerank_node()` |
| **Grounding Validation** | Heuristic check that answer references source content (≥20% overlap) | `core/graph/nodes.py` → `make_validate_node()` |
| **Hot Index Reload** | After ingestion/enrichment, queries automatically use updated index | `core/vector_store.py` → `mark_dirty()` |
| **OCR Support** | Scanned/image PDFs are rendered at 300 DPI and OCR'd via Tesseract | `core/pdf_processor.py` → `_ocr_page()` |
| **Table Extraction** | Tables detected via `PyMuPDF.find_tables()`, converted to Markdown | `core/pdf_processor.py` → `_extract_tables()` |
| **Legacy Data Migration** | Auto-copies data from pre-refactor flat directories to `data/` | `config/settings.py` → `_migrate_legacy_data()` |
| **Offline Embeddings** | Pre-download embedding model for fully offline startup | `download_embeddings.py` → `download_model()` |

---

## 🔧 DevOps & Tooling

| Feature | Description | Source |
|---------|-------------|--------|
| **CI Pipeline** | Automated pytest on every push/PR to `main` (Windows runner) | `.github/workflows/ci-cd.yml` → `test` job |
| **CD Pipeline** | Automated electron-builder on push to `main`, uploads `.exe` artifact | `.github/workflows/ci-cd.yml` → `build` job |
| **Backend Tests** | API info, Ollama status, document listing, session CRUD tests | `tests/test_backend.py` |
| **Dev Mode** | Hot-reload backend + Electron launch via `start-dev.bat` | `start-dev.bat` |
| **Production Launch** | Venv check + Electron install + backend start + Electron launch | `start-app.bat` |
| **Environment Setup** | Automated Python venv, pip install, embedding download, Ollama install | `setup_env.bat` |
| **NSIS Installer** | Custom installer runs `setup_env.bat` post-install, cleans venv on uninstall | `electron/installer.nsh` |
| **Distributable Build** | electron-builder produces Windows NSIS installer | `electron/package.json` → `build` config |

---

## User Identity

| Feature | Description | Source |
|---------|-------------|--------|
| **OS-Level Identity** | Current OS username detected via `getpass.getuser()` | `backend/server.py` → `USERNAME` |
| **Per-User Sessions** | Sessions filtered by username field — users only see their own history | `sessions/manager.py` → `list_for_user()` |
| **No Authentication** | Auth system removed in v2.0 — app uses OS-level user identity | `security/__init__.py` |
