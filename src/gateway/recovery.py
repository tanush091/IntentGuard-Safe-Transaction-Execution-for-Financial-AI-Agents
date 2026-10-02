import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from src.database.models import (
    AuthorizationModel, EffectModel, ReviewCaseModel,
    TransactionAttemptModel, AuditLogModel
)
from src.schemas.types import (
    IntentState, ProviderTransactionStatus,
    ReviewCaseStatus, OperationType, AttemptStatus
)
from src.mock_payment.service import payment_service

class RecoveryPolicyEngine:
    """
    Implements state-aware recovery policies:
    - Proposal has not executed -> Block without a financial effect
    - Pending, cancellation supported -> Cancel and verify
    - Completed or cancellation unsupported -> Escalate; record unresolved amount
    - Status unknown -> Reconcile; do not declare success or failure
    - Correctly completed -> Record verified completion; suppress further attempts
    """

    @classmethod
    async def recover_pending_transaction(cls, db: Session, intent_id: str, provider_tx_id: str) -> bool:
        """
        Attempts to cancel a pending transaction at the provider and verify resulting state.
        Never declares transaction reversed merely because agent internal state changed.
        """
        auth = db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == intent_id).first()
        if not auth:
            return False

        cls._log_audit(db, intent_id, "RECOVERY_CANCEL_ATTEMPT", f"Attempting cancellation of provider transaction {provider_tx_id}")

        auth.current_state = IntentState.CANCEL_REQUESTED.value
        db.commit()

        try:
            if auth.operation_type == OperationType.REFUND.value:
                cancel_resp = await payment_service.cancel_refund(provider_tx_id)
            else:
                cancel_resp = await payment_service.cancel_payment_auth(provider_tx_id)

            # Verification of external effect!
            if cancel_resp.status == ProviderTransactionStatus.CANCELLED:
                auth.current_state = IntentState.CANCELLED.value

                # Update effect in durable ledger
                effect = db.query(EffectModel).filter(EffectModel.provider_transaction_id == provider_tx_id).first()
                if effect:
                    effect.status = ProviderTransactionStatus.CANCELLED.value
                db.commit()

                cls._log_audit(db, intent_id, "RECOVERY_CANCEL_VERIFIED", f"External state verified as CANCELLED for {provider_tx_id}")
                return True
            else:
                raise Exception(f"Provider reported non-cancelled status: {cancel_resp.status}")

        except Exception as e:
            # Cancellation failed or unsupported! Escalate!
            auth.current_state = IntentState.ESCALATED.value
            review_case = ReviewCaseModel(
                case_id=f"case_{uuid.uuid4().hex[:12]}",
                intent_id=intent_id,
                reason=f"CANCELLATION_FAILED: Unable to cancel provider transaction {provider_tx_id}: {str(e)}",
                discrepancy_amount=auth.authorized_amount,
                status=ReviewCaseStatus.OPEN.value
            )
            db.add(review_case)
            db.commit()
            cls._log_audit(db, intent_id, "RECOVERY_CANCEL_FAILED_ESCALATED", str(e))
            return False

    @classmethod
    def escalate_unresolved(cls, db: Session, intent_id: str, reason: str, discrepancy_amount: float = 0.0) -> ReviewCaseModel:
        """
        Escalates an unresolved state or discrepancy to human review.
        """
        auth = db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == intent_id).first()
        if auth:
            auth.current_state = IntentState.ESCALATED.value

        case = ReviewCaseModel(
            case_id=f"case_{uuid.uuid4().hex[:12]}",
            intent_id=intent_id,
            reason=reason,
            discrepancy_amount=discrepancy_amount,
            status=ReviewCaseStatus.OPEN.value
        )
        db.add(case)
        db.commit()
        cls._log_audit(db, intent_id, "ESCALATION_RECORDED", f"Case {case.case_id}: {reason}")
        return case

    @staticmethod
    def _log_audit(db: Session, intent_id: str, event_type: str, event_data: str):
        log = AuditLogModel(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            intent_id=intent_id,
            event_type=event_type,
            event_data=event_data,
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
