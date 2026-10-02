"""
State-Aware Recovery Service for IntentGuard.
Handles cancellation attempts, controlled retry permits, and human review escalations.
"""

from datetime import datetime, timezone
import uuid
import httpx
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.intent import IntentModel
from backend.app.models.review_case import ReviewCaseModel
from backend.app.services.audit_service import AuditService
from backend.app.services.http_client import send_payment_request
from backend.app.state_machine.transaction_state_machine import TransactionStateMachine


class RecoveryService:
    @staticmethod
    def escalate(
        db: Session,
        intent: IntentModel,
        reason: str,
        severity: str = "HIGH"
    ) -> ReviewCaseModel:
        """Create an escalated review case and transition intent to ESCALATED."""
        if TransactionStateMachine.is_legal(intent.current_state, "ESCALATED"):
            intent.current_state = "ESCALATED"
            db.commit()

        case = ReviewCaseModel(
            id=f"rev_{uuid.uuid4().hex[:10]}",
            intent_id=intent.id,
            reason=reason,
            severity=severity,
            status="OPEN"
        )
        db.add(case)
        db.commit()
        db.refresh(case)

        AuditService.record_event(
            db=db,
            intent_id=intent.id,
            event_type="HUMAN_ESCALATION",
            decision="ESCALATE",
            reason=f"Transaction escalated for human review (Case {case.id}): {reason}",
            event_data={"case_id": case.id, "severity": severity}
        )
        return case

    @staticmethod
    def attempt_cancellation(
        db: Session,
        intent: IntentModel,
        provider_reference: str
    ) -> bool:
        """Attempt to cancel an unwanted or incorrect provider effect."""
        cancel_url = f"{settings.PAYMENT_SERVICE_URL}/refunds/{provider_reference}/cancel"
        try:
            resp = send_payment_request("POST", cancel_url)
            if resp.status_code == 200:
                intent.current_state = "CANCELLED"
                db.commit()
                AuditService.record_event(
                    db=db,
                    intent_id=intent.id,
                    event_type="EFFECT_CANCELLED",
                    decision="CANCELLED",
                    reason=f"Successfully reversed external effect {provider_reference}"
                )
                return True
            else:
                RecoveryService.escalate(
                    db=db,
                    intent=intent,
                    reason=f"Provider refused cancellation of {provider_reference} (HTTP {resp.status_code})"
                )
                return False
        except Exception as e:
            RecoveryService.escalate(
                db=db,
                intent=intent,
                reason=f"Cancellation request network failure for {provider_reference}: {e}"
            )
            return False
