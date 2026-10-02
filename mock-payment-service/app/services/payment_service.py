"""
Simulated Payment Service Engine for IntentGuard.
Maintains in-memory ledgers for mock refunds and payment authorizations.
"""

from datetime import datetime, timezone
import uuid
import time
from typing import Dict, List, Optional
from fastapi import HTTPException, status

from ..schemas import (
    RefundCreateRequest,
    RefundResponse,
    AuthorizationCreateRequest,
    AuthorizationResponse,
)
from .fault_injector import fault_injector


class PaymentService:
    def __init__(self):
        self.refunds: Dict[str, Dict] = {}
        self.authorizations: Dict[str, Dict] = {}
        self.idempotency_map: Dict[str, str] = {}  # idempotency_key -> refund_id

    def process_refund(self, req: RefundCreateRequest, idempotency_key: Optional[str] = None) -> RefundResponse:
        # Check provider-level idempotency
        if idempotency_key and idempotency_key in self.idempotency_map:
            existing_id = self.idempotency_map[idempotency_key]
            rec = self.refunds[existing_id]
            return RefundResponse(**rec)

        # 1. Fault: 503 Provider Outage
        if fault_injector.should_trigger("OUTAGE_503", req.order_id):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Simulated Payment Gateway Outage (503 Service Unavailable)"
            )

        # 2. Fault: Timeout BEFORE execution
        if fault_injector.should_trigger("TIMEOUT_BEFORE_EXECUTION", req.order_id):
            delay = fault_injector.get_delay(req.order_id) or 0.1
            time.sleep(delay)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Simulated Gateway Timeout before execution"
            )

        # Compute amount (simulate corrupt amount if configured)
        settled_amount = req.amount
        if fault_injector.should_trigger("CORRUPT_AMOUNT", req.order_id):
            settled_amount = req.amount * 10.0

        refund_id = f"ref_sim_{uuid.uuid4().hex[:10]}"
        now_str = datetime.now(timezone.utc).isoformat()

        record = {
            "id": refund_id,
            "order_id": req.order_id,
            "customer_id": req.customer_id,
            "amount": settled_amount,
            "currency": req.currency.upper(),
            "status": "COMPLETED",
            "idempotency_key": idempotency_key,
            "created_at": now_str
        }

        # Persist record
        self.refunds[refund_id] = record
        if idempotency_key:
            self.idempotency_map[idempotency_key] = refund_id

        # 3. Fault: Lost Response AFTER execution
        if fault_injector.should_trigger("LOST_RESPONSE_AFTER_EXECUTION", req.order_id):
            # Settled in database, but HTTP connection drops!
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Simulated Network Drop: Execution completed but response was lost."
            )

        return RefundResponse(**record)

    def get_refund(self, refund_id: str) -> Optional[RefundResponse]:
        rec = self.refunds.get(refund_id)
        return RefundResponse(**rec) if rec else None

    def list_refunds_by_order(self, order_id: str) -> List[RefundResponse]:
        # 4. Fault: Delayed Visibility
        if fault_injector.should_trigger("DELAYED_VISIBILITY", order_id):
            return []  # Simulate eventual consistency lag
        
        matches = [r for r in self.refunds.values() if r["order_id"] == order_id]
        return [RefundResponse(**m) for m in matches]

    def cancel_refund(self, refund_id: str) -> RefundResponse:
        rec = self.refunds.get(refund_id)
        if not rec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found")

        if fault_injector.should_trigger("CANCELLATION_REFUSED", rec["order_id"]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cancellation rejected by provider settlement rules"
            )

        rec["status"] = "CANCELLED"
        return RefundResponse(**rec)

    # Secondary transaction type: Payment Authorizations & Voids
    def create_authorization(self, req: AuthorizationCreateRequest) -> AuthorizationResponse:
        auth_id = f"auth_sim_{uuid.uuid4().hex[:10]}"
        now_str = datetime.now(timezone.utc).isoformat()
        rec = {
            "id": auth_id,
            "order_id": req.order_id,
            "customer_id": req.customer_id,
            "amount": req.amount,
            "currency": req.currency.upper(),
            "status": "AUTHORIZED",
            "created_at": now_str
        }
        self.authorizations[auth_id] = rec
        return AuthorizationResponse(**rec)

    def get_authorization(self, auth_id: str) -> Optional[AuthorizationResponse]:
        rec = self.authorizations.get(auth_id)
        return AuthorizationResponse(**rec) if rec else None

    def void_authorization(self, auth_id: str) -> AuthorizationResponse:
        rec = self.authorizations.get(auth_id)
        if not rec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authorization not found")
        rec["status"] = "VOIDED"
        return AuthorizationResponse(**rec)


payment_service = PaymentService()
