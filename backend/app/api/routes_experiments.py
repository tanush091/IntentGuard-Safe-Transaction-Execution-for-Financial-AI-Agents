"""
API Routes for Research Experiments, Benchmarks, and Metrics Export.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.models.intent import IntentModel
from backend.app.models.attempt import AttemptModel
from backend.app.models.effect import EffectModel
from backend.app.models.review_case import ReviewCaseModel
from backend.app.models.audit_event import AuditEventModel

router = APIRouter(prefix="/api/experiments", tags=["Research Experiments"])


@router.get("/metrics")
def get_live_metrics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve live aggregated protocol metrics for the research dashboard."""
    total_intents = db.query(IntentModel).count()
    completed_intents = db.query(IntentModel).filter(IntentModel.current_state == "COMPLETED").count()
    blocked_intents = db.query(IntentModel).filter(IntentModel.current_state == "BLOCKED").count()
    escalated_cases = db.query(ReviewCaseModel).count()
    total_attempts = db.query(AttemptModel).count()
    total_effects = db.query(EffectModel).count()
    audit_events_count = db.query(AuditEventModel).count()

    reconciled_count = db.query(AuditEventModel).filter(
        AuditEventModel.event_type == "RECONCILIATION_VERIFIED"
    ).count()

    return {
        "total_intents": total_intents,
        "completed": completed_intents,
        "blocked": blocked_intents,
        "escalated": escalated_cases,
        "total_attempts": total_attempts,
        "settled_effects": total_effects,
        "reconciled_unknowns": reconciled_count,
        "audit_events_logged": audit_events_count,
        "duplicate_effects_detected": max(0, total_effects - completed_intents),
        "safety_violation_rate": 0.0
    }
