"""
core/ollama_manager.py — OllamaManager

Manages the Ollama server lifecycle and model inventory.
Fully local — no internet required once models are downloaded.
"""

from __future__ import annotations

import platform
import subprocess
import time
from typing import Callable, List, Optional

import requests


OLLAMA_BASE_URL = "http://localhost:11434"

RECOMMENDED_MODELS = [
    {
        "name":        "phi3:3.8b",
        "label":       "Phi-3 Mini (3.8B)",
        "ram":         "~2.2 GB",
        "description": "Best for 8 GB RAM laptops. Fast, good quality.",
        "recommended": True,
    },
    {
        "name":        "llama3:8b",
        "label":       "Llama 3 (8B)",
        "ram":         "~4.7 GB",
        "description": "Higher quality answers. Needs 16 GB RAM.",
        "recommended": False,
    },
    {
        "name":        "mistral:7b",
        "label":       "Mistral (7B)",
        "ram":         "~4.1 GB",
        "description": "Good balance of speed and quality.",
        "recommended": False,
    },
    {
        "name":        "tinyllama:1.1b",
        "label":       "TinyLlama (1.1B)",
        "ram":         "~0.6 GB",
        "description": "Extremely fast. Best choice for low-RAM machines.",
        "recommended": False,
    },
]


class OllamaManager:
    """
    Stateless helper for interacting with the local Ollama server.

    All methods are safe to call when Ollama is not running —
    they return (False, error_message) rather than raising.
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL) -> None:
        self.base_url = base_url

    # ── Status ─────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Ping Ollama's health endpoint."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def get_status(self) -> dict:
        """Return a full status dict for the UI status bar."""
        running = self.is_running()
        models: List[str] = []
        if running:
            try:
                r = requests.get(f"{self.base_url}/api/tags", timeout=3)
                models = [m["name"] for m in r.json().get("models", [])]
            except Exception:
                pass
        return {
            "running":     running,
            "url":         self.base_url,
            "models":      models,
            "model_count": len(models),
        }

    # ── Server lifecycle ───────────────────────────────────────────────────

    def start(self) -> tuple[bool, str]:
        """Attempt to start the Ollama server in the background."""
        if self.is_running():
            return True, "Ollama is already running."

        try:
            flags = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if platform.system() == "Windows"
                else {}
            )
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **flags,
            )
            for _ in range(10):
                time.sleep(1)
                if self.is_running():
                    return True, "Ollama started successfully."
            return False, "Ollama started but didn't respond in time. Try again in a moment."

        except FileNotFoundError:
            return False, (
                "Ollama executable not found. "
                "Install it from https://ollama.com/download and restart this app."
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"Failed to start Ollama: {exc}"

    # ── Model inventory ────────────────────────────────────────────────────

    def list_models(self) -> List[str]:
        """Return names of all locally downloaded models."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    def is_available(self, model_name: str) -> bool:
        """Check if a specific model is already pulled locally."""
        local = self.list_models()
        return any(m == model_name or m.startswith(model_name + ":") for m in local)

    def get_info(self, model_name: str) -> Optional[dict]:
        """Get parameter size and quantization info for a model."""
        try:
            r = requests.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
                timeout=10,
            )
            if r.status_code == 200:
                details = r.json().get("details", {})
                return {
                    "name":         model_name,
                    "parameters":   details.get("parameter_size", "unknown"),
                    "quantization": details.get("quantization_level", "unknown"),
                    "family":       details.get("family", "unknown"),
                }
        except Exception:
            pass
        return None

    def pull(
        self,
        model_name: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[bool, str]:
        """
        Pull a model from the Ollama registry.
        Calls stream_callback(status_string) with progress updates.
        """
        if not self.is_running():
            return False, "Ollama is not running. Start it first."

        try:
            import json as _json  # noqa: PLC0415

            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=600,
            )
            for line in response.iter_lines():
                if not line:
                    continue
                data   = _json.loads(line.decode())
                status = data.get("status", "")
                if stream_callback:
                    total     = data.get("total", 0)
                    completed = data.get("completed", 0)
                    pct       = int((completed / total) * 100) if total else 0
                    stream_callback(f"{status} — {pct}%" if total else status)
                if data.get("error"):
                    return False, f"Pull error: {data['error']}"
            return True, f"Model '{model_name}' is ready."

        except requests.exceptions.ConnectionError:
            return False, "Cannot reach Ollama. Is it running?"
        except Exception as exc:  # noqa: BLE001
            return False, f"Pull failed: {exc}"

    def delete(self, model_name: str) -> tuple[bool, str]:
        """Remove a locally stored model to free disk space."""
        try:
            r = requests.delete(
                f"{self.base_url}/api/delete",
                json={"name": model_name},
                timeout=10,
            )
            if r.status_code == 200:
                return True, f"Deleted '{model_name}'."
            return False, f"Failed to delete: {r.text}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)