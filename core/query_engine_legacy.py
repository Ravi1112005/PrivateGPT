"""
core/query_engine.py — QueryEngine

Two-phase RAG with streaming output:

  Phase 1 — Retrieval (~0.5s with cached VectorStoreManager):
    Fetch fetch_k chunks → Python post-filter by source_file → keep top_k.

  Phase 2 — Generation (streaming):
    Build prompt → stream tokens from Ollama → yield to st.write_stream.

Performance impact vs original:
  Retrieval: 14s → ~0.5s  (no model/index load on every call)
  Perception: 70s wait → answer starts appearing in ~2-3s (streaming)
"""

from __future__ import annotations

import time
import psutil
from typing import TYPE_CHECKING, Dict, Generator, List, Optional

if TYPE_CHECKING:
    from config.settings import Settings
    from core.embeddings import EmbeddingsManager
    from core.vector_store import VectorStoreManager


_PROMPT_TEMPLATE = """\
You are a precise document assistant. Answer the question using ONLY the \
context provided below.

Rules:
- If the answer is clearly present, answer it directly and concisely.
- If partial information is available, share what you know and note what is missing.
- If the context is completely unrelated to the question, say:
  "The selected documents do not appear to contain information about this topic."
- Do NOT use knowledge outside the provided context.
- Do NOT make up facts, numbers, or names.

Context (extracted from documents):
{context}

Question: {question}

Answer:"""


class QueryEngine:
    """
    Orchestrates retrieval + LLM generation for a single RAG query.

    Designed to be constructed once (per Streamlit session or as a singleton)
    and reused for every question — no model loading overhead after first call.
    """

    def __init__(
        self,
        vsm: "VectorStoreManager",
        settings: "Settings",
    ) -> None:
        self._vsm = vsm
        self._settings = settings

    # ── Public API ─────────────────────────────────────────────────────────

    def retrieve(
        self,
        question: str,
        filter_files: Optional[List[str]] = None,
    ) -> tuple[List, str, str]:
        """
        Phase 1: Retrieve relevant chunks and build the prompt.

        Returns:
            source_docs : list of LangChain Document objects
            context     : formatted context string for the LLM
            prompt_text : full prompt ready to send to the LLM
        """
        # Wide-net search then Python post-filter (FAISS $in is unsupported)
        raw = self._vsm.search(question, k=self._settings.fetch_k)

        if filter_files:
            fset = {f.lower() for f in filter_files}
            filtered = [d for d in raw if d.metadata.get("source_file", "").lower() in fset]
            source_docs = filtered[:self._settings.top_k] if filtered else raw[:self._settings.top_k]
        else:
            source_docs = raw[:self._settings.top_k]

        context    = self._format_docs(source_docs)
        prompt_text = _PROMPT_TEMPLATE.format(context=context, question=question)
        return source_docs, context, prompt_text

    def stream_answer(
        self,
        prompt_text: str,
        model: str,
    ) -> Generator[str, None, None]:
        """
        Phase 2: Stream answer tokens from the LLM.

        Designed for use with st.write_stream():
            answer = st.write_stream(engine.stream_answer(prompt, model))

        Yields individual string tokens as they arrive from Ollama.
        """
        from langchain_ollama import OllamaLLM  # noqa: PLC0415

        llm = OllamaLLM(model=model, temperature=self._settings.llm_temperature)
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
        Blocking (non-streaming) query — collects the full answer.

        Used for session export and non-interactive contexts.
        Returns the same dict shape as before for full backward compatibility.
        """
        t0   = time.time()
        mem0 = psutil.Process().memory_info().rss / (1024 ** 2)

        source_docs, context, prompt_text = self.retrieve(question, filter_files)

        if not source_docs:
            return self._empty_result(t0, mem0, model, context)

        from langchain_ollama import OllamaLLM          # noqa: PLC0415
        from langchain_core.output_parsers import StrOutputParser  # noqa

        llm    = OllamaLLM(model=model, temperature=self._settings.llm_temperature)
        answer = StrOutputParser().parse(llm.invoke(prompt_text))

        return self._build_result(answer, source_docs, context, model, t0, mem0)

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _format_docs(docs: List) -> str:
        if not docs:
            return "(No relevant content found in the selected documents.)"
        return "\n\n---\n\n".join(
            f"[Source: {d.metadata.get('source_file', 'unknown')} | "
            f"Page: {d.metadata.get('page', '?')}]\n{d.page_content}"
            for d in docs
        )

    @staticmethod
    def _build_result(answer, source_docs, context, model, t0, mem0) -> Dict:
        latency  = round(time.time() - t0, 2)
        ram_used = round(psutil.Process().memory_info().rss / (1024 ** 2) - mem0, 1)
        sources  = [
            {
                "file":    d.metadata.get("source_file", "unknown"),
                "page":    d.metadata.get("page", "?"),
                "snippet": d.page_content[:150] + "…",
            }
            for d in source_docs
        ]
        return {
            "answer":  answer,
            "sources": sources,
            "metrics": {
                "latency_sec":  latency,
                "ram_delta_mb": ram_used,
                "chunks_used":  len(source_docs),
                "model":        model,
            },
            "context": context,
        }

    @staticmethod
    def _empty_result(t0, mem0, model, context) -> Dict:
        latency  = round(time.time() - t0, 2)
        ram_used = round(psutil.Process().memory_info().rss / (1024 ** 2) - mem0, 1)
        return {
            "answer": (
                "⚠️ No document content could be retrieved. "
                "Please make sure documents are indexed and selected in the sidebar."
            ),
            "sources": [],
            "metrics": {
                "latency_sec":  latency,
                "ram_delta_mb": ram_used,
                "chunks_used":  0,
                "model":        model,
            },
            "context": context,
        }