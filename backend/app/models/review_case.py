"""
Review Case SQLAlchemy Model.
Holds escalated exceptions, ambiguous reconciliation results, and disputes for human review.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ReviewCaseModel(Base):
    __tablename__ = "review_cases"

    id = Column(String(64), primary_key=True, default=lambda: f"rev_{uuid.uuid4().hex[:12]}")
    intent_id = Column(String(64), ForeignKey("intents.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    severity = Column(String(16), nullable=False, default="HIGH")  # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(String(32), nullable=False, default="OPEN")  # OPEN, IN_REVIEW, RESOLVED, DISMISSED
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    intent = relationship("IntentModel", back_populates="review_cases")
