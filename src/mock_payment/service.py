import uuid
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import HTTPException

from src.schemas.types import (
    ProviderTransactionStatus, FaultType,
    PaymentProviderRefundRequest, PaymentProviderRefundResponse,
    PaymentProviderAuthRequest, PaymentProviderAuthResponse
)
from src.mock_payment.faults import fault_engine

class MockPaymentService:
    def __init__(self):
        # Store transactions: id -> dict
        self.refunds: Dict[str, dict] = {}
        self.payment_auths: Dict[str, dict] = {}
        # Idempotency maps: idempotency_key -> transaction_id
        self.refund_idempotency_map: Dict[str, str] = {}
        self.auth_idempotency_map: Dict[str, str] = {}
        # Record creation timestamps for delayed status
        self.creation_times: Dict[str, float] = {}

    def reset(self):
        self.refunds.clear()
        self.payment_auths.clear()
        self.refund_idempotency_map.clear()
        self.auth_idempotency_map.clear()
        self.creation_times.clear()
        fault_engine.clear_faults()

    async def process_refund(self, req: PaymentProviderRefundRequest) -> PaymentProviderRefundResponse:
        fault = fault_engine.get_fault_for_order(req.order_id, req.fault)

        # Fault: Timeout Before Execution (Provider never executes or records)
        if fault.fault_type == FaultType.TIMEOUT_BEFORE_EXECUTION:
            await asyncio.sleep(0.1)
            raise HTTPException(status_code=504, detail="Gateway Timeout: Upstream provider did not respond before execution")

        # Fault: Service Outage
        if fault.fault_type == FaultType.SERVICE_OUTAGE:
            raise HTTPException(status_code=503, detail="Service Unavailable: Payment network offline")

        # Check Idempotency Key
        if req.idempotency_key and req.idempotency_key in self.refund_idempotency_map:
            existing_id = self.refund_idempotency_map[req.idempotency_key]
            existing = self.refunds[existing_id]
            return PaymentProviderRefundResponse(**existing)

        # Determine Amount (check for corrupt amount fault)
        executed_amount = req.amount
        if fault.fault_type == FaultType.CORRUPT_AMOUNT:
            executed_amount = req.amount * 1.5

        # Determine Initial Status
        initial_status = ProviderTransactionStatus.COMPLETED
        if fault.fault_type == FaultType.DELAYED_STATUS:
            initial_status = ProviderTransactionStatus.PENDING

        refund_id = f"ref_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        record = {
            "refund_id": refund_id,
            "order_id": req.order_id,
            "customer_id": req.customer_id,
            "amount": executed_amount,
            "currency": req.currency,
            "status": initial_status,
            "created_at": now
        }

        self.refunds[refund_id] = record
        self.creation_times[refund_id] = time.time()

        if req.idempotency_key:
            self.refund_idempotency_map[req.idempotency_key] = refund_id

        # Fault: Timeout After Execution (Provider completed, but response is lost / dropped)
        if fault.fault_type == FaultType.TIMEOUT_AFTER_EXECUTION:
            await asyncio.sleep(0.1)
            raise HTTPException(status_code=504, detail="Gateway Timeout: Transaction recorded but downstream connection dropped")

        return PaymentProviderRefundResponse(**record)

    def get_refund(self, refund_id: str) -> PaymentProviderRefundResponse:
        if refund_id not in self.refunds:
            raise HTTPException(status_code=404, detail=f"Refund {refund_id} not found")

        record = self.refunds[refund_id]

        # Handle delayed status: if pending for > 0.5s, resolve to COMPLETED
        if record["status"] == ProviderTransactionStatus.PENDING:
            elapsed = time.time() - self.creation_times.get(refund_id, time.time())
            if elapsed > 0.3:
                record["status"] = ProviderTransactionStatus.COMPLETED

        return PaymentProviderRefundResponse(**record)

    def list_refunds_by_order(self, order_id: str) -> List[PaymentProviderRefundResponse]:
        results = []
        for r_id, record in self.refunds.items():
            if record["order_id"] == order_id:
                if record["status"] == ProviderTransactionStatus.PENDING:
                    elapsed = time.time() - self.creation_times.get(r_id, time.time())
                    if elapsed > 0.3:
                        record["status"] = ProviderTransactionStatus.COMPLETED
                results.append(PaymentProviderRefundResponse(**record))
        return results

    async def cancel_refund(self, refund_id: str, force_fail: bool = False) -> PaymentProviderRefundResponse:
        if refund_id not in self.refunds:
            raise HTTPException(status_code=404, detail=f"Refund {refund_id} not found")

        record = self.refunds[refund_id]
        fault = fault_engine.get_fault_for_order(record["order_id"])

        if force_fail or fault.fault_type == FaultType.FAILED_CANCELLATION:
            raise HTTPException(status_code=400, detail="Cancellation rejected: Provider state does not permit cancellation")

        # Cancellation is only permissible in PENDING state
        if record["status"] != ProviderTransactionStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"Cannot cancel refund in state {record['status']}. Only PENDING refunds can be cancelled.")

        record["status"] = ProviderTransactionStatus.CANCELLED
        return PaymentProviderRefundResponse(**record)

    # --- Secondary Workflow: Payment Authorizations ---
    async def process_payment_auth(self, req: PaymentProviderAuthRequest) -> PaymentProviderAuthResponse:
        fault = fault_engine.get_fault_for_order(req.order_id, req.fault)

        if fault.fault_type == FaultType.TIMEOUT_BEFORE_EXECUTION:
            await asyncio.sleep(0.1)
            raise HTTPException(status_code=504, detail="Gateway Timeout: Authorization request timed out before execution")

        if fault.fault_type == FaultType.SERVICE_OUTAGE:
            raise HTTPException(status_code=503, detail="Service Unavailable: Card network offline")

        if req.idempotency_key and req.idempotency_key in self.auth_idempotency_map:
            existing_id = self.auth_idempotency_map[req.idempotency_key]
            existing = self.payment_auths[existing_id]
            return PaymentProviderAuthResponse(**existing)

        auth_id = f"auth_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        record = {
            "auth_id": auth_id,
            "order_id": req.order_id,
            "customer_id": req.customer_id,
            "amount": req.amount,
            "currency": req.currency,
            "status": ProviderTransactionStatus.PENDING, # Auth holds funds as PENDING until capture or cancel
            "created_at": now
        }
        self.payment_auths[auth_id] = record

        if req.idempotency_key:
            self.auth_idempotency_map[req.idempotency_key] = auth_id

        if fault.fault_type == FaultType.TIMEOUT_AFTER_EXECUTION:
            await asyncio.sleep(0.1)
            raise HTTPException(status_code=504, detail="Gateway Timeout: Authorization held but connection dropped")

        return PaymentProviderAuthResponse(**record)

    def get_payment_auth(self, auth_id: str) -> PaymentProviderAuthResponse:
        if auth_id not in self.payment_auths:
            raise HTTPException(status_code=404, detail=f"Payment Authorization {auth_id} not found")
        return PaymentProviderAuthResponse(**self.payment_auths[auth_id])

    def list_payment_auths_by_order(self, order_id: str) -> List[PaymentProviderAuthResponse]:
        results = [
            PaymentProviderAuthResponse(**record)
            for record in self.payment_auths.values()
            if record["order_id"] == order_id
        ]
        return results

    async def cancel_payment_auth(self, auth_id: str) -> PaymentProviderAuthResponse:
        if auth_id not in self.payment_auths:
            raise HTTPException(status_code=404, detail=f"Payment Authorization {auth_id} not found")

        record = self.payment_auths[auth_id]
        fault = fault_engine.get_fault_for_order(record["order_id"])

        if fault.fault_type == FaultType.FAILED_CANCELLATION:
            raise HTTPException(status_code=400, detail="Cancellation failed: Void rejected by issuing bank")

        if record["status"] != ProviderTransactionStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"Cannot void authorization in status {record['status']}")

        record["status"] = ProviderTransactionStatus.CANCELLED
        return PaymentProviderAuthResponse(**record)

payment_service = MockPaymentService()
