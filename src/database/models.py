from datetime import datetime
import json
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship, declarative_base

from src.schemas.types import (
    OperationType, ApprovalStatus, IntentState,
    DecisionType, DecisionReason, AttemptStatus,
    ProviderTransactionStatus, ReviewCaseStatus
)

Base = declarative_base()

class AuthorizationModel(Base):
    __tablename__ = "authorizations"

    intent_id = Column(String(64), primary_key=True, index=True)
    operator_id = Column(String(64), nullable=False)
    customer_id = Column(String(64), nullable=False, index=True)
    order_id = Column(String(64), nullable=False, index=True)
    operation_type = Column(String(32), default=OperationType.REFUND.value, nullable=False)
    authorized_amount = Column(Float, nullable=False)
    currency = Column(String(16), default="INR", nullable=False)
    approval_status = Column(String(32), default=ApprovalStatus.APPROVED.value, nullable=False)
    current_state = Column(String(32), default=IntentState.AUTHORIZED.value, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    proposals = relationship("AgentProposalModel", back_populates="authorization", cascade="all, delete-orphan")
    decisions = relationship("GatewayDecisionModel", back_populates="authorization", cascade="all, delete-orphan")
    attempts = relationship("TransactionAttemptModel", back_populates="authorization", cascade="all, delete-orphan")
    effects = relationship("EffectModel", back_populates="authorization", cascade="all, delete-orphan")
    review_cases = relationship("ReviewCaseModel", back_populates="authorization", cascade="all, delete-orphan")

class AgentProposalModel(Base):
    __tablename__ = "agent_proposals"

    proposal_id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), ForeignKey("authorizations.intent_id"), nullable=False, index=True)
    request_id = Column(String(64), nullable=False, index=True)
    operation = Column(String(32), default=OperationType.REFUND.value, nullable=False)
    customer_id = Column(String(64), nullable=False)
    order_id = Column(String(64), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(16), default="INR", nullable=False)
    agent_id = Column(String(64), default="agent-primary")
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    authorization = relationship("AuthorizationModel", back_populates="proposals")
    decision = relationship("GatewayDecisionModel", back_populates="proposal", uselist=False)

class GatewayDecisionModel(Base):
    __tablename__ = "gateway_decisions"

    decision_id = Column(String(64), primary_key=True, index=True)
    proposal_id = Column(String(64), ForeignKey("agent_proposals.proposal_id"), nullable=False, index=True)
    intent_id = Column(String(64), ForeignKey("authorizations.intent_id"), nullable=False, index=True)
    decision = Column(String(32), nullable=False)
    reason = Column(String(64), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    authorization = relationship("AuthorizationModel", back_populates="decisions")
    proposal = relationship("AgentProposalModel", back_populates="decision")

class TransactionAttemptModel(Base):
    __tablename__ = "transaction_attempts"

    attempt_id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), ForeignKey("authorizations.intent_id"), nullable=False, index=True)
    provider_request_id = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default=AttemptStatus.PENDING.value, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    authorization = relationship("AuthorizationModel", back_populates="attempts")

class EffectModel(Base):
    """Durable Effects Ledger: Records the ground truth of financial effects observed at the provider."""
    __tablename__ = "effects"

    effect_id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), ForeignKey("authorizations.intent_id"), nullable=False, index=True)
    attempt_id = Column(String(64), nullable=True, index=True)
    provider_transaction_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False)
    order_id = Column(String(64), nullable=False, index=True)
    operation = Column(String(32), default=OperationType.REFUND.value, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(16), default="INR", nullable=False)
    status = Column(String(32), default=ProviderTransactionStatus.COMPLETED.value, nullable=False)
    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    authorization = relationship("AuthorizationModel", back_populates="effects")

class ReviewCaseModel(Base):
    __tablename__ = "review_cases"

    case_id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), ForeignKey("authorizations.intent_id"), nullable=False, index=True)
    reason = Column(String(128), nullable=False)
    discrepancy_amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(32), default=ReviewCaseStatus.OPEN.value, nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    authorization = relationship("AuthorizationModel", back_populates="review_cases")

class AuditLogModel(Base):
    """Immutable audit trail for all gateway state changes, decisions, and provider reconciliation checks."""
    __tablename__ = "audit_logs"

    log_id = Column(String(64), primary_key=True, index=True)
    intent_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    event_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
