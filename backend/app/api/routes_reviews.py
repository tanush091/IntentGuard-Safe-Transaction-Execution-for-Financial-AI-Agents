"""
API Routes for Managing Human Escalation and Review Cases.
"""

from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.models.review_case import ReviewCaseModel
from backend.app.schemas.recovery import ReviewCaseResponse, ReviewCaseResolveRequest

router = APIRouter(prefix="/api/reviews", tags=["Human Review Cases"])


@router.get("", response_model=List[ReviewCaseResponse])
def list_review_cases(status: str = None, db: Session = Depends(get_db)):
    """List review and escalation tickets requiring human operator intervention."""
    query = db.query(ReviewCaseModel)
    if status:
        query = query.filter(ReviewCaseModel.status == status.upper())
    return query.order_by(ReviewCaseModel.created_at.desc()).all()


@router.post("/{case_id}/resolve", response_model=ReviewCaseResponse)
def resolve_review_case(
    case_id: str,
    req: ReviewCaseResolveRequest,
    db: Session = Depends(get_db)
):
    """Manually resolve an escalated review case with human operator justification."""
    case = db.query(ReviewCaseModel).filter(ReviewCaseModel.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review case '{case_id}' not found."
        )

    case.status = "RESOLVED" if req.action.upper() == "RESOLVE" else "DISMISSED"
    case.resolved_at = datetime.now(timezone.utc)
    case.resolution_notes = req.resolution_notes
    db.commit()
    db.refresh(case)
    return case
