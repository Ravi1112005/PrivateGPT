# 🔒 PrivateGPT

**Air-gapped document intelligence — all data stays on your machine.**

PrivateGPT is a fully local RAG (Retrieval-Augmented Generation) system that lets you chat with your PDF documents using locally-running LLMs. No cloud services, no API keys, no data ever leaves your machine.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔒 **100% Local** | Ollama LLMs, FAISS vectors, Tesseract OCR — everything runs on your machine |
| 📄 **Smart PDF Processing** | 3-tier extraction: digital text, tables (→ Markdown), scanned pages (OCR) |
| 🔍 **Hybrid Search** | FAISS (semantic) + BM25 (keyword) fused via Reciprocal Rank Fusion |
| 🎯 **Cross-Encoder Reranking** | Deep attention reranking for precision retrieval |
| 📐 **Neighbor Expansion** | Adjacent chunks included for context continuity across chunk boundaries |
| ⚡ **Background Enrichment** | LLM-generated context prepended to chunks — quality improves while you work |
| 💬 **Streaming Chat** | Tokens appear live with source citations and performance metrics |
| 👥 **Multi-User Auth** | PBKDF2-HMAC-SHA256 password hashing with role-based access control |
| 📋 **Audit Trail** | Every authentication event logged with timestamps |
| 🕘 **Session History** | Save, load, and export chat conversations |

---

## 🏗️ Architecture

```
Electron UI ──▶ app.js (SPA Logic) ──▶ renderer/ (HTML/CSS)
                                                │
                    ┌───────────────────────────┴────────────────────────────┐
                    │                                                        │
              FastAPI Backend (server.py) ──▶ core/ (Pure Python)            │
                                                                             │
                    ┌──────────────────────────┼──────────────────────────┐  │
                    │                          │                          │  │
              PDFProcessor              VectorStoreManager         RAGGraphEngine
             (text/table/OCR)           (FAISS + BM25 + RRF)     (LangGraph pipeline)
                    │                          │                          │
                    ▼                          ▼                          ▼
            IngestionPipeline ──▶ BackgroundEnricher ──▶ Ollama LLM (localhost)
```

**Design principles:** Clean layer separation (Frontend ↔ Backend ↔ Core Logic), dependency injection, module-level singleton caching, thread-safe concurrent access.

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Ollama** — [Download](https://ollama.com/download)
- **8 GB RAM** minimum (16 GB recommended)

### Installation

```bash
# 1. Clone and setup
git clone <repo-url>
cd PrivateGPT
python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # Linux/macOS
pip install -r requirements.txt

# 2. Install Electron Dependencies
cd electron
npm install
cd ..

# 3. Run
start-app.bat
```

### First Use

1. Run the app using `start-app.bat` which will open the Desktop Window.
2. Sign in: `admin / admin123`
3. Go to **🤖 Models** → Pull **Phi-3 Mini** (3.8B, ~2.2 GB)
4. Go to **📄 Documents** → Upload PDFs → Click **Index documents**
5. Go to **💬 Chat** → Ask questions

### Optional: OCR for Scanned PDFs

Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) to `C:\Program Files\Tesseract-OCR`. The app auto-detects it — no configuration needed.

---

## 📁 Project Structure

```
PrivateGPT/
├── backend/
│   └── server.py                   # FastAPI REST + SSE backend
├── electron/                       # Electron frontend
│   ├── main.js                     # Main process
│   ├── package.json
│   └── renderer/                   # SPA frontend code
├── requirements.txt                # Python dependencies
│
├── config/
│   └── settings.py                 # Central configuration (dataclass)
│
├── core/                           # Business logic (pure Python)
│   ├── pdf_processor.py            # 3-tier PDF extraction (text/table/OCR)
│   ├── embeddings.py               # EmbeddingsManager (all-MiniLM-L6-v2)
│   ├── ingestion.py                # IngestionPipeline (PDF → FAISS)
│   ├── vector_store.py             # VectorStoreManager (hybrid search + neighbors)
│   ├── enrichment.py               # BackgroundEnricher (daemon thread)
│   ├── ollama_manager.py           # Ollama server + model lifecycle
│   ├── ssl_patch.py                # SSL bypass for HuggingFace
│   └── graph/                      # LangGraph RAG pipeline
│       ├── state.py                # RAGState TypedDict
│       ├── nodes.py                # 6 graph node functions
│       ├── builder.py              # StateGraph construction
│       └── engine.py               # RAGGraphEngine (public API)
│
├── security/
│   └── auth.py                     # AuthManager (PBKDF2 + audit)
│
├── sessions/
│   └── manager.py                  # SessionManager (per-user JSON)
│
├── ui/                             # Legacy UI layer
│   └── ...                         # (Removed)
│
├── data/                           # Runtime data (gitignored)
│   ├── documents/                  # Uploaded PDFs
│   ├── faiss_index/                # Vector + BM25 indexes
│   ├── sessions/                   # Chat sessions
│   └── security/                   # Auth data
│
└── docs/                           # Documentation
    ├── ARCHITECTURE.md
    ├── WORKFLOW.md
    ├── FUNCTIONALITIES.md
    ├── TECHNOLOGY_STACK.md
    ├── API_REFERENCE.md
    ├── SECURITY.md
    ├── CONFIGURATION.md
    └── DEPLOYMENT.md
```

---

## 🛠️ Technology Stack

| Category | Technology | Why |
|----------|-----------|-----|
| **UI** | Electron + HTML/JS/CSS | Desktop window with native OS integration |
| **Backend API** | FastAPI | High performance async endpoints and SSE streaming |
| **LLM** | Ollama | Local LLM server, REST API, model management |
| **Framework** | LangChain + LangGraph | LLM abstractions + stateful graph pipelines |
| **Embeddings** | all-MiniLM-L6-v2 | 384d, ~80 MB, fast CPU inference |
| **Vector DB** | FAISS | In-process, no server, serializable |
| **Keyword Search** | BM25 (rank_bm25) | Exact keyword matching, zero infrastructure |
| **Reranking** | ms-marco-MiniLM-L-6-v2 | Cross-encoder precision scoring |
| **PDF** | PyMuPDF | Text, tables, image rendering |
| **OCR** | Tesseract (pytesseract) | Local OCR for scanned PDFs |
| **Auth** | PBKDF2-HMAC-SHA256 | Python stdlib, NIST-recommended |

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
- **[API Reference](docs/API_REFERENCE.md)** — Class-level documentation
- **[Security](docs/SECURITY.md)** — Auth, encryption, threat model
- **[Configuration](docs/CONFIGURATION.md)** — All tunable parameters
- **[Deployment](docs/DEPLOYMENT.md)** — Setup guide + troubleshooting

---

## 🔐 Security

- **Passwords:** PBKDF2-HMAC-SHA256 (260K iterations) with per-user random salt
- **Comparison:** Timing-safe (`hmac.compare_digest`)
- **Roles:** `admin` (full access) / `user` (chat, docs, models, history)
- **Audit:** Every auth event logged with timestamp and event type
- **Data:** All data stored locally in `data/` — never transmitted

---

## 📋 Requirements

```
langchain
langchain-community
langchain-huggingface
langchain-ollama
langchain-core
langchain-text-splitters
langgraph
faiss-cpu
sentence-transformers
pypdf
psutil
streamlit
requests
rank-bm25
PyMuPDF
pytesseract
Pillow
```

---

## 📄 License

Private project. All rights reserved.
