"""
Unit test for Mock Payment Service simulator health and info endpoints.
"""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure mock-payment-service root is in sys.path
mock_service_dir = Path(__file__).parent.parent
if str(mock_service_dir) not in sys.path:
    sys.path.insert(0, str(mock_service_dir))

from app.main import app

client = TestClient(app)


def test_mock_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "Mock Payment Service" in data["service"]
    assert "NEVER CONNECT" in data["prototype_notice"]


def test_mock_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["simulation_mode"] is True
    assert data["live_money_connected"] is False


def test_mock_info_endpoint():
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    assert "refund_settlement" in data["capabilities"]
