"""
Payment Authorization API Endpoints for Mock Payment Simulator (Secondary Workflow).
"""

from fastapi import APIRouter, HTTPException, status
from ..schemas import AuthorizationCreateRequest, AuthorizationResponse
from ..services.payment_service import payment_service

router = APIRouter(prefix="/authorizations", tags=["Authorizations"])


@router.post("", response_model=AuthorizationResponse, status_code=status.HTTP_201_CREATED)
def create_authorization(req: AuthorizationCreateRequest):
    """Place a simulated hold or authorization on funds."""
    return payment_service.create_authorization(req)


@router.get("/{auth_id}", response_model=AuthorizationResponse)
def get_authorization(auth_id: str):
    """Retrieve status of an authorization."""
    auth = payment_service.get_authorization(auth_id)
    if not auth:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authorization not found")
    return auth


@router.post("/{auth_id}/void", response_model=AuthorizationResponse)
def void_authorization(auth_id: str):
    """Void or cancel an active authorization."""
    return payment_service.void_authorization(auth_id)
