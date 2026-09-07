import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.company import Company
from models.wave_category import WaveCategory
from schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from schemas.wave_category import WaveCategoryResponse
from services.wave import (
    WaveAuthError,
    WaveConfigurationError,
    WaveError,
    WaveGraphQLError,
    WaveNotConnectedError,
    sync_company_categories,
)

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=list[CompanyResponse])
def list_companies(db: Annotated[Session, Depends(get_db)]) -> list[Company]:
    """Retrieve all companies ordered by name."""
    stmt = select(Company).order_by(Company.name)
    return list(db.scalars(stmt).all())


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Annotated[Session, Depends(get_db)],
) -> Company:
    """Create a new company record."""
    company = Company(
        name=payload.name,
        wave_equity_account_id=payload.wave_equity_account_id,
        wave_business_id=payload.wave_business_id,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Company:
    """Retrieve a single company by ID."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )
    return company


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Company:
    """Update an existing company record."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)

    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a company record."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )
    db.delete(company)
    db.commit()


@router.post("/{company_id}/sync-categories", response_model=list[WaveCategoryResponse])
def sync_categories(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[WaveCategory]:
    """Trigger synchronization of Chart of Accounts categories from Wave."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    try:
        return sync_company_categories(company, db=db)
    except (WaveNotConnectedError, WaveConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except WaveAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Wave authentication failure: {exc}",
        ) from exc
    except (WaveGraphQLError, WaveError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Wave sync error: {exc}",
        ) from exc


@router.get("/{company_id}/categories", response_model=list[WaveCategoryResponse])
def list_company_categories(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[WaveCategory]:
    """Retrieve all cached categories for a specific company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )
    stmt = select(WaveCategory).where(WaveCategory.company_id == company_id).order_by(WaveCategory.name)
    return list(db.scalars(stmt).all())
