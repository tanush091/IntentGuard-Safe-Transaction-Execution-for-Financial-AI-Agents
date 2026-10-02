"""
Attempt Ledger SQLAlchemy Model.
Represents an individual physical API request dispatched toward the payment provider.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class AttemptModel(Base):
    __tablename__ = "attempts"

    id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), ForeignKey("intents.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    request_payload = Column(JSON, nullable=True)
    provider_reference = Column(String(128), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="SUBMITTED")  # SUBMITTED, COMPLETED, UNKNOWN, FAILED
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    intent = relationship("IntentModel", back_populates="attempts")
    effects = relationship("EffectModel", back_populates="attempt")
    audit_events = relationship("AuditEventModel", back_populates="attempt")
