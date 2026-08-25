import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FundingDomainBase(BaseModel):
    name: str
    icon: str = "wallet"
    color: str = "#6B7280"
    description: Optional[str] = None
    is_active: bool = True


class FundingDomainCreate(FundingDomainBase):
    pass


class FundingDomainUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FundingDomainRead(FundingDomainBase):
    id: uuid.UUID
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
