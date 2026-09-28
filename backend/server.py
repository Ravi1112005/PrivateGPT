"""
backend/server.py — FastAPI backend for PrivateGPT Electron app

Architecture:
  - Singletons (embeddings, vector store, session manager) are initialized
    once at startup and kept in RAM — no reloading per request.
  - Business logic lives in core/ (unchanged from Streamlit version).
  - SSE streaming for real-time token delivery to the frontend.
  - All state lives on the backend — the frontend is purely a renderer.

Run: uvicorn backend.server:app --port 8765 --reload
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Add project root to path so core/ imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from core.embeddings import EmbeddingsManager
from core.vector_store import VectorStoreManager
from core.ingestion import IngestionPipeline
from core.graph import RAGGraphEngine
from core.ollama_manager import OllamaManager, RECOMMENDED_MODELS
from sessions.manager import SessionManager


# ══════════════════════════════════════════════════════════════════════════
# FastAPI app
# ══════════════════════════════════════════════════════════════════════════

app = FastAPI(title="PrivateGPT Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════
# Singletons — loaded once at startup, kept in RAM
# ══════════════════════════════════════════════════════════════════════════

print("[*] Loading embedding model...")
model_to_load = str(settings.embedding_model_path) if (settings.embedding_model_path / "config.json").exists() else settings.embedding_model
embeddings = EmbeddingsManager(model_to_load)
embeddings.preload()
print("[OK] Embedding model loaded")

vsm = VectorStoreManager(settings.index_dir, embeddings)
ollama = OllamaManager()
session_mgr = SessionManager(settings.sessions_dir)
pipeline = IngestionPipeline(settings, embeddings, vsm)
engine = RAGGraphEngine(vsm, settings)

USERNAME = getpass.getuser()


# ══════════════════════════════════════════════════════════════════════════
# Request / Response models
# ══════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    question: str
    model: str = "phi3"
    session_id: str
    filter_files: List[str] = []

class SessionCreateRequest(BaseModel):
    label: Optional[str] = None

class SessionRenameRequest(BaseModel):
    new_label: str

class ModelPullRequest(BaseModel):
    name: str


# ══════════════════════════════════════════════════════════════════════════
# Ollama endpoints
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/ollama/status")
def ollama_status():
    return ollama.get_status()

@app.post("/api/ollama/start")
def ollama_start():
    ok, msg = ollama.start()
    return {"ok": ok, "message": msg}

@app.get("/api/ollama/models")
def ollama_models():
    models = ollama.list_models()
    details = []
    for m in models:
        info = ollama.get_info(m) or {}
        details.append({
            "name": m,
            "parameters": info.get("parameters", "unknown"),
            "quantization": info.get("quantization", "unknown"),
            "family": info.get("family", "unknown"),
        })
    return {"models": details}

@app.get("/api/ollama/recommended")
def ollama_recommended():
    local = ollama.list_models()
    result = []
    for rec in RECOMMENDED_MODELS:
        available = any(m == rec["name"] or m.startswith(rec["name"] + ":") for m in local)
        result.append({**rec, "available": available})
    return {"models": result}

@app.post("/api/ollama/pull")
def ollama_pull(req: ModelPullRequest):
    """Pull a model with streaming progress via SSE."""
    def generate():
        def callback(status: str):
            data = json.dumps({"status": status})
            yield f"data: {data}\n\n"
        
        ok, msg = ollama.pull(req.name, stream_callback=lambda s: None)
        yield f"data: {json.dumps({'done': True, 'ok': ok, 'message': msg})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/ollama/pull/sync")
def ollama_pull_sync(req: ModelPullRequest):
    ok, msg = ollama.pull(req.name)
    return {"ok": ok, "message": msg}

@app.delete("/api/ollama/models/{model_name:path}")
def ollama_delete(model_name: str):
    ok, msg = ollama.delete(model_name)
    return {"ok": ok, "message": msg}


# ══════════════════════════════════════════════════════════════════════════
# Document endpoints
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/documents")
def list_documents():
    return {"documents": pipeline.list_documents()}

@app.post("/api/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    tmp_paths = []
    try:
        for f in files:
            dest = os.path.join(tempfile.gettempdir(), f.filename)
            with open(dest, "wb") as out:
                content = await f.read()
                out.write(content)
            tmp_paths.append(dest)

        result = pipeline.ingest(tmp_paths)
        return result
    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    ok = pipeline.remove(filename)
    if not ok:
        raise HTTPException(404, f"Document '{filename}' not found")
    return {"ok": True, "message": f"Removed '{filename}'"}

@app.post("/api/documents/rebuild")
def rebuild_index():
    result = pipeline.rebuild()
    return result


# ══════════════════════════════════════════════════════════════════════════
# Chat endpoints
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/chat")
def chat(req: ChatRequest):
    """Non-streaming full query."""
    result = engine.query(req.question, req.model, req.filter_files or None)
    
    # Persist to session
    session_mgr.add_message(req.session_id, "user", req.question)
    session_mgr.add_message(req.session_id, "assistant", result["answer"], {
        "sources": result["sources"],
        "metrics": result["metrics"],
        "context": result["context"],
    })
    
    return result

@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """Streaming chat with SSE — sends retrieval results first, then tokens."""
    def generate():
        t0 = time.time()
        
        # Phase 1: Retrieval
        source_docs, context, prompt_text = engine.retrieve(
            req.question, req.filter_files or None
        )
        retrieval_sec = round(time.time() - t0, 2)
        
        sources = [
            {
                "file": d.metadata.get("source_file", "?"),
                "page": d.metadata.get("page", "?"),
                "snippet": d.page_content[:80] + "…",
            }
            for d in source_docs
        ]
        
        # Send retrieval results
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources, 'retrieval_sec': retrieval_sec})}\n\n"
        
        if not source_docs:
            answer = "⚠️ No document content retrieved. Make sure documents are indexed and selected."
            yield f"data: {json.dumps({'type': 'token', 'token': answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'metrics': {'latency_sec': round(time.time() - t0, 2), 'retrieval_sec': retrieval_sec, 'chunks_used': 0, 'model': req.model}})}\n\n"
            return
        
        # Phase 2: Streaming generation
        full_answer = ""
        try:
            for token in engine.stream_answer(prompt_text, req.model):
                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
        except Exception as exc:
            error_msg = f"\n\n⚠️ Generation error: {exc}"
            full_answer += error_msg
            yield f"data: {json.dumps({'type': 'token', 'token': error_msg})}\n\n"
        
        total_sec = round(time.time() - t0, 2)
        metrics = {
            "latency_sec": total_sec,
            "retrieval_sec": retrieval_sec,
            "chunks_used": len(source_docs),
            "model": req.model,
        }
        
        # Persist to session
        session_mgr.add_message(req.session_id, "user", req.question)
        full_sources = [
            {
                "file": d.metadata.get("source_file", "unknown"),
                "page": d.metadata.get("page", "?"),
                "snippet": d.page_content[:150] + "…",
            }
            for d in source_docs
        ]
        session_mgr.add_message(req.session_id, "assistant", full_answer, {
            "sources": full_sources,
            "metrics": metrics,
            "context": context,
        })
        
        yield f"data: {json.dumps({'type': 'done', 'metrics': metrics})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


# ══════════════════════════════════════════════════════════════════════════
# Session endpoints
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/sessions")
def list_sessions():
    sessions = session_mgr.list_for_user(USERNAME)
    return {"sessions": sessions, "username": USERNAME}

@app.post("/api/sessions")
def create_session(req: SessionCreateRequest = None):
    label = req.label if req else None
    sess = session_mgr.create(USERNAME, label)
    return sess

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    sess = session_mgr.load(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    return sess

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    ok = session_mgr.delete(session_id)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"ok": True}

@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, req: SessionRenameRequest):
    session_mgr.rename(session_id, req.new_label)
    return {"ok": True}

@app.get("/api/sessions/{session_id}/export")
def export_session(session_id: str):
    txt = session_mgr.export_txt(session_id)
    if not txt:
        raise HTTPException(404, "Session not found")
    return {"text": txt}


# ══════════════════════════════════════════════════════════════════════════
# App info
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/info")
def app_info():
    return {
        "version": "2.0.0",
        "username": USERNAME,
        "embedding_model": settings.embedding_model,
        "default_model": settings.default_model,
        "index_exists": settings.index_exists(),
        "documents_count": len(pipeline.list_documents()),
    }
