"""
Transaction Execution Dispatcher and Attempt Coordinator.
Dispatches requests to the Mock Payment Simulator, tracks attempts, and handles outcomes.
"""

from typing import Dict, Any, Optional
import uuid
import httpx
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.intent import IntentModel
from backend.app.models.attempt import AttemptModel
from backend.app.models.effect import EffectModel
from backend.app.schemas.proposal import AgentProposal, GatewayEvaluationResult
from backend.app.services.idempotency_service import IdempotencyService
from backend.app.services.audit_service import AuditService
from backend.app.services.reconciliation_service import ReconciliationService
from backend.app.services.http_client import send_payment_request
from backend.app.state_machine.transaction_state_machine import TransactionStateMachine


class ExecutionService:
    @staticmethod
    def execute_approved_proposal(
        db: Session,
        intent: IntentModel,
        proposal: AgentProposal
    ) -> GatewayEvaluationResult:
        last_attempt = db.query(AttemptModel).filter(
            AttemptModel.intent_id == intent.id
        ).order_by(AttemptModel.attempt_number.desc()).first()
        attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1

        idempotency_key = IdempotencyService.generate_key(intent.id, attempt_number)
        attempt_id = f"att_{intent.id}_{attempt_number}"

        payload = {
            "order_id": intent.order_id,
            "customer_id": intent.customer_id,
            "amount": float(proposal.amount),
            "currency": intent.currency,
            "reason": f"Execution attempt {attempt_number} for intent {intent.id}"
        }

        attempt = AttemptModel(
            id=attempt_id,
            intent_id=intent.id,
            attempt_number=attempt_number,
            request_payload=payload,
            status="SUBMITTED",
            idempotency_key=idempotency_key
        )
        db.add(attempt)

        if TransactionStateMachine.is_legal(intent.current_state, "SUBMITTED"):
            intent.current_state = "SUBMITTED"
        db.commit()
        db.refresh(attempt)

        AuditService.record_event(
            db=db,
            intent_id=intent.id,
            attempt_id=attempt.id,
            event_type="ATTEMPT_DISPATCHED",
            decision="SUBMITTED",
            reason=f"Dispatched attempt {attempt_number} to payment provider with idempotency key {idempotency_key}",
            event_data=payload
        )

        target_url = f"{settings.PAYMENT_SERVICE_URL}/refunds"
        headers = {"Idempotency-Key": idempotency_key, "Content-Type": "application/json"}

        try:
            response = send_payment_request("POST", target_url, json=payload, headers=headers)
            
            if response.status_code in [200, 201]:
                data = response.json()
                prov_ref = data.get("id") or data.get("refund_id") or data.get("provider_reference", f"sim_{uuid.uuid4().hex[:8]}")
                attempt.status = "COMPLETED"
                attempt.provider_reference = prov_ref

                effect = EffectModel(
                    id=f"eff_{uuid.uuid4().hex[:10]}",
                    intent_id=intent.id,
                    attempt_id=attempt.id,
                    provider_reference=prov_ref,
                    effect_type=intent.operation_type,
                    order_id=intent.order_id,
                    amount=float(proposal.amount),
                    currency=intent.currency,
                    status="COMPLETED"
                )
                db.add(effect)
                intent.current_state = "COMPLETED"
                db.commit()

                AuditService.record_event(
                    db=db,
                    intent_id=intent.id,
                    attempt_id=attempt.id,
                    event_type="TRANSACTION_SETTLED",
                    decision="COMPLETED",
                    reason=f"Refund settled successfully at provider (Reference: {prov_ref})",
                    event_data={"provider_reference": prov_ref}
                )
                return GatewayEvaluationResult(
                    intent_id=intent.id,
                    decision="APPROVED",
                    current_state="COMPLETED",
                    reason="Transaction settled and verified with provider.",
                    attempt_number=attempt_number,
                    provider_reference=prov_ref
                )

            elif response.status_code >= 500:
                attempt.status = "UNKNOWN"
                intent.current_state = "UNKNOWN"
                db.commit()
                recon_res = ReconciliationService.reconcile(db, intent, attempt)
                return GatewayEvaluationResult(
                    intent_id=intent.id,
                    decision="APPROVED",
                    current_state=intent.current_state,
                    reason=f"Provider 5xx encountered; reconciled outcome: {recon_res.get('outcome')}",
                    attempt_number=attempt_number,
                    provider_reference=recon_res.get("provider_reference")
                )

            else:
                attempt.status = "FAILED"
                intent.current_state = "FAILED"
                db.commit()
                return GatewayEvaluationResult(
                    intent_id=intent.id,
                    decision="APPROVED",
                    current_state="FAILED",
                    reason=f"Provider rejected transaction: HTTP {response.status_code}",
                    attempt_number=attempt_number
                )

        except (httpx.TimeoutException, httpx.NetworkError, Exception) as exc:
            attempt.status = "UNKNOWN"
            intent.current_state = "UNKNOWN"
            db.commit()

            AuditService.record_event(
                db=db,
                intent_id=intent.id,
                attempt_id=attempt.id,
                event_type="EXECUTION_TIMEOUT",
                decision="UNKNOWN",
                reason=f"Execution attempt timed out or network dropped: {exc}. Reconciling..."
            )
            recon_res = ReconciliationService.reconcile(db, intent, attempt)
            return GatewayEvaluationResult(
                intent_id=intent.id,
                decision="APPROVED",
                current_state=intent.current_state,
                reason=f"Network drop handled; reconciled outcome: {recon_res.get('outcome')}",
                attempt_number=attempt_number,
                provider_reference=recon_res.get("provider_reference")
            )
