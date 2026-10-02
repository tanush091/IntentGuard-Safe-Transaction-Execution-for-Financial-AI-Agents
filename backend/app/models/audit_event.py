"""
Audit Event Journal SQLAlchemy Model.
Append-only immutable record of all safety checks, transitions, and decisions.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, default=lambda: f"aud_{uuid.uuid4().hex[:12]}")
    intent_id = Column(String(64), ForeignKey("intents.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_id = Column(String(64), ForeignKey("attempts.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False)  # PROPOSAL_EVALUATION, CHECK_FAILED, RECONCILIATION, STATE_CHANGE
    event_data = Column(JSON, nullable=True)
    decision = Column(String(32), nullable=False)  # APPROVED, BLOCKED, RECONCILE, ESCALATE
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    intent = relationship("IntentModel", back_populates="audit_events")
    attempt = relationship("AttemptModel", back_populates="audit_events")
