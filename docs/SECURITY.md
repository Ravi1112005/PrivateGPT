# 🔐 Security

PrivateGPT is designed for environments where data must never leave the host machine. This document covers the security architecture and threat model.

---

## Core Security Principle: Air-Gap

**No data ever leaves the machine.** This is enforced at every layer:

| Layer | How Privacy is Enforced |
|-------|------------------------|
| **LLM** | Ollama runs locally. No API calls to OpenAI, Anthropic, or any cloud service. |
| **Embeddings** | all-MiniLM-L6-v2 runs locally via sentence-transformers. No embedding API calls. |
| **Vector Store** | FAISS index stored on local disk. No Pinecone, Chroma, or cloud vector DB. |
| **OCR** | Tesseract runs locally. No Google Vision, AWS Textract, or cloud OCR. |
| **Authentication** | PBKDF2-HMAC-SHA256 in Python's standard library. No external auth services. |
| **Storage** | All data stored under `data/` on local filesystem. No cloud storage. |
| **Network** | After initial Ollama model download, the system is fully offline-capable. |

---

## Authentication

### Password Hashing

```
Password → PBKDF2-HMAC-SHA256 (260,000 iterations) → 256-bit key
                    ↑
              256-bit random salt (per user)
```

| Property | Value | Why |
|----------|-------|-----|
| **Algorithm** | PBKDF2-HMAC-SHA256 | NIST SP 800-132 recommended. In Python stdlib. |
| **Iterations** | 260,000 | OWASP 2023 recommendation for PBKDF2-SHA256. Makes brute-force infeasible. |
| **Salt** | 256-bit random | `secrets.token_hex(32)`. Unique per user — prevents rainbow table attacks. |
| **Comparison** | `hmac.compare_digest()` | Constant-time comparison — prevents timing attacks. |

### Password Storage Format

```json
// data/security/users.json
{
  "admin": {
    "hash": "a3f2b8c1...",     // PBKDF2 output (hex)
    "salt": "7e9d4f12...",     // Random salt (hex)
    "role": "admin",
    "created_at": "2026-08-05T10:30:00",
    "last_login": "2026-08-09T22:00:00"
  }
}
```

**Passwords are never stored in plaintext.** The hash is irreversible — even with access to `users.json`, recovering the password requires brute-forcing 260,000 iterations of PBKDF2 per guess.

### Role-Based Access Control

| Role | Permissions |
|------|------------|
| `user` | Chat, Documents, Models, History |
| `admin` | All of above + User Management + Audit Log |

Admin pages are gated in `app.py`:
```python
elif tab == "users" and st.session_state.role == "admin":
    render_users_page(auth_mgr)
```

### Admin Protections

- **Default admin:** `admin / admin123` is auto-created on first run. Should be changed immediately.
- **Last admin guard:** `AuthManager.delete()` refuses to delete the last admin account — prevents lockout.
- **Self-deletion guard:** Admin UI hides the delete button for the currently signed-in user.

---

## Audit Logging

Every authentication event is logged to `data/security/audit.log`:

```
2026-08-05T10:30:00 | SETUP                | admin                | Default admin created — change password immediately
2026-08-05T10:31:00 | LOGIN_OK             | admin                |
2026-08-05T10:35:00 | LOGIN_FAIL           | hacker               | user not found
2026-08-05T10:36:00 | REGISTER             | alice                | role=user
2026-08-05T10:40:00 | PASSWD_CHANGE        | admin                |
2026-08-05T10:45:00 | DELETE_USER          | bob                  |
```

| Event | When Logged |
|-------|-------------|
| `SETUP` | Default admin created on first run |
| `LOGIN_OK` | Successful authentication |
| `LOGIN_FAIL` | Wrong username or password (logs which) |
| `REGISTER` | New user created |
| `PASSWD_CHANGE` | Password updated |
| `DELETE_USER` | User account removed |

The audit log is append-only and never truncated. Admins can view and download it from the Audit Log page.

---

## Data Isolation

### Per-User Session Isolation

Each user's chat sessions are stored in separate JSON files:

```
data/sessions/
├── a1b2c3d4.json    ← alice's session
├── e5f6g7h8.json    ← alice's session
└── i9j0k1l2.json    ← bob's session
```

`SessionManager.list_for_user(username)` filters by the `username` field inside each JSON — users only see their own sessions.

### Document Visibility

All indexed documents are shared across all users (organizational knowledge base model). The sidebar document filter allows users to scope their queries, but does not restrict access.

---

## Threat Model

### In Scope

| Threat | Mitigation |
|--------|-----------|
| Credential brute-force | PBKDF2 with 260K iterations + timing-safe comparison |
| Rainbow table attack | Unique 256-bit salt per user |
| Timing attack on auth | `hmac.compare_digest()` |
| Data exfiltration via cloud APIs | Zero cloud dependencies — fully offline |
| Unauthorized admin access | Role-based access control + audit logging |
| Admin lockout | Last-admin deletion guard |

### Out of Scope

| Threat | Why Not Addressed |
|--------|------------------|
| Physical access to the machine | Out of scope for an application-level tool. Use OS-level disk encryption (BitLocker, LUKS). |
| Network-based attacks on FastAPI | FastAPI binds to localhost by default. The Electron app connects locally. |
| `users.json` file access | Protected by OS file permissions. The file is gitignored. |
| Session hijacking | Handled internally within the JS SPA memory and FastAPI. |

---

## SSL Certificate Bypass

The system includes a shared SSL patch (`core/ssl_patch.py`) that disables TLS certificate verification for HuggingFace Hub downloads. This is required on corporate networks with self-signed CA chains.

**This only affects model downloads from HuggingFace** (first run). It does not affect the security of the application itself, and has no effect once models are cached locally.
