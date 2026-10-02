"""
Intent-Consistency Safety Gateway Evaluation Engine.
Executes the deterministic 10-point pre-execution validation checks.
"""

from typing import List, Tuple
from sqlalchemy.orm import Session
import httpx

from backend.app.config import settings
from backend.app.models.intent import IntentModel
from backend.app.schemas.proposal import AgentProposal, GatewayEvaluationResult
from backend.app.services.idempotency_service import IdempotencyService
from backend.app.services.audit_service import AuditService
from backend.app.state_machine.transaction_state_machine import TransactionStateMachine


class GatewayService:
    @staticmethod
    def evaluate_proposal(db: Session, intent: IntentModel, proposal: AgentProposal) -> GatewayEvaluationResult:
        passed_checks: List[str] = []
        failed_checks: List[str] = []

        # Check 1: Customer identification match
        if proposal.customer_id == intent.customer_id:
            passed_checks.append("CHECK_1_CUSTOMER_MATCH")
        else:
            failed_checks.append(f"CHECK_1_CUSTOMER_MISMATCH (Proposed: {proposal.customer_id}, Authorized: {intent.customer_id})")

        # Check 2: Target order association match
        if proposal.order_id == intent.order_id:
            passed_checks.append("CHECK_2_ORDER_MATCH")
        else:
            failed_checks.append(f"CHECK_2_ORDER_MISMATCH (Proposed: {proposal.order_id}, Authorized: {intent.order_id})")

        # Check 3: Financial operation type match
        prop_op = proposal.operation.value if hasattr(proposal.operation, "value") else str(proposal.operation)
        if prop_op == intent.operation_type:
            passed_checks.append("CHECK_3_OPERATION_MATCH")
        else:
            failed_checks.append(f"CHECK_3_OPERATION_MISMATCH (Proposed: {prop_op}, Authorized: {intent.operation_type})")

        # Check 4: Exact amount conformity
        if abs(float(proposal.amount) - float(intent.authorized_amount)) < 0.001:
            passed_checks.append("CHECK_4_AMOUNT_CONFORMITY")
        else:
            failed_checks.append(f"CHECK_4_AMOUNT_MISMATCH (Proposed: {proposal.amount:.2f}, Authorized: {intent.authorized_amount:.2f})")

        # Check 5: Currency ISO-4217 code match
        if proposal.currency.upper() == intent.currency.upper():
            passed_checks.append("CHECK_5_CURRENCY_MATCH")
        else:
            failed_checks.append(f"CHECK_5_CURRENCY_MISMATCH (Proposed: {proposal.currency}, Authorized: {intent.currency})")

        # Check 6: Operator authorization status
        if intent.approval_status == "APPROVED" and not intent.operator_id.startswith("REVOKED"):
            passed_checks.append("CHECK_6_OPERATOR_AUTHORIZATION")
        else:
            failed_checks.append(f"CHECK_6_OPERATOR_UNAUTHORIZED (Status: {intent.approval_status}, Operator: {intent.operator_id})")

        # Check 7: Duplicate completed effect in ledger
        existing_completed = IdempotencyService.get_completed_effect(db, intent.id)
        if not existing_completed:
            passed_checks.append("CHECK_7_NO_DUPLICATE_EFFECT")
        else:
            failed_checks.append(f"CHECK_7_DUPLICATE_EFFECT_EXISTS (Provider Ref: {existing_completed.provider_reference})")

        # Check 8: Concurrent in-flight attempt lock
        active_attempt = IdempotencyService.get_active_attempt(db, intent.id)
        if not active_attempt:
            passed_checks.append("CHECK_8_NO_CONCURRENT_ATTEMPT")
        else:
            failed_checks.append(f"CHECK_8_CONCURRENT_ATTEMPT_ACTIVE (Attempt ID: {active_attempt.id}, Status: {active_attempt.status})")

        # Check 9: Existing settled effect on external provider or order
        order_effect = IdempotencyService.get_order_effect(db, intent.order_id)
        if not order_effect or order_effect.intent_id == intent.id:
            passed_checks.append("CHECK_9_NO_UNLINKED_PROVIDER_EFFECT")
        else:
            failed_checks.append(f"CHECK_9_ORDER_ALREADY_SETTLED (Settled by Intent: {order_effect.intent_id})")

        # Check 10: Finite state machine transition validity
        is_fsm_valid = (
            TransactionStateMachine.is_legal(intent.current_state, "PROPOSED") or
            TransactionStateMachine.is_legal(intent.current_state, "APPROVED") or
            intent.current_state in ["AUTHORIZED", "PROPOSED", "RETRY_ALLOWED"]
        )
        if is_fsm_valid and not TransactionStateMachine.is_terminal(intent.current_state):
            passed_checks.append("CHECK_10_STATE_MACHINE_VALID")
        else:
            failed_checks.append(f"CHECK_10_INVALID_STATE (Current: {intent.current_state})")

        # Decision formulation
        if not failed_checks:
            reason = "Proposal verified and approved across all 10 safety gateway checks."
            AuditService.record_event(
                db=db,
                intent_id=intent.id,
                event_type="PROPOSAL_EVALUATION",
                decision="APPROVED",
                reason=reason,
                event_data={"passed": passed_checks}
            )
            return GatewayEvaluationResult(
                intent_id=intent.id,
                decision="APPROVED",
                current_state="APPROVED",
                reason=reason,
                checks_passed=passed_checks,
                checks_failed=[]
            )
        else:
            reason = f"Gateway BLOCKED proposal: {'; '.join(failed_checks)}"
            # Update intent state to BLOCKED if legal
            if TransactionStateMachine.is_legal(intent.current_state, "BLOCKED"):
                intent.current_state = "BLOCKED"
                db.commit()

            AuditService.record_event(
                db=db,
                intent_id=intent.id,
                event_type="PROPOSAL_EVALUATION",
                decision="BLOCKED",
                reason=reason,
                event_data={"passed": passed_checks, "failed": failed_checks}
            )
            return GatewayEvaluationResult(
                intent_id=intent.id,
                decision="BLOCKED",
                current_state=intent.current_state,
                reason=reason,
                checks_passed=passed_checks,
                checks_failed=failed_checks
            )
