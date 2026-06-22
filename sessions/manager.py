"""
sessions/manager.py — SessionManager

Persists per-user chat sessions as JSON files in data/sessions/.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class SessionManager:
    """
    Manages the lifecycle of chat sessions.

    Each session is a single JSON file named <session_id>.json stored
    in data/sessions/.
    """

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        sessions_dir.mkdir(parents=True, exist_ok=True)

    # ── CRUD ───────────────────────────────────────────────────────────────

    def create(self, username: str, label: Optional[str] = None) -> Dict:
        session = {
            "id":         str(uuid.uuid4())[:8],
            "username":   username,
            "label":      label or f"Chat {datetime.now().strftime('%b %d %H:%M')}",
            "created_at": datetime.now().isoformat(),
            "messages":   [],
        }
        self._save(session)
        return session

    def load(self, session_id: str) -> Optional[Dict]:
        path = self._path(session_id)
        if not path.exists():
            return None
        with open(path) as fh:
            return json.load(fh)

    def list_for_user(self, username: str) -> List[Dict]:
        sessions = []
        for fpath in sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            with open(fpath) as fh:
                s = json.load(fh)
            if s.get("username") == username:
                sessions.append({
                    "id":         s["id"],
                    "label":      s["label"],
                    "created_at": s["created_at"],
                    "msg_count":  len(s.get("messages", [])),
                })
        return sessions

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        session = self.load(session_id)
        if not session:
            return
        session["messages"].append({
            "role":      role,
            "content":   content,
            "timestamp": datetime.now().isoformat(),
            "metadata":  metadata or {},
        })
        self._save(session)

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def rename(self, session_id: str, new_label: str) -> None:
        session = self.load(session_id)
        if session:
            session["label"] = new_label
            self._save(session)

    def export_txt(self, session_id: str) -> str:
        session = self.load(session_id)
        if not session:
            return ""
        lines = [
            f"Session: {session['label']}",
            f"Date: {session['created_at']}",
            "=" * 50,
            "",
        ]
        for msg in session.get("messages", []):
            role = "You" if msg["role"] == "user" else "AI"
            lines.append(f"[{role}] {msg['content']}")
            if msg["role"] == "assistant":
                for src in msg.get("metadata", {}).get("sources", []):
                    lines.append(f"  Source: {src['file']} p.{src['page']}")
            lines.append("")
        return "\n".join(lines)

    # ── Internal ───────────────────────────────────────────────────────────

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _save(self, session: Dict) -> None:
        with open(self._path(session["id"]), "w") as fh:
            json.dump(session, fh, indent=2)