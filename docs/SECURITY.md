# 🔐 Security & Privacy

PrivateGPT is designed for environments where data must never leave the host machine. This document covers the privacy architecture and data handling model.

---

## Core Security Principle: Air-Gap

**No data ever leaves the machine.** This is enforced at every layer:

| Layer | How Privacy is Enforced |
|-------|------------------------|
| **LLM** | Ollama runs locally. No API calls to OpenAI, Anthropic, or any cloud service. |
| **Embeddings** | all-MiniLM-L6-v2 runs locally via sentence-transformers. No embedding API calls. Pre-cached to `data/models/embeddings/` for fully offline startup. |
| **Vector Store** | FAISS index stored on local disk. No Pinecone, Chroma, or cloud vector DB. |
| **OCR** | Tesseract runs locally. No Google Vision, AWS Textract, or cloud OCR. |
| **Storage** | All data stored under `data/` on local filesystem. No cloud storage. |
| **Network** | After initial model downloads, the system is fully offline-capable. |

---

## User Identity

PrivateGPT v2.0 uses OS-level user identity instead of an application-level authentication system:

```python
# backend/server.py
import getpass
USERNAME = getpass.getuser()  # Detects current OS user
```

| Property | Value |
|----------|-------|
| **Identity Source** | Operating system username (`getpass.getuser()`) |
| **Session Isolation** | Sessions filtered by `username` field — users only see their own chat history |
| **Access Control** | Relies on OS-level file permissions and user accounts |
| **No Password Storage** | No `users.json`, no password hashing, no auth tokens |

**Rationale:** As a local desktop application, PrivateGPT inherits the security of the host operating system. The user who launches the app is the authenticated user. Application-level authentication was removed in v2.0 as it added complexity without meaningful security benefit for a single-machine desktop app.

---

## Electron Security

The Electron desktop frontend follows security best practices:

| Security Feature | Implementation |
|------------------|----------------|
| **Context Isolation** | `contextIsolation: true` — renderer has no access to Node.js APIs |
| **No Node Integration** | `nodeIntegration: false` — prevents remote code execution via the renderer |
| **Preload Bridge** | `preload.js` uses `contextBridge.exposeInMainWorld()` with minimal API surface |
| **Local Backend Only** | FastAPI binds to `127.0.0.1:8765` — not accessible from the network |
| **No Remote Content** | App loads only local HTML files, no remote URLs |

### Exposed IPC Surface

The preload bridge exposes exactly 8 functions — no filesystem, no shell, no network access:

```javascript
contextBridge.exposeInMainWorld("electronAPI", {
  getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),
  minimize: ()    => ipcRenderer.invoke("window-minimize"),
  maximize: ()    => ipcRenderer.invoke("window-maximize"),
  close: ()       => ipcRenderer.invoke("window-close"),
  isMaximized: () => ipcRenderer.invoke("window-is-maximized"),
  selectFiles: () => ipcRenderer.invoke("select-files"),
  onBackendReady: (cb) => ipcRenderer.on("backend-ready", cb),
  onBackendError: (cb) => ipcRenderer.on("backend-error", cb),
});
```

---

## Data Isolation

### Per-User Session Isolation

Each user's chat sessions are stored in separate JSON files:

```
data/sessions/
├── a1b2c3d4.json    ← alice's session (if OS user = alice)
├── e5f6g7h8.json    ← alice's session
└── i9j0k1l2.json    ← bob's session (if OS user = bob)
```

`SessionManager.list_for_user(username)` filters by the `username` field inside each JSON — users only see their own sessions. The `username` is the OS-level user from `getpass.getuser()`.

### Document Visibility

All indexed documents are shared across all users (organizational knowledge base model). The frontend document filter allows users to scope their queries, but does not restrict access.

### Data Directory Structure

```
data/                            # All runtime data (gitignored)
├── documents/                   # Permanent PDF copies
├── faiss_index/                 # FAISS + BM25 indexes + metadata
│   ├── index.faiss              # Vector index
│   ├── index.pkl                # FAISS docstore
│   ├── bm25_index.pkl           # BM25 keyword index
│   ├── doc_metadata.json        # Document metadata registry
│   └── index_state.json         # Embedding backend version
├── sessions/                    # Per-user chat session JSON files
└── models/embeddings/           # Cached embedding model
    └── all-MiniLM-L6-v2/        # Pre-downloaded for offline use
```

---

## Threat Model

### In Scope

| Threat | Mitigation |
|--------|-----------|
| Data exfiltration via cloud APIs | Zero cloud dependencies — fully offline |
| Unauthorized network access to backend | FastAPI binds to `127.0.0.1` only — not accessible from network |
| Renderer process compromise | Context isolation + no nodeIntegration + minimal IPC bridge |
| Embedding model download interception | SSL patch only for initial download; model cached locally after first use |
| Cross-user session access | Sessions filtered by OS username |

### Out of Scope

| Threat | Why Not Addressed |
|--------|------------------|
| Physical access to the machine | Out of scope for an application-level tool. Use OS-level disk encryption (BitLocker, LUKS). |
| `data/` directory access by other OS users | Protected by OS file permissions. The directory is gitignored. |
| Malicious PDF exploitation | PyMuPDF handles PDF parsing; no sandboxing of PDF content. |
| Local privilege escalation | The app runs with the current user's privileges — no elevation required. |

---

## SSL Certificate Bypass

The system includes a shared SSL patch (`core/ssl_patch.py`) that disables TLS certificate verification for HuggingFace Hub downloads. This is required on corporate networks with self-signed CA chains.

**This only affects model downloads from HuggingFace** (first run or when models aren't cached locally). It does not affect the security of the application itself, and has no effect once models are cached in `data/models/embeddings/`.

---

## Network Exposure Summary

| Component | Binds To | Internet Required |
|-----------|----------|-------------------|
| FastAPI Backend | `127.0.0.1:8765` | No (after model download) |
| Ollama Server | `localhost:11434` | Only for model pulls |
| Electron App | Local window | No |
| Embedding Model | Local disk | Only for first download |
| FAISS Index | Local disk | No |
| BM25 Index | Local disk | No |
