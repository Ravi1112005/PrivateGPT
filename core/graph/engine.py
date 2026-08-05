"""
core/graph/engine.py — RAGGraphEngine

Drop-in replacement for the legacy ``QueryEngine``.  Exposes the same
public API so ``app.py`` and ``chat.py`` require only an import swap.

Public methods:
  - ``retrieve(question, filter_files)``  →  (source_docs, context, prompt_text)
  - ``stream_answer(prompt_text, model)`` →  Generator[str]
  - ``query(question, model, filter_files)`` → dict  (full graph invocation)

The compiled LangGraph is built once in ``__init__`` and reused for every
call — no overhead beyond the first construction.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, Generator, List, Optional

import psutil

from core.graph.builder import build_rag_graph
from core.graph.nodes import _PROMPT_TEMPLATE, _format_docs

if TYPE_CHECKING:
    from config.settings import Settings
    from core.vector_store import VectorStoreManager


class RAGGraphEngine:
    """
    Orchestrates retrieval + LLM generation for RAG queries using
    a LangGraph workflow.

    Designed to be constructed once (per Streamlit session or as a
    singleton) and reused — no model loading overhead after first call.
    """

    def __init__(
        self,
        vsm: "VectorStoreManager",
        settings: "Settings",
    ) -> None:
        self._vsm = vsm
        self._settings = settings
        self._graph = build_rag_graph(vsm, settings)

    # ── Public API ─────────────────────────────────────────────────────────

    def retrieve(
        self,
        question: str,
        filter_files: Optional[List[str]] = None,
    ) -> tuple[List, str, str]:
        """
        Phase 1: Retrieve relevant chunks and build the prompt.

        This runs only the retrieval logic (not the full graph) so
        the streaming chat UI can show source chips immediately.

        Returns
        -------
        source_docs : list of LangChain Document objects
        context     : formatted context string for the LLM
        prompt_text : full prompt ready to send to the LLM
        """
        # Hybrid retrieval with neighbor expansion
        raw = self._vsm.search_with_neighbors(
            question,
            k=self._settings.rerank_candidates,
            neighbor_window=self._settings.neighbor_window,
            bm25_weight=self._settings.bm25_weight,
            faiss_weight=self._settings.faiss_weight,
        )

        if filter_files:
            fset = {f.lower() for f in filter_files}
            filtered = [
                d for d in raw
                if d.metadata.get("source_file", "").lower() in fset
            ]
            source_docs = filtered if filtered else raw
        else:
            source_docs = raw

        # Inline cross-encoder reranking (mirrors the graph rerank node)
        try:
            from core.ssl_patch import patch_ssl_for_hf  # noqa: PLC0415
            patch_ssl_for_hf()
            from sentence_transformers import CrossEncoder  # noqa: PLC0415

            if len(source_docs) > self._settings.rerank_top_n:
                model = CrossEncoder(self._settings.reranker_model)
                pairs = [(question, d.page_content) for d in source_docs]
                scores = model.predict(pairs)
                scored = sorted(
                    zip(source_docs, scores),
                    key=lambda x: x[1],
                    reverse=True,
                )
                source_docs = [d for d, _ in scored[: self._settings.rerank_top_n]]
        except Exception:  # noqa: BLE001
            # Reranker unavailable — fall back to top_k from retrieval
            source_docs = source_docs[: self._settings.top_k]

        context     = _format_docs(source_docs)
        prompt_text = _PROMPT_TEMPLATE.format(context=context, question=question)
        return source_docs, context, prompt_text


    def stream_answer(
        self,
        prompt_text: str,
        model: str,
    ) -> Generator[str, None, None]:
        """
        Phase 2: Stream answer tokens from the LLM.

        Designed for use with ``st.write_stream()``::

            answer = st.write_stream(engine.stream_answer(prompt, model))

        Yields individual string tokens as they arrive from Ollama.
        """
        from langchain_ollama import OllamaLLM  # noqa: PLC0415

        llm = OllamaLLM(
            model=model,
            temperature=self._settings.llm_temperature,
        )
        try:
            for token in llm.stream(prompt_text):
                yield str(token)
        except Exception as exc:  # noqa: BLE001
            yield f"\n\n⚠️ Generation error: {exc}"

    def query(
        self,
        question: str,
        model: str,
        filter_files: Optional[List[str]] = None,
    ) -> Dict:
        """
        Full graph invocation — collects the complete answer.

        Used for session export and non-interactive contexts.
        Returns the same dict shape as the legacy ``QueryEngine.query()``
        for full backward compatibility::

            {
                "answer":  str,
                "sources": [{file, page, snippet}, …],
                "metrics": {latency_sec, ram_delta_mb, chunks_used, model, …},
                "context": str,
            }
        """
        t0   = time.time()
        mem0 = psutil.Process().memory_info().rss / (1024 ** 2)

        initial_state = {
            "question":        question,
            "model":           model,
            "filter_files":    filter_files or [],
            "fetch_k":         self._settings.fetch_k,
            "top_k":           self._settings.top_k,
            "llm_temperature": self._settings.llm_temperature,
            "t0":              t0,
            "mem0":            mem0,
        }

        final_state = self._graph.invoke(initial_state)

        return {
            "answer":  final_state.get("answer", ""),
            "sources": final_state.get("sources", []),
            "metrics": final_state.get("metrics", {}),
            "context": final_state.get("context", ""),
        }

    # ── Convenience ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"RAGGraphEngine(vsm={self._vsm!r}, "
            f"graph_nodes={list(self._graph.get_graph().nodes)})"
        )
