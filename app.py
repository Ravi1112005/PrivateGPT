"""
app.py — PrivateGPT entry point
Run: streamlit run app.py

Architecture:
  - @st.cache_resource singletons ensure EmbeddingsManager and VectorStoreManager
    are loaded ONCE and kept in RAM for the life of the server process.
  - Business logic lives in core/ (pure Python, no Streamlit).
  - UI rendering lives in ui/ (Streamlit only, no business logic).
  - All runtime data is under data/ (documents, index, sessions, security).
"""

import streamlit as st

# ── Central config (creates data/ dirs + migrates legacy data) ─────────────
from config.settings import settings

# ── Core layer ─────────────────────────────────────────────────────────────
from core.embeddings    import EmbeddingsManager
from core.vector_store  import VectorStoreManager
from core.ingestion     import IngestionPipeline
from core.graph         import RAGGraphEngine
from core.ollama_manager import OllamaManager

# ── Auth & Sessions ────────────────────────────────────────────────────────
from security.auth   import AuthManager
from sessions.manager import SessionManager

# ── UI layer ───────────────────────────────────────────────────────────────
from ui.styles  import inject_styles
from ui.sidebar import render_sidebar
from ui.pages.chat      import render_chat_page
from ui.pages.documents import render_documents_page
from ui.pages.models    import render_models_page
from ui.pages.history   import render_history_page
from ui.pages.admin     import render_users_page, render_audit_page


# ══════════════════════════════════════════════════════════════════════════
# Singleton factories — @st.cache_resource keeps these objects alive across
# all Streamlit reruns.  Model and index are loaded exactly ONCE.
# ══════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Loading embedding model… (first run only)")
def _get_embeddings() -> EmbeddingsManager:
    """Load the sentence-transformer model once and keep it in RAM."""
    mgr = EmbeddingsManager(settings.embedding_model)
    mgr.preload()   # warm the model so first query has no load delay
    return mgr


@st.cache_resource(show_spinner=False)
def _get_vector_store() -> VectorStoreManager:
    """Load FAISS index once and keep it in RAM."""
    return VectorStoreManager(settings.index_dir, _get_embeddings())


@st.cache_resource(show_spinner=False)
def _get_ollama() -> OllamaManager:
    return OllamaManager()


@st.cache_resource(show_spinner=False)
def _get_auth() -> AuthManager:
    return AuthManager(settings.security_dir)


@st.cache_resource(show_spinner=False)
def _get_session_mgr() -> SessionManager:
    return SessionManager(settings.sessions_dir)


# ══════════════════════════════════════════════════════════════════════════
# App initialisation
# ══════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="PrivateGPT", page_icon="🔒", layout="wide")
inject_styles()

# Resolve singletons (fast after first call)
embeddings  = _get_embeddings()
vsm         = _get_vector_store()
ollama      = _get_ollama()
auth_mgr    = _get_auth()
session_mgr = _get_session_mgr()

# Per-request objects (cheap to construct — they hold no state themselves)
pipeline = IngestionPipeline(settings, embeddings, vsm)
engine   = RAGGraphEngine(vsm, settings)

# Bootstrap default admin on first run
auth_mgr.setup_default_admin()

# Session state defaults
_DEFAULTS = {
    "logged_in":    False,
    "username":     "",
    "role":         "",
    "session_id":   None,
    "messages":     [],
    "active_tab":   "chat",
    "selected_docs": [],
    "model":        settings.default_model,
    "show_debug":   False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════
# Login gate
# ══════════════════════════════════════════════════════════════════════════

if not st.session_state.logged_in:
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("## 🔒 PrivateGPT")
        st.caption("Air-gapped document intelligence — all data stays on this machine.")
        st.divider()

        tab_login, tab_register = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            uname = st.text_input("Username", key="login_user")
            upass = st.text_input("Password", type="password", key="login_pass")
            if st.button("Sign In", type="primary", use_container_width=True, key="login_btn"):
                ok, result = auth_mgr.authenticate(uname, upass)
                if ok:
                    sess = session_mgr.create(uname)
                    st.session_state.update({
                        "logged_in":  True,
                        "username":   uname,
                        "role":       result,
                        "session_id": sess["id"],
                        "messages":   [],
                    })
                    st.rerun()
                else:
                    st.error(result)

        with tab_register:
            new_u = st.text_input("Choose username",              key="reg_user")
            new_p = st.text_input("Choose password (8+ chars)",   key="reg_pass", type="password")
            if st.button("Create Account", use_container_width=True, key="reg_btn"):
                ok, msg = auth_mgr.register(new_u, new_p, role="user")
                st.success("Account created — sign in above.") if ok else st.error(msg)

        st.caption("Default login: **admin / admin123**")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# Main app — sidebar + page routing
# ══════════════════════════════════════════════════════════════════════════

render_sidebar(auth_mgr, pipeline, ollama)

tab = st.session_state.active_tab

if tab == "chat":
    render_chat_page(engine, session_mgr, ollama, pipeline)

elif tab == "documents":
    render_documents_page(pipeline, settings)

elif tab == "models":
    render_models_page(ollama)

elif tab == "history":
    render_history_page(session_mgr)

elif tab == "users" and st.session_state.role == "admin":
    render_users_page(auth_mgr)

elif tab == "audit log" and st.session_state.role == "admin":
    render_audit_page(auth_mgr)