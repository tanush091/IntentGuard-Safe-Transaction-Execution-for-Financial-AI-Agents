"""
API Routes for Inspecting Attempts, Effects, and Immutable Audit Trails.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.models.attempt import AttemptModel
from backend.app.models.effect import EffectModel
from backend.app.models.audit_event import AuditEventModel
from backend.app.schemas.transaction import AttemptResponse, EffectResponse, AuditEventResponse

router = APIRouter(prefix="/api/transactions", tags=["Transactions & Ledgers"])


@router.get("/intents/{intent_id}/attempts", response_model=List[AttemptResponse])
def get_intent_attempts(intent_id: str, db: Session = Depends(get_db)):
    """Fetch all physical execution attempts associated with an intent."""
    return db.query(AttemptModel).filter(
        AttemptModel.intent_id == intent_id
    ).order_by(AttemptModel.attempt_number.asc()).all()


@router.get("/intents/{intent_id}/effects", response_model=List[EffectResponse])
def get_intent_effects(intent_id: str, db: Session = Depends(get_db)):
    """Fetch observed external financial effects linked to an intent."""
    return db.query(EffectModel).filter(
        EffectModel.intent_id == intent_id
    ).order_by(EffectModel.observed_at.desc()).all()


@router.get("/intents/{intent_id}/audit-trail", response_model=List[AuditEventResponse])
def get_intent_audit_trail(intent_id: str, db: Session = Depends(get_db)):
    """Fetch the chronological, append-only security audit log for an intent."""
    return db.query(AuditEventModel).filter(
        AuditEventModel.intent_id == intent_id
    ).order_by(AuditEventModel.created_at.asc()).all()


@router.get("/audit-events", response_model=List[AuditEventResponse])
def list_recent_audit_events(limit: int = 50, db: Session = Depends(get_db)):
    """List recent security audit decisions across all intents."""
    return db.query(AuditEventModel).order_by(AuditEventModel.created_at.desc()).limit(limit).all()
