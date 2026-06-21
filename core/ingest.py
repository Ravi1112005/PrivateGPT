"""
ingest.py — Multi-document ingestion engine
Handles PDF loading, chunking, embedding, and FAISS index management.
"""

import os
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_DIR   = "faiss_index"
META_FILE   = "faiss_index/doc_metadata.json"


def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def file_hash(path: str) -> str:
    """SHA-256 of a file — used to skip re-indexing unchanged docs."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_metadata() -> Dict:
    if os.path.exists(META_FILE):
        with open(META_FILE, "r") as f:
            return json.load(f)
    return {}


def save_metadata(meta: Dict):
    os.makedirs(INDEX_DIR, exist_ok=True)
    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)


def ingest_documents(pdf_paths: List[str], progress_callback=None) -> Dict:
    """
    Ingest one or more PDF files into the shared FAISS index.
    Skips files that haven't changed (same hash as last run).
    Returns a summary dict.
    """
    embeddings = get_embeddings()
    metadata   = load_metadata()
    splitter   = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

    new_docs   = []
    skipped    = []
    ingested   = []
    errors     = []

    for i, pdf_path in enumerate(pdf_paths):
        name = Path(pdf_path).name
        if progress_callback:
            progress_callback(i, len(pdf_paths), f"Processing {name}...")

        try:
            fhash = file_hash(pdf_path)

            # Skip if already indexed with same content
            if name in metadata and metadata[name]["hash"] == fhash:
                skipped.append(name)
                continue

            loader = PyPDFLoader(pdf_path)
            pages  = loader.load()
            chunks = splitter.split_documents(pages)

            # Tag every chunk with its source filename
            for chunk in chunks:
                chunk.metadata["source_file"] = name

            new_docs.extend(chunks)
            metadata[name] = {
                "hash":        fhash,
                "pages":       len(pages),
                "chunks":      len(chunks),
                "indexed_at":  datetime.now().isoformat(),
                "path":        pdf_path,
            }
            ingested.append(name)

        except Exception as e:
            errors.append({"file": name, "error": str(e)})

    # Merge into (or create) the FAISS index
    if new_docs:
        if os.path.exists(INDEX_DIR) and os.path.exists(f"{INDEX_DIR}/index.faiss"):
            db = FAISS.load_local(INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
            db.add_documents(new_docs)
        else:
            db = FAISS.from_documents(new_docs, embeddings)
        db.save_local(INDEX_DIR)

    save_metadata(metadata)

    return {
        "ingested": ingested,
        "skipped":  skipped,
        "errors":   errors,
        "total_chunks": sum(v["chunks"] for v in metadata.values()),
        "total_docs":   len(metadata),
    }


def remove_document(filename: str) -> bool:
    """
    Remove a document from the metadata registry.
    NOTE: FAISS does not support partial deletion — full re-index is needed.
    Call rebuild_index() after removing docs.
    """
    metadata = load_metadata()
    if filename not in metadata:
        return False
    del metadata[filename]
    save_metadata(metadata)
    return True


def rebuild_index(progress_callback=None) -> Dict:
    """Re-index all tracked documents from scratch (needed after deletions)."""
    metadata = load_metadata()
    if not metadata:
        return {"ingested": [], "skipped": [], "errors": [], "total_chunks": 0, "total_docs": 0}

    # Wipe old index
    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)

    pdf_paths = [v["path"] for v in metadata.values() if os.path.exists(v["path"])]
    # Clear metadata so ingest treats everything as new
    save_metadata({})
    return ingest_documents(pdf_paths, progress_callback)


def list_documents() -> List[Dict]:
    """Return all indexed documents with their metadata."""
    meta = load_metadata()
    return [
        {
            "name":       k,
            "pages":      v.get("pages", 0),
            "chunks":     v.get("chunks", 0),
            "indexed_at": v.get("indexed_at", ""),
        }
        for k, v in meta.items()
    ]