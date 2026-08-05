"""
core/ssl_patch.py — Shared SSL certificate verification bypass.

Suppresses SSL errors when downloading models from HuggingFace Hub on
networks that use a self-signed / corporate CA chain.

Usage::

    from core.ssl_patch import patch_ssl_for_hf
    patch_ssl_for_hf()  # Call once before any HuggingFace import
"""

from __future__ import annotations

import os


def patch_ssl_for_hf() -> None:
    """
    Suppress SSL certificate verification for HuggingFace Hub downloads.

    Sets environment variables that ``requests``, ``urllib3``, and
    ``huggingface_hub`` check before establishing TLS connections:

      - ``CURL_CA_BUNDLE=""``                → requests/urllib3 skip verify
      - ``HF_HUB_DISABLE_SSL_VERIFICATION=1`` → huggingface_hub skips verify
      - ``REQUESTS_CA_BUNDLE=""``             → fallback for older requests

    Safe to call multiple times (uses ``setdefault``).
    """
    os.environ.setdefault("CURL_CA_BUNDLE", "")
    os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFICATION", "1")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:  # noqa: BLE001
        pass
