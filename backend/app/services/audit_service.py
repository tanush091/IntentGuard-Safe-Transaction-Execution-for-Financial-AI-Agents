"""
Append-only Audit Journal Service for IntentGuard.
Guarantees that security decisions, state transitions, and check failures are immutably logged.
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.audit_event import AuditEventModel


class AuditService:
    @staticmethod
    def record_event(
        db: Session,
        intent_id: str,
        event_type: str,
        decision: str,
        reason: str,
        attempt_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None
    ) -> AuditEventModel:
        event = AuditEventModel(
            intent_id=intent_id,
            attempt_id=attempt_id,
            event_type=event_type,
            event_data=event_data or {},
            decision=decision,
            reason=reason
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def get_events_for_intent(db: Session, intent_id: str):
        return db.query(AuditEventModel).filter(
            AuditEventModel.intent_id == intent_id
        ).order_by(AuditEventModel.created_at.asc()).all()
