# 🛠️ Technology Stack — Why & How

Every technology in PrivateGPT was chosen to satisfy a single non-negotiable constraint: **complete air-gap operation**. This document explains not just *what* we use, but *why* we chose it over alternatives and *how* it integrates.

---

## Desktop Framework

### Electron + FastAPI

| | |
|---|---|
| **What** | Desktop app framework (Electron) and async Python web framework (FastAPI) |
| **Version** | Electron ^33.0.0, FastAPI 0.128.0, Uvicorn 0.40.0 |
| **Why chosen** | Provides instant UI transitions, native desktop features (custom title bar, file dialogs), and clean separation between frontend and backend. FastAPI serves the Python core logic via REST and SSE, while Electron renders the interface without Python reruns. |
| **Why not Streamlit** | Streamlit re-executes the entire script on every interaction, causing slow UI transitions and requiring complex caching workarounds. It also lacks native desktop features (frameless window, custom title bar, native file pickers). |
| **How used** | `electron/main.js` launches `backend/server.py` as a child process via `spawn()`. The renderer connects via standard HTTP requests and EventSource for SSE streaming. `preload.js` provides a secure bridge with `contextBridge`. |

### Electron Security Architecture

| | |
|---|---|
| **Context Isolation** | `contextIsolation: true` — renderer process cannot access Node.js APIs |
| **No Node Integration** | `nodeIntegration: false` — prevents remote code execution |
| **Preload Bridge** | `preload.js` exposes exactly 8 functions via `contextBridge.exposeInMainWorld()` |
| **Local Only** | FastAPI binds to `127.0.0.1:8765` — not accessible from the network |

---

## LLM Infrastructure

### Ollama

| | |
|---|---|
| **What** | Local LLM server — runs models like Phi-3, Llama 3, Mistral on your machine |
| **Why chosen** | Ollama is the simplest way to run LLMs locally on Windows/Mac/Linux. One binary, one command (`ollama serve`), REST API at `localhost:11434`. Supports streaming, model management, and quantized models for low-RAM machines. |
| **Why not OpenAI API** | Violates the air-gap constraint. Every query would leave the machine. |
| **Why not llama.cpp directly** | Ollama wraps llama.cpp with a clean REST API, model registry, and automatic quantization. Using llama.cpp directly would require manual model format conversion, GGUF management, and a custom HTTP server. |
| **Why not vLLM** | vLLM requires CUDA GPUs and is optimized for high-throughput serving. PrivateGPT targets commodity hardware (8-16 GB RAM, CPU-only). |
| **How used** | `core/ollama_manager.py` manages server lifecycle (start/stop) and model inventory (pull/delete/list/availability check). `core/graph/engine.py` calls Ollama via LangChain's `OllamaLLM` wrapper for generation and streaming. The FastAPI backend exposes Ollama operations via REST endpoints. |

### LangChain

| | |
|---|---|
| **What** | Framework for building LLM-powered applications |
| **Version** | langchain 1.3.10, langchain-core 1.4.8 |
| **Why chosen** | Provides unified interfaces for embeddings (`Embeddings` base class), document loaders, text splitters, and LLM connectors. The `OllamaLLM` wrapper handles streaming, retry logic, and serialization. |
| **Why not LlamaIndex** | LlamaIndex is more opinionated about index structures. We needed raw FAISS control for hybrid search and neighbor expansion. LangChain's lighter abstractions gave us more flexibility. |
| **How used** | `langchain_core.documents.Document` is the universal data structure. `langchain_ollama.OllamaLLM` wraps Ollama. `langchain_text_splitters.RecursiveCharacterTextSplitter` handles chunking. `langchain_community.vectorstores.FAISS` manages the vector store. |

### LangGraph

| | |
|---|---|
| **What** | State machine framework for multi-step LLM workflows |
| **Version** | langgraph 1.2.6 |
| **Why chosen** | The RAG pipeline has conditional branching (skip generation if no docs found), multiple processing stages (retrieve → rerank → check → generate → validate → finalize), and needs to pass state between nodes. LangGraph models this as a directed graph with typed state, conditional edges, and deterministic execution. |
| **Why not a simple function chain** | A linear function chain can't express conditional branching (what if retrieval finds nothing?). A graph with conditional edges (`check_retrieval → generate OR finalize`) models this cleanly. |
| **How used** | `core/graph/builder.py` constructs a `StateGraph` with 6 nodes. `core/graph/state.py` defines the `RAGState` TypedDict. `core/graph/nodes.py` implements each node as a pure function. `core/graph/engine.py` exposes the compiled graph via `RAGGraphEngine`. |

---

## Embedding & Retrieval

### all-MiniLM-L6-v2 (sentence-transformers)

| | |
|---|---|
| **What** | 384-dimensional sentence embedding model |
| **Version** | sentence-transformers 5.2.3 |
| **Why chosen** | ~80 MB model, fast CPU inference (~8 ms/query), no GPU required. Runs fully offline after first download. Good semantic quality for English documents. |
| **Why not OpenAI embeddings** | Violates air-gap. Every document chunk would be sent to OpenAI's servers. |
| **Why not BGE-M3** | BGE-M3 is superior (1024d, multilingual, top-5 MTEB) but is ~2.3 GB — too large for the target hardware (8 GB RAM laptops). all-MiniLM-L6-v2 is the best trade-off for constrained environments. |
| **How used** | `core/embeddings.py` → `EmbeddingsManager` wraps `SentenceTransformer`. Implements LangChain's `Embeddings` interface (`embed_query`, `embed_documents`). Loaded once at FastAPI startup and kept in RAM. The model can be pre-cached to `data/models/embeddings/` via `download_embeddings.py` for fully offline startup. |

### FAISS

| | |
|---|---|
| **What** | Facebook AI Similarity Search — dense vector index |
| **Version** | faiss-cpu 1.13.2 |
| **Why chosen** | In-process (no server), fast nearest-neighbor search, serializable to disk, and works with LangChain's `FAISS` wrapper out of the box. |
| **Why not Chroma/Pinecone/Weaviate** | Chroma requires a separate server process. Pinecone/Weaviate are cloud services — violate air-gap. FAISS is a single library, in-process, zero-config. |
| **How used** | `core/vector_store.py` → `VectorStoreManager` loads the FAISS index once, caches it in RAM, and exposes `search()` and `hybrid_search()`. Index is saved to `data/faiss_index/`. |

### BM25 (rank_bm25)

| | |
|---|---|
| **What** | Classic keyword-based ranking algorithm (Okapi BM25) |
| **Version** | rank-bm25 0.2.2 |
| **Why chosen** | FAISS (semantic search) is great for paraphrased queries but misses exact keyword matches (e.g., searching for "PBKDF2" won't match if the embedding model doesn't know that term). BM25 catches these keyword-exact queries. |
| **Why not Elasticsearch** | Elasticsearch requires a JVM and a separate server process. BM25Okapi is a pure Python library — zero infrastructure. |
| **How used** | Built alongside FAISS during ingestion. Stored as a pickle file. `VectorStoreManager.hybrid_search()` runs both FAISS and BM25, then merges results with Reciprocal Rank Fusion. |

### Cross-Encoder Reranking (ms-marco-MiniLM-L-6-v2)

| | |
|---|---|
| **What** | A cross-encoder model that scores (query, passage) pairs with deep bidirectional attention |
| **Why chosen** | Bi-encoders (like all-MiniLM-L6-v2) embed query and document independently — fast but less accurate. Cross-encoders process both together — slower but much more precise. Using a bi-encoder for candidate generation (fast, 40 candidates) and a cross-encoder for precision reranking (accurate, top 4) is the standard two-stage retrieval pattern. |
| **Why not use only the cross-encoder** | Cross-encoders are O(n) in the corpus size — scoring every chunk against every query would be prohibitively slow. The bi-encoder narrows the candidate pool first. |
| **How used** | `core/graph/nodes.py` → `make_rerank_node()`. Lazy-loaded on first use, cached in closure. Runs in ~100-200ms on CPU for 40 candidates. Also used inline in `RAGGraphEngine.retrieve()` for SSE streaming. |

---

## PDF Processing

### PyMuPDF (fitz)

| | |
|---|---|
| **What** | High-performance PDF rendering and text extraction library |
| **Version** | PyMuPDF 1.27.2 |
| **Why chosen** | Handles digital PDFs, scanned PDFs, and mixed-content documents. `page.get_text("text")` extracts selectable text. `page.find_tables()` detects table structures. `page.get_pixmap()` renders pages to images for OCR. ~10x faster than PyPDF. |
| **Why not PyPDF** | PyPDF only extracts selectable text — tables become word soup, scanned pages return nothing. PyMuPDF handles all three content types. |
| **Why not Unstructured** | Unstructured is a heavy framework with many dependencies (Poppler, LibreOffice, etc.) and cloud-oriented design. PyMuPDF is a single wheel with no system dependencies on Windows. |
| **How used** | `core/pdf_processor.py` → `PDFProcessor.extract()`. Falls back to PyPDFLoader if PyMuPDF is not installed. |

### Tesseract OCR (pytesseract)

| | |
|---|---|
| **What** | Open-source OCR engine (Google) |
| **Version** | pytesseract 0.3.13 |
| **Why chosen** | Industry-standard for local OCR. Supports 100+ languages. Free. Runs offline. |
| **Why not Google Vision / AWS Textract** | Cloud services — violate air-gap. |
| **Why not EasyOCR** | EasyOCR pulls ~300 MB of PyTorch models. Tesseract is lighter and faster for English text. |
| **How used** | `core/pdf_processor.py` → `_ocr_page()`. Pages with <30 chars of selectable text are rendered at 300 DPI via PyMuPDF, then OCR'd. Tesseract is optional — if not installed, scanned pages are skipped with a warning. Auto-detects common Windows install paths. |

---

## Chunking Strategy

### RecursiveCharacterTextSplitter

| | |
|---|---|
| **What** | LangChain's hierarchical text splitter |
| **Version** | langchain-text-splitters 1.1.2 |
| **Why chosen** | Splits on `\n\n` → `\n` → `. ` → `! ` → `? ` → `; ` → ` ` → `""` in order of preference — preserves paragraph boundaries when possible, falls back to sentences, then words. O(n) linear scan — no model calls. |
| **Why not SemanticChunker** | SemanticChunker computes pairwise embeddings to find semantic boundaries. This is O(n²) in the number of sentences — a 500-page PDF took 45+ minutes. RecursiveCharacterTextSplitter processes the same PDF in <1 second. |
| **Configuration** | `chunk_size=1000`, `chunk_overlap=200`. Larger chunks (vs. 500-char default) give the LLM more context per chunk. 200-char overlap ensures sentences aren't cut mid-thought. |
| **How used** | `core/ingestion.py` → `_run()`. |

---

## UI Design

### Dark Theme (Custom CSS)

| | |
|---|---|
| **What** | GitHub-inspired dark color palette with glassmorphism elements |
| **Why chosen** | Dark themes reduce eye strain for document work. The custom styling includes a frameless window design with glassmorphism sidebar, smooth transitions, and responsive layout. |
| **How used** | `electron/renderer/styles.css` (28KB) — comprehensive stylesheet with custom classes for chat bubbles, source chips, metric displays, status indicators, and glassmorphism effects. Loaded directly by `index.html`. |

### Inter (Google Font)

| | |
|---|---|
| **What** | Professional sans-serif typeface designed for screen readability |
| **Why chosen** | Highly legible at small sizes (11-14px), variable weight support, widely used in developer tools. |
| **How used** | Loaded via `@import url()` in the CSS. Applied globally. |

---

## Testing & CI/CD

### pytest + FastAPI TestClient

| | |
|---|---|
| **What** | Python testing framework with FastAPI's built-in test client |
| **Why chosen** | Allows testing REST API endpoints without starting a real server. Tests run synchronously, deterministically, and fast. |
| **How used** | `tests/test_backend.py` — tests app info, Ollama status, document listing, and session CRUD operations. |

### GitHub Actions

| | |
|---|---|
| **What** | CI/CD pipeline for automated testing and desktop app builds |
| **Why chosen** | Native integration with the GitHub repository. Free for open source projects. Supports Windows runners needed for Electron builds. |
| **How used** | `.github/workflows/ci-cd.yml` — **CI:** runs pytest on every push/PR to `main`. **CD:** builds Windows NSIS installer via electron-builder on push to `main`, uploads `.exe` as artifact. |

### electron-builder + NSIS

| | |
|---|---|
| **What** | Build tool for distributable Electron applications + NSIS installer framework |
| **Version** | electron-builder 26.15.3 |
| **Why chosen** | Produces Windows installers with custom scripts. Bundles all Python backend code as `extraResources`. NSIS supports custom install/uninstall hooks. |
| **How used** | `electron/package.json` → `build` config bundles `backend/`, `core/`, `config/`, `security/`, `sessions/`, `requirements.txt`, `setup_env.bat`, and `download_embeddings.py`. `installer.nsh` runs automated environment setup post-install. |

---

## Data Persistence

All runtime data lives under `data/` (gitignored):

| Directory | Format | Contents |
|-----------|--------|----------|
| `data/documents/` | PDF files | Permanent copies of uploaded documents |
| `data/faiss_index/` | Binary + JSON | `index.faiss`, `index.pkl`, `bm25_index.pkl`, `doc_metadata.json`, `index_state.json` |
| `data/sessions/` | JSON files | One file per chat session: `<session_id>.json` |
| `data/models/embeddings/` | Model files | Pre-cached embedding model (`all-MiniLM-L6-v2/`) for offline startup |
