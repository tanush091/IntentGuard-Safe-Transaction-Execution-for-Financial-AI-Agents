"""
Integration tests for the complete IntentGuard transaction execution lifecycle.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import Base, engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield


def test_end_to_end_successful_refund():
    intent_id = "INT-E2E-SUCCESS"
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR",
        "approval_status": "APPROVED"
    }

    # Step 1: Create Authorization
    resp = client.post("/api/intents", json=auth_payload)
    assert resp.status_code == 201
    assert resp.json()["current_state"] == "AUTHORIZED"

    mock_provider_response = {
        "id": "ref_sim_live123",
        "order_id": "ORD-204",
        "customer_id": "C-17",
        "amount": 1500.0,
        "currency": "INR",
        "status": "COMPLETED",
        "created_at": "2026-10-03T00:00:00Z"
    }

    with patch("backend.app.services.execution_service.send_payment_request") as mock_send:
        mock_send.return_value = MagicMock(status_code=201, json=lambda: mock_provider_response)

        # Step 2: AI Agent Submits Proposal
        proposal_payload = {
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-204",
            "amount": 1500.0,
            "currency": "INR"
        }
        prop_resp = client.post("/api/proposals", json=proposal_payload)
        assert prop_resp.status_code == 200
        prop_data = prop_resp.json()
        assert prop_data["decision"] == "APPROVED"
        assert prop_data["current_state"] == "COMPLETED"
        assert prop_data["provider_reference"] == "ref_sim_live123"

    # Step 3: Verify Intent State in Database
    intent_resp = client.get(f"/api/intents/{intent_id}")
    assert intent_resp.status_code == 200
    assert intent_resp.json()["current_state"] == "COMPLETED"

    # Step 4: Verify Effect in Ledger
    effects_resp = client.get(f"/api/transactions/intents/{intent_id}/effects")
    assert effects_resp.status_code == 200
    effects = effects_resp.json()
    assert len(effects) == 1
    assert effects[0]["provider_reference"] == "ref_sim_live123"
    assert effects[0]["amount"] == 1500.0


def test_end_to_end_blocked_mismatch():
    intent_id = "INT-E2E-BLOCKED"
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    }
    client.post("/api/intents", json=auth_payload)

    # Propose ₹15,000 (hallucinated amount)
    proposal_payload = {
        "intent_id": intent_id,
        "operation": "REFUND",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "amount": 15000.0,
        "currency": "INR"
    }
    prop_resp = client.post("/api/proposals", json=proposal_payload)
    assert prop_resp.status_code == 200
    data = prop_resp.json()
    assert data["decision"] == "BLOCKED"
    assert "CHECK_4_AMOUNT_MISMATCH" in data["checks_failed"][0]
