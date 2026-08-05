"""
core/graph/nodes.py — Graph node functions

Pure(-ish) functions that each receive the current ``RAGState`` and
return a partial state update dict.  They are wired together by
``builder.py`` into a LangGraph ``StateGraph``.

Node overview:
  1. retrieve        — hybrid search + neighbor expansion + file filtering
  2. rerank          — cross-encoder precision re-scoring
  3. check_retrieval — early-stop guard if no docs found
  4. generate        — build prompt, call Ollama LLM
  5. validate        — lightweight heuristic grounding check
  6. finalize        — assemble the response dict (answer, sources, metrics)

Dependencies (VectorStoreManager, Settings) are injected via the factory
functions ``make_*`` so the graph stays testable and DI-friendly.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable, List, Optional

import psutil

from core.graph.state import RAGState

if TYPE_CHECKING:
    from config.settings import Settings
    from core.vector_store import VectorStoreManager


# ── Prompt template ───────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """\
You are a knowledgeable document assistant. Answer the question using \
ONLY the context provided below.

Instructions:
1. Synthesize information from the context to give a clear, direct answer.
2. When the context contains the answer, present it confidently.
3. If only partial information is found, answer what you can and note \
   what specific details are missing.
4. Only if NONE of the context relates to the question, say: \
   "The provided documents do not cover this topic."
5. Cite source pages to support your answer, e.g. (p. 830).
6. Never fabricate information not present in the context.

Context (extracted from documents):
{context}

Question: {question}

Answer:"""


# ═══════════════════════════════════════════════════════════════════════════
# Node factory functions — return callables suitable for StateGraph.add_node
# ═══════════════════════════════════════════════════════════════════════════


def make_retrieve_node(
    vsm: "VectorStoreManager",
    settings: Optional["Settings"] = None,
) -> Callable[[RAGState], dict]:
    """
    **Node 1 — Retrieve**

    Run hybrid search with neighbor chunk expansion using the
    VectorStoreManager, then apply file filtering from the sidebar.
    Returns a larger candidate pool for the reranker to filter down.
    """

    def retrieve(state: RAGState) -> dict:
        k = state.get("fetch_k", 40)
        neighbor_window = settings.neighbor_window if settings else 1

        # Hybrid search with neighbor expansion
        raw: List = vsm.search_with_neighbors(
            state["question"],
            k=k,
            neighbor_window=neighbor_window,
            bm25_weight=0.4,
            faiss_weight=0.6,
        )

        filter_files = state.get("filter_files")
        if filter_files:
            fset = {f.lower() for f in filter_files}
            filtered = [
                d for d in raw
                if d.metadata.get("source_file", "").lower() in fset
            ]
            # Keep full candidate pool for reranker, fallback to unfiltered
            source_docs = filtered if filtered else raw
        else:
            source_docs = raw

        context = _format_docs(source_docs)
        return {"source_docs": source_docs, "context": context}

    return retrieve


def make_rerank_node(settings: "Settings") -> Callable[[RAGState], dict]:
    """
    **Node 1.5 — Rerank (cross-encoder)**

    Scores each (query, chunk) pair with a cross-encoder that uses deep
    bidirectional attention, then keeps only the top-N most relevant chunks.

    ~100-200ms on CPU for 40 candidates.  CrossEncoder is lazy-loaded on
    first call and cached in the closure to avoid repeated disk reads.
    """
    _ce_model = None  # Cached CrossEncoder instance (closure variable)

    def rerank(state: RAGState) -> dict:
        nonlocal _ce_model

        source_docs = state.get("source_docs", [])
        question = state["question"]
        top_n = settings.rerank_top_n

        if len(source_docs) <= top_n:
            # Already few enough candidates — skip reranking
            return {
                "source_docs": source_docs,
                "pre_rerank_count": len(source_docs),
                "context": _format_docs(source_docs),
            }

        try:
            from core.ssl_patch import patch_ssl_for_hf  # noqa: PLC0415
            patch_ssl_for_hf()
            from sentence_transformers import CrossEncoder  # noqa: PLC0415

            if _ce_model is None:
                _ce_model = CrossEncoder(settings.reranker_model)

            pairs = [(question, doc.page_content) for doc in source_docs]
            scores = _ce_model.predict(pairs)

            # Sort by relevance score descending, keep top_n
            scored = sorted(
                zip(source_docs, scores),
                key=lambda x: x[1],
                reverse=True,
            )
            reranked = [doc for doc, _ in scored[:top_n]]
            top_scores = [float(s) for _, s in scored[:top_n]]

            return {
                "source_docs": reranked,
                "pre_rerank_count": len(source_docs),
                "rerank_scores": top_scores,
                "context": _format_docs(reranked),
            }

        except Exception:  # noqa: BLE001
            # Reranker unavailable — pass through all candidates
            return {
                "source_docs": source_docs,
                "pre_rerank_count": len(source_docs),
                "context": _format_docs(source_docs),
            }

    return rerank


def make_check_retrieval_node() -> Callable[[RAGState], dict]:
    """
    **Node 2 — Check Retrieval**

    If no relevant documents were found, stop early by setting
    ``retrieval_ok=False``.  The conditional edge in the graph will
    route directly to ``finalize``.
    """

    def check_retrieval(state: RAGState) -> dict:
        docs = state.get("source_docs", [])
        if not docs:
            return {
                "retrieval_ok": False,
                "answer": (
                    "⚠️ No document content could be retrieved. "
                    "Please make sure documents are indexed and "
                    "selected in the sidebar."
                ),
                "raw_answer": "",
                "prompt_text": "",
            }
        return {"retrieval_ok": True}

    return check_retrieval


def make_generate_node() -> Callable[[RAGState], dict]:
    """
    **Node 3 — Generate Answer**

    Build the full prompt from the retrieved context, call Ollama via
    LangChain, and store the raw answer.
    """

    def generate(state: RAGState) -> dict:
        from langchain_ollama import OllamaLLM          # noqa: PLC0415
        from langchain_core.output_parsers import StrOutputParser  # noqa: PLC0415

        prompt_text = _PROMPT_TEMPLATE.format(
            context=state["context"],
            question=state["question"],
        )

        llm = OllamaLLM(
            model=state["model"],
            temperature=state.get("llm_temperature", 0.1),
        )

        try:
            raw_answer = StrOutputParser().parse(llm.invoke(prompt_text))
        except Exception as exc:  # noqa: BLE001
            return {
                "prompt_text": prompt_text,
                "raw_answer": "",
                "error": f"Generation error: {exc}",
            }

        return {"prompt_text": prompt_text, "raw_answer": raw_answer}

    return generate


def make_validate_node() -> Callable[[RAGState], dict]:
    """
    **Node 4 — Validate / Ground  (simple heuristic)**

    Check whether the answer text mentions keywords from the retrieved
    source documents.  This is a zero-latency heuristic — no extra LLM
    call.  It inspects:
      - source filenames mentioned in the answer
      - key phrases from chunk content appearing in the answer

    Sets ``is_grounded`` and a human-readable ``grounding_note``.
    """

    def validate(state: RAGState) -> dict:
        answer = state.get("raw_answer", "").lower()
        source_docs = state.get("source_docs", [])

        if not answer or not source_docs:
            return {
                "is_grounded": False,
                "grounding_note": "No answer or sources to validate.",
            }

        # 1) Check how many source filenames are referenced
        filenames = {
            d.metadata.get("source_file", "").lower() for d in source_docs
        }
        filenames.discard("")
        referenced = sum(1 for fn in filenames if fn.replace(".pdf", "") in answer)

        # 2) Check key-phrase overlap from chunk content
        chunks_with_overlap = 0
        for doc in source_docs:
            # Take significant phrases (5+ word sequences) from the chunk
            words = doc.page_content.split()
            phrases = [
                " ".join(words[i : i + 5]).lower()
                for i in range(0, len(words) - 4, 3)
            ]
            if any(phrase in answer for phrase in phrases[:10]):
                chunks_with_overlap += 1

        total = len(source_docs)
        score = chunks_with_overlap / total if total else 0
        is_grounded = score >= 0.2  # at least 20% chunk overlap

        note_parts = []
        if filenames:
            note_parts.append(
                f"Answer references {referenced}/{len(filenames)} source file(s)"
            )
        note_parts.append(
            f"Content overlap: {chunks_with_overlap}/{total} chunks "
            f"({score:.0%})"
        )

        return {
            "is_grounded": is_grounded,
            "grounding_note": ". ".join(note_parts) + ".",
        }

    return validate


def make_finalize_node() -> Callable[[RAGState], dict]:
    """
    **Node 5 — Finalize**

    Assemble the final response dict: answer, sources list, and metrics.
    Output shape is identical to the legacy ``QueryEngine.query()`` return.
    """

    def finalize(state: RAGState) -> dict:
        t0   = state.get("t0", 0.0)
        mem0 = state.get("mem0", 0.0)

        latency  = round(time.time() - t0, 2) if t0 else 0.0
        ram_used = round(
            psutil.Process().memory_info().rss / (1024 ** 2) - mem0, 1
        )

        source_docs = state.get("source_docs", [])
        error = state.get("error", "")

        # Determine final answer
        if error:
            answer = f"⚠️ {error}"
        elif not state.get("retrieval_ok", False):
            answer = state.get("answer", "⚠️ No documents retrieved.")
        else:
            answer = state.get("raw_answer", "")

        sources = [
            {
                "file":    d.metadata.get("source_file", "unknown"),
                "page":    d.metadata.get("page", "?"),
                "snippet": d.page_content[:150] + "…",
            }
            for d in source_docs
        ]

        metrics = {
            "latency_sec":    latency,
            "ram_delta_mb":   ram_used,
            "chunks_used":    len(source_docs),
            "model":          state.get("model", "?"),
            "is_grounded":    state.get("is_grounded"),
            "grounding_note": state.get("grounding_note", ""),
        }

        return {
            "answer":  answer,
            "sources": sources,
            "metrics": metrics,
        }

    return finalize


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════

def _format_docs(docs: list) -> str:
    """Format a list of LangChain Document objects into a context string."""
    if not docs:
        return "(No relevant content found in the selected documents.)"
    return "\n\n---\n\n".join(
        f"[Source: {d.metadata.get('source_file', 'unknown')} | "
        f"Page: {d.metadata.get('page', '?')}]\n{d.page_content}"
        for d in docs
    )
