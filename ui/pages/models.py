"""
ui/pages/models.py — Model Manager page
"""

from __future__ import annotations

import streamlit as st

from core.ollama_manager import RECOMMENDED_MODELS


def render_models_page(ollama) -> None:
    st.markdown("## 🤖 Model Manager")

    if not ollama.is_running():
        st.error("Ollama is not running. Start it from the sidebar first.")
        return

    local_models = ollama.list_models()

    # ── Downloaded models ──────────────────────────────────────────────────
    st.markdown("### Downloaded models")
    if not local_models:
        st.info("No models downloaded yet. Pull one below.")
    else:
        for m in local_models:
            info = ollama.get_info(m) or {}
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.markdown(f"**{m}**")
            c2.caption(info.get("parameters", ""))
            c3.caption(info.get("quantization", ""))
            if c4.button("🗑 Delete", key=f"del_model_{m}"):
                ok, msg = ollama.delete(m)
                st.success(msg) if ok else st.error(msg)
                st.rerun()

    st.divider()

    # ── Recommended models ─────────────────────────────────────────────────
    st.markdown("### Pull a recommended model")
    st.caption("⚠️ Requires internet on first pull only. Fully offline after that.")

    for rec in RECOMMENDED_MODELS:
        already = ollama.is_available(rec["name"])
        c1, c2 = st.columns([4, 1])
        with c1:
            badge = "✅ Downloaded" if already else f"📦 {rec['ram']}"
            st.markdown(f"**{rec['label']}** &nbsp; `{badge}`")
            st.caption(rec["description"])
        with c2:
            if already:
                st.caption("Ready ✅")
            elif st.button("Pull", key=f"pull_{rec['name']}", type="primary"):
                prog_text = st.empty()
                prog_bar  = st.progress(0)

                def _cb(status, pb=prog_bar, pt=prog_text):
                    pt.caption(status)
                    try:
                        pct = int(status.split("—")[-1].strip().replace("%", ""))
                        pb.progress(pct)
                    except Exception:
                        pass

                ok, msg = ollama.pull(rec["name"], stream_callback=_cb)
                prog_text.empty()
                prog_bar.empty()
                st.success(msg) if ok else st.error(msg)
                st.rerun()

    st.divider()

    # ── Custom model ───────────────────────────────────────────────────────
    st.markdown("### Pull any other model")
    c1, c2 = st.columns([3, 1])
    custom = c1.text_input("Model name", placeholder="e.g. gemma:2b", key="custom_model_input")
    if c2.button("Pull", key="pull_custom") and custom:
        status_ph = st.empty()
        ok, msg = ollama.pull(custom, stream_callback=lambda s: status_ph.caption(s))
        status_ph.empty()
        st.success(msg) if ok else st.error(msg)
        st.rerun()
