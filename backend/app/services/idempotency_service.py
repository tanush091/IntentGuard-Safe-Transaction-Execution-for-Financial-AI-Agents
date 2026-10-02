"""
Deterministic Idempotency and Concurrency Management Service.
Prevents duplicate financial executions and concurrent in-flight race conditions.
"""

from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.attempt import AttemptModel
from backend.app.models.effect import EffectModel


class IdempotencyService:
    @staticmethod
    def generate_key(intent_id: str, attempt_number: int) -> str:
        """Generate a deterministic, intent-bound idempotency key."""
        return f"{intent_id}-att-{attempt_number}"

    @staticmethod
    def get_active_attempt(db: Session, intent_id: str) -> Optional[AttemptModel]:
        """Check if an attempt is currently in flight for the given intent."""
        return db.query(AttemptModel).filter(
            AttemptModel.intent_id == intent_id,
            AttemptModel.status.in_(["SUBMITTED", "PENDING", "RECONCILING"])
        ).first()

    @staticmethod
    def get_completed_effect(db: Session, intent_id: str) -> Optional[EffectModel]:
        """Check if the intent has already settled an effect in the local ledger."""
        return db.query(EffectModel).filter(
            EffectModel.intent_id == intent_id,
            EffectModel.status == "COMPLETED"
        ).first()

    @staticmethod
    def get_order_effect(db: Session, order_id: str) -> Optional[EffectModel]:
        """Check if a settled effect already exists for this order in the ledger."""
        return db.query(EffectModel).filter(
            EffectModel.order_id == order_id,
            EffectModel.status == "COMPLETED"
        ).first()
