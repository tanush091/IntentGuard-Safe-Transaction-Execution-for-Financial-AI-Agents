from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database.connection import get_db, init_db
from src.database.models import (
    AuthorizationModel, AgentProposalModel, GatewayDecisionModel,
    TransactionAttemptModel, EffectModel, ReviewCaseModel, AuditLogModel
)
from src.schemas.types import (
    AuthorizationCreate, AuthorizationResponse,
    ProposalCreate, GatewayDecisionResponse,
    TransactionAttemptResponse, EffectResponse,
    ReviewCaseResponse, ReviewCaseStatus, IntentFullHistory,
    FaultType
)
from src.gateway.engine import GatewayEngine
from src.gateway.reconciliation import ReconciliationEngine
from src.gateway.recovery import RecoveryPolicyEngine

# Initialize database
init_db()

app = FastAPI(
    title="IntentGuard Safety Gateway",
    description="Intent-Consistent Transaction Execution and Recovery Gateway for Financial AI Agents",
    version="1.0.0"
)

@app.post("/authorizations", response_model=AuthorizationResponse, tags=["Authorizations"])
def create_authorization(data: AuthorizationCreate, db: Session = Depends(get_db)):
    engine = GatewayEngine(db)
    auth = engine.create_authorization(data)
    return auth

@app.get("/authorizations/{intent_id}", response_model=AuthorizationResponse, tags=["Authorizations"])
def get_authorization(intent_id: str, db: Session = Depends(get_db)):
    auth = db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == intent_id).first()
    if not auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    return auth

@app.get("/authorizations", response_model=List[AuthorizationResponse], tags=["Authorizations"])
def list_authorizations(db: Session = Depends(get_db)):
    return db.query(AuthorizationModel).order_by(AuthorizationModel.created_at.desc()).all()

@app.post("/proposals", tags=["Proposals & Execution"])
async def submit_proposal(
    proposal: ProposalCreate,
    simulated_fault: Optional[FaultType] = Query(None),
    db: Session = Depends(get_db)
):
    engine = GatewayEngine(db)
    result = await engine.process_proposal(proposal, simulated_fault=simulated_fault)
    return result

@app.get("/intents/{intent_id}/history", response_model=IntentFullHistory, tags=["History & Audit"])
def get_intent_history(intent_id: str, db: Session = Depends(get_db)):
    auth = db.query(AuthorizationModel).filter(AuthorizationModel.intent_id == intent_id).first()
    if not auth:
        raise HTTPException(status_code=404, detail="Intent not found")

    proposals = db.query(AgentProposalModel).filter(AgentProposalModel.intent_id == intent_id).order_by(AgentProposalModel.created_at.asc()).all()
    decisions = db.query(GatewayDecisionModel).filter(GatewayDecisionModel.intent_id == intent_id).order_by(GatewayDecisionModel.created_at.asc()).all()
    attempts = db.query(TransactionAttemptModel).filter(TransactionAttemptModel.intent_id == intent_id).order_by(TransactionAttemptModel.started_at.asc()).all()
    effects = db.query(EffectModel).filter(EffectModel.intent_id == intent_id).order_by(EffectModel.observed_at.asc()).all()
    review_cases = db.query(ReviewCaseModel).filter(ReviewCaseModel.intent_id == intent_id).order_by(ReviewCaseModel.created_at.asc()).all()

    return IntentFullHistory(
        authorization=auth,
        proposals=proposals,
        decisions=decisions,
        attempts=attempts,
        effects=effects,
        review_cases=review_cases,
        final_state=auth.current_state
    )

@app.post("/attempts/{attempt_id}/reconcile", tags=["Reconciliation"])
async def reconcile_attempt(attempt_id: str, db: Session = Depends(get_db)):
    attempt = db.query(TransactionAttemptModel).filter(TransactionAttemptModel.attempt_id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    result = await ReconciliationEngine.reconcile_intent(db, attempt.intent_id, attempt_id)
    return {
        "attempt_id": attempt_id,
        "intent_id": attempt.intent_id,
        "resolved": result.resolved,
        "final_state": result.final_state.value,
        "message": result.message,
        "discrepancy_amount": result.discrepancy_amount
    }

@app.get("/review-cases", response_model=List[ReviewCaseResponse], tags=["Review Cases"])
def list_review_cases(status: Optional[ReviewCaseStatus] = Query(None), db: Session = Depends(get_db)):
    q = db.query(ReviewCaseModel)
    if status:
        q = q.filter(ReviewCaseModel.status == status.value)
    return q.order_by(ReviewCaseModel.created_at.desc()).all()

@app.post("/review-cases/{case_id}/resolve", tags=["Review Cases"])
def resolve_review_case(case_id: str, resolution: str = "RESOLVED", db: Session = Depends(get_db)):
    case = db.query(ReviewCaseModel).filter(ReviewCaseModel.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Review case not found")
    case.status = ReviewCaseStatus.RESOLVED.value
    case.resolved_at = datetime.utcnow()
    db.commit()
    return {"status": "case_resolved", "case_id": case_id}

@app.get("/effects", response_model=List[EffectResponse], tags=["Effects Ledger"])
def list_effects(order_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(EffectModel)
    if order_id:
        q = q.filter(EffectModel.order_id == order_id)
    return q.order_by(EffectModel.observed_at.desc()).all()

@app.get("/audit-logs", tags=["History & Audit"])
def list_audit_logs(intent_id: Optional[str] = Query(None), limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(AuditLogModel)
    if intent_id:
        q = q.filter(AuditLogModel.intent_id == intent_id)
    return q.order_by(AuditLogModel.created_at.desc()).limit(limit).all()

@app.post("/recovery/cancel", tags=["Recovery Policies"])
async def trigger_cancel_recovery(intent_id: str, provider_tx_id: str, db: Session = Depends(get_db)):
    success = await RecoveryPolicyEngine.recover_pending_transaction(db, intent_id, provider_tx_id)
    return {"intent_id": intent_id, "provider_tx_id": provider_tx_id, "recovery_successful": success}

# Observability Dashboard Endpoints
import os
import json
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

dashboard_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="static")

@app.get("/", tags=["Dashboard"])
def get_dashboard():
    index_file = os.path.join(dashboard_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "IntentGuard Gateway API online. Dashboard assets not found."}

@app.get("/api/benchmark-results", tags=["Dashboard"])
def get_benchmark_results():
    benchmark_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "benchmark_results.json"))
    if not os.path.exists(benchmark_file):
        benchmark_file = "benchmark_results.json"

    if os.path.exists(benchmark_file):
        with open(benchmark_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Benchmark results not yet generated. Run 'python run_benchmark.py'"}

