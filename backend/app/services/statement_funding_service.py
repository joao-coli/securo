import calendar
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.account import Account
from app.models.credit_card_bill import CreditCardBill
from app.models.credit_card_payment_allocation import CreditCardPaymentAllocation
from app.models.funding_domain import FundingDomain
from app.models.transaction import Transaction
from app.schemas.credit_card_payment_allocation import (
    CreditCardPaymentCandidate,
    CreditCardPaymentAllocationCreate,
    CreditCardPaymentAllocationUpdate,
    StatementFundingLine,
    StatementFundingReport,
    StatementFundingTransaction,
)
from app.schemas.funding_domain import FundingDomainRead
from app.services._query_filters import credit_card_bill_bucket_date, credit_card_bill_scope
from app.services.account_service import get_account
from app.services.funding_domain_service import get_assignable_funding_domain


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _previous_month(d: date) -> tuple[int, int]:
    if d.month == 1:
        return d.year - 1, 12
    return d.year, d.month - 1


def _next_month(d: date) -> tuple[int, int]:
    if d.month == 12:
        return d.year + 1, 1
    return d.year, d.month + 1


def _statement_due_date_for_window(account: Account, date_to: date) -> Optional[date]:
    if not account.payment_due_day:
        return None
    close_date = date_to + timedelta(days=1)
    due_date = _clamp_day(close_date.year, close_date.month, account.payment_due_day)
    if due_date <= close_date:
        year, month = _next_month(close_date)
        due_date = _clamp_day(year, month, account.payment_due_day)
    return due_date


def _allocation_scope_filters(
    account: Account,
    *,
    bill_id: Optional[uuid.UUID],
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[ColumnElement[bool]]:
    if bill_id is not None:
        return [CreditCardPaymentAllocation.bill_id == bill_id]

    legacy_filters = []
    if date_from is not None:
        legacy_filters.append(Transaction.date >= date_from)
    if date_to is not None:
        legacy_filters.append(Transaction.date <= date_to)

    target_due_date = _statement_due_date_for_window(account, date_to) if date_to is not None else None
    if target_due_date is None:
        return legacy_filters

    return [
        or_(
            CreditCardPaymentAllocation.statement_due_date == target_due_date,
            and_(
                CreditCardPaymentAllocation.statement_due_date.is_(None),
                *legacy_filters,
            ),
        )
    ]


def _cycle_window_for_bill(account: Account, bill: CreditCardBill) -> tuple[date, date]:
    if not account.statement_close_day:
        raise ValueError("Credit-card account must have statement_close_day to infer bill window")
    close_date = _clamp_day(bill.due_date.year, bill.due_date.month, account.statement_close_day)
    if close_date > bill.due_date:
        year, month = _previous_month(bill.due_date)
        close_date = _clamp_day(year, month, account.statement_close_day)
    prev_year, prev_month = _previous_month(close_date)
    previous_close = _clamp_day(prev_year, prev_month, account.statement_close_day)
    return previous_close, close_date - timedelta(days=1)


def _serialize_domain(domain: Optional[FundingDomain]) -> Optional[FundingDomainRead]:
    return FundingDomainRead.model_validate(domain, from_attributes=True) if domain else None


async def _get_credit_card_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Account:
    account = await get_account(session, account_id, workspace_id)
    if account is None:
        raise ValueError("Credit-card account not found")
    if account.type != "credit_card":
        raise ValueError("Account is not a credit card")
    return account


async def _validate_payment_transaction(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    payment_transaction_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
) -> tuple[Transaction, Transaction]:
    payment = await session.get(Transaction, payment_transaction_id)
    if payment is None or payment.workspace_id != workspace_id:
        raise ValueError("Payment transaction not found")
    if payment.transfer_pair_id is None:
        raise ValueError("Payment transaction must be linked as a transfer")
    if payment.type == "credit" and payment.account_id == credit_card_account_id:
        card_credit = payment
        debit_result = await session.execute(
            select(Transaction).where(
                Transaction.transfer_pair_id == payment.transfer_pair_id,
                Transaction.id != payment.id,
                Transaction.type == "debit",
            )
        )
        debit_payment = debit_result.scalar_one_or_none()
        if debit_payment is None or debit_payment.workspace_id != workspace_id:
            raise ValueError("Payment transfer must include a debit side")
        return debit_payment, card_credit
    if payment.type != "debit":
        raise ValueError("Payment allocation must point to a card payment transfer")
    pair_result = await session.execute(
        select(Transaction).where(
            Transaction.transfer_pair_id == payment.transfer_pair_id,
            Transaction.id != payment.id,
            Transaction.account_id == credit_card_account_id,
            Transaction.type == "credit",
        )
    )
    card_credit = pair_result.scalar_one_or_none()
    if card_credit is None:
        raise ValueError("Payment transfer must credit the selected card account")
    return payment, card_credit


async def _validate_payment_allocation_amount(
    session: AsyncSession,
    payment_transaction_id: uuid.UUID,
    card_credit_amount: Decimal,
    new_amount: Decimal,
    *,
    exclude_allocation_id: Optional[uuid.UUID] = None,
) -> None:
    filters = [CreditCardPaymentAllocation.payment_transaction_id == payment_transaction_id]
    if exclude_allocation_id is not None:
        filters.append(CreditCardPaymentAllocation.id != exclude_allocation_id)
    result = await session.execute(
        select(func.coalesce(func.sum(CreditCardPaymentAllocation.amount), 0)).where(*filters)
    )
    already_allocated = Decimal(str(result.scalar() or 0))
    if already_allocated + new_amount > Decimal(str(card_credit_amount)):
        raise ValueError("Payment allocations cannot exceed the card payment amount")


async def _validate_bill(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    bill_id: Optional[uuid.UUID],
) -> Optional[CreditCardBill]:
    if bill_id is None:
        return None
    result = await session.execute(
        select(CreditCardBill).where(
            CreditCardBill.id == bill_id,
            CreditCardBill.workspace_id == workspace_id,
            CreditCardBill.account_id == credit_card_account_id,
        )
    )
    bill = result.scalar_one_or_none()
    if bill is None:
        raise ValueError("Credit-card bill not found")
    return bill


async def create_payment_allocation(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    data: CreditCardPaymentAllocationCreate,
) -> CreditCardPaymentAllocation:
    await _get_credit_card_account(session, credit_card_account_id, workspace_id)
    canonical_payment, card_credit = await _validate_payment_transaction(
        session, workspace_id, data.payment_transaction_id, credit_card_account_id
    )
    await get_assignable_funding_domain(session, data.funding_domain_id, user_id)
    bill = await _validate_bill(session, workspace_id, credit_card_account_id, data.bill_id)
    if data.amount <= Decimal("0"):
        raise ValueError("Allocation amount must be positive")
    await _validate_payment_allocation_amount(
        session,
        canonical_payment.id,
        Decimal(str(card_credit.amount)),
        data.amount,
    )

    allocation = CreditCardPaymentAllocation(
        user_id=user_id,
        credit_card_account_id=credit_card_account_id,
        payment_transaction_id=canonical_payment.id,
        bill_id=data.bill_id,
        statement_due_date=bill.due_date if bill is not None else data.statement_due_date,
        funding_domain_id=data.funding_domain_id,
        amount=data.amount,
        notes=data.notes,
    )
    session.add(allocation)
    await session.commit()
    await session.refresh(allocation, ["funding_domain"])
    return allocation


async def list_payment_allocations(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    *,
    bill_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[CreditCardPaymentAllocation]:
    account = await _get_credit_card_account(session, credit_card_account_id, workspace_id)
    query = (
        select(CreditCardPaymentAllocation)
        .join(Transaction, Transaction.id == CreditCardPaymentAllocation.payment_transaction_id)
        .options(selectinload(CreditCardPaymentAllocation.funding_domain))
        .where(
            CreditCardPaymentAllocation.credit_card_account_id == credit_card_account_id,
        )
    )
    query = query.where(*_allocation_scope_filters(
        account,
        bill_id=bill_id,
        date_from=date_from,
        date_to=date_to,
    ))
    result = await session.execute(query.order_by(CreditCardPaymentAllocation.created_at.desc()))
    return list(result.scalars().all())


async def list_payment_candidates(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    *,
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[CreditCardPaymentCandidate]:
    await _get_credit_card_account(session, credit_card_account_id, workspace_id)
    if date_from is None or date_to is None:
        raise ValueError("date_from/date_to are required")

    debit_payment = aliased(Transaction)
    allocated_subq = (
        select(
            CreditCardPaymentAllocation.payment_transaction_id.label("payment_transaction_id"),
            func.coalesce(func.sum(CreditCardPaymentAllocation.amount), 0).label("allocated_amount"),
        )
        .where(
            CreditCardPaymentAllocation.credit_card_account_id == credit_card_account_id,
        )
        .group_by(CreditCardPaymentAllocation.payment_transaction_id)
        .subquery()
    )
    query = (
        select(
            Transaction.id,
            debit_payment.id,
            Transaction.transfer_pair_id,
            Transaction.description,
            Transaction.amount,
            func.coalesce(allocated_subq.c.allocated_amount, 0),
            Transaction.currency,
            Transaction.date,
        )
        .join(
            debit_payment,
            and_(
                debit_payment.transfer_pair_id == Transaction.transfer_pair_id,
                debit_payment.id != Transaction.id,
                debit_payment.workspace_id == workspace_id,
                debit_payment.type == "debit",
            ),
        )
        .outerjoin(allocated_subq, allocated_subq.c.payment_transaction_id == debit_payment.id)
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.account_id == credit_card_account_id,
            Transaction.type == "credit",
            Transaction.source != "opening_balance",
            Transaction.transfer_pair_id.is_not(None),
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        )
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
    )
    result = await session.execute(query)
    candidates: list[CreditCardPaymentCandidate] = []
    for (
        card_credit_id,
        debit_payment_id,
        transfer_pair_id,
        description,
        amount,
        allocated_amount,
        currency,
        tx_date,
    ) in result.all():
        payment_amount = Decimal(str(amount))
        allocated = Decimal(str(allocated_amount or 0))
        remaining = payment_amount - allocated
        if remaining <= Decimal("0"):
            continue
        candidates.append(
            CreditCardPaymentCandidate(
                payment_transaction_id=card_credit_id,
                canonical_payment_transaction_id=debit_payment_id,
                transfer_pair_id=transfer_pair_id,
                description=description,
                amount=payment_amount,
                allocated_amount=allocated,
                remaining_amount=remaining,
                currency=currency,
                date=tx_date.isoformat(),
            )
        )
    return candidates


async def update_payment_allocation(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    allocation_id: uuid.UUID,
    data: CreditCardPaymentAllocationUpdate,
) -> Optional[CreditCardPaymentAllocation]:
    result = await session.execute(
        select(CreditCardPaymentAllocation)
        .where(
            CreditCardPaymentAllocation.id == allocation_id,
            CreditCardPaymentAllocation.user_id == user_id,
            CreditCardPaymentAllocation.credit_card_account_id == credit_card_account_id,
        )
    )
    allocation = result.scalar_one_or_none()
    if allocation is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if "funding_domain_id" in update_data:
        if update_data["funding_domain_id"] is None:
            raise ValueError("Funding domain is required")
        await get_assignable_funding_domain(session, update_data["funding_domain_id"], user_id)
    if "bill_id" in update_data:
        bill = await _validate_bill(session, workspace_id, credit_card_account_id, update_data["bill_id"])
        if bill is not None and "statement_due_date" not in update_data:
            update_data["statement_due_date"] = bill.due_date
    if "amount" in update_data and update_data["amount"] <= Decimal("0"):
        raise ValueError("Allocation amount must be positive")
    if "amount" in update_data:
        _, card_credit = await _validate_payment_transaction(
            session,
            workspace_id,
            allocation.payment_transaction_id,
            credit_card_account_id,
        )
        await _validate_payment_allocation_amount(
            session,
            allocation.payment_transaction_id,
            Decimal(str(card_credit.amount)),
            update_data["amount"],
            exclude_allocation_id=allocation.id,
        )
    for key, value in update_data.items():
        setattr(allocation, key, value)
    await session.commit()
    await session.refresh(allocation, ["funding_domain"])
    return allocation


async def delete_payment_allocation(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    allocation_id: uuid.UUID,
) -> bool:
    await _get_credit_card_account(session, credit_card_account_id, workspace_id)
    result = await session.execute(
        select(CreditCardPaymentAllocation).where(
            CreditCardPaymentAllocation.id == allocation_id,
            CreditCardPaymentAllocation.user_id == user_id,
            CreditCardPaymentAllocation.credit_card_account_id == credit_card_account_id,
        )
    )
    allocation = result.scalar_one_or_none()
    if allocation is None:
        return False
    await session.delete(allocation)
    await session.commit()
    return True


async def get_statement_funding_report(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    credit_card_account_id: uuid.UUID,
    *,
    bill_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> StatementFundingReport:
    account = await _get_credit_card_account(session, credit_card_account_id, workspace_id)
    if bill_id is not None:
        bill = await _validate_bill(session, workspace_id, credit_card_account_id, bill_id)
        if date_from is None or date_to is None:
            date_from, date_to = _cycle_window_for_bill(account, bill)
    if date_from is None or date_to is None:
        raise ValueError("date_from/date_to are required when bill_id is not provided")

    bucket_date = credit_card_bill_bucket_date()
    base_filters = [
        Transaction.workspace_id == workspace_id,
        Transaction.account_id == credit_card_account_id,
        Transaction.type == "debit",
        Transaction.source != "opening_balance",
        Transaction.transfer_pair_id.is_(None),
    ]
    if bill_id is not None:
        base_filters.append(credit_card_bill_scope(bill_id, date_from=date_from, date_to=date_to, bucket_date=bucket_date))
    else:
        base_filters.extend([bucket_date >= date_from, bucket_date <= date_to])

    tx_result = await session.execute(
        select(
            Transaction.id,
            Transaction.description,
            Transaction.amount,
            Transaction.date,
            Transaction.funding_domain_id,
            FundingDomain,
        )
        .outerjoin(FundingDomain, Transaction.funding_domain_id == FundingDomain.id)
        .where(*base_filters)
        .order_by(bucket_date, Transaction.created_at)
    )

    expected_by_domain: dict[Optional[uuid.UUID], Decimal] = defaultdict(lambda: Decimal("0"))
    txs_by_domain: dict[Optional[uuid.UUID], list[StatementFundingTransaction]] = defaultdict(list)
    domain_by_id: dict[uuid.UUID, FundingDomain] = {}
    for tx_id, description, amount, tx_date, domain_id, domain in tx_result.all():
        expected_by_domain[domain_id] += Decimal(str(amount))
        if domain is not None:
            domain_by_id[domain.id] = domain
        txs_by_domain[domain_id].append(
            StatementFundingTransaction(
                id=tx_id,
                description=description,
                amount=Decimal(str(amount)),
                date=tx_date.isoformat(),
                funding_domain_id=domain_id,
            )
        )

    allocation_filters = [
        CreditCardPaymentAllocation.credit_card_account_id == credit_card_account_id,
    ]
    allocation_filters.extend(_allocation_scope_filters(
        account,
        bill_id=bill_id,
        date_from=date_from,
        date_to=date_to,
    ))

    alloc_result = await session.execute(
        select(CreditCardPaymentAllocation)
        .join(Transaction, Transaction.id == CreditCardPaymentAllocation.payment_transaction_id)
        .options(selectinload(CreditCardPaymentAllocation.funding_domain))
        .where(*allocation_filters)
    )
    allocations = list(alloc_result.scalars().all())
    allocated_by_domain: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    for allocation in allocations:
        allocated_by_domain[allocation.funding_domain_id] += Decimal(str(allocation.amount))
        if allocation.funding_domain is not None:
            domain_by_id[allocation.funding_domain.id] = allocation.funding_domain

    all_domain_ids = set(expected_by_domain) | set(allocated_by_domain)
    lines: list[StatementFundingLine] = []
    for domain_id in sorted(all_domain_ids, key=lambda value: "" if value is None else str(value)):
        expected = expected_by_domain.get(domain_id, Decimal("0"))
        allocated = allocated_by_domain.get(domain_id, Decimal("0")) if domain_id is not None else Decimal("0")
        lines.append(
            StatementFundingLine(
                funding_domain_id=domain_id,
                funding_domain=(
                    _serialize_domain(domain_by_id.get(domain_id))
                    if domain_id is not None
                    else None
                ),
                expected_amount=expected,
                allocated_amount=allocated,
                remaining_amount=expected - allocated,
                transactions=txs_by_domain.get(domain_id, []),
            )
        )

    expected_total = sum(expected_by_domain.values(), Decimal("0"))
    allocated_total = sum(allocated_by_domain.values(), Decimal("0"))
    return StatementFundingReport(
        credit_card_account_id=credit_card_account_id,
        bill_id=bill_id,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        expected_amount=expected_total,
        allocated_amount=allocated_total,
        remaining_amount=expected_total - allocated_total,
        lines=lines,
    )
