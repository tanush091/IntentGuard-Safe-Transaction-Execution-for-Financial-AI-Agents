"""
Durable Intent Record SQLAlchemy Model.
Represents the immutable business authorization issued by an operator or trusted source.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class IntentModel(Base):
    __tablename__ = "intents"

    id = Column(String(64), primary_key=True, index=True)
    operator_id = Column(String(64), nullable=False)
    customer_id = Column(String(64), nullable=False, index=True)
    order_id = Column(String(64), nullable=False, index=True)
    operation_type = Column(String(32), nullable=False)  # REFUND, PAYMENT_AUTHORIZE
    authorized_amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    approval_status = Column(String(32), nullable=False, default="APPROVED")
    current_state = Column(String(32), nullable=False, default="AUTHORIZED", index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    attempts = relationship("AttemptModel", back_populates="intent", cascade="all, delete-orphan")
    effects = relationship("EffectModel", back_populates="intent", cascade="all, delete-orphan")
    audit_events = relationship("AuditEventModel", back_populates="intent", cascade="all, delete-orphan")
    review_cases = relationship("ReviewCaseModel", back_populates="intent", cascade="all, delete-orphan")
