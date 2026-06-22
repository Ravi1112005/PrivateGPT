"""
ui/pages/chat.py — Chat page

Key feature: STREAMING via st.write_stream()
  - Phase 1 (retrieval): ~0.5s → source chips appear immediately
  - Phase 2 (generation): tokens stream live → no more 70s blank wait
"""

from __future__ import annotations

import time

import streamlit as st

from core.query_engine import QueryEngine
from core.ollama_manager import OllamaManager


def render_chat_page(
    engine: QueryEngine,
    session_mgr,
    ollama: OllamaManager,
    pipeline,
) -> None:
    st.markdown("## 💬 Chat with your documents")

    # ── Pre-flight checks ──────────────────────────────────────────────────
    if not ollama.is_running():
        st.error("Ollama is not running. Click **▶ Start Ollama** in the sidebar.")
        return
    if not ollama.list_models():
        st.warning("No models downloaded. Go to the **🤖 Models** tab to pull one.")
        return
    if not pipeline.list_documents():
        st.info("No documents indexed. Go to **📄 Documents** to upload PDFs.")
        return
    if not st.session_state.selected_docs:
        st.warning("No documents selected. Pick at least one in the sidebar filter.")
        return

    # ── New chat button ────────────────────────────────────────────────────
    col_title, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("＋ New chat", key="chat_new"):
            sess = session_mgr.create(st.session_state.username)
            st.session_state.session_id = sess["id"]
            st.session_state.messages   = []
            st.rerun()

    # ── Render conversation history ────────────────────────────────────────
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="user-bubble">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="ai-bubble">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
            _render_sources(msg.get("metadata", {}).get("sources", []))
            _render_metrics(msg.get("metadata", {}).get("metrics", {}))
            if st.session_state.get("show_debug"):
                ctx = msg.get("metadata", {}).get("context", "")
                if ctx:
                    with st.expander("🔍 Context sent to LLM", expanded=False):
                        st.code(ctx, language=None)

    # ── Chat input ─────────────────────────────────────────────────────────
    if question := st.chat_input("Ask anything about your documents…"):
        st.session_state.messages.append({"role": "user", "content": question})
        session_mgr.add_message(st.session_state.session_id, "user", question)

        model        = st.session_state.get("model", "phi3")
        filter_files = st.session_state.selected_docs

        # ── Phase 1: Retrieval (cached — fast) ────────────────────────────
        t0 = time.time()
        source_docs, context, prompt_text = engine.retrieve(question, filter_files)
        retrieval_sec = round(time.time() - t0, 2)

        if not source_docs:
            answer = (
                "⚠️ No document content retrieved. "
                "Make sure documents are indexed and selected."
            )
            sources, metrics = [], {}
        else:
            # Show source chips immediately — before generation starts
            st.markdown("**Retrieved sources:**")
            _render_sources([
                {
                    "file": d.metadata.get("source_file", "?"),
                    "page": d.metadata.get("page", "?"),
                    "snippet": d.page_content[:80] + "…",
                }
                for d in source_docs
            ])

            # ── Phase 2: Streaming generation ─────────────────────────────
            st.markdown("**Generating answer…**")
            answer_placeholder = st.empty()
            full_answer        = ""

            try:
                for token in engine.stream_answer(prompt_text, model):
                    full_answer += token
                    # Live streaming with blinking cursor
                    answer_placeholder.markdown(
                        f'<div class="ai-bubble">{full_answer}▌</div>',
                        unsafe_allow_html=True,
                    )
                # Final render without cursor
                answer_placeholder.markdown(
                    f'<div class="ai-bubble">{full_answer}</div>',
                    unsafe_allow_html=True,
                )
                answer = full_answer
            except Exception as exc:
                answer = f"❌ Generation error: {exc}"
                answer_placeholder.error(answer)

            total_sec = round(time.time() - t0, 2)
            sources   = [
                {
                    "file":    d.metadata.get("source_file", "unknown"),
                    "page":    d.metadata.get("page", "?"),
                    "snippet": d.page_content[:150] + "…",
                }
                for d in source_docs
            ]
            metrics = {
                "latency_sec":  total_sec,
                "retrieval_sec": retrieval_sec,
                "ram_delta_mb": 0,
                "chunks_used":  len(source_docs),
                "model":        model,
            }

        meta = {"sources": sources, "metrics": metrics, "context": context}
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "metadata": meta}
        )
        session_mgr.add_message(st.session_state.session_id, "assistant", answer, meta)
        st.rerun()


# ── Helpers ────────────────────────────────────────────────────────────────

def _render_sources(sources: list) -> None:
    if not sources:
        return
    chips = "".join(
        f'<span class="source-chip">📄 {s["file"]} p.{s["page"]}</span>'
        for s in sources
    )
    st.markdown(chips, unsafe_allow_html=True)


def _render_metrics(metrics: dict) -> None:
    if not metrics:
        return
    retrieval = metrics.get("retrieval_sec")
    retrieval_str = f" | 🔎 retrieval {retrieval}s" if retrieval else ""
    st.markdown(
        f'<div class="metric-row">'
        f'⏱ {metrics.get("latency_sec","?")}s total'
        f'{retrieval_str}'
        f' &nbsp;|&nbsp; 🔍 {metrics.get("chunks_used","?")} chunks'
        f' &nbsp;|&nbsp; 🤖 {metrics.get("model","?")}'
        f'</div>',
        unsafe_allow_html=True,
    )
