"""
security/auth.py — Local user authentication
Stores bcrypt-hashed passwords in a local JSON file.
No external auth services — fully air-gapped.
"""

import os
import json
import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Optional, Dict


USERS_FILE  = "security/users.json"
AUDIT_FILE  = "security/audit.log"


# ── Helpers ────────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """PBKDF2-HMAC-SHA256 password hashing (no bcrypt dependency needed)."""
    if salt is None:
        salt = secrets.token_hex(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return key.hex(), salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    candidate, _ = _hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)


def _load_users() -> Dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_users(users: Dict):
    os.makedirs("security", exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _audit(event: str, username: str, detail: str = ""):
    os.makedirs("security", exist_ok=True)
    with open(AUDIT_FILE, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {event:20s} | {username:20s} | {detail}\n")


# ── Public API ─────────────────────────────────────────────────────────────

def setup_default_admin():
    """Create admin/admin123 on first run if no users exist."""
    users = _load_users()
    if not users:
        register_user("admin", "admin123", role="admin")
        _audit("SETUP", "admin", "Default admin created — change password immediately")


def register_user(username: str, password: str, role: str = "user") -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    users = _load_users()
    if username in users:
        return False, "Username already exists."
    hashed, salt = _hash_password(password)
    users[username] = {
        "hash":       hashed,
        "salt":       salt,
        "role":       role,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
    }
    _save_users(users)
    _audit("REGISTER", username, f"role={role}")
    return True, "User created."


def authenticate(username: str, password: str) -> tuple[bool, str]:
    users = _load_users()
    if username not in users:
        _audit("LOGIN_FAIL", username, "user not found")
        return False, "Invalid username or password."
    u = users[username]
    if not _verify_password(password, u["hash"], u["salt"]):
        _audit("LOGIN_FAIL", username, "wrong password")
        return False, "Invalid username or password."
    # Update last login
    u["last_login"] = datetime.now().isoformat()
    _save_users(users)
    _audit("LOGIN_OK", username)
    return True, u["role"]


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    ok, _ = authenticate(username, old_password)
    if not ok:
        return False, "Current password is incorrect."
    if len(new_password) < 8:
        return False, "New password must be at least 8 characters."
    users = _load_users()
    hashed, salt = _hash_password(new_password)
    users[username]["hash"] = hashed
    users[username]["salt"] = salt
    _save_users(users)
    _audit("PASSWD_CHANGE", username)
    return True, "Password changed."


def get_role(username: str) -> Optional[str]:
    users = _load_users()
    return users.get(username, {}).get("role")


def list_users() -> list:
    users = _load_users()
    return [
        {
            "username":   k,
            "role":       v["role"],
            "created_at": v["created_at"],
            "last_login": v["last_login"],
        }
        for k, v in users.items()
    ]


def delete_user(username: str) -> tuple[bool, str]:
    users = _load_users()
    if username not in users:
        return False, "User not found."
    if users[username]["role"] == "admin" and sum(1 for u in users.values() if u["role"] == "admin") <= 1:
        return False, "Cannot delete the last admin."
    del users[username]
    _save_users(users)
    _audit("DELETE_USER", username)
    return True, "User deleted."


def read_audit_log(lines: int = 100) -> str:
    if not os.path.exists(AUDIT_FILE):
        return "No audit log yet."
    with open(AUDIT_FILE, "r") as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])