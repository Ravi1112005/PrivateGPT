# 📚 PrivateGPT — Project Documentation

This directory contains comprehensive project documentation for PrivateGPT.

## Contents

| Document | Description |
|----------|-------------|
| [Architecture](ARCHITECTURE.md) | System architecture, layer design, data flow, and component interactions |
| [Workflow](WORKFLOW.md) | End-to-end workflows: ingestion pipeline, query pipeline, enrichment, and authentication |
| [Functionalities](FUNCTIONALITIES.md) | Complete feature inventory with page-level details |
| [Technology Stack](TECHNOLOGY_STACK.md) | Every technology used, why it was chosen, and how it integrates |
| [API Reference](API_REFERENCE.md) | Class-level API documentation for all core modules |
| [Security](SECURITY.md) | Authentication, data isolation, and air-gap design |
| [Configuration](CONFIGURATION.md) | All tunable parameters and their effects |

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd PrivateGPT
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt

# 2. Install Ollama (one-time)
# Download from https://ollama.com/download

# 3. Run
streamlit run app.py
```

**Default login:** `admin / admin123`
