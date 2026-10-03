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


def test_reconciliation_zero_effects_permits_safe_retry():
    """
    When execution times out before reaching the external provider,
    reconciliation observes 0 records and marks state as RETRY_ALLOWED.
    """
    intent_id = "INT-RECON-ZERO-EFFECTS"
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-25",
        "order_id": "ORD-ZERO-88",
        "operation_type": "REFUND",
        "authorized_amount": 2200.0,
        "currency": "INR"
    }
    client.post("/api/intents", json=auth_payload)

    with patch("backend.app.services.execution_service.send_payment_request") as mock_exec_send, \
         patch("backend.app.services.reconciliation_service.send_payment_request") as mock_recon_send:

        # Execution timed out, external provider has zero records
        mock_exec_send.side_effect = httpx.TimeoutException("Execution Timeout")
        mock_recon_send.return_value = MagicMock(status_code=200, json=lambda: [])

        proposal_payload = {
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-25",
            "order_id": "ORD-ZERO-88",
            "amount": 2200.0,
            "currency": "INR"
        }
        resp = client.post("/api/proposals", json=proposal_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_state"] == "RETRY_ALLOWED"

    # Verify intent record status in DB
    intent_resp = client.get(f"/api/intents/{intent_id}")
    assert intent_resp.status_code == 200
    assert intent_resp.json()["current_state"] == "RETRY_ALLOWED"


def test_reconciliation_provider_unreachable_triggers_critical_escalation():
    """
    If the external payment provider cannot be reached even during reconciliation,
    the protocol escalates to manual operator review to prevent double settlement.
    """
    intent_id = "INT-RECON-NETWORK-CRASH"
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-30",
        "order_id": "ORD-CRASH-99",
        "operation_type": "REFUND",
        "authorized_amount": 3500.0,
        "currency": "INR"
    }
    client.post("/api/intents", json=auth_payload)

    with patch("backend.app.services.execution_service.send_payment_request") as mock_exec_send, \
         patch("backend.app.services.reconciliation_service.send_payment_request") as mock_recon_send:

        mock_exec_send.side_effect = httpx.TimeoutException("Execution Timeout")
        mock_recon_send.side_effect = httpx.ConnectError("Connection refused by provider")

        proposal_payload = {
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-30",
            "order_id": "ORD-CRASH-99",
            "amount": 3500.0,
            "currency": "INR"
        }
        resp = client.post("/api/proposals", json=proposal_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_state"] == "ESCALATED"

    # Verify critical escalation review case created
    reviews_resp = client.get("/api/reviews")
    assert reviews_resp.status_code == 200
    cases = reviews_resp.json()
    assert any(c["intent_id"] == intent_id and c["severity"] == "CRITICAL" for c in cases)

