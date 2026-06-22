"""
ui/sidebar.py — Sidebar rendering

Renders the persistent sidebar: branding, Ollama status, navigation,
document filter, model selector, and debug toggle.

Returns the chosen active_tab string.
"""

from __future__ import annotations

import streamlit as st

from core.ollama_manager import OllamaManager


def render_sidebar(
    auth_mgr,
    pipeline,
    ollama: OllamaManager,
) -> None:
    """
    Render the full sidebar.

    Reads / writes st.session_state directly for nav and settings.
    """
    with st.sidebar:
        # ── Branding ───────────────────────────────────────────────────────
        st.markdown("### 🔒 PrivateGPT")
        st.caption(
            f"Signed in as **{st.session_state.username}** "
            f"({st.session_state.role})"
        )
        if st.button("Sign Out", use_container_width=True, key="sb_signout"):
            for k in ["logged_in", "username", "role", "session_id", "messages", "selected_docs"]:
                st.session_state[k] = (
                    False if k == "logged_in"
                    else "" if k in ("username", "role")
                    else None if k == "session_id"
                    else []
                )
            st.rerun()

        st.divider()

        # ── Ollama status ──────────────────────────────────────────────────
        status = ollama.get_status()
        if status["running"]:
            st.markdown('<span class="status-ok">🟢 Ollama running</span>', unsafe_allow_html=True)
            st.caption(f"{status['model_count']} model(s) available")
        else:
            st.markdown('<span class="status-err">🔴 Ollama offline</span>', unsafe_allow_html=True)
            if st.button("▶ Start Ollama", use_container_width=True, key="sb_start_ollama"):
                with st.spinner("Starting Ollama…"):
                    ok, msg = ollama.start()
                st.success(msg) if ok else st.error(msg)
                st.rerun()

        st.divider()

        # ── Navigation ─────────────────────────────────────────────────────
        nav_items = ["💬 Chat", "📄 Documents", "🤖 Models", "🕘 History"]
        if st.session_state.role == "admin":
            nav_items += ["👤 Users", "📋 Audit Log"]

        for item in nav_items:
            tab_key = item.split()[-1].lower()
            is_active = st.session_state.active_tab == tab_key
            if st.button(
                item,
                use_container_width=True,
                type="primary" if is_active else "secondary",
                key=f"nav_{tab_key}",
            ):
                st.session_state.active_tab = tab_key
                st.rerun()

        st.divider()

        # ── Document filter ────────────────────────────────────────────────
        docs = pipeline.list_documents()
        if docs:
            all_names = [d["name"] for d in docs]
            selected  = st.multiselect(
                "Filter by document",
                options=all_names,
                default=st.session_state.selected_docs or all_names,
                key="sb_doc_filter",
            )
            st.session_state.selected_docs = selected

        st.divider()

        # ── Model selector ─────────────────────────────────────────────────
        local_models = ollama.list_models() if status["running"] else []
        if local_models:
            chosen = st.selectbox("Active model", local_models, key="sb_model_select")
            st.session_state.model = chosen
        else:
            st.caption("No models — go to **🤖 Models** tab")

        st.divider()

        # ── Debug toggle ───────────────────────────────────────────────────
        st.session_state.show_debug = st.toggle(
            "🔍 Debug context",
            value=st.session_state.get("show_debug", False),
            key="sb_debug_toggle",
        )

        # ── Footer stats ───────────────────────────────────────────────────
        st.caption(f"🗂 {len(docs)} doc(s) indexed")
        st.caption("🔴 Network: air-gapped")
