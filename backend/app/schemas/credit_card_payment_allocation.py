import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.funding_domain import FundingDomainRead


class CreditCardPaymentAllocationBase(BaseModel):
    payment_transaction_id: uuid.UUID
    bill_id: Optional[uuid.UUID] = None
    statement_due_date: Optional[date] = None
    funding_domain_id: uuid.UUID
    amount: Decimal
    notes: Optional[str] = None


class CreditCardPaymentAllocationCreate(CreditCardPaymentAllocationBase):
    pass


class CreditCardPaymentAllocationUpdate(BaseModel):
    bill_id: Optional[uuid.UUID] = None
    statement_due_date: Optional[date] = None
    funding_domain_id: Optional[uuid.UUID] = None
    amount: Optional[Decimal] = None
    notes: Optional[str] = None


class CreditCardPaymentAllocationRead(CreditCardPaymentAllocationBase):
    id: uuid.UUID
    user_id: uuid.UUID
    credit_card_account_id: uuid.UUID
    created_at: datetime
    funding_domain: Optional[FundingDomainRead] = None

    model_config = ConfigDict(from_attributes=True)


class CreditCardPaymentCandidate(BaseModel):
    payment_transaction_id: uuid.UUID
    canonical_payment_transaction_id: uuid.UUID
    transfer_pair_id: uuid.UUID
    description: str
    amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    currency: str
    date: str


class StatementFundingTransaction(BaseModel):
    id: uuid.UUID
    description: str
    amount: Decimal
    date: str
    funding_domain_id: Optional[uuid.UUID] = None


class StatementFundingLine(BaseModel):
    funding_domain_id: Optional[uuid.UUID] = None
    funding_domain: Optional[FundingDomainRead] = None
    expected_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    transactions: list[StatementFundingTransaction]


class StatementFundingReport(BaseModel):
    credit_card_account_id: uuid.UUID
    bill_id: Optional[uuid.UUID] = None
    date_from: str
    date_to: str
    expected_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    lines: list[StatementFundingLine]
