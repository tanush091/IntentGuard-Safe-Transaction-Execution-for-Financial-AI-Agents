#!/usr/bin/env python3
"""
IntentGuard Interactive Research Demo CLI Runner.
Demonstrates the 6 core research safety scenarios with formatted terminal output.
STRICTLY A SIMULATION - NO REAL FINANCIAL ACCOUNTS OR REAL MONEY INVOLVED.
"""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows PowerShell
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import uuid
from unittest.mock import patch, MagicMock
import httpx
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import Base, engine, init_db

init_db()
client = TestClient(app)


def print_banner(title: str):
    print("\n" + "=" * 80)
    print(f" >>> {title}")
    print("=" * 80)


def demo_1_correct_refund():
    print_banner("DEMO 1: Authorized Correct Refund (Normal Happy Path)")
    intent_id = f"INT-DEMO-1-{uuid.uuid4().hex[:6]}"
    print(f"[Operator Authorization] Authorizing ₹1,500 for Order ORD-204 to Customer C-17 (Intent: {intent_id})")

    auth_resp = client.post("/api/intents", json={
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    })
    print(f" -> Intent Record Created: Status = {auth_resp.json()['current_state']}")

    print("[AI Agent] AI proposes: Refund ₹1,500 for ORD-204 to C-17")
    mock_provider_resp = {
        "id": "ref_sim_demo_01",
        "order_id": "ORD-204",
        "amount": 1500.0,
        "status": "COMPLETED"
    }

    with patch("backend.app.services.execution_service.send_payment_request") as mock_send:
        mock_send.return_value = MagicMock(status_code=201, json=lambda: mock_provider_resp)
        prop_resp = client.post("/api/proposals", json={
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-204",
            "amount": 1500.0,
            "currency": "INR"
        })

    data = prop_resp.json()
    print(f"[Safety Gateway Decision] {data['decision']} - Reason: {data['reason']}")
    print(f"[Execution State] Current State: {data['current_state']} | Provider Reference: {data['provider_reference']}")
    assert data["current_state"] == "COMPLETED"


def demo_2_wrong_amount():
    print_banner("DEMO 2: Hallucinated / Altered Amount (Security Gateway Block)")
    intent_id = f"INT-DEMO-2-{uuid.uuid4().hex[:6]}"
    print(f"[Operator Authorization] Authorizing ₹1,500 for Order ORD-204 (Intent: {intent_id})")

    client.post("/api/intents", json={
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    })

    print("[AI Agent Hallucination] AI proposes inflated amount: ₹15,000 (10x unauthorized drift!)")
    prop_resp = client.post("/api/proposals", json={
        "intent_id": intent_id,
        "operation": "REFUND",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "amount": 15000.0,
        "currency": "INR"
    })

    data = prop_resp.json()
    print(f"[Safety Gateway Decision] {data['decision']} - Result: BLOCKED at Check 4")
    print(f" -> Reason: {data['reason']}")
    assert data["decision"] == "BLOCKED"


def demo_3_wrong_order():
    print_banner("DEMO 3: Wrong Order ID (Identifier Transposition Block)")
    intent_id = f"INT-DEMO-3-{uuid.uuid4().hex[:6]}"
    print(f"[Operator Authorization] Authorizing ₹1,500 for Order ORD-204 (Intent: {intent_id})")

    client.post("/api/intents", json={
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-204",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    })

    print("[AI Agent Semantic Drift] AI proposes transposed order ID: ORD-240 instead of ORD-204")
    prop_resp = client.post("/api/proposals", json={
        "intent_id": intent_id,
        "operation": "REFUND",
        "customer_id": "C-17",
        "order_id": "ORD-240",
        "amount": 1500.0,
        "currency": "INR"
    })

    data = prop_resp.json()
    print(f"[Safety Gateway Decision] {data['decision']} - Result: BLOCKED at Check 2")
    print(f" -> Reason: {data['reason']}")
    assert data["decision"] == "BLOCKED"


def demo_4_timeout_reconciliation():
    print_banner("DEMO 4: Network Drop After Execution -> Active Reconciliation (No Duplicate)")
    intent_id = f"INT-DEMO-4-{uuid.uuid4().hex[:6]}"
    print(f"[Operator Authorization] Authorizing ₹1,500 for Order ORD-LOST-555 (Intent: {intent_id})")

    client.post("/api/intents", json={
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-LOST-555",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    })

    print("[Network Fault Injected] Execution request sent to provider; provider settles refund, but response connection DROPS!")
    print("[State Transition] Gateway catches timeout -> Status: UNKNOWN. Immediate retry HALTED.")
    print("[Active Reconciliation] Gateway queries GET /refunds?order_id=ORD-LOST-555 to discover ground truth...")

    mock_discovered = [
        {
            "id": "ref_sim_reconciled_999",
            "order_id": "ORD-LOST-555",
            "customer_id": "C-17",
            "amount": 1500.0,
            "currency": "INR",
            "status": "COMPLETED"
        }
    ]

    with patch("backend.app.services.execution_service.send_payment_request") as mock_exec, \
         patch("backend.app.services.reconciliation_service.send_payment_request") as mock_recon:
        
        mock_exec.side_effect = httpx.TimeoutException("Network Connection Dropped")
        mock_recon.return_value = MagicMock(status_code=200, json=lambda: mock_discovered)

        prop_resp = client.post("/api/proposals", json={
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-LOST-555",
            "amount": 1500.0,
            "currency": "INR"
        })

    data = prop_resp.json()
    print(f"[Reconciliation Verdict] Found settled provider transaction: {data['provider_reference']}")
    print(f"[Final State] {data['current_state']} - Zero duplicate payout dispatched!")
    assert data["current_state"] == "COMPLETED"


def demo_5_agent_restart_duplicate_prevention():
    print_banner("DEMO 5: Agent Restart / Replay Duplicate Prevention")
    intent_id = f"INT-DEMO-5-{uuid.uuid4().hex[:6]}"
    print(f"[Operator Authorization] Authorizing ₹1,500 for Order ORD-SETTLED (Intent: {intent_id})")

    client.post("/api/intents", json={
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-SETTLED",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    })

    # First proposal settles
    mock_prov = {"id": "ref_prior_settled", "order_id": "ORD-SETTLED", "amount": 1500.0, "status": "COMPLETED"}
    with patch("backend.app.services.execution_service.send_payment_request") as mock_send:
        mock_send.return_value = MagicMock(status_code=201, json=lambda: mock_prov)
        client.post("/api/proposals", json={
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-SETTLED",
            "amount": 1500.0,
            "currency": "INR"
        })

    print("[Agent Crash & Restart] Agent boots up, re-reads ticket, and generates a fresh duplicate proposal!")
    prop_resp = client.post("/api/proposals", json={
        "intent_id": intent_id,
        "operation": "REFUND",
        "customer_id": "C-17",
        "order_id": "ORD-SETTLED",
        "amount": 1500.0,
        "currency": "INR"
    })

    data = prop_resp.json()
    print(f"[Safety Gateway Decision] {data['decision']} - Blocked at Check 7 (DUPLICATE_EFFECT_EXISTS)")
    print(f" -> Reason: {data['reason']}")
    assert data["decision"] == "BLOCKED"


def demo_6_incorrect_effect_escalation():
    print_banner("DEMO 6: Inconsistent Provider Effect -> Cancellation & Human Escalation")
    intent_id = f"INT-DEMO-6-{uuid.uuid4().hex[:6]}"
    print(f"[Operator Authorization] Authorizing ₹1,500 for Order ORD-CORRUPTED (Intent: {intent_id})")

    client.post("/api/intents", json={
        "intent_id": intent_id,
        "operator_id": "OP-10",
        "customer_id": "C-17",
        "order_id": "ORD-CORRUPTED",
        "operation_type": "REFUND",
        "authorized_amount": 1500.0,
        "currency": "INR"
    })

    print("[Upstream Anomaly] Provider recorded corrupted amount (₹15,000 instead of ₹1,500).")
    print("[State-Aware Recovery] Gateway attempts automatic provider cancellation...")
    print("[Cancellation Refused] Provider returns HTTP 409 Conflict. Gateway escalates to Human Operator.")

    mock_corrupted = [{
        "id": "ref_corrupted_123",
        "order_id": "ORD-CORRUPTED",
        "customer_id": "C-17",
        "amount": 15000.0,
        "currency": "INR",
        "status": "COMPLETED"
    }]

    with patch("backend.app.services.execution_service.send_payment_request") as mock_exec, \
         patch("backend.app.services.reconciliation_service.send_payment_request") as mock_recon, \
         patch("backend.app.services.recovery_service.send_payment_request") as mock_recov:

        mock_exec.side_effect = httpx.TimeoutException("Execution Timeout")
        mock_recon.return_value = MagicMock(status_code=200, json=lambda: mock_corrupted)
        mock_recov.return_value = MagicMock(status_code=409)

        prop_resp = client.post("/api/proposals", json={
            "intent_id": intent_id,
            "operation": "REFUND",
            "customer_id": "C-17",
            "order_id": "ORD-CORRUPTED",
            "amount": 1500.0,
            "currency": "INR"
        })

    data = prop_resp.json()
    print(f"[Resolution] Intent State: {data['current_state']}")
    assert data["current_state"] == "ESCALATED"

    review_cases = client.get("/api/reviews").json()
    matching_case = next(c for c in review_cases if c["intent_id"] == intent_id)
    print(f" -> Human Review Ticket Created: {matching_case['id']} | Severity: {matching_case['severity']}")
    print(f" -> Reason: {matching_case['reason']}")


def main():
    print("\n" + "=" * 80)
    print("  INTENTGUARD: INTENT-CONSISTENT TRANSACTION EXECUTION & RECOVERY DEMO")
    print("  ACADEMIC RESEARCH PROTOTYPE - SIMULATION SANDBOX ONLY")
    print("=" * 80)

    demo_1_correct_refund()
    demo_2_wrong_amount()
    demo_3_wrong_order()
    demo_4_timeout_reconciliation()
    demo_5_agent_restart_duplicate_prevention()
    demo_6_incorrect_effect_escalation()

    print("\n" + "=" * 80)
    print(" ALL 6 RESEARCH DEMONSTRATIONS COMPLETED SUCCESSFULLY WITH ZERO SAFETY VIOLATIONS!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
