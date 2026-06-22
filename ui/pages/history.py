"""
ui/pages/history.py — Chat History page
"""

from __future__ import annotations

import streamlit as st


def render_history_page(session_mgr) -> None:
    st.markdown("## 🕘 Chat History")

    sessions = session_mgr.list_for_user(st.session_state.username)
    if not sessions:
        st.info("No saved chats yet.")
        return

    for s in sessions:
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        c1.markdown(
            f"**{s['label']}**  \n"
            f"<small>{s['created_at'][:16]} · {s['msg_count']} msgs</small>",
            unsafe_allow_html=True,
        )
        if c2.button("Load", key=f"load_{s['id']}"):
            sess_data = session_mgr.load(s["id"])
            st.session_state.session_id = s["id"]
            st.session_state.messages   = sess_data.get("messages", []) if sess_data else []
            st.session_state.active_tab = "chat"
            st.rerun()
        c3.download_button(
            "Export",
            data=session_mgr.export_txt(s["id"]),
            file_name=f"chat_{s['id']}.txt",
            mime="text/plain",
            key=f"exp_{s['id']}",
        )
        if c4.button("🗑", key=f"del_sess_{s['id']}"):
            session_mgr.delete(s["id"])
            st.rerun()
