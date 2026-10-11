# 🔒 PrivateGPT

**Air-gapped document intelligence — all data stays on your machine.**

PrivateGPT is a fully local RAG (Retrieval-Augmented Generation) desktop application that lets you chat with your PDF documents using locally-running LLMs. No cloud services, no API keys, no data ever leaves your machine.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔒 **100% Local** | Ollama LLMs, FAISS vectors, Tesseract OCR — everything runs on your machine |
| 🖥️ **Desktop App** | Native Electron window with custom title bar, frameless design, and dark theme |
| 📄 **Smart PDF Processing** | 3-tier extraction: digital text, tables (→ Markdown), scanned pages (OCR) |
| 🔍 **Hybrid Search** | FAISS (semantic) + BM25 (keyword) fused via Reciprocal Rank Fusion |
| 🎯 **Cross-Encoder Reranking** | Deep attention reranking for precision retrieval |
| 📐 **Neighbor Expansion** | Adjacent chunks included for context continuity across chunk boundaries |
| ⚡ **Background Enrichment** | LLM-generated context prepended to chunks — quality improves while you work |
| 💬 **Streaming Chat** | Tokens appear live via SSE with source citations and performance metrics |
| 🕘 **Session History** | Save, load, rename, and export chat conversations |
| 🔧 **CI/CD Pipeline** | GitHub Actions for automated testing (pytest) and desktop app builds (electron-builder) |
| 📦 **Distributable Installer** | NSIS-based Windows installer with automated environment setup |

---

## 🏗️ Architecture

```
Electron Desktop App (electron/)
├── main.js ──────────── Launches FastAPI backend as child process
├── preload.js ───────── Secure IPC bridge (contextBridge)
└── renderer/ ────────── SPA frontend (HTML/JS/CSS)
        │
        │  HTTP + SSE
        ▼
FastAPI Backend (backend/server.py)
├── REST API endpoints ─── Documents, Chat, Sessions, Models, Info
├── SSE streaming ─────── Real-time token delivery
└── Singleton wiring ──── EmbeddingsManager, VectorStoreManager, etc.
        │
        ▼
Core Logic (core/)
├── PDFProcessor ──────── 3-tier PDF extraction (text/table/OCR)
├── VectorStoreManager ── FAISS + BM25 + RRF hybrid search
├── IngestionPipeline ──── PDF → chunks → index
├── BackgroundEnricher ── Daemon thread for LLM-based enrichment
├── RAGGraphEngine ────── LangGraph pipeline (retrieve → rerank → generate → validate)
└── OllamaManager ─────── Local LLM server lifecycle
```

**Design principles:** Clean layer separation (Electron ↔ FastAPI ↔ Core Logic), dependency injection, module-level singleton caching, thread-safe concurrent access.

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** (for Electron)
- **Ollama** — [Download](https://ollama.com/download)
- **8 GB RAM** minimum (16 GB recommended)

### Installation

```bash
# 1. Clone and setup
git clone https://github.com/Ravi1112005/PrivateGPT.git
cd PrivateGPT
python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # Linux/macOS
pip install -r requirements.txt

# 2. Pre-download embedding model (for offline use)
python download_embeddings.py

# 3. Install Electron dependencies
cd electron
npm install
cd ..

# 4. Run
start-app.bat
```

### First Use

1. Run the app using `start-app.bat` — the Electron desktop window opens automatically.
2. The app detects the current OS user automatically (no login required).
3. Go to **🤖 Models** → Pull **Phi-3 Mini** (3.8B, ~2.2 GB)
4. Go to **📄 Documents** → Upload PDFs → Click **Index documents**
5. Go to **💬 Chat** → Ask questions

### Development Mode

```bash
start-dev.bat    # Starts backend with hot-reload + Electron
```

### Optional: OCR for Scanned PDFs

Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) to `C:\Program Files\Tesseract-OCR`. The app auto-detects it — no configuration needed.

---

## 📁 Project Structure

```
PrivateGPT/
├── backend/
│   └── server.py                   # FastAPI REST + SSE backend (v2.0.0)
├── electron/                       # Electron desktop frontend
│   ├── main.js                     # Main process (backend launcher + window)
│   ├── preload.js                  # Secure IPC bridge (contextBridge)
│   ├── package.json                # Electron + electron-builder config
│   ├── installer.nsh               # NSIS installer customization
│   ├── assets/                     # App icons
│   └── renderer/                   # SPA frontend
│       ├── index.html              # Main HTML shell
│       ├── app.js                  # SPA logic (32KB)
│       └── styles.css              # Dark theme CSS (28KB)
│
├── core/                           # Business logic (pure Python)
│   ├── pdf_processor.py            # 3-tier PDF extraction (text/table/OCR)
│   ├── embeddings.py               # EmbeddingsManager (all-MiniLM-L6-v2)
│   ├── ingestion.py                # IngestionPipeline (PDF → FAISS)
│   ├── vector_store.py             # VectorStoreManager (hybrid search + neighbors)
│   ├── enrichment.py               # BackgroundEnricher (daemon thread)
│   ├── ollama_manager.py           # Ollama server + model lifecycle
│   ├── ssl_patch.py                # SSL bypass for HuggingFace
│   ├── query_engine_legacy.py      # Legacy query engine (superseded by graph/)
│   └── graph/                      # LangGraph RAG pipeline
│       ├── state.py                # RAGState TypedDict
│       ├── nodes.py                # 6 graph node functions
│       ├── builder.py              # StateGraph construction
│       └── engine.py               # RAGGraphEngine (public API)
│
├── config/
│   └── settings.py                 # Central configuration (dataclass)
│
├── security/                       # Placeholder (auth removed in v2.0)
│   └── __init__.py
│
├── sessions/
│   └── manager.py                  # SessionManager (per-user JSON)
│
├── tests/
│   └── test_backend.py             # Automated backend tests (pytest)
│
├── .github/workflows/
│   └── ci-cd.yml                   # CI: pytest | CD: electron-builder
│
├── data/                           # Runtime data (gitignored)
│   ├── documents/                  # Uploaded PDFs
│   ├── faiss_index/                # Vector + BM25 indexes
│   ├── sessions/                   # Chat sessions
│   └── models/embeddings/          # Cached embedding model
│
├── requirements.txt                # Python dependencies (pinned versions)
├── download_embeddings.py          # Pre-download embeddings for offline use
├── setup_env.bat                   # Automated environment setup
├── start-app.bat                   # Production launcher
├── start-dev.bat                   # Development mode launcher
│
└── docs/                           # Documentation
    ├── ARCHITECTURE.md
    ├── WORKFLOW.md
    ├── FUNCTIONALITIES.md
    ├── TECHNOLOGY_STACK.md
    ├── API_REFERENCE.md
    ├── SECURITY.md
    └── CONFIGURATION.md
```

---

## 🛠️ Technology Stack

| Category | Technology | Why |
|----------|-----------|-----|
| **Desktop UI** | Electron + HTML/JS/CSS | Native desktop window with custom title bar, frameless design, dark theme |
| **Backend API** | FastAPI + Uvicorn | High performance async REST endpoints and SSE streaming |
| **LLM** | Ollama | Local LLM server, REST API, model management |
| **Framework** | LangChain + LangGraph | LLM abstractions + stateful graph pipelines |
| **Embeddings** | all-MiniLM-L6-v2 | 384d, ~80 MB, fast CPU inference |
| **Vector DB** | FAISS | In-process, no server, serializable |
| **Keyword Search** | BM25 (rank_bm25) | Exact keyword matching, zero infrastructure |
| **Reranking** | ms-marco-MiniLM-L-6-v2 | Cross-encoder precision scoring |
| **PDF** | PyMuPDF | Text, tables, image rendering |
| **OCR** | Tesseract (pytesseract) | Local OCR for scanned PDFs |
| **Testing** | pytest + FastAPI TestClient | Automated backend API testing |
| **CI/CD** | GitHub Actions | Automated testing + desktop app builds |
| **Packaging** | electron-builder + NSIS | Windows installer with automated env setup |

> See [docs/TECHNOLOGY_STACK.md](docs/TECHNOLOGY_STACK.md) for detailed "Why & How" justifications for every technology choice.

---

## 📄 RAG Pipeline

```
Question → Hybrid Search (FAISS + BM25) → Neighbor Expansion (±1 chunks)
    → Cross-Encoder Reranking (top 4) → Prompt Template → Ollama LLM → Streaming Answer
```

### Ingestion Pipeline

```
PDF → PDFProcessor (text/table/OCR) → Chunker (1000 chars, 200 overlap)
    → FAISS Index + BM25 Index → Background Enrichment (LLM context)
```

---

## 📚 Documentation

Full documentation is in the [`docs/`](docs/) directory:

- **[Architecture](docs/ARCHITECTURE.md)** — System design, layers, data flow
- **[Workflow](docs/WORKFLOW.md)** — Step-by-step flows for ingestion, query, enrichment
- **[Functionalities](docs/FUNCTIONALITIES.md)** — Complete feature inventory
- **[Technology Stack](docs/TECHNOLOGY_STACK.md)** — Why & How for every technology
- **[API Reference](docs/API_REFERENCE.md)** — Class-level and REST API documentation
- **[Security](docs/SECURITY.md)** — Air-gap design and data privacy
- **[Configuration](docs/CONFIGURATION.md)** — All tunable parameters

---

## 🔐 Security & Privacy

- **Air-Gapped:** All processing (LLM, embeddings, OCR, vector search) runs locally
- **Zero Cloud Dependencies:** No data ever leaves the machine after initial model downloads
- **User Identity:** OS-level username (`getpass.getuser()`) — no password management
- **Data Storage:** All data stored locally in `data/` — never transmitted
- **Electron Security:** Context isolation enabled, no `nodeIntegration` in renderer

---

## 📋 Requirements

```
# Core
langchain-huggingface==1.2.2
langchain-ollama==1.1.0
langchain==1.3.10
langchain-community==0.4.2
langchain-core==1.4.8
langchain-text-splitters==1.1.2
langgraph==1.2.6
faiss-cpu==1.13.2
sentence-transformers==5.2.3
rank-bm25==0.2.2
pypdf==6.13.3
psutil==5.9.6
requests==2.32.5
PyMuPDF==1.27.2
pytesseract==0.3.13
Pillow==12.1.1

# Electron backend
fastapi==0.128.0
uvicorn[standard]==0.40.0
python-multipart==0.0.21
```

---

## 🧪 Testing

```bash
# Run automated tests
python -m pytest tests/test_backend.py

# Tests cover: API info, Ollama status, document listing, session CRUD
```

---

## 📦 Building the Installer

```bash
cd electron
npm run build    # Builds NSIS installer via electron-builder
```

The installer bundles Python setup (`setup_env.bat`), embedding model download, and Ollama installation.

---

## 📄 License

MIT License — see [package.json](electron/package.json) for details.
