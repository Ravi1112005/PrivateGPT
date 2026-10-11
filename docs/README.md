# 📚 PrivateGPT — Project Documentation

This directory contains comprehensive project documentation for PrivateGPT v2.0, the final prototype of the air-gapped desktop RAG application.

## Contents

| Document | Description |
|----------|-------------|
| [Architecture](ARCHITECTURE.md) | System architecture (Electron + FastAPI + Core), layer design, data flow, CI/CD pipeline |
| [Workflow](WORKFLOW.md) | End-to-end workflows: app startup, ingestion, RAG query, enrichment, session management, CI/CD, installer |
| [Functionalities](FUNCTIONALITIES.md) | Complete feature inventory across Desktop, Chat, Documents, Models, History, and DevOps |
| [Technology Stack](TECHNOLOGY_STACK.md) | Every technology used, why it was chosen, and how it integrates (with pinned versions) |
| [API Reference](API_REFERENCE.md) | REST API endpoints (FastAPI), Electron IPC bridge, and class-level Python API |
| [Security](SECURITY.md) | Air-gap design, Electron security, data privacy, and threat model |
| [Configuration](CONFIGURATION.md) | All tunable parameters, offline model loading, and environment setup |

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/Ravi1112005/PrivateGPT.git
cd PrivateGPT
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt

# 2. Pre-download embedding model (for offline use)
python download_embeddings.py

# 3. Install Electron dependencies
cd electron
npm install
cd ..

# 4. Run
start-app.bat
```

The app detects the current OS user automatically — no login required.
