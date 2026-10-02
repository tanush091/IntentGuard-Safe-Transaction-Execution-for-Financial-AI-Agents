from typing import Optional, Tuple
from sqlalchemy.orm import Session
from src.database.models import AuthorizationModel, EffectModel, TransactionAttemptModel
from src.schemas.types import (
    ProposalCreate, DecisionType, DecisionReason,
    ApprovalStatus, IntentState, AttemptStatus, ProviderTransactionStatus
)
from src.config import settings

class ValidationResult:
    def __init__(self, is_valid: bool, decision: DecisionType, reason: DecisionReason, message: str):
        self.is_valid = is_valid
        self.decision = decision
        self.reason = reason
        self.message = message

class GatewayValidator:
    """
    Validates agent proposals against durable authorization records and historical effects.
    """

    @classmethod
    def validate_proposal(cls, db: Session, proposal: ProposalCreate, auth: AuthorizationModel) -> ValidationResult:
        # 1. Approval status check
        if auth.approval_status != ApprovalStatus.APPROVED.value:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.INTENT_NOT_APPROVED,
                message=f"Intent {auth.intent_id} is in status {auth.approval_status}, not APPROVED."
            )

        # 2. Check if intent already completed
        if auth.current_state == IntentState.COMPLETED.value:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.ALREADY_COMPLETED,
                message=f"Intent {auth.intent_id} has already executed and completed its authorized financial effect."
            )

        # Check durable effects table for already completed effect for this intent or order
        prior_completed_effect = db.query(EffectModel).filter(
            EffectModel.intent_id == auth.intent_id,
            EffectModel.status == ProviderTransactionStatus.COMPLETED.value
        ).first()

        if prior_completed_effect:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.DUPLICATE_REQUEST_SUPPRESSED,
                message=f"Intent {auth.intent_id} already has a verified provider effect: {prior_completed_effect.effect_id}."
            )

        # 3. Customer match
        if proposal.customer_id != auth.customer_id:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.CUSTOMER_MISMATCH,
                message=f"Proposed customer '{proposal.customer_id}' does not match authorized customer '{auth.customer_id}'."
            )

        # 4. Order match
        if proposal.order_id != auth.order_id:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.ORDER_MISMATCH,
                message=f"Proposed order '{proposal.order_id}' does not match authorized order '{auth.order_id}'."
            )

        # 5. Operation type match
        if proposal.operation.value != auth.operation_type:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.OPERATION_TYPE_MISMATCH,
                message=f"Proposed operation '{proposal.operation.value}' does not match authorized operation '{auth.operation_type}'."
            )

        # 6. Currency match
        if proposal.currency.upper() != auth.currency.upper():
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.CURRENCY_MISMATCH,
                message=f"Proposed currency '{proposal.currency}' does not match authorized currency '{auth.currency}'."
            )

        # 7. Amount check (must be positive and not exceed authorized amount)
        if proposal.amount <= 0:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.AMOUNT_EXCEEDS_AUTHORIZATION,
                message=f"Proposed amount {proposal.amount} is invalid (must be > 0)."
            )

        if proposal.amount > auth.authorized_amount:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.AMOUNT_EXCEEDS_AUTHORIZATION,
                message=f"Proposed amount {proposal.amount} {proposal.currency} exceeds authorized amount {auth.authorized_amount} {auth.currency}."
            )

        # 8. Concurrent attempt check
        in_flight_attempt = db.query(TransactionAttemptModel).filter(
            TransactionAttemptModel.intent_id == auth.intent_id,
            TransactionAttemptModel.status == AttemptStatus.IN_FLIGHT.value
        ).first()

        if in_flight_attempt:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.CONCURRENT_ATTEMPT_IN_PROGRESS,
                message=f"Attempt {in_flight_attempt.attempt_id} is currently in-flight for intent {auth.intent_id}."
            )

        # 9. Attempt limit check
        prior_attempts_count = db.query(TransactionAttemptModel).filter(
            TransactionAttemptModel.intent_id == auth.intent_id
        ).count()

        if prior_attempts_count >= settings.MAX_ATTEMPTS_PER_INTENT:
            return ValidationResult(
                is_valid=False,
                decision=DecisionType.BLOCK,
                reason=DecisionReason.ATTEMPT_LIMIT_EXCEEDED,
                message=f"Intent {auth.intent_id} has reached the maximum attempt limit ({settings.MAX_ATTEMPTS_PER_INTENT})."
            )

        return ValidationResult(
            is_valid=True,
            decision=DecisionType.ALLOW,
            reason=DecisionReason.VALID,
            message="Proposal strictly matches durable authorization."
        )
