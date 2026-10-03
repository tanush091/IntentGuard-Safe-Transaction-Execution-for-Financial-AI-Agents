"""
Unit & Integration tests for Mock Payment Service Simulator.
"""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

mock_service_dir = Path(__file__).parent.parent
if str(mock_service_dir) not in sys.path:
    sys.path.insert(0, str(mock_service_dir))

from app.main import app
from app.services.payment_service import payment_service
from app.services.fault_injector import fault_injector

client = TestClient(app)


def setup_function():
    payment_service.refunds.clear()
    payment_service.idempotency_map.clear()
    payment_service.authorizations.clear()
    fault_injector.reset()


def test_process_refund_success():
    payload = {
        "order_id": "ORD-204",
        "customer_id": "C-17",
        "amount": 1500.0,
        "currency": "INR"
    }
    resp = client.post("/refunds", json=payload, headers={"Idempotency-Key": "key-1"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["order_id"] == "ORD-204"
    assert data["amount"] == 1500.0
    assert data["status"] == "COMPLETED"
    assert data["idempotency_key"] == "key-1"


def test_refund_idempotency():
    payload = {
        "order_id": "ORD-204",
        "customer_id": "C-17",
        "amount": 1500.0,
        "currency": "INR"
    }
    resp1 = client.post("/refunds", json=payload, headers={"Idempotency-Key": "key-idemp"})
    assert resp1.status_code == 201
    ref_id = resp1.json()["id"]

    resp2 = client.post("/refunds", json=payload, headers={"Idempotency-Key": "key-idemp"})
    assert resp2.status_code == 201
    assert resp2.json()["id"] == ref_id  # Exactly same transaction record returned


def test_cancel_refund():
    payload = {"order_id": "ORD-204", "customer_id": "C-17", "amount": 1500.0, "currency": "INR"}
    resp = client.post("/refunds", json=payload)
    ref_id = resp.json()["id"]

    cancel_resp = client.post(f"/refunds/{ref_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"


def test_fault_outage_503():
    fault_injector.configure_fault("OUTAGE_503", target_order_id="ORD-OUTAGE")
    payload = {"order_id": "ORD-OUTAGE", "customer_id": "C-17", "amount": 1500.0, "currency": "INR"}
    resp = client.post("/refunds", json=payload)
    assert resp.status_code == 503


def test_fault_lost_response_persists_effect():
    fault_injector.configure_fault("LOST_RESPONSE_AFTER_EXECUTION", target_order_id="ORD-LOST")
    payload = {"order_id": "ORD-LOST", "customer_id": "C-17", "amount": 1500.0, "currency": "INR"}
    resp = client.post("/refunds", json=payload)
    # The client encounters 504 Gateway Timeout
    assert resp.status_code == 504
    # But the provider has stored the refund!
    list_resp = client.get("/refunds?order_id=ORD-LOST")
    assert list_resp.status_code == 200
    records = list_resp.json()
    assert len(records) == 1
    assert records[0]["status"] == "COMPLETED"
