"""
API Routes for Managing Durable Intent Records and Authorizations.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.schemas.intent import IntentCreate, IntentResponse
from backend.app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/api/intents", tags=["Intents & Authorizations"])


@router.post("", response_model=IntentResponse, status_code=status.HTTP_201_CREATED)
def create_intent(intent_in: IntentCreate, db: Session = Depends(get_db)):
    """Register a new durable business authorization record."""
    return AuthorizationService.create_intent(db, intent_in)


@router.get("/{intent_id}", response_model=IntentResponse)
def get_intent(intent_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed state and bounds for a specific intent."""
    intent = AuthorizationService.get_intent(db, intent_id)
    if not intent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent '{intent_id}' not found."
        )
    return intent


@router.get("", response_model=List[IntentResponse])
def list_intents(limit: int = 50, skip: int = 0, db: Session = Depends(get_db)):
    """List recent durable intent records."""
    return AuthorizationService.list_intents(db, limit=limit, skip=skip)
