"""
sessions/manager.py — Chat session persistence
Saves and loads per-user conversation history as JSON files.
"""

import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


SESSIONS_DIR = "sessions_data"


def _session_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def create_session(username: str, label: Optional[str] = None) -> Dict:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    session = {
        "id":         str(uuid.uuid4())[:8],
        "username":   username,
        "label":      label or f"Chat {datetime.now().strftime('%b %d %H:%M')}",
        "created_at": datetime.now().isoformat(),
        "messages":   [],
    }
    _save_session(session)
    return session


def _save_session(session: Dict):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(_session_path(session["id"]), "w") as f:
        json.dump(session, f, indent=2)


def load_session(session_id: str) -> Optional[Dict]:
    path = _session_path(session_id)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def list_sessions(username: str) -> List[Dict]:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    sessions = []
    for fname in sorted(Path(SESSIONS_DIR).glob("*.json"), key=os.path.getmtime, reverse=True):
        with open(fname) as f:
            s = json.load(f)
        if s.get("username") == username:
            sessions.append({
                "id":         s["id"],
                "label":      s["label"],
                "created_at": s["created_at"],
                "msg_count":  len(s.get("messages", [])),
            })
    return sessions


def add_message(session_id: str, role: str, content: str, metadata: Optional[Dict] = None):
    session = load_session(session_id)
    if not session:
        return
    session["messages"].append({
        "role":      role,
        "content":   content,
        "timestamp": datetime.now().isoformat(),
        "metadata":  metadata or {},
    })
    _save_session(session)


def delete_session(session_id: str) -> bool:
    path = _session_path(session_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def rename_session(session_id: str, new_label: str):
    session = load_session(session_id)
    if session:
        session["label"] = new_label
        _save_session(session)


def export_session_txt(session_id: str) -> str:
    """Export a session as plain text for download."""
    session = load_session(session_id)
    if not session:
        return ""
    lines = [f"Session: {session['label']}", f"Date: {session['created_at']}", "=" * 50, ""]
    for msg in session.get("messages", []):
        role = "You" if msg["role"] == "user" else "AI"
        lines.append(f"[{role}] {msg['content']}")
        if msg["role"] == "assistant" and msg.get("metadata", {}).get("sources"):
            for src in msg["metadata"]["sources"]:
                lines.append(f"  Source: {src['file']} p.{src['page']}")
        lines.append("")
    return "\n".join(lines)