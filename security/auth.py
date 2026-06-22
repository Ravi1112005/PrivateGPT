"""
security/auth.py — AuthManager

Local user authentication using PBKDF2-HMAC-SHA256.
No external auth services — all data stays on this machine.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class AuthManager:
    """
    Manages users, password hashing, and audit logging.

    Users are persisted as JSON in data/security/users.json.
    Audit events are appended to data/security/audit.log.
    """

    def __init__(self, security_dir: Path) -> None:
        self._security_dir = security_dir
        self._users_file   = security_dir / "users.json"
        self._audit_file   = security_dir / "audit.log"
        security_dir.mkdir(parents=True, exist_ok=True)

    # ── Bootstrap ──────────────────────────────────────────────────────────

    def setup_default_admin(self) -> None:
        """Create admin/admin123 on first run if no users exist."""
        if not self._load_users():
            self.register("admin", "admin123", role="admin")
            self._audit("SETUP", "admin", "Default admin created — change password immediately")

    # ── Authentication ─────────────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> tuple[bool, str]:
        """Verify credentials. Returns (True, role) or (False, error_msg)."""
        users = self._load_users()
        if username not in users:
            self._audit("LOGIN_FAIL", username, "user not found")
            return False, "Invalid username or password."

        u = users[username]
        if not self._verify(password, u["hash"], u["salt"]):
            self._audit("LOGIN_FAIL", username, "wrong password")
            return False, "Invalid username or password."

        u["last_login"] = datetime.now().isoformat()
        self._save_users(users)
        self._audit("LOGIN_OK", username)
        return True, u["role"]

    # ── User management ────────────────────────────────────────────────────

    def register(
        self, username: str, password: str, role: str = "user"
    ) -> tuple[bool, str]:
        if len(password) < 8:
            return False, "Password must be at least 8 characters."
        users = self._load_users()
        if username in users:
            return False, "Username already exists."
        hashed, salt = self._hash(password)
        users[username] = {
            "hash":       hashed,
            "salt":       salt,
            "role":       role,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
        }
        self._save_users(users)
        self._audit("REGISTER", username, f"role={role}")
        return True, "User created."

    def change_password(
        self, username: str, old_password: str, new_password: str
    ) -> tuple[bool, str]:
        ok, _ = self.authenticate(username, old_password)
        if not ok:
            return False, "Current password is incorrect."
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters."
        users = self._load_users()
        hashed, salt = self._hash(new_password)
        users[username]["hash"] = hashed
        users[username]["salt"] = salt
        self._save_users(users)
        self._audit("PASSWD_CHANGE", username)
        return True, "Password changed."

    def delete(self, username: str) -> tuple[bool, str]:
        users = self._load_users()
        if username not in users:
            return False, "User not found."
        admin_count = sum(1 for u in users.values() if u["role"] == "admin")
        if users[username]["role"] == "admin" and admin_count <= 1:
            return False, "Cannot delete the last admin."
        del users[username]
        self._save_users(users)
        self._audit("DELETE_USER", username)
        return True, "User deleted."

    def list_users(self) -> List[Dict]:
        return [
            {
                "username":   k,
                "role":       v["role"],
                "created_at": v["created_at"],
                "last_login": v["last_login"],
            }
            for k, v in self._load_users().items()
        ]

    def get_role(self, username: str) -> Optional[str]:
        return self._load_users().get(username, {}).get("role")

    # ── Audit log ──────────────────────────────────────────────────────────

    def read_audit_log(self, lines: int = 200) -> str:
        if not self._audit_file.exists():
            return "No audit log yet."
        with open(self._audit_file) as fh:
            all_lines = fh.readlines()
        return "".join(all_lines[-lines:])

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _hash(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        if salt is None:
            salt = secrets.token_hex(32)
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return key.hex(), salt

    @staticmethod
    def _verify(password: str, stored_hash: str, salt: str) -> bool:
        candidate, _ = AuthManager._hash(password, salt)
        return hmac.compare_digest(candidate, stored_hash)

    def _load_users(self) -> Dict:
        if self._users_file.exists():
            with open(self._users_file) as fh:
                return json.load(fh)
        return {}

    def _save_users(self, users: Dict) -> None:
        with open(self._users_file, "w") as fh:
            json.dump(users, fh, indent=2)

    def _audit(self, event: str, username: str, detail: str = "") -> None:
        with open(self._audit_file, "a") as fh:
            fh.write(
                f"{datetime.now().isoformat()} | {event:20s} | {username:20s} | {detail}\n"
            )