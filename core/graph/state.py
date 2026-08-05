"""
core/graph/state.py — RAGState

Typed state dictionary that flows through every node in the LangGraph
RAG pipeline.  Each node reads its required keys and writes new ones;
the state accumulates data as it progresses through the graph.

Design notes:
  - ``total=False`` makes every key optional — nodes that run first don't
    need the keys that later nodes will populate.
  - All timing / diagnostic fields live here so ``finalize`` can build
    the metrics dict without re-importing ``time`` or ``psutil``.
"""

from __future__ import annotations

from typing import List, TypedDict


class RAGState(TypedDict, total=False):
    """Immutable schema for the data flowing through the RAG graph."""

    # ── Inputs (set before graph invocation) ──────────────────────────────
    question: str                 # user's natural-language query
    model: str                    # Ollama model name  (e.g. "phi3")
    filter_files: List[str]       # sidebar document selection
    fetch_k: int                  # wide candidate pool size
    top_k: int                    # final chunk count sent to LLM
    llm_temperature: float        # generation temperature

    # ── Populated by  retrieve  node ──────────────────────────────────────
    source_docs: list             # LangChain Document objects
    context: str                  # formatted context string for the prompt

    # ── Populated by  rerank  node (NEW) ──────────────────────────────────
    pre_rerank_count: int         # How many candidates before reranking
    reranked_docs: list           # Documents after cross-encoder scoring
    rerank_scores: list           # Cross-encoder scores for transparency

    # ── Populated by  check_retrieval  node ───────────────────────────────
    retrieval_ok: bool            # False → graph short-circuits to finalize

    # ── Populated by  generate  node ──────────────────────────────────────
    prompt_text: str              # full prompt sent to the LLM
    raw_answer: str               # raw text returned by the LLM

    # ── Populated by  validate  node ──────────────────────────────────────
    is_grounded: bool             # heuristic: answer references sources?
    grounding_note: str           # e.g. "Answer references 3/5 sources"

    # ── Populated by  finalize  node ──────────────────────────────────────
    answer: str                   # final answer string
    sources: List[dict]           # [{file, page, snippet}, …]
    metrics: dict                 # {latency_sec, ram_delta_mb, …}

    # ── Timing / diagnostics ──────────────────────────────────────────────
    t0: float                     # time.time() at graph start
    mem0: float                   # RSS in MB at graph start
    error: str                    # non-empty if something went wrong
