"""
External Financial Effect Ledger SQLAlchemy Model.
Represents verified financial outcomes observed on the payment provider.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class EffectModel(Base):
    __tablename__ = "effects"

    id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), ForeignKey("intents.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_id = Column(String(64), ForeignKey("attempts.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_reference = Column(String(128), nullable=False, index=True)
    effect_type = Column(String(32), nullable=False)  # REFUND, PAYMENT_AUTHORIZE, REVERSAL
    order_id = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(String(32), nullable=False, default="COMPLETED")  # COMPLETED, CANCELLED
    observed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    intent = relationship("IntentModel", back_populates="effects")
    attempt = relationship("AttemptModel", back_populates="effects")
