# ⚙️ Functionalities

A complete inventory of every feature in PrivateGPT, organized by the UI page where it surfaces.

---

## 🔒 Authentication System

| Feature | Description | Source |
|---------|-------------|--------|
| **Sign In** | Username + password login with PBKDF2-HMAC-SHA256 verification | `security/auth.py` → `authenticate()` |
| **Create Account** | Self-registration with password validation (8+ chars) | `security/auth.py` → `register()` |
| **Default Admin** | Auto-creates `admin / admin123` on first run | `security/auth.py` → `setup_default_admin()` |
| **Role-Based Access** | Two roles: `admin` (full access) and `user` (no admin pages) | `app.py` line 173 |
| **Timing-Safe Auth** | Uses `hmac.compare_digest()` to prevent timing attacks | `security/auth.py` → `_verify()` |
| **Audit Logging** | Every auth event logged with timestamp, event type, username | `security/auth.py` → `_audit()` |

---

## 💬 Chat Page

| Feature | Description | Source |
|---------|-------------|--------|
| **Streaming Answers** | Tokens appear one-by-one with a blinking cursor — no blank wait | `ui/pages/chat.py` line 107 |
| **Source Citations** | Green chips show source file + page for each retrieved chunk | `ui/pages/chat.py` → `_render_sources()` |
| **Performance Metrics** | Total latency, retrieval time, chunk count, model name | `ui/pages/chat.py` → `_render_metrics()` |
| **Debug Context** | Toggle to see the raw context sent to the LLM | `ui/pages/chat.py` line 64 |
| **Conversation Memory** | Full message history persisted per session, survives page reload | `sessions/manager.py` → `add_message()` |
| **New Chat** | Start a fresh conversation (creates a new session) | `ui/pages/chat.py` line 44 |
| **Pre-flight Checks** | Guards: Ollama running? Models downloaded? Docs indexed? Docs selected? | `ui/pages/chat.py` lines 28-39 |

---

## 📄 Documents Page

| Feature | Description | Source |
|---------|-------------|--------|
| **Multi-file Upload** | Upload multiple PDFs simultaneously via drag-and-drop or file picker | `ui/pages/documents.py` line 31 |
| **Progress Bar** | Per-file progress feedback during indexing | `ui/pages/documents.py` → callback `cb()` |
| **Idempotent Indexing** | SHA-256 hash check — unchanged files are skipped automatically | `core/ingestion.py` → `_file_hash()` |
| **3-Tier PDF Extraction** | Handles digital text, tables (→ Markdown), and scanned pages (OCR) | `core/pdf_processor.py` → `extract()` |
| **Text Cleaning** | Removes headers, footers, page numbers, boilerplate, junk pages | `core/pdf_processor.py` → `_clean_text()` |
| **Migration Banner** | Shows warning when embedding backend changes — prompts rebuild | `ui/pages/documents.py` line 22 |
| **Document List** | Shows all indexed docs with page count, chunk count, delete button | `ui/pages/documents.py` line 89 |
| **Delete Document** | Remove from metadata + permanent storage (requires rebuild) | `core/ingestion.py` → `remove()` |
| **Full Rebuild** | Re-index all documents from scratch with current settings | `core/ingestion.py` → `rebuild()` |
| **Chunk Statistics** | Shows total chunks and total docs after indexing | `ui/pages/documents.py` line 77 |

---

## 🤖 Models Page

| Feature | Description | Source |
|---------|-------------|--------|
| **Downloaded Models** | List all locally available Ollama models with param count + quantization | `ui/pages/models.py` line 22 |
| **Recommended Models** | Curated list with RAM requirements and descriptions | `core/ollama_manager.py` → `RECOMMENDED_MODELS` |
| **Streaming Pull** | Download models with real-time progress bar (% completion) | `core/ollama_manager.py` → `pull()` |
| **Custom Pull** | Pull any model by name (e.g., `gemma:2b`) | `ui/pages/models.py` line 73 |
| **Delete Model** | Remove locally downloaded models to free disk space | `core/ollama_manager.py` → `delete()` |
| **Model Info** | Show parameter size, quantization level, model family | `core/ollama_manager.py` → `get_info()` |

---

## 🕘 History Page

| Feature | Description | Source |
|---------|-------------|--------|
| **Session List** | All past chat sessions for the current user, sorted by date | `sessions/manager.py` → `list_for_user()` |
| **Load Session** | Restore a previous conversation into the chat view | `ui/pages/history.py` line 25 |
| **Export to TXT** | Download a formatted text transcript of any session | `sessions/manager.py` → `export_txt()` |
| **Delete Session** | Permanently remove a chat session | `sessions/manager.py` → `delete()` |

---

## 👤 Admin: User Management (admin-only)

| Feature | Description | Source |
|---------|-------------|--------|
| **Create User** | Admin can create accounts with chosen role | `ui/pages/admin.py` → `render_users_page()` |
| **User List** | All users with role, creation date, last login | `security/auth.py` → `list_users()` |
| **Delete User** | Remove any user (protects last admin from deletion) | `security/auth.py` → `delete()` |
| **Change Password** | Admin can change their own password | `security/auth.py` → `change_password()` |

---

## 📋 Admin: Audit Log (admin-only)

| Feature | Description | Source |
|---------|-------------|--------|
| **View Audit Log** | Last 200 lines of auth events | `ui/pages/admin.py` → `render_audit_page()` |
| **Download Log** | Export full audit log as text file | `ui/pages/admin.py` line 49 |

---

## Sidebar (Global)

| Feature | Description | Source |
|---------|-------------|--------|
| **Ollama Status** | Green/red indicator for server health | `ui/sidebar.py` line 47 |
| **Start Ollama** | One-click server launch (auto-detects platform) | `core/ollama_manager.py` → `start()` |
| **Navigation** | Tab-based routing to all pages | `ui/sidebar.py` line 61 |
| **Document Filter** | Multi-select filter — queries only search selected docs | `ui/sidebar.py` line 84 |
| **Model Selector** | Switch active LLM model from dropdown | `ui/sidebar.py` line 97 |
| **Debug Toggle** | Show/hide raw context sent to LLM in chat | `ui/sidebar.py` line 105 |
| **Enrichment Badge** | Live progress indicator: `⚡ Enhancing: 45%` | `ui/sidebar.py` line 117 |
| **Sign Out** | Clears all session state and redirects to login | `ui/sidebar.py` line 34 |

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
