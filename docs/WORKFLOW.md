# 🔄 Workflow

This document traces every major workflow through the system, from the user's click to the final output. Each step references the exact source file and method responsible.

---

## 1. Document Ingestion Workflow

**Trigger:** User uploads PDFs on the Documents page and clicks "Index documents".

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────┐
│ Upload   │───▶│ PDFProcessor │───▶│   Chunker    │───▶│  FAISS   │───▶│  BM25    │
│ (UI)     │    │ (3-tier)     │    │ (Recursive)  │    │  Index   │    │  Index   │
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
| 1. **Upload** | `ui/pages/documents.py` → `render_documents_page()` | User selects PDF files via `st.file_uploader()`. Files are written to OS temp dir. |
| 2. **Permanent copy** | `core/ingestion.py` → `_ensure_permanent_copy()` | PDF is copied to `data/documents/` for persistence. |
| 3. **Hash check** | `core/ingestion.py` → `_file_hash()` | SHA-256 hash is compared against stored metadata. If unchanged, file is skipped (idempotent). |
| 4. **PDF extraction** | `core/pdf_processor.py` → `extract()` | 3-tier extraction runs per page (see below). |
| 5. **Text cleaning** | `core/pdf_processor.py` → `_clean_text()` | Headers, footers, page numbers, and boilerplate are stripped. |
| 6. **Chunking** | `core/ingestion.py` → `_run()` | `RecursiveCharacterTextSplitter` splits into 1000-char chunks with 200-char overlap. Each chunk gets a sequential `chunk_index` in metadata. |
| 7. **FAISS indexing** | `core/ingestion.py` → `_run()` | Chunks are embedded via `EmbeddingsManager` (all-MiniLM-L6-v2) and stored in FAISS. |
| 8. **BM25 indexing** | `core/ingestion.py` → `_run()` | Parallel keyword index built with `rank_bm25.BM25Okapi`. |
| 9. **Hot reload** | `core/vector_store.py` → `mark_dirty()` | Signals `VectorStoreManager` to reload from disk on next query. |
| 10. **Enrichment** | `core/enrichment.py` → `BackgroundEnricher.start()` | Daemon thread starts enriching chunks with LLM-generated context (non-blocking). |
| 11. **UI feedback** | `ui/pages/documents.py` | Progress bar, success/error messages, and enrichment badge in sidebar. |

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

**Trigger:** User types a question in the Chat page.

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
| 1. **Hybrid search** | `core/vector_store.py` → `search_with_neighbors()` | FAISS (dense, semantic) + BM25 (sparse, keyword) search in parallel. |
| 2. **RRF fusion** | `core/vector_store.py` → `_rrf_fuse()` | Reciprocal Rank Fusion merges both result lists with configurable weights (60% FAISS, 40% BM25). |
| 3. **Neighbor expansion** | `core/vector_store.py` → `_expand_neighbors()` | For each hit, ±1 adjacent chunks from the same document are included. Uses `chunk_index` metadata and binary search over the chunk registry. |
| 4. **File filtering** | `core/graph/engine.py` → `retrieve()` | Only chunks from sidebar-selected documents are kept. |
| 5. **Cross-encoder reranking** | `core/graph/engine.py` → `retrieve()` | `ms-marco-MiniLM-L-6-v2` scores each (query, chunk) pair with deep attention. Top 4 kept. |
| 6. **UI: source chips** | `ui/pages/chat.py` | Source file/page badges are shown immediately — user sees retrieval results while generation starts. |

### Phase 2: Generation (streaming, ~5-70s)

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 7. **Prompt assembly** | `core/graph/nodes.py` → `_PROMPT_TEMPLATE` | Context chunks formatted with source attribution, injected into a strict grounding prompt. |
| 8. **Streaming** | `core/graph/engine.py` → `stream_answer()` | `OllamaLLM.stream()` yields tokens one-by-one. |
| 9. **Live render** | `ui/pages/chat.py` | Each token is appended to the answer with a blinking cursor `▌`. |
| 10. **Session save** | `sessions/manager.py` → `add_message()` | Full answer, sources, and metrics are persisted to the session JSON. |

### Full Graph (non-streaming fallback)

When the full LangGraph is invoked (e.g., for session export), it executes all 6 nodes:

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
              │ UI Badge │                  │mark_dirty│
              │ "⚡ 45%" │                  │(hot swap)│
              └──────────┘                  └──────────┘
```

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Launch** | `core/enrichment.py` → `BackgroundEnricher.start()` | A Python daemon thread starts (dies when FastAPI backend stops). |
| 2. **Per-chunk enrichment** | `core/enrichment.py` → `_enrich_loop()` | For each chunk, the LLM (phi3) generates a 1-2 sentence context summary: *"This chunk is from document X, page Y, discussing Z."* |
| 3. **Prepend context** | `core/enrichment.py` → `_enrich_loop()` | Context is prepended as `[Context: ...]` to the chunk text. |
| 4. **Re-index** | `core/enrichment.py` → `_rebuild_indexes()` | Enriched chunks are re-embedded and stored in FAISS + BM25. |
| 5. **Hot swap** | `core/vector_store.py` → `mark_dirty()` | Next query automatically uses the enriched index. |
| 6. **UI badge** | `ui/sidebar.py` | Sidebar shows `⚡ Enhancing: 45%` progress via `enricher.status`. |

**Key property:** The system is immediately queryable after ingestion. Enrichment improves quality progressively in the background.

---

## 4. Authentication Workflow

**Trigger:** User opens the app (unauthenticated state).

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Login    │──▶│ PBKDF2   │──▶│ Audit    │──▶│ Session  │
│ Form     │   │ Verify   │   │ Log      │   │ Create   │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
```

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **Login gate** | `app.py` line 115 | If `st.session_state.logged_in` is False, only the login/register form is shown. `st.stop()` blocks all other rendering. |
| 2. **Credential check** | `security/auth.py` → `authenticate()` | Password is hashed with PBKDF2-HMAC-SHA256 (260,000 iterations) using the stored salt, then compared via `hmac.compare_digest()` (timing-safe). |
| 3. **Audit log** | `security/auth.py` → `_audit()` | Every auth event (success, failure, registration, deletion) is appended to `data/security/audit.log`. |
| 4. **Session creation** | `sessions/manager.py` → `create()` | A new session JSON file is created in `data/sessions/`. |
| 5. **State update** | `app.py` line 131 | `st.session_state` is updated with username, role, session_id, and the page reruns. |

---

## 5. Model Management Workflow

**Trigger:** User navigates to the Models page.

| Step | Code Location | What Happens |
|------|---------------|-------------|
| 1. **List models** | `core/ollama_manager.py` → `list_models()` | HTTP GET to Ollama's `/api/tags` endpoint (localhost:11434). |
| 2. **Pull model** | `core/ollama_manager.py` → `pull()` | Streaming HTTP POST to `/api/pull`. Progress is streamed back to the UI in real-time. |
| 3. **Delete model** | `core/ollama_manager.py` → `delete()` | HTTP DELETE to `/api/delete`. |
| 4. **Server start** | `core/ollama_manager.py` → `start()` | `subprocess.Popen(["ollama", "serve"])` with platform-specific flags. Polls health endpoint for 10s. |
