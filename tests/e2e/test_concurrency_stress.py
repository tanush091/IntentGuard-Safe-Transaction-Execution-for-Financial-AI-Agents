import asyncio
import httpx
import uuid
import pytest
from src.schemas.types import AuthorizationCreate, ProposalCreate, OperationType

@pytest.mark.asyncio
async def test_concurrency_stress():
    # Requires docker-compose to be running!
    intent_id = f"SCEN-CONCURRENT-{uuid.uuid4().hex[:6]}"
    
    auth_payload = {
        "intent_id": intent_id,
        "operator_id": "OP-1",
        "customer_id": "C-99",
        "order_id": "ORD-999",
        "operation_type": "REFUND",
        "authorized_amount": 1000.0,
        "currency": "INR",
        "approval_status": "APPROVED"
    }

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        # Create auth
        try:
            resp = await client.post("/api/v1/gateway/authorizations", json=auth_payload)
            if resp.status_code != 200:
                pytest.skip("Gateway API returned non-200. Is docker-compose running?")
                return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            pytest.skip("Gateway API not reachable at 127.0.0.1:8000. Is docker-compose running?")
            return

        async def send_proposal(i):
            payload = {
                "intent_id": intent_id,
                "request_id": f"req_concurrent_{i}",
                "operation": "REFUND",
                "customer_id": "C-99",
                "order_id": "ORD-999",
                "amount": 1000.0,
                "currency": "INR"
            }
            return await client.post("/api/v1/gateway/proposals", json=payload)
        
        # Fire 50 concurrent requests!
        responses = await asyncio.gather(*(send_proposal(i) for i in range(50)))
        
        # Check decisions
        allows = 0
        blocks = 0
        
        for r in responses:
            if r.status_code == 200:
                data = r.json()
                if data.get("decision") == "ALLOW":
                    allows += 1
                elif data.get("decision") == "BLOCK":
                    blocks += 1
                    
        # EXACTLY ONE should be ALLOW!
        assert allows == 1
        # The rest should be BLOCKED because of IN_FLIGHT or ALREADY_COMPLETED!
        assert blocks == 49
