# 🏗️ Architecture

PrivateGPT is a fully air-gapped, local-first document intelligence system. It runs entirely on the user's machine — no cloud services, no telemetry, no external API calls. Every component is designed with this constraint as the primary architectural driver.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Streamlit Frontend                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │   Chat   │ │Documents │ │  Models  │ │ History  │ │   Admin   │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬─────┘ │
│       │             │            │             │             │       │
│  ┌────┴─────────────┴────────────┴─────────────┴─────────────┴────┐ │
│  │                       Sidebar (Navigation + State)              │ │
│  └─────────────────────────────┬───────────────────────────────────┘ │
└────────────────────────────────┼─────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │        app.py           │
                    │   (Entry Point + DI)    │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
┌───────┴───────┐    ┌───────────┴──────────┐   ┌────────┴────────┐
│  core/ Layer  │    │  security/ Layer     │   │ sessions/ Layer │
│  (Pure Python)│    │  (Auth + Audit)      │   │ (Chat History)  │
└───────┬───────┘    └────────────────────┘   └─────────────────┘
        │
   ┌────┴──────────────────────────────────────────┐
   │              Core Components                    │
   │                                                 │
   │  ┌──────────────┐  ┌────────────────────────┐  │
   │  │PDFProcessor  │  │  IngestionPipeline     │  │
   │  │(3-tier       │─▶│  (Chunk + Index)       │  │
   │  │ extraction)  │  └───────────┬────────────┘  │
   │  └──────────────┘              │                │
   │                      ┌─────────┴──────────┐     │
   │                      ▼                    ▼     │
   │            ┌──────────────┐     ┌───────────┐   │
   │            │VectorStore   │     │Background │   │
   │            │Manager       │     │Enricher   │   │
   │            │(FAISS+BM25)  │     │(daemon)   │   │
   │            └──────┬───────┘     └───────────┘   │
   │                   │                              │
   │            ┌──────┴───────┐                      │
   │            │RAGGraphEngine│                      │
   │            │(LangGraph)   │                      │
   │            └──────┬───────┘                      │
   │                   │                              │
   │            ┌──────┴───────┐                      │
   │            │  Ollama LLM  │◀── OllamaManager    │
   │            │  (localhost)  │                      │
   │            └──────────────┘                      │
   └──────────────────────────────────────────────────┘
```

---

## Design Principles

### 1. Air-Gapped by Design

Every component is selected for offline operation:
- **Ollama** runs LLMs locally — no OpenAI, no API keys
- **FAISS** stores vector indexes on local disk — no Pinecone, no cloud vector DBs
- **sentence-transformers** embeds text on the local CPU — no embedding API calls
- **Tesseract OCR** runs locally — no Google Vision, no AWS Textract
- **PBKDF2-HMAC-SHA256** for password hashing — no external auth services

The only network call is the initial one-time download of Ollama models. After that, the system is fully functional without internet.

### 2. Clean Layer Separation

```
┌─────────────────────────────────────┐
│  UI Layer (ui/)                     │  Streamlit-only. No business logic.
│  - Pages render state               │  Never imports from core/ internals.
│  - Sidebar manages navigation       │
├─────────────────────────────────────┤
│  Entry Point (app.py)               │  Wires everything together with DI.
│  - @st.cache_resource singletons    │  The only file that knows about both
│  - Session state defaults            │  ui/ and core/.
├─────────────────────────────────────┤
│  Core Layer (core/)                 │  Pure Python. Zero Streamlit imports.
│  - PDF extraction                    │  Can be tested independently.
│  - Embeddings, vector store          │  Thread-safe where needed.
│  - LangGraph RAG pipeline           │
├─────────────────────────────────────┤
│  Config Layer (config/)             │  Dataclass-based settings singleton.
│  - All paths, model names, params    │  Auto-creates dirs on import.
├─────────────────────────────────────┤
│  Support Layers                     │
│  - security/ (auth + audit)          │  PBKDF2 hashing, JSON persistence.
│  - sessions/ (chat history)          │  Per-user JSON file storage.
└─────────────────────────────────────┘
```

**Why this matters:** The core layer has zero Streamlit dependencies. You can import and use `PDFProcessor`, `VectorStoreManager`, or `RAGGraphEngine` in a plain Python script, a Flask API, or a test harness — no UI framework lock-in.

### 3. Singleton Pattern via `@st.cache_resource`

Heavy objects are loaded exactly once and kept in RAM:

| Object | Load time | Memory | Reused across |
|--------|-----------|--------|---------------|
| `EmbeddingsManager` | ~10s (first load) | ~80 MB | All users, all reruns |
| `VectorStoreManager` | ~4s (first load) | Varies by index size | All users, all reruns |
| `OllamaManager` | Instant | Negligible | All users, all reruns |
| `AuthManager` | Instant | Negligible | All users, all reruns |
| `SessionManager` | Instant | Negligible | All users, all reruns |

**Why:** Streamlit reruns the entire `app.py` on every user interaction (button click, input change). Without `@st.cache_resource`, the embedding model would reload from disk on every click — a 10-second delay each time.

### 4. Dependency Injection

Core components receive their dependencies through constructor arguments, not global imports:

```python
# In app.py — the only place where wiring happens
embeddings = _get_embeddings()          # Singleton
vsm        = _get_vector_store()        # Depends on embeddings
pipeline   = IngestionPipeline(settings, embeddings, vsm)  # Injected
engine     = RAGGraphEngine(vsm, settings)                 # Injected
```

**Why:** This makes every core class independently testable. You can construct a `VectorStoreManager` with a mock `EmbeddingsManager` in a unit test — no Streamlit, no Ollama, no disk.

---

## Directory Structure

```
PrivateGPT/
├── app.py                      # Entry point + DI wiring
├── requirements.txt            # Python dependencies
├── .gitignore
│
├── config/
│   ├── __init__.py
│   └── settings.py             # Settings dataclass (singleton)
│
├── core/                       # Pure business logic (no Streamlit)
│   ├── __init__.py
│   ├── pdf_processor.py        # 3-tier PDF extraction (text/table/OCR)
│   ├── embeddings.py           # EmbeddingsManager (sentence-transformers)
│   ├── ingestion.py            # IngestionPipeline (PDF → chunks → FAISS)
│   ├── vector_store.py         # VectorStoreManager (FAISS + BM25 + neighbors)
│   ├── enrichment.py           # BackgroundEnricher (daemon thread)
│   ├── ollama_manager.py       # OllamaManager (server + model lifecycle)
│   ├── ssl_patch.py            # Shared SSL bypass for HuggingFace
│   ├── query_engine_legacy.py  # Legacy query engine (superseded by graph/)
│   └── graph/                  # LangGraph RAG pipeline
│       ├── __init__.py
│       ├── state.py            # RAGState TypedDict
│       ├── nodes.py            # 6 graph node functions
│       ├── builder.py          # StateGraph construction
│       └── engine.py           # RAGGraphEngine (public API)
│
├── security/
│   ├── __init__.py
│   └── auth.py                 # AuthManager (PBKDF2 + audit log)
│
├── sessions/
│   └── manager.py              # SessionManager (per-user JSON files)
│
├── ui/                         # Streamlit presentation layer
│   ├── __init__.py
│   ├── styles.py               # CSS injection (dark theme)
│   ├── sidebar.py              # Sidebar rendering
│   └── pages/
│       ├── __init__.py
│       ├── chat.py             # Chat page (streaming)
│       ├── documents.py        # Document Manager page
│       ├── models.py           # Model Manager page
│       ├── history.py          # Chat History page
│       └── admin.py            # User Management + Audit Log
│
├── data/                       # Runtime data (gitignored)
│   ├── documents/              # Permanent PDF copies
│   ├── faiss_index/            # FAISS + BM25 indexes + metadata
│   ├── sessions/               # Per-user chat session JSON files
│   └── security/               # users.json + audit.log
│
└── docs/                       # This documentation
```

---

## Component Interaction Map

```mermaid
graph TD
    A["app.py<br/>(Entry + DI)"] --> B["EmbeddingsManager"]
    A --> C["VectorStoreManager"]
    A --> D["IngestionPipeline"]
    A --> E["RAGGraphEngine"]
    A --> F["OllamaManager"]
    A --> G["AuthManager"]
    A --> H["SessionManager"]

    D -->|"uses"| I["PDFProcessor"]
    D -->|"builds"| C
    D -->|"starts"| J["BackgroundEnricher"]

    E -->|"searches"| C
    E -->|"calls"| F

    C -->|"embeds via"| B
    J -->|"enriches via"| F
    J -->|"re-indexes"| C

    subgraph "LangGraph Pipeline"
        E --> K["retrieve"]
        K --> L["rerank"]
        L --> M["check_retrieval"]
        M -->|"ok"| N["generate"]
        M -->|"fail"| P["finalize"]
        N --> O["validate"]
        O --> P
    end
```

---

## Data Flow Summary

| Flow | Path |
|------|------|
| **PDF → Index** | Upload → `PDFProcessor` (3-tier) → `RecursiveCharacterTextSplitter` → `FAISS.from_documents()` + `BM25Okapi` → disk |
| **Query → Answer** | Question → `hybrid_search` (FAISS + BM25 RRF) → neighbor expansion → cross-encoder rerank → prompt template → Ollama LLM → streaming tokens |
| **Login → Session** | Username/password → `PBKDF2-HMAC-SHA256` verify → audit log → `SessionManager.create()` → `st.session_state` |
| **Enrichment** | Background daemon → per-chunk LLM context generation → re-embed → replace FAISS index → `mark_dirty()` |
