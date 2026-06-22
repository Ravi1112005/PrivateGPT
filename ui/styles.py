"""
ui/styles.py — All CSS for the PrivateGPT interface.

Import and call inject_styles() once at the top of app.py.
"""

import streamlit as st


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Sidebar ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #21262d;
}
[data-testid="stSidebar"] * { color: #c9d1d9 !important; }

/* ── Chat bubbles ─────────────────────────────────────────────────────── */
.user-bubble {
    background: linear-gradient(135deg, #1e3a5f, #1a3050);
    color: #e8f0fe;
    padding: 12px 16px;
    border-radius: 18px 18px 4px 18px;
    margin: 8px 0;
    max-width: 80%;
    margin-left: auto;
    font-size: 14px;
    line-height: 1.6;
    box-shadow: 0 2px 8px rgba(0,0,0,.3);
}
.ai-bubble {
    background: #161b22;
    color: #c9d1d9;
    padding: 12px 16px;
    border-radius: 18px 18px 18px 4px;
    margin: 8px 0;
    max-width: 88%;
    font-size: 14px;
    line-height: 1.7;
    border: 1px solid #30363d;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
}

/* ── Source chips ─────────────────────────────────────────────────────── */
.source-chip {
    display: inline-block;
    background: #0d1f12;
    color: #56d364;
    border: 1px solid #238636;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    margin: 3px 3px 0 0;
    font-weight: 500;
}

/* ── Metric row ───────────────────────────────────────────────────────── */
.metric-row { color: #8b949e; font-size: 11px; margin-top: 8px; }

/* ── Status indicators ────────────────────────────────────────────────── */
.status-ok  { color: #3fb950; font-weight: 600; }
.status-err { color: #f85149; font-weight: 600; }

/* ── Info banners ─────────────────────────────────────────────────────── */
.warning-banner {
    background: #2d1f00;
    border: 1px solid #6e4c0e;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 10px 0;
    color: #d29922;
}
.info-banner {
    background: #0d1f2d;
    border: 1px solid #1f6feb;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 10px 0;
    color: #58a6ff;
}

/* ── Streaming cursor ─────────────────────────────────────────────────── */
.streaming-cursor::after {
    content: '▌';
    animation: blink 0.7s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
</style>
"""


def inject_styles() -> None:
    """Inject all application CSS. Call once at app startup."""
    st.markdown(_CSS, unsafe_allow_html=True)
