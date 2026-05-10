import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user
from app.core.database import get_async_session
from app.models.user import User
from app.schemas.funding_domain import (
    FundingDomainCreate,
    FundingDomainRead,
    FundingDomainUpdate,
)
from app.services import funding_domain_service

router = APIRouter(prefix="/api/funding-domains", tags=["funding-domains"])


@router.get("", response_model=list[FundingDomainRead])
async def list_funding_domains(
    include_inactive: bool = Query(False),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await funding_domain_service.get_funding_domains(
        session,
        user.id,
        include_inactive=include_inactive,
    )


@router.post("", response_model=FundingDomainRead, status_code=status.HTTP_201_CREATED)
async def create_funding_domain(
    data: FundingDomainCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await funding_domain_service.create_funding_domain(session, user.id, data)


@router.patch("/{domain_id}", response_model=FundingDomainRead)
async def update_funding_domain(
    domain_id: uuid.UUID,
    data: FundingDomainUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    domain = await funding_domain_service.update_funding_domain(session, domain_id, user.id, data)
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funding domain not found")
    return domain


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_funding_domain(
    domain_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    deleted = await funding_domain_service.delete_funding_domain(session, domain_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funding domain not found")
