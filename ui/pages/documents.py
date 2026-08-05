"""
ui/pages/documents.py — Document Manager page
"""

from __future__ import annotations

import os
import tempfile

import streamlit as st


def render_documents_page(pipeline, settings) -> None:
    st.markdown("## 📄 Document Manager")

    # ── Backend migration notice ───────────────────────────────────────────
    import json
    state_path = settings.index_state_path
    if state_path.exists():
        with open(state_path) as fh:
            state = json.load(fh)
        if state.get("embedding_backend") and state["embedding_backend"] != pipeline.EMBEDDING_BACKEND:
            st.markdown(
                '<div class="warning-banner">⚠️ <strong>Index migration required.</strong> '
                "The embedding model was upgraded. Click <strong>Rebuild full index</strong> "
                "below to re-embed all documents with the new model.</div>",
                unsafe_allow_html=True,
            )

    # ── Upload section ─────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "Upload PDF files",
        type="pdf",
        accept_multiple_files=True,
        key="doc_uploader",
    )
    if uploaded and st.button("Index documents", type="primary", key="doc_index_btn"):
        tmp_paths = []
        for f in uploaded:
            dest = os.path.join(tempfile.gettempdir(), f.name)
            with open(dest, "wb") as out:
                out.write(f.read())
            tmp_paths.append(dest)

        progress = st.progress(0, text="Starting…")

        def cb(i, total, msg, _p=progress):
            _p.progress(int((i / max(total, 1)) * 100), text=msg)

        try:
            result = pipeline.ingest(tmp_paths, progress_callback=cb)
        except Exception as exc:
            progress.empty()
            st.error(str(exc))
            for p in tmp_paths:
                try: os.unlink(p)
                except: pass  # noqa: E722
            return
        finally:
            progress.empty()
            for p in tmp_paths:
                try: os.unlink(p)
                except: pass  # noqa: E722

        if result["ingested"]:
            st.success(f"✅ Indexed: {', '.join(result['ingested'])}")

            # Store enricher in session_state so it persists across reruns
            if pipeline.enricher is not None:
                st.session_state["_enricher"] = pipeline.enricher

            if settings.contextual_enrichment:
                st.info(
                    "⚡ Deep indexing started in background. "
                    "You can start chatting — quality will improve automatically."
                )
        if result["skipped"]:
            st.info(f"⏭ Skipped (unchanged): {', '.join(result['skipped'])}")
        for err in result["errors"]:
            st.error(f"{err['file']}: {err['error']}")
        if result["ingested"]:
            st.info(f"📊 Total: {result['total_chunks']} chunks across {result['total_docs']} doc(s)")
        st.rerun()


    # ── Document list ──────────────────────────────────────────────────────
    st.markdown("### Indexed documents")
    docs = pipeline.list_documents()

    if not docs:
        st.info("No documents indexed yet.")
        return

    for doc in docs:
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        c1.markdown(f"**{doc['name']}**")
        c2.caption(f"{doc['pages']}p")
        c3.caption(f"{doc['chunks']} chunks")
        if c4.button("🗑", key=f"del_doc_{doc['name']}"):
            pipeline.remove(doc["name"])
            st.warning(f"Removed **{doc['name']}**. Click **Rebuild** to update the index.")
            st.rerun()

    st.divider()
    if st.button("🔄 Rebuild full index", key="doc_rebuild_btn"):
        with st.spinner("Re-embedding all documents… this may take a few minutes."):
            result = pipeline.rebuild()

        # Store enricher after rebuild too
        if pipeline.enricher is not None:
            st.session_state["_enricher"] = pipeline.enricher

        st.success(f"✅ Done — {result['total_chunks']} chunks across {result['total_docs']} docs")
        st.rerun()
