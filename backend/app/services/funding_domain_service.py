import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funding_domain import FundingDomain
from app.schemas.funding_domain import FundingDomainCreate, FundingDomainUpdate


async def get_funding_domains(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    include_inactive: bool = False,
) -> list[FundingDomain]:
    query = select(FundingDomain).where(FundingDomain.workspace_id == workspace_id)
    if not include_inactive:
        query = query.where(FundingDomain.is_active.is_(True))
    result = await session.execute(query.order_by(FundingDomain.name))
    return list(result.scalars().all())


async def get_funding_domain(
    session: AsyncSession,
    domain_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Optional[FundingDomain]:
    result = await session.execute(
        select(FundingDomain).where(
            FundingDomain.id == domain_id,
            FundingDomain.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def get_assignable_funding_domain(
    session: AsyncSession,
    domain_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> FundingDomain:
    domain = await get_funding_domain(session, domain_id, workspace_id)
    if domain is None or not domain.is_active:
        raise ValueError("Funding domain not found")
    return domain


async def create_funding_domain(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    data: FundingDomainCreate,
) -> FundingDomain:
    domain = FundingDomain(workspace_id=workspace_id, user_id=user_id, **data.model_dump())
    session.add(domain)
    await session.commit()
    await session.refresh(domain)
    return domain


async def update_funding_domain(
    session: AsyncSession,
    domain_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    data: FundingDomainUpdate,
) -> Optional[FundingDomain]:
    domain = await get_funding_domain(session, domain_id, workspace_id)
    if not domain:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(domain, key, value)
    await session.commit()
    await session.refresh(domain)
    return domain


async def delete_funding_domain(
    session: AsyncSession,
    domain_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    domain = await get_funding_domain(session, domain_id, workspace_id)
    if not domain:
        return False
    domain.is_active = False
    await session.commit()
    return True
