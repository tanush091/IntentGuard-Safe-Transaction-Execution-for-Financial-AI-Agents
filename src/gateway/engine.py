import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException

from src.database.models import (
    AuthorizationModel, AgentProposalModel, GatewayDecisionModel,
    TransactionAttemptModel, EffectModel, ReviewCaseModel, AuditLogModel
)
from src.schemas.types import (
    AuthorizationCreate, ProposalCreate, DecisionType, DecisionReason,
    IntentState, AttemptStatus, ProviderTransactionStatus,
    PaymentProviderRefundRequest, PaymentProviderAuthRequest,
    OperationType, FaultType
)
from src.gateway.validator import GatewayValidator
from src.gateway.state_machine import TransactionStateMachine
from src.gateway.reconciliation import ReconciliationEngine
from src.gateway.recovery import RecoveryPolicyEngine
from src.mock_payment.service import payment_service

logger = logging.getLogger("IntentGuard.Gateway")

class GatewayEngine:
    def __init__(self, db: Session):
        self.db = db

    def create_authorization(self, data: AuthorizationCreate) -> AuthorizationModel:
        existing = self.db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == data.intent_id).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Intent {data.intent_id} already exists.")

        auth = AuthorizationModel(
            intent_id=data.intent_id,
            operator_id=data.operator_id,
            customer_id=data.customer_id,
            order_id=data.order_id,
            operation_type=data.operation_type.value,
            authorized_amount=data.authorized_amount,
            currency=data.currency.upper(),
            approval_status=data.approval_status.value,
            current_state=IntentState.AUTHORIZED.value,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.db.add(auth)
        self.db.commit()
        self.db.refresh(auth)

        self._audit(auth.intent_id, "AUTHORIZATION_CREATED", f"Authorized {data.operation_type.value} of {data.authorized_amount} {data.currency} for {data.order_id}")
        return auth

    async def process_proposal(self, proposal: ProposalCreate, simulated_fault: Optional[FaultType] = None) -> Dict[str, Any]:
        auth = self.db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == proposal.intent_id).with_for_update().first()
        if not auth:
            return {
                "decision": DecisionType.BLOCK,
                "reason": DecisionReason.INTENT_NOT_APPROVED,
                "message": f"Authorization record for intent {proposal.intent_id} not found.",
                "intent_id": proposal.intent_id,
                "proposal_id": proposal.proposal_id or "unknown"
            }

        # 1. Record proposal
        proposal_id = proposal.proposal_id or f"prop_{uuid.uuid4().hex[:12]}"
        proposal_model = AgentProposalModel(
            proposal_id=proposal_id,
            intent_id=proposal.intent_id,
            request_id=proposal.request_id,
            operation=proposal.operation.value,
            customer_id=proposal.customer_id,
            order_id=proposal.order_id,
            amount=proposal.amount,
            currency=proposal.currency,
            agent_id=proposal.agent_id or "agent-primary",
            rationale=proposal.rationale,
            created_at=datetime.utcnow()
        )
        self.db.add(proposal_model)

        # Transition state to PROPOSED if currently AUTHORIZED or BLOCKED
        if auth.current_state in (IntentState.AUTHORIZED.value, IntentState.BLOCKED.value):
            auth.current_state = IntentState.PROPOSED.value

        self.db.commit()

        # 2. Validate proposal against durable authorization
        validation = GatewayValidator.validate_proposal(self.db, proposal, auth)

        # 3. Record decision in DB BEFORE any external execution
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        decision_model = GatewayDecisionModel(
            decision_id=decision_id,
            proposal_id=proposal_id,
            intent_id=proposal.intent_id,
            decision=validation.decision.value,
            reason=validation.reason.value,
            message=validation.message,
            created_at=datetime.utcnow()
        )
        self.db.add(decision_model)
        self.db.commit()

        self._audit(auth.intent_id, f"DECISION_{validation.decision.value}", f"Reason: {validation.reason.value}. {validation.message}")

        if not validation.is_valid:
            if auth.current_state != IntentState.COMPLETED.value:
                auth.current_state = IntentState.BLOCKED.value
                self.db.commit()
            return {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "intent_id": proposal.intent_id,
                "decision": validation.decision,
                "reason": validation.reason,
                "message": validation.message,
                "current_state": auth.current_state
            }

        # 4. Proceed to Execution
        auth.current_state = TransactionStateMachine.transition(
            IntentState(auth.current_state),
            IntentState.EXECUTING,
            "Proposal validated. Transitioning to EXECUTING."
        ).value
        self.db.commit()

        # Generate attempt record
        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        # Durable intent-anchored idempotency key
        idempotency_key = f"idem_{auth.intent_id}"

        attempt_model = TransactionAttemptModel(
            attempt_id=attempt_id,
            intent_id=auth.intent_id,
            provider_request_id=f"req_{proposal.request_id}",
            idempotency_key=idempotency_key,
            status=AttemptStatus.IN_FLIGHT.value,
            started_at=datetime.utcnow()
        )
        self.db.add(attempt_model)
        self.db.commit()

        self._audit(auth.intent_id, "EXECUTION_ATTEMPT_STARTED", f"Attempt {attempt_id} dispatched to payment provider.")

        # 5. Call external payment service
        try:
            if auth.operation_type == OperationType.REFUND.value:
                req_obj = PaymentProviderRefundRequest(
                    customer_id=proposal.customer_id,
                    order_id=proposal.order_id,
                    amount=proposal.amount,
                    currency=proposal.currency,
                    idempotency_key=idempotency_key,
                    fault=simulated_fault or FaultType.NONE
                )
                provider_resp = await payment_service.process_refund(req_obj)
                tx_id = provider_resp.refund_id
            else:
                req_obj = PaymentProviderAuthRequest(
                    customer_id=proposal.customer_id,
                    order_id=proposal.order_id,
                    amount=proposal.amount,
                    currency=proposal.currency,
                    idempotency_key=idempotency_key,
                    fault=simulated_fault or FaultType.NONE
                )
                provider_resp = await payment_service.process_payment_auth(req_obj)
                tx_id = provider_resp.auth_id

            # Step 5: Verify external effect against authorization
            attempt_model.completed_at = datetime.utcnow()

            # Record durable effect in effects ledger
            effect_id = f"eff_{uuid.uuid4().hex[:12]}"
            effect_model = EffectModel(
                effect_id=effect_id,
                intent_id=auth.intent_id,
                attempt_id=attempt_id,
                provider_transaction_id=tx_id,
                customer_id=provider_resp.customer_id,
                order_id=provider_resp.order_id,
                operation=auth.operation_type,
                amount=provider_resp.amount,
                currency=provider_resp.currency,
                status=provider_resp.status.value,
                observed_at=datetime.utcnow()
            )
            self.db.add(effect_model)

            # Check for financial discrepancy in observed effect
            amount_diff = abs(provider_resp.amount - auth.authorized_amount)
            if amount_diff > 0.001 or provider_resp.order_id != auth.order_id:
                # Discrepancy detected! Provider returned an unauthorized financial effect.
                attempt_model.status = AttemptStatus.FAILED.value
                attempt_model.error_message = f"Discrepancy: Provider executed {provider_resp.amount} vs authorized {auth.authorized_amount}"
                auth.current_state = IntentState.ESCALATED.value

                review_case = ReviewCaseModel(
                    case_id=f"case_{uuid.uuid4().hex[:12]}",
                    intent_id=auth.intent_id,
                    reason=f"DISCREPANCY_DETECTED: Provider executed {provider_resp.amount} {provider_resp.currency} for order {provider_resp.order_id}, but {auth.authorized_amount} {auth.currency} was authorized.",
                    discrepancy_amount=amount_diff,
                    status=ReviewCaseStatus.OPEN.value
                )
                self.db.add(review_case)
                self.db.commit()

                self._audit(auth.intent_id, "DISCREPANCY_ESCALATED", f"Discrepancy of {amount_diff} observed on tx {tx_id}. Escalated.")

                return {
                    "decision_id": decision_id,
                    "proposal_id": proposal_id,
                    "intent_id": proposal.intent_id,
                    "attempt_id": attempt_id,
                    "decision": DecisionType.ESCALATE,
                    "reason": DecisionReason.DISCREPANCY_DETECTED,
                    "message": f"Financial discrepancy detected: executed {provider_resp.amount} vs authorized {auth.authorized_amount}. Escalated to human review.",
                    "provider_transaction_id": tx_id,
                    "current_state": auth.current_state
                }

            # If verified correctly:
            attempt_model.status = AttemptStatus.SUCCESS.value
            auth.current_state = IntentState.COMPLETED.value
            self.db.commit()

            self._audit(auth.intent_id, "TRANSACTION_COMPLETED", f"Provider transaction {tx_id} completed and verified successfully.")

            return {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "intent_id": proposal.intent_id,
                "attempt_id": attempt_id,
                "decision": DecisionType.ALLOW,
                "reason": DecisionReason.VALID,
                "message": f"Transaction completed successfully. Provider ID: {tx_id}",
                "provider_transaction_id": tx_id,
                "current_state": auth.current_state
            }

        except HTTPException as http_err:
            # Handle simulated provider faults (504 timeout, 503 outage, etc.)
            logger.warning(f"Provider call returned HTTP error: {http_err.status_code} - {http_err.detail}")
            attempt_model.status = AttemptStatus.UNKNOWN.value
            attempt_model.error_message = f"HTTP {http_err.status_code}: {http_err.detail}"
            auth.current_state = IntentState.UNKNOWN.value
            self.db.commit()

            self._audit(auth.intent_id, "TRANSACTION_UNKNOWN", f"Outcome unknown due to error: {http_err.detail}. Triggering reconciliation.")

            # RECONCILIATION PHASE: Active verification against provider ground truth
            recon_result = await ReconciliationEngine.reconcile_intent(self.db, auth.intent_id, attempt_id)

            return {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "intent_id": proposal.intent_id,
                "attempt_id": attempt_id,
                "decision": DecisionType.HOLD if recon_result.final_state in (IntentState.UNKNOWN, IntentState.ESCALATED) else DecisionType.ALLOW,
                "reason": DecisionReason.OUTCOME_UNKNOWN_RECONCILING,
                "message": f"Network outcome was uncertain. Reconciliation performed: {recon_result.message}",
                "reconciliation": {
                    "resolved": recon_result.resolved,
                    "final_state": recon_result.final_state.value,
                    "discrepancy": recon_result.discrepancy_amount
                },
                "current_state": auth.current_state
            }

        except Exception as ex:
            # Catch unexpected network or runtime exceptions
            attempt_model.status = AttemptStatus.FAILED.value
            attempt_model.error_message = str(ex)
            auth.current_state = IntentState.UNKNOWN.value
            self.db.commit()

            recon_result = await ReconciliationEngine.reconcile_intent(self.db, auth.intent_id, attempt_id)
            return {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "intent_id": proposal.intent_id,
                "attempt_id": attempt_id,
                "decision": DecisionType.HOLD,
                "reason": DecisionReason.PROVIDER_ERROR,
                "message": f"Unexpected execution failure: {str(ex)}. Reconciled: {recon_result.message}",
                "current_state": auth.current_state
            }

    def _audit(self, intent_id: str, event_type: str, event_data: str):
        log = AuditLogModel(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            intent_id=intent_id,
            event_type=event_type,
            event_data=event_data,
            created_at=datetime.utcnow()
        )
        self.db.add(log)
        self.db.commit()
