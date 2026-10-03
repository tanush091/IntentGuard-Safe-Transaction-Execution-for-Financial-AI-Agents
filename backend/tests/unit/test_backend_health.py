"""
Unit test for IntentGuard Gateway Backend Health and Info endpoints.
"""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "IntentGuard"
    assert "Simulation Only" in data["prototype_notice"]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "intentguard-backend"


def test_info_endpoint():
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert data["default_currency"] == "INR"
