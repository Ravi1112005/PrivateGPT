"""
core/graph/builder.py — LangGraph StateGraph construction

Builds and compiles the RAG workflow graph:

    __start__  →  retrieve  →  check_retrieval  ─┬─ (ok)  → generate → validate → finalize → __end__
                                                  └─ (fail) → finalize ─────────────────────→ __end__

The compiled graph is a re-entrant, thread-safe callable.  It is built
once at startup and invoked on every query via ``RAGGraphEngine``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from core.graph.nodes import (
    make_check_retrieval_node,
    make_finalize_node,
    make_generate_node,
    make_rerank_node,
    make_retrieve_node,
    make_validate_node,
)
from core.graph.state import RAGState

if TYPE_CHECKING:
    from config.settings import Settings
    from core.vector_store import VectorStoreManager


def build_rag_graph(
    vsm: "VectorStoreManager",
    settings: "Settings",
):
    """
    Construct and compile the RAG LangGraph.

    Parameters
    ----------
    vsm : VectorStoreManager
        Shared FAISS vector store (injected, not created here).
    settings : Settings
        Application settings for fetch_k, top_k, temperature, etc.

    Returns
    -------
    compiled : CompiledGraph
        A callable that accepts a ``RAGState`` dict and returns
        the final ``RAGState`` dict.
    """
    # ── Create node callables (dependencies injected via closure) ──────────
    retrieve_node        = make_retrieve_node(vsm, settings)
    rerank_node          = make_rerank_node(settings)
    check_retrieval_node = make_check_retrieval_node()
    generate_node        = make_generate_node()
    validate_node        = make_validate_node()
    finalize_node        = make_finalize_node()

    # ── Build the graph ───────────────────────────────────────────────────
    graph = StateGraph(RAGState)

    graph.add_node("retrieve",        retrieve_node)
    graph.add_node("rerank",          rerank_node)
    graph.add_node("check_retrieval", check_retrieval_node)
    graph.add_node("generate",        generate_node)
    graph.add_node("validate",        validate_node)
    graph.add_node("finalize",        finalize_node)

    # ── Wire edges ────────────────────────────────────────────────────────
    graph.set_entry_point("retrieve")

    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank",   "check_retrieval")

    # Conditional branch: skip generation if no documents were retrieved
    graph.add_conditional_edges(
        "check_retrieval",
        _route_after_check,
        {
            "generate": "generate",
            "finalize": "finalize",
        },
    )

    graph.add_edge("generate", "validate")
    graph.add_edge("validate", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# ── Routing helpers ───────────────────────────────────────────────────────

def _route_after_check(state: RAGState) -> str:
    """Route to ``generate`` if documents exist, else straight to ``finalize``."""
    if state.get("retrieval_ok", False):
        return "generate"
    return "finalize"
