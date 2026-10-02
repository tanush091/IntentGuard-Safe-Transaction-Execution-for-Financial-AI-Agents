"""
API Routes for AI Agent Transaction Proposals and Gateway Safety Execution.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.schemas.proposal import AgentProposal, GatewayEvaluationResult
from backend.app.services.authorization_service import AuthorizationService
from backend.app.services.gateway_service import GatewayService
from backend.app.services.execution_service import ExecutionService

router = APIRouter(prefix="/api/proposals", tags=["Proposals & Safety Gateway"])


@router.post("", response_model=GatewayEvaluationResult)
def submit_proposal(proposal: AgentProposal, db: Session = Depends(get_db)):
    """
    Submit an AI agent's structured proposal to the Safety Gateway.
    Evaluates all 10 checks and, if approved, dispatches execution.
    """
    intent = AuthorizationService.get_intent(db, proposal.intent_id)
    if not intent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent '{proposal.intent_id}' not found. Cannot evaluate proposal without durable authorization."
        )

    # Step 1: Pre-Execution Safety Gateway Evaluation (10 checks)
    eval_result = GatewayService.evaluate_proposal(db, intent, proposal)
    if eval_result.decision == "BLOCKED":
        return eval_result

    # Step 2: Dispatch Execution to Mock Payment Simulator
    return ExecutionService.execute_approved_proposal(db, intent, proposal)
