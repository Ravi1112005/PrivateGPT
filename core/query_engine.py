"""
query_engine.py — Production RAG query engine
Supports per-query document filtering, streaming, and metrics.
"""

import time
import psutil
from typing import List, Optional, Dict, Generator

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser


EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_DIR   = "faiss_index"

SYSTEM_PROMPT = PromptTemplate(
    template="""You are a precise document assistant. Use ONLY the context below to answer.
        If the answer is not explicitly present, respond with:
        "Information not found in the selected documents."
        Never guess or use outside knowledge.

        Context:
        {context}

        Question:
        {question}

        Answer:""",
    input_variables=["context", "question"],
)


def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def load_retriever(filter_files: Optional[List[str]] = None, k: int = 4):
    """
    Load FAISS retriever.
    filter_files: if provided, only retrieve chunks from those filenames.
    """
    embeddings = get_embeddings()
    db = FAISS.load_local(INDEX_DIR, embeddings, allow_dangerous_deserialization=True)

    search_kwargs = {"k": k}
    if filter_files:
        search_kwargs["filter"] = {"source_file": {"$in": filter_files}}

    return db.as_retriever(search_type="similarity", search_kwargs=search_kwargs)


def build_chain(model: str = "phi3", filter_files: Optional[List[str]] = None):
    retriever = load_retriever(filter_files)
    llm = OllamaLLM(model=model, temperature=0.0)

    def format_docs(docs):
        return "\n\n---\n\n".join(
            f"[{doc.metadata.get('source_file','?')} | p.{doc.metadata.get('page','?')}]\n{doc.page_content}"
            for doc in docs
        )

    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | SYSTEM_PROMPT
        | llm
        | StrOutputParser()
    )
    return chain, retriever


def query(
    question: str,
    model: str = "phi3",
    filter_files: Optional[List[str]] = None,
) -> Dict:
    """
    Run a query and return answer + sources + performance metrics.
    """
    chain, retriever = build_chain(model, filter_files)

    t0   = time.time()
    mem0 = psutil.Process().memory_info().rss / (1024 ** 2)

    answer      = chain.invoke(question)
    source_docs = retriever.invoke(question)

    latency  = round(time.time() - t0, 2)
    ram_used = round(psutil.Process().memory_info().rss / (1024 ** 2) - mem0, 1)

    sources = [
        {
            "file":    doc.metadata.get("source_file", "unknown"),
            "page":    doc.metadata.get("page", "?"),
            "snippet": doc.page_content[:120] + "...",
        }
        for doc in source_docs
    ]

    return {
        "answer":  answer,
        "sources": sources,
        "metrics": {
            "latency_sec": latency,
            "ram_delta_mb": ram_used,
            "chunks_used": len(source_docs),
            "model": model,
        },
    }