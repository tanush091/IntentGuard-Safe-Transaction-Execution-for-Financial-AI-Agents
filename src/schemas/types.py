from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class OperationType(str, Enum):
    REFUND = "REFUND"
    PAYMENT_AUTHORIZATION = "PAYMENT_AUTHORIZATION"
    PAYMENT_CANCEL = "PAYMENT_CANCEL"

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class IntentState(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"
    BLOCKED = "BLOCKED"

class DecisionType(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    RETRY = "RETRY"
    CANCEL = "CANCEL"
    ESCALATE = "ESCALATE"
    HOLD = "HOLD"

class DecisionReason(str, Enum):
    VALID = "VALID"
    AMOUNT_EXCEEDS_AUTHORIZATION = "AMOUNT_EXCEEDS_AUTHORIZATION"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    CUSTOMER_MISMATCH = "CUSTOMER_MISMATCH"
    OPERATION_TYPE_MISMATCH = "OPERATION_TYPE_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    OPERATOR_NOT_AUTHORIZED = "OPERATOR_NOT_AUTHORIZED"
    INTENT_NOT_APPROVED = "INTENT_NOT_APPROVED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    CONCURRENT_ATTEMPT_IN_PROGRESS = "CONCURRENT_ATTEMPT_IN_PROGRESS"
    DUPLICATE_REQUEST_SUPPRESSED = "DUPLICATE_REQUEST_SUPPRESSED"
    ATTEMPT_LIMIT_EXCEEDED = "ATTEMPT_LIMIT_EXCEEDED"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    OUTCOME_UNKNOWN_RECONCILING = "OUTCOME_UNKNOWN_RECONCILING"
    CANCELLATION_UNSUPPORTED = "CANCELLATION_UNSUPPORTED"
    PROVIDER_ERROR = "PROVIDER_ERROR"

class AttemptStatus(str, Enum):
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

class ProviderTransactionStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class ReviewCaseStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"

class FaultType(str, Enum):
    NONE = "NONE"
    TIMEOUT_BEFORE_EXECUTION = "TIMEOUT_BEFORE_EXECUTION"
    TIMEOUT_AFTER_EXECUTION = "TIMEOUT_AFTER_EXECUTION"
    SERVICE_OUTAGE = "SERVICE_OUTAGE"
    DELAYED_STATUS = "DELAYED_STATUS"
    FAILED_CANCELLATION = "FAILED_CANCELLATION"
    CORRUPT_AMOUNT = "CORRUPT_AMOUNT"

# --- Authorization Schemas ---
class AuthorizationCreate(BaseModel):
    intent_id: str
    operator_id: str
    customer_id: str
    order_id: str
    operation_type: OperationType = OperationType.REFUND
    authorized_amount: float
    currency: str = "INR"
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED

class AuthorizationResponse(AuthorizationCreate):
    current_state: IntentState = IntentState.AUTHORIZED
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Agent Proposal Schemas ---
class ProposalCreate(BaseModel):
    proposal_id: Optional[str] = None
    intent_id: str
    request_id: str
    operation: OperationType = OperationType.REFUND
    customer_id: str
    order_id: str
    amount: float
    currency: str = "INR"
    agent_id: Optional[str] = "agent-primary"
    rationale: Optional[str] = None

class ProposalResponse(ProposalCreate):
    created_at: datetime

    class Config:
        from_attributes = True

# --- Gateway Decision Schemas ---
class GatewayDecisionResponse(BaseModel):
    decision_id: str
    proposal_id: str
    intent_id: str
    decision: DecisionType
    reason: DecisionReason
    message: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Execution & Attempt Schemas ---
class TransactionAttemptResponse(BaseModel):
    attempt_id: str
    intent_id: str
    provider_request_id: str
    status: AttemptStatus
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Effect Schemas ---
class EffectResponse(BaseModel):
    effect_id: str
    intent_id: str
    attempt_id: Optional[str] = None
    provider_transaction_id: str
    customer_id: str
    order_id: str
    operation: OperationType
    amount: float
    currency: str
    status: ProviderTransactionStatus
    observed_at: datetime

    class Config:
        from_attributes = True

# --- Review Case Schemas ---
class ReviewCaseCreate(BaseModel):
    case_id: Optional[str] = None
    intent_id: str
    reason: str
    discrepancy_amount: float = 0.0
    status: ReviewCaseStatus = ReviewCaseStatus.OPEN
    metadata_json: Optional[Dict[str, Any]] = None

class ReviewCaseResponse(ReviewCaseCreate):
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Mock Payment Request/Response Schemas ---
class PaymentProviderRefundRequest(BaseModel):
    customer_id: str
    order_id: str
    amount: float
    currency: str = "INR"
    idempotency_key: Optional[str] = None
    fault: FaultType = FaultType.NONE

class PaymentProviderRefundResponse(BaseModel):
    refund_id: str
    order_id: str
    customer_id: str
    amount: float
    currency: str
    status: ProviderTransactionStatus
    created_at: datetime

class PaymentProviderAuthRequest(BaseModel):
    customer_id: str
    order_id: str
    amount: float
    currency: str = "INR"
    idempotency_key: Optional[str] = None
    fault: FaultType = FaultType.NONE

class PaymentProviderAuthResponse(BaseModel):
    auth_id: str
    order_id: str
    customer_id: str
    amount: float
    currency: str
    status: ProviderTransactionStatus
    created_at: datetime

class FaultConfig(BaseModel):
    fault_type: FaultType = FaultType.NONE
    delay_seconds: float = 0.0
    target_order_id: Optional[str] = None

# --- Comprehensive Intent History ---
class IntentFullHistory(BaseModel):
    authorization: AuthorizationResponse
    proposals: List[ProposalResponse]
    decisions: List[GatewayDecisionResponse]
    attempts: List[TransactionAttemptResponse]
    effects: List[EffectResponse]
    review_cases: List[ReviewCaseResponse]
    final_state: IntentState
