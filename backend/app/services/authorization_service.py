"""
Durable Intent Record and Authorization Service.
Manages operator authorizations and intent lifecycle persistence.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.intent import IntentModel
from backend.app.schemas.intent import IntentCreate
from backend.app.state_machine.transaction_state_machine import TransactionStateMachine
from backend.app.services.audit_service import AuditService


class AuthorizationService:
    @staticmethod
    def create_intent(db: Session, intent_in: IntentCreate) -> IntentModel:
        """Create and persist an authorized durable intent record."""
        existing = db.query(IntentModel).filter(IntentModel.id == intent_in.intent_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Intent '{intent_in.intent_id}' already exists in ledger."
            )

        intent = IntentModel(
            id=intent_in.intent_id,
            operator_id=intent_in.operator_id,
            customer_id=intent_in.customer_id,
            order_id=intent_in.order_id,
            operation_type=intent_in.operation_type.value,
            authorized_amount=intent_in.authorized_amount,
            currency=intent_in.currency.upper(),
            approval_status=intent_in.approval_status.value,
            current_state="AUTHORIZED"
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)

        AuditService.record_event(
            db=db,
            intent_id=intent.id,
            event_type="INTENT_AUTHORIZED",
            decision="APPROVED",
            reason=(
                f"Operator {intent.operator_id} authorized {intent.operation_type} "
                f"of {intent.currency} {intent.authorized_amount:.2f} for order {intent.order_id}"
            ),
            event_data={
                "customer_id": intent.customer_id,
                "order_id": intent.order_id,
                "amount": intent.authorized_amount,
                "currency": intent.currency
            }
        )
        return intent

    @staticmethod
    def get_intent(db: Session, intent_id: str) -> Optional[IntentModel]:
        return db.query(IntentModel).filter(IntentModel.id == intent_id).first()

    @staticmethod
    def list_intents(db: Session, limit: int = 50, skip: int = 0) -> List[IntentModel]:
        return db.query(IntentModel).order_by(IntentModel.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def transition_intent_state(db: Session, intent: IntentModel, target_state: str, reason: str = "") -> str:
        new_state = TransactionStateMachine.transition(intent.current_state, target_state, reason)
        intent.current_state = new_state
        db.commit()
        db.refresh(intent)
        AuditService.record_event(
            db=db,
            intent_id=intent.id,
            event_type="STATE_TRANSITION",
            decision=new_state,
            reason=reason or f"Transitioned to {new_state}"
        )
        return new_state
