"""
app.py — PrivateGPT Production UI
Run: streamlit run app.py
"""

import os
import tempfile
import streamlit as st
from pathlib import Path

# Local modules
from security.auth import (
    setup_default_admin, authenticate, register_user,
    change_password, list_users, delete_user, get_role, read_audit_log
)
from sessions.manager import (
    create_session, load_session, list_sessions,
    add_message, delete_session, rename_session, export_session_txt
)
from core.ingest import ingest_documents, list_documents, remove_document, rebuild_index
from core.query_engine import query


# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PrivateGPT",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Clean dark sidebar */
[data-testid="stSidebar"] { background: #0f1117; }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }

/* Chat bubbles */
.user-bubble {
    background: #1e3a5f; color: #e8f0fe;
    padding: 10px 14px; border-radius: 14px 14px 4px 14px;
    margin: 6px 0; max-width: 80%; margin-left: auto;
    font-size: 14px; line-height: 1.6;
}
.ai-bubble {
    background: #1a1f2e; color: #e0e0e0;
    padding: 10px 14px; border-radius: 14px 14px 14px 4px;
    margin: 6px 0; max-width: 85%;
    font-size: 14px; line-height: 1.6; border: 1px solid #2a3040;
}
.source-chip {
    display: inline-block;
    background: #1a2a1a; color: #7ecf7e;
    border: 1px solid #2a4a2a;
    padding: 2px 9px; border-radius: 20px;
    font-size: 11px; margin: 2px 3px 0 0;
}
.metric-row { color: #666; font-size: 11px; margin-top: 6px; }
.section-title {
    font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #555; margin: 16px 0 6px;
}
</style>
""", unsafe_allow_html=True)


# ── Bootstrap ──────────────────────────────────────────────────────────────
setup_default_admin()


# ── Session state defaults ─────────────────────────────────────────────────
for key, default in [
    ("logged_in", False),
    ("username", ""),
    ("role", ""),
    ("session_id", None),
    ("messages", []),
    ("active_tab", "chat"),
    ("selected_docs", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════════════════════════════════
# LOGIN SCREEN
# ══════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("## 🔒 PrivateGPT")
        st.caption("Air-gapped document intelligence — all data stays on this machine.")
        st.divider()

        tab_login, tab_register = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Sign In", type="primary", use_container_width=True):
                ok, result = authenticate(username, password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username  = username
                    st.session_state.role      = result          # role string
                    # Create a new session for this login
                    sess = create_session(username)
                    st.session_state.session_id = sess["id"]
                    st.session_state.messages   = []
                    st.rerun()
                else:
                    st.error(result)

        with tab_register:
            new_user = st.text_input("Choose username", key="reg_user")
            new_pass = st.text_input("Choose password (8+ chars)", type="password", key="reg_pass")
            if st.button("Create Account", use_container_width=True):
                ok, msg = register_user(new_user, new_pass, role="user")
                if ok:
                    st.success("Account created — sign in above.")
                else:
                    st.error(msg)

        st.caption("Default admin login: **admin / admin123** — change after first login.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# MAIN APP (logged in)
# ══════════════════════════════════════════════════════════════════════════

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 🔒 PrivateGPT")
    st.caption(f"Signed in as **{st.session_state.username}** ({st.session_state.role})")
    if st.button("Sign Out", use_container_width=True):
        for key in ["logged_in","username","role","session_id","messages","selected_docs"]:
            st.session_state[key] = False if key == "logged_in" else "" if key in ["username","role"] else None if key == "session_id" else []
        st.rerun()

    st.divider()

    # Navigation
    tabs = ["💬 Chat", "📄 Documents", "🕘 History"]
    if st.session_state.role == "admin":
        tabs += ["👤 Users", "📋 Audit Log"]

    for t in tabs:
        key = t.split()[-1].lower()
        if st.button(t, use_container_width=True,
                     type="primary" if st.session_state.active_tab == key else "secondary"):
            st.session_state.active_tab = key
            st.rerun()

    st.divider()

    # Document filter for chat
    docs = list_documents()
    if docs:
        st.markdown('<div class="section-title">Filter chat by document</div>', unsafe_allow_html=True)
        all_names = [d["name"] for d in docs]
        selected  = st.multiselect(
            "Active documents",
            options=all_names,
            default=st.session_state.selected_docs or all_names,
            label_visibility="collapsed",
        )
        st.session_state.selected_docs = selected
        st.caption(f"{len(selected)} of {len(all_names)} docs active")

    # Model selector
    st.divider()
    st.markdown('<div class="section-title">Model</div>', unsafe_allow_html=True)
    model = st.selectbox(
        "LLM model",
        ["phi3", "phi3:3.8b", "llama3", "llama3:8b", "mistral"],
        label_visibility="collapsed",
    )
    st.session_state.model = model

    st.divider()
    st.caption("🟢 Ollama · localhost:11434")
    st.caption(f"🗂 {len(docs)} doc(s) indexed")
    st.caption("🔴 Network: air-gapped")


# ══════════════════════════════════════════════════════════════════════════
# TAB: CHAT
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.active_tab == "chat":
    st.markdown("## 💬 Chat with your documents")

    if not list_documents():
        st.info("No documents indexed yet. Go to **Documents** tab to upload PDFs.")
        st.stop()

    if not st.session_state.selected_docs:
        st.warning("No documents selected. Pick at least one in the sidebar.")
        st.stop()

    # New chat button
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("＋ New chat"):
            sess = create_session(st.session_state.username)
            st.session_state.session_id = sess["id"]
            st.session_state.messages   = []
            st.rerun()

    # Render message history
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="user-bubble">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="ai-bubble">{msg["content"]}</div>', unsafe_allow_html=True)
            # Source chips
            sources = msg.get("metadata", {}).get("sources", [])
            if sources:
                chips = "".join(
                    f'<span class="source-chip">📄 {s["file"]} p.{s["page"]}</span>'
                    for s in sources
                )
                st.markdown(chips, unsafe_allow_html=True)
            # Metrics
            m = msg.get("metadata", {}).get("metrics", {})
            if m:
                st.markdown(
                    f'<div class="metric-row">⏱ {m.get("latency_sec","?")}s &nbsp;|&nbsp; '
                    f'💾 {m.get("ram_delta_mb","?")} MB &nbsp;|&nbsp; '
                    f'🔍 {m.get("chunks_used","?")} chunks &nbsp;|&nbsp; '
                    f'🤖 {m.get("model","?")}</div>',
                    unsafe_allow_html=True,
                )

    # Input
    if question := st.chat_input("Ask anything about your documents…"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": question})
        add_message(st.session_state.session_id, "user", question)

        with st.spinner("Searching documents…"):
            try:
                result = query(
                    question,
                    model=st.session_state.get("model", "phi3"),
                    filter_files=st.session_state.selected_docs,
                )
                answer  = result["answer"]
                sources = result["sources"]
                metrics = result["metrics"]
            except Exception as e:
                answer  = f"Error: {str(e)}"
                sources = []
                metrics = {}

        # Add AI message
        meta = {"sources": sources, "metrics": metrics}
        st.session_state.messages.append({"role": "assistant", "content": answer, "metadata": meta})
        add_message(st.session_state.session_id, "assistant", answer, meta)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB: DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "documents":
    st.markdown("## 📄 Document Manager")

    # Upload
    st.markdown("### Upload new PDFs")
    uploaded = st.file_uploader(
        "Drop PDF files here", type="pdf", accept_multiple_files=True
    )

    if uploaded and st.button("Index documents", type="primary"):
        tmp_paths = []
        for f in uploaded:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix=f.name.replace(".pdf","_"))
            tmp.write(f.read())
            tmp.close()
            # Rename so source_file metadata matches original filename
            dest = os.path.join(tempfile.gettempdir(), f.name)
            os.replace(tmp.name, dest)
            tmp_paths.append(dest)

        progress = st.progress(0, text="Starting…")

        def cb(i, total, msg):
            progress.progress(int((i / total) * 100), text=msg)

        result = ingest_documents(tmp_paths, progress_callback=cb)
        progress.empty()

        for p in tmp_paths:
            try: os.unlink(p)
            except: pass

        if result["ingested"]:
            st.success(f"Indexed: {', '.join(result['ingested'])}")
        if result["skipped"]:
            st.info(f"Skipped (unchanged): {', '.join(result['skipped'])}")
        if result["errors"]:
            for e in result["errors"]:
                st.error(f"Error — {e['file']}: {e['error']}")
        st.rerun()

    # Document list
    st.markdown("### Indexed documents")
    docs = list_documents()
    if not docs:
        st.info("No documents indexed yet. Upload PDFs above.")
    else:
        for doc in docs:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            col1.markdown(f"**{doc['name']}**")
            col2.caption(f"{doc['pages']} pages")
            col3.caption(f"{doc['chunks']} chunks")
            if col4.button("🗑 Remove", key=f"del_{doc['name']}"):
                remove_document(doc["name"])
                st.warning(f"Removed {doc['name']} from registry. Click 'Rebuild index' to apply.")
                st.rerun()

        st.divider()
        if st.button("🔄 Rebuild full index", help="Required after removing documents"):
            with st.spinner("Rebuilding index from scratch…"):
                result = rebuild_index()
            st.success(f"Rebuilt: {len(result['ingested'])} docs, {result['total_chunks']} chunks")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB: HISTORY
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "history":
    st.markdown("## 🕘 Chat History")

    sessions = list_sessions(st.session_state.username)
    if not sessions:
        st.info("No saved chats yet.")
    else:
        for s in sessions:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            col1.markdown(f"**{s['label']}**  \n<small>{s['created_at'][:16]} · {s['msg_count']} messages</small>", unsafe_allow_html=True)

            if col2.button("Load", key=f"load_{s['id']}"):
                sess_data = load_session(s["id"])
                st.session_state.session_id = s["id"]
                st.session_state.messages   = sess_data.get("messages", [])
                st.session_state.active_tab = "chat"
                st.rerun()

            export_txt = export_session_txt(s["id"])
            col3.download_button(
                "Export", data=export_txt,
                file_name=f"chat_{s['id']}.txt",
                mime="text/plain",
                key=f"exp_{s['id']}",
            )

            if col4.button("🗑", key=f"del_sess_{s['id']}"):
                delete_session(s["id"])
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB: USERS (admin only)
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "users" and st.session_state.role == "admin":
    st.markdown("## 👤 User Management")

    st.markdown("### Create user")
    col1, col2, col3 = st.columns(3)
    nu = col1.text_input("Username")
    np = col2.text_input("Password", type="password")
    nr = col3.selectbox("Role", ["user", "admin"])
    if st.button("Create user"):
        ok, msg = register_user(nu, np, nr)
        st.success(msg) if ok else st.error(msg)

    st.markdown("### All users")
    for u in list_users():
        col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
        col1.markdown(f"**{u['username']}**")
        col2.caption(u["role"])
        col3.caption(f"Last login: {(u['last_login'] or 'Never')[:16]}")
        if u["username"] != st.session_state.username:
            if col4.button("Delete", key=f"del_u_{u['username']}"):
                ok, msg = delete_user(u["username"])
                st.success(msg) if ok else st.error(msg)
                st.rerun()

    st.divider()
    st.markdown("### Change my password")
    op = st.text_input("Current password", type="password", key="cp_old")
    np2 = st.text_input("New password", type="password", key="cp_new")
    if st.button("Update password"):
        ok, msg = change_password(st.session_state.username, op, np2)
        st.success(msg) if ok else st.error(msg)


# ══════════════════════════════════════════════════════════════════════════
# TAB: AUDIT LOG (admin only)
# ══════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "audit log" and st.session_state.role == "admin":
    st.markdown("## 📋 Audit Log")
    st.caption("Last 200 security events")
    log = read_audit_log(200)
    st.code(log, language=None)
    st.download_button("Download full log", data=log, file_name="audit.log", mime="text/plain")