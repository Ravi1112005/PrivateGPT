import pytest
from fastapi.testclient import TestClient
from backend.server import app
from config.settings import settings

client = TestClient(app)

def test_read_info():
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["version"] == "2.0.0"
    assert "default_model" in data
    assert data["default_model"] == settings.default_model

def test_ollama_status():
    response = client.get("/api/ollama/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "models" in data

def test_list_documents():
    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert isinstance(data["documents"], list)

def test_sessions_api():
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)

    # Create session
    res = client.post("/api/sessions")
    assert res.status_code == 200
    session_data = res.json()
    assert "id" in session_data
    session_id = session_data["id"]

    # Delete session
    del_res = client.delete(f"/api/sessions/{session_id}")
    assert del_res.status_code == 200
