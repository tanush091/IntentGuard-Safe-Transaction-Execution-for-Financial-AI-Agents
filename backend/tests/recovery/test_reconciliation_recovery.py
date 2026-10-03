"""
Recovery and Active Reconciliation Integration Tests for IntentGuard.
"""

from unittest.mock import patch, MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import Base, engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield


def test_timeout_triggers_active_reconciliation():
    intent_id = "INT-RECON-LOST-RESPONSE"
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-LOST-204",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    }
    client.post("/api/intents", json=auth_payload)

    mock_discovered_refunds = [
        {
            "id": "ref_discovered_777",
            "order_id": "ORD-LOST-204",
            "customer_id": "C-17",
            "amount": 1500.0,
            "currency": "INR",
            "status": "COMPLETED"
        }
    ]

    with patch("backend.app.services.execution_service.send_payment_request") as mock_exec_send, \
         patch("backend.app.services.reconciliation_service.send_payment_request") as mock_recon_send:

        mock_exec_send.side_effect = httpx.TimeoutException("Execution Timeout")
        mock_recon_send.return_value = MagicMock(status_code=200, json=lambda: mock_discovered_refunds)

        proposal_payload = {
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-LOST-204",
            "amount": 1500.0,
            "currency": "INR"
        }
        resp = client.post("/api/proposals", json=proposal_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_state"] == "COMPLETED"
        assert data["provider_reference"] == "ref_discovered_777"


def test_corrupted_effect_triggers_escalation():
    intent_id = "INT-RECON-CORRUPT"
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-CORRUPT-500",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    }
    client.post("/api/intents", json=auth_payload)

    mock_corrupted_refunds = [
        {
            "id": "ref_corrupted_999",
            "order_id": "ORD-CORRUPT-500",
            "customer_id": "C-17",
            "amount": 15000.0,  # Corrupt amount!
            "currency": "INR",
            "status": "COMPLETED"
        }
    ]

    with patch("backend.app.services.execution_service.send_payment_request") as mock_exec_send, \
         patch("backend.app.services.reconciliation_service.send_payment_request") as mock_recon_send, \
         patch("backend.app.services.recovery_service.send_payment_request") as mock_recov_send:

        mock_exec_send.side_effect = httpx.TimeoutException("Execution Timeout")
        mock_recon_send.return_value = MagicMock(status_code=200, json=lambda: mock_corrupted_refunds)
        mock_recov_send.return_value = MagicMock(status_code=409)

        proposal_payload = {
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-CORRUPT-500",
            "amount": 1500.0,
            "currency": "INR"
        }
        resp = client.post("/api/proposals", json=proposal_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_state"] == "ESCALATED"

    # Verify Review Case created
    reviews_resp = client.get("/api/reviews")
    assert reviews_resp.status_code == 200
    cases = reviews_resp.json()
    assert any(c["intent_id"] == intent_id for c in cases)
