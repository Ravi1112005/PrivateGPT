"""
ui/pages/admin.py — Admin pages: User Management + Audit Log
"""

from __future__ import annotations

import streamlit as st


def render_users_page(auth_mgr) -> None:
    st.markdown("## 👤 User Management")

    # ── Create user ────────────────────────────────────────────────────────
    st.markdown("### Create new user")
    c1, c2, c3 = st.columns(3)
    nu = c1.text_input("Username",           key="admin_new_user")
    np = c2.text_input("Password",           key="admin_new_pass", type="password")
    nr = c3.selectbox("Role", ["user", "admin"], key="admin_new_role")
    if st.button("Create user", key="admin_create_btn"):
        ok, msg = auth_mgr.register(nu, np, nr)
        st.success(msg) if ok else st.error(msg)

    st.divider()
    st.markdown("### All users")
    for u in auth_mgr.list_users():
        c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
        c1.markdown(f"**{u['username']}**")
        c2.caption(u["role"])
        c3.caption(f"Last login: {(u['last_login'] or 'Never')[:16]}")
        if u["username"] != st.session_state.username:
            if c4.button("Delete", key=f"del_user_{u['username']}"):
                ok, msg = auth_mgr.delete(u["username"])
                st.success(msg) if ok else st.error(msg)
                st.rerun()

    st.divider()
    st.markdown("### Change my password")
    op  = st.text_input("Current password", type="password", key="admin_old_pass")
    np2 = st.text_input("New password",     type="password", key="admin_new_pass2")
    if st.button("Update password", key="admin_update_pass_btn"):
        ok, msg = auth_mgr.change_password(st.session_state.username, op, np2)
        st.success(msg) if ok else st.error(msg)


def render_audit_page(auth_mgr) -> None:
    st.markdown("## 📋 Audit Log")
    log = auth_mgr.read_audit_log(200)
    st.code(log, language=None)
    st.download_button(
        "Download",
        data=log,
        file_name="audit.log",
        mime="text/plain",
        key="audit_download_btn",
    )
