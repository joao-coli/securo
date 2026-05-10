import uuid
from datetime import date
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.credit_card_bill import CreditCardBill
    from app.models.funding_domain import FundingDomain
    from app.models.transaction import Transaction


class CreditCardPaymentAllocation(Base):
    """Explains which Funding Domain a real credit-card payment settles."""

    __tablename__ = "credit_card_payment_allocations"
    __table_args__ = (
        Index(
            "ix_cc_payment_allocations_account_created",
            "user_id",
            "credit_card_account_id",
            "created_at",
        ),
        Index(
            "ix_cc_payment_allocations_account_bill_created",
            "user_id",
            "credit_card_account_id",
            "bill_id",
            "created_at",
        ),
        Index(
            "ix_cc_payment_allocations_account_due_created",
            "user_id",
            "credit_card_account_id",
            "statement_due_date",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    payment_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credit_card_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bill_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_card_bills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    statement_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    funding_domain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("funding_domains.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    payment_transaction: Mapped["Transaction"] = relationship(foreign_keys=[payment_transaction_id])
    credit_card_account: Mapped["Account"] = relationship(foreign_keys=[credit_card_account_id])
    bill: Mapped[Optional["CreditCardBill"]] = relationship()
    funding_domain: Mapped["FundingDomain"] = relationship()
