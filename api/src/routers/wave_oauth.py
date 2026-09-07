import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.security import allow_anonymous
from database import get_db
from models.company import Company
from schemas.company import CompanyResponse
from schemas.wave import WaveAuthorizeResponse
from services.wave import (
    WaveAuthError,
    build_oauth_authorize_url,
    exchange_oauth_code,
    verify_oauth_state,
)

router = APIRouter(prefix="/api/wave/oauth", tags=["wave-oauth"])


@router.get("/authorize", response_model=WaveAuthorizeResponse)
def oauth_authorize(
    company_id: Annotated[uuid.UUID, Query(description="Company ID to connect with Wave")],
    db: Annotated[Session, Depends(get_db)],
    redirect: Annotated[bool, Query(description="Whether to return a redirect response immediately")] = False,
):
    """Initiate Wave OAuth authorization flow for a specific company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    auth_url = build_oauth_authorize_url(company_id)
    if redirect:
        return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return WaveAuthorizeResponse(authorization_url=auth_url, redirect_url=auth_url)


@router.get("/callback", response_model=CompanyResponse)
@allow_anonymous
def oauth_callback(
    db: Annotated[Session, Depends(get_db)],
    code: Annotated[str | None, Query(description="Authorization code returned by Wave")] = None,
    state: Annotated[str | None, Query(description="Signed JWT state parameter")] = None,
    error: Annotated[str | None, Query(description="Error message if authorization failed")] = None,
) -> Company:
    """Handle Wave OAuth redirect callback, exchange code for tokens, and persist to company."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Wave OAuth authorization error: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code parameter",
        )

    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter",
        )

    try:
        company_id = verify_oauth_state(state)
    except WaveAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    try:
        token_data = exchange_oauth_code(code)
    except WaveAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    company.wave_access_token = token_data["access_token"]
    if token_data.get("refresh_token"):
        company.wave_refresh_token = token_data["refresh_token"]

    expires_in = token_data.get("expires_in")
    if expires_in is not None:
        company.wave_token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    db.add(company)
    db.commit()
    db.refresh(company)

    return company
