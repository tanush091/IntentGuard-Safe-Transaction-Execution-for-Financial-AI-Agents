import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.database.models import (
    AuthorizationModel, TransactionAttemptModel, EffectModel,
    ReviewCaseModel, AuditLogModel
)
from src.schemas.types import (
    IntentState, AttemptStatus, ProviderTransactionStatus,
    DecisionType, DecisionReason, ReviewCaseStatus, OperationType
)
from src.gateway.state_machine import TransactionStateMachine
from src.mock_payment.service import payment_service

class ReconciliationResult:
    def __init__(self, resolved: bool, final_state: IntentState, message: str, effect: Optional[EffectModel] = None, discrepancy_amount: float = 0.0):
        self.resolved = resolved
        self.final_state = final_state
        self.message = message
        self.effect = effect
        self.discrepancy_amount = discrepancy_amount

class ReconciliationEngine:
    """
    Reconciles uncertain transaction outcomes against the external payment service.
    """

    @classmethod
    async def reconcile_intent(cls, db: Session, intent_id: str, attempt_id: Optional[str] = None) -> ReconciliationResult:
        auth = db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == intent_id).first()
        if not auth:
            return ReconciliationResult(resolved=False, final_state=IntentState.UNKNOWN, message="Intent not found")

        # Log start of reconciliation
        cls._log_audit(db, intent_id, "RECONCILIATION_STARTED", f"Reconciling intent {intent_id}, current state {auth.current_state}")

        # Transition to RECONCILING if allowed
        if auth.current_state in (IntentState.UNKNOWN.value, IntentState.EXECUTING.value):
            auth.current_state = TransactionStateMachine.transition(
                IntentState(auth.current_state),
                IntentState.RECONCILING,
                "Starting reconciliation check with provider"
            ).value
            db.commit()

        # Step 1: Query external provider for effects on this order
        try:
            if auth.operation_type == OperationType.REFUND.value:
                provider_records = payment_service.list_refunds_by_order(auth.order_id)
            else:
                provider_records = payment_service.list_payment_auths_by_order(auth.order_id)
        except Exception as e:
            # Provider is unreachable (service outage)
            cls._log_audit(db, intent_id, "RECONCILIATION_PROVIDER_UNREACHABLE", str(e))
            return ReconciliationResult(
                resolved=False,
                final_state=IntentState.UNKNOWN,
                message=f"Payment provider unreachable: {str(e)}. Outcome remains UNKNOWN."
            )

        # Step 2: Analyze discovered provider records
        if not provider_records:
            # Evidence: No transaction was recorded by the provider
            cls._log_audit(db, intent_id, "RECONCILIATION_NO_EFFECT_FOUND", "Provider confirmed 0 transactions for this order.")

            # Update attempt status if provided
            if attempt_id:
                attempt = db.query(TransactionAttemptModel).filter(TransactionAttemptModel.attempt_id == attempt_id).first()
                if attempt:
                    attempt.status = AttemptStatus.TIMEOUT.value
                    attempt.completed_at = datetime.utcnow()
                    attempt.error_message = "No provider effect found during reconciliation."

            # Safe for a controlled retry if attempts limit not exceeded
            attempt_count = db.query(TransactionAttemptModel).filter(TransactionAttemptModel.intent_id == intent_id).count()
            if attempt_count < 3:
                auth.current_state = IntentState.VALIDATED.value
                db.commit()
                return ReconciliationResult(
                    resolved=True,
                    final_state=IntentState.VALIDATED,
                    message="Confirmed transaction did not execute at provider. Permitted controlled retry."
                )
            else:
                auth.current_state = IntentState.ESCALATED.value
                review_case = ReviewCaseModel(
                    case_id=f"case_{uuid.uuid4().hex[:12]}",
                    intent_id=intent_id,
                    reason="ATTEMPT_LIMIT_EXCEEDED_AFTER_RECONCILIATION",
                    discrepancy_amount=0.0,
                    status=ReviewCaseStatus.OPEN.value
                )
                db.add(review_case)
                db.commit()
                return ReconciliationResult(
                    resolved=False,
                    final_state=IntentState.ESCALATED,
                    message="Attempt limit exceeded without effect. Escalated to human review."
                )

        # There are transactions on provider side!
        for rec in provider_records:
            tx_id = getattr(rec, "refund_id", None) or getattr(rec, "auth_id", None)

            # Check if this effect is already logged in our effects table
            existing_effect = db.query(EffectModel).filter(
                EffectModel.provider_transaction_id == tx_id
            ).first()

            if not existing_effect:
                # Add to durable effects ledger!
                existing_effect = EffectModel(
                    effect_id=f"eff_{uuid.uuid4().hex[:12]}",
                    intent_id=intent_id,
                    attempt_id=attempt_id,
                    provider_transaction_id=tx_id,
                    customer_id=rec.customer_id,
                    order_id=rec.order_id,
                    operation=auth.operation_type,
                    amount=rec.amount,
                    currency=rec.currency,
                    status=rec.status.value,
                    observed_at=datetime.utcnow()
                )
                db.add(existing_effect)
                db.flush()

            # Check matching correctness
            amount_matches = abs(rec.amount - auth.authorized_amount) < 0.001
            customer_matches = (rec.customer_id == auth.customer_id)

            if not amount_matches or not customer_matches:
                # Discrepancy! Provider executed a mismatched transaction!
                discrepancy = abs(rec.amount - auth.authorized_amount)
                auth.current_state = IntentState.ESCALATED.value
                review_case = ReviewCaseModel(
                    case_id=f"case_{uuid.uuid4().hex[:12]}",
                    intent_id=intent_id,
                    reason=f"DISCREPANCY_DETECTED: Provider record {tx_id} had amount {rec.amount} vs authorized {auth.authorized_amount}",
                    discrepancy_amount=discrepancy,
                    status=ReviewCaseStatus.OPEN.value
                )
                db.add(review_case)
                db.commit()
                cls._log_audit(db, intent_id, "DISCREPANCY_ESCALATED", f"Discrepancy of {discrepancy} on tx {tx_id}")
                return ReconciliationResult(
                    resolved=False,
                    final_state=IntentState.ESCALATED,
                    message=f"Discrepancy detected at provider: amount {rec.amount} vs authorized {auth.authorized_amount}. Escalated.",
                    effect=existing_effect,
                    discrepancy_amount=discrepancy
                )

            # Status check
            if rec.status == ProviderTransactionStatus.COMPLETED:
                auth.current_state = IntentState.COMPLETED.value
                if attempt_id:
                    attempt = db.query(TransactionAttemptModel).filter(TransactionAttemptModel.attempt_id == attempt_id).first()
                    if attempt:
                        attempt.status = AttemptStatus.SUCCESS.value
                        attempt.completed_at = datetime.utcnow()
                db.commit()
                cls._log_audit(db, intent_id, "RECONCILIATION_VERIFIED_COMPLETED", f"Verified provider effect {tx_id}")
                return ReconciliationResult(
                    resolved=True,
                    final_state=IntentState.COMPLETED,
                    message=f"Successfully verified provider completed transaction {tx_id}. Intent marked COMPLETED.",
                    effect=existing_effect
                )

            elif rec.status == ProviderTransactionStatus.PENDING:
                # If pending and we need to cancel, or if delayed status
                cls._log_audit(db, intent_id, "RECONCILIATION_PENDING", f"Transaction {tx_id} is currently PENDING at provider.")
                # We leave as RECONCILING or check recovery policy
                db.commit()
                return ReconciliationResult(
                    resolved=False,
                    final_state=IntentState.RECONCILING,
                    message=f"Transaction {tx_id} is still PENDING at provider. Waiting for status resolution.",
                    effect=existing_effect
                )

            elif rec.status == ProviderTransactionStatus.CANCELLED:
                auth.current_state = IntentState.CANCELLED.value
                db.commit()
                cls._log_audit(db, intent_id, "RECONCILIATION_CANCELLED", f"Transaction {tx_id} is CANCELLED at provider.")
                return ReconciliationResult(
                    resolved=True,
                    final_state=IntentState.CANCELLED,
                    message=f"Transaction {tx_id} was CANCELLED at provider.",
                    effect=existing_effect
                )

        db.commit()
        return ReconciliationResult(resolved=False, final_state=IntentState(auth.current_state), message="Reconciliation cycle finished without definitive state change.")

    @staticmethod
    def _log_audit(db: Session, intent_id: str, event_type: str, event_data: str):
        log = AuditLogModel(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            intent_id=intent_id,
            event_type=event_type,
            event_data=event_data,
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
