from datetime import date
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_card_bill import CreditCardBill


def money(value) -> Decimal:
    return Decimal(str(value))


@pytest.mark.asyncio
async def test_statement_funding_report_tracks_partial_domain_payment(
    client: AsyncClient,
    auth_headers: dict,
    session: AsyncSession,
    test_user,
):
    cc_account = (
        await client.post(
            "/api/accounts",
            json={
                "name": "Main CC",
                "type": "credit_card",
                "balance": "0",
                "currency": "BRL",
                "statement_close_day": 15,
                "payment_due_day": 19,
            },
            headers=auth_headers,
        )
    ).json()
    checking = (
        await client.post(
            "/api/accounts",
            json={"name": "Checking", "type": "checking", "balance": "3000", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    apartment = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()
    general = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Crédito Geral", "icon": "wallet", "color": "#6B7280"},
            headers=auth_headers,
        )
    ).json()

    bill = CreditCardBill(
        user_id=test_user.id,
        account_id=uuid.UUID(cc_account["id"]),
        external_id="bill-2026-05",
        due_date=date(2026, 5, 19),
        total_amount=Decimal("2300.00"),
        currency="BRL",
    )
    session.add(bill)
    await session.commit()
    await session.refresh(bill)

    for description, amount, tx_date, domain_id in [
        ("Sofa", "1200.00", "2026-04-16", apartment["id"]),
        ("Mesa", "800.00", "2026-05-10", apartment["id"]),
        ("Mercado", "300.00", "2026-05-11", general["id"]),
    ]:
        response = await client.post(
            "/api/transactions",
            json={
                "account_id": cc_account["id"],
                "description": description,
                "amount": amount,
                "date": tx_date,
                "type": "debit",
                "currency": "BRL",
                "funding_domain_id": domain_id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text

    transfer_response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": checking["id"],
            "to_account_id": cc_account["id"],
            "amount": "1000.00",
            "date": "2026-05-18",
            "description": "Partial card payment",
        },
        headers=auth_headers,
    )
    assert transfer_response.status_code == 201, transfer_response.text
    payment_debit = transfer_response.json()["debit"]
    card_credit = transfer_response.json()["credit"]

    allocation_response = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": card_credit["id"],
            "bill_id": str(bill.id),
            "funding_domain_id": apartment["id"],
            "amount": "1000.00",
        },
        headers=auth_headers,
    )
    assert allocation_response.status_code == 201, allocation_response.text
    assert allocation_response.json()["payment_transaction_id"] == payment_debit["id"]

    report_response = await client.get(
        f"/api/accounts/{cc_account['id']}/statement-funding",
        params={"bill_id": str(bill.id)},
        headers=auth_headers,
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["date_from"] == "2026-04-15"
    assert report["date_to"] == "2026-05-14"
    assert money(report["expected_amount"]) == Decimal("2300.00")
    assert money(report["allocated_amount"]) == Decimal("1000.00")
    assert money(report["remaining_amount"]) == Decimal("1300.00")

    lines = {line["funding_domain"]["name"]: line for line in report["lines"]}
    assert money(lines["Apartamento"]["expected_amount"]) == Decimal("2000.00")
    assert money(lines["Apartamento"]["allocated_amount"]) == Decimal("1000.00")
    assert money(lines["Apartamento"]["remaining_amount"]) == Decimal("1000.00")
    assert len(lines["Apartamento"]["transactions"]) == 2
    assert money(lines["Crédito Geral"]["expected_amount"]) == Decimal("300.00")
    assert money(lines["Crédito Geral"]["allocated_amount"]) == Decimal("0")
    assert money(lines["Crédito Geral"]["remaining_amount"]) == Decimal("300.00")


@pytest.mark.asyncio
async def test_payment_allocation_requires_transfer_to_card(
    client: AsyncClient,
    auth_headers: dict,
):
    cc_account = (
        await client.post(
            "/api/accounts",
            json={"name": "Main CC", "type": "credit_card", "balance": "0", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    checking = (
        await client.post(
            "/api/accounts",
            json={"name": "Checking", "type": "checking", "balance": "3000", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()
    payment = (
        await client.post(
            "/api/transactions",
            json={
                "account_id": checking["id"],
                "description": "Not linked transfer",
                "amount": "1000.00",
                "date": "2026-05-18",
                "type": "debit",
                "currency": "BRL",
            },
            headers=auth_headers,
        )
    ).json()

    response = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment["id"],
            "funding_domain_id": domain["id"],
            "amount": "1000.00",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "linked as a transfer" in response.json()["detail"]


@pytest.mark.asyncio
async def test_payment_allocations_cannot_exceed_card_payment_amount(
    client: AsyncClient,
    auth_headers: dict,
):
    cc_account = (
        await client.post(
            "/api/accounts",
            json={"name": "Main CC", "type": "credit_card", "balance": "0", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    checking = (
        await client.post(
            "/api/accounts",
            json={"name": "Checking", "type": "checking", "balance": "3000", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    apartment = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()
    general = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Crédito Geral", "icon": "wallet", "color": "#6B7280"},
            headers=auth_headers,
        )
    ).json()
    transfer_response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": checking["id"],
            "to_account_id": cc_account["id"],
            "amount": "1000.00",
            "date": "2026-05-18",
            "description": "Partial card payment",
        },
        headers=auth_headers,
    )
    payment_debit = transfer_response.json()["debit"]

    first_response = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment_debit["id"],
            "funding_domain_id": apartment["id"],
            "amount": "700.00",
        },
        headers=auth_headers,
    )
    assert first_response.status_code == 201, first_response.text

    second_response = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment_debit["id"],
            "funding_domain_id": general["id"],
            "amount": "400.00",
        },
        headers=auth_headers,
    )

    assert second_response.status_code == 400
    assert "cannot exceed" in second_response.json()["detail"]


@pytest.mark.asyncio
async def test_payment_candidates_show_remaining_until_fully_allocated(
    client: AsyncClient,
    auth_headers: dict,
    session: AsyncSession,
    test_user,
):
    cc_account = (
        await client.post(
            "/api/accounts",
            json={
                "name": "Main CC",
                "type": "credit_card",
                "balance": "0",
                "currency": "BRL",
                "statement_close_day": 15,
                "payment_due_day": 19,
            },
            headers=auth_headers,
        )
    ).json()
    checking = (
        await client.post(
            "/api/accounts",
            json={"name": "Checking", "type": "checking", "balance": "3000", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()
    bill = CreditCardBill(
        user_id=test_user.id,
        account_id=uuid.UUID(cc_account["id"]),
        external_id="bill-2026-05",
        due_date=date(2026, 5, 19),
        total_amount=Decimal("1000.00"),
        currency="BRL",
    )
    session.add(bill)
    await session.commit()
    await session.refresh(bill)

    transfer_response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": checking["id"],
            "to_account_id": cc_account["id"],
            "amount": "1000.00",
            "date": "2026-05-18",
            "description": "Card payment",
        },
        headers=auth_headers,
    )
    assert transfer_response.status_code == 201, transfer_response.text
    payment_credit = transfer_response.json()["credit"]

    candidates_response = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-candidates",
        params={"from": "2026-04-15", "to": "2026-05-19"},
        headers=auth_headers,
    )
    assert candidates_response.status_code == 200, candidates_response.text
    candidates = candidates_response.json()
    assert len(candidates) == 1
    assert candidates[0]["payment_transaction_id"] == payment_credit["id"]
    assert money(candidates[0]["remaining_amount"]) == Decimal("1000.00")

    first_allocation = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment_credit["id"],
            "bill_id": str(bill.id),
            "funding_domain_id": domain["id"],
            "amount": "700.00",
        },
        headers=auth_headers,
    )
    assert first_allocation.status_code == 201, first_allocation.text

    candidates_response = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-candidates",
        params={"from": "2026-05-15", "to": "2026-06-14"},
        headers=auth_headers,
    )
    assert candidates_response.status_code == 200, candidates_response.text
    candidates = candidates_response.json()
    assert len(candidates) == 1
    assert money(candidates[0]["remaining_amount"]) == Decimal("300.00")

    second_allocation = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment_credit["id"],
            "bill_id": str(bill.id),
            "funding_domain_id": domain["id"],
            "amount": "300.00",
        },
        headers=auth_headers,
    )
    assert second_allocation.status_code == 201, second_allocation.text

    candidates_response = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-candidates",
        params={"from": "2026-04-15", "to": "2026-05-19"},
        headers=auth_headers,
    )
    assert candidates_response.status_code == 200, candidates_response.text
    assert candidates_response.json() == []


@pytest.mark.asyncio
async def test_due_date_payment_allocation_stays_on_explicit_previous_bill(
    client: AsyncClient,
    auth_headers: dict,
    session: AsyncSession,
    test_user,
):
    cc_account = (
        await client.post(
            "/api/accounts",
            json={
                "name": "Main CC",
                "type": "credit_card",
                "balance": "0",
                "currency": "BRL",
                "statement_close_day": 15,
                "payment_due_day": 19,
            },
            headers=auth_headers,
        )
    ).json()
    checking = (
        await client.post(
            "/api/accounts",
            json={"name": "Checking", "type": "checking", "balance": "3000", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()
    previous_bill = CreditCardBill(
        user_id=test_user.id,
        account_id=uuid.UUID(cc_account["id"]),
        external_id="bill-2026-05",
        due_date=date(2026, 5, 19),
        total_amount=Decimal("1000.00"),
        currency="BRL",
    )
    next_bill = CreditCardBill(
        user_id=test_user.id,
        account_id=uuid.UUID(cc_account["id"]),
        external_id="bill-2026-06",
        due_date=date(2026, 6, 19),
        total_amount=Decimal("500.00"),
        currency="BRL",
    )
    session.add_all([previous_bill, next_bill])
    await session.commit()
    await session.refresh(previous_bill)
    await session.refresh(next_bill)

    transfer_response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": checking["id"],
            "to_account_id": cc_account["id"],
            "amount": "1000.00",
            "date": "2026-05-19",
            "description": "Payment on due date",
        },
        headers=auth_headers,
    )
    assert transfer_response.status_code == 201, transfer_response.text
    payment_credit = transfer_response.json()["credit"]

    allocation_response = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment_credit["id"],
            "bill_id": str(previous_bill.id),
            "funding_domain_id": domain["id"],
            "amount": "1000.00",
        },
        headers=auth_headers,
    )
    assert allocation_response.status_code == 201, allocation_response.text
    assert allocation_response.json()["bill_id"] == str(previous_bill.id)

    previous_allocations = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        params={"bill_id": str(previous_bill.id), "from": "2026-04-15", "to": "2026-05-14"},
        headers=auth_headers,
    )
    next_allocations = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        params={"bill_id": str(next_bill.id), "from": "2026-05-15", "to": "2026-06-14"},
        headers=auth_headers,
    )
    assert previous_allocations.status_code == 200, previous_allocations.text
    assert next_allocations.status_code == 200, next_allocations.text
    assert len(previous_allocations.json()) == 1
    assert next_allocations.json() == []


@pytest.mark.asyncio
async def test_due_date_payment_allocation_without_bill_uses_statement_due_date(
    client: AsyncClient,
    auth_headers: dict,
):
    cc_account = (
        await client.post(
            "/api/accounts",
            json={
                "name": "Manual CC",
                "type": "credit_card",
                "balance": "0",
                "currency": "BRL",
                "statement_close_day": 15,
                "payment_due_day": 19,
            },
            headers=auth_headers,
        )
    ).json()
    checking = (
        await client.post(
            "/api/accounts",
            json={"name": "Checking", "type": "checking", "balance": "3000", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()

    purchase_response = await client.post(
        "/api/transactions",
        json={
            "account_id": cc_account["id"],
            "description": "Previous statement purchase",
            "amount": "1000.00",
            "date": "2026-05-10",
            "type": "debit",
            "currency": "BRL",
            "funding_domain_id": domain["id"],
        },
        headers=auth_headers,
    )
    assert purchase_response.status_code == 201, purchase_response.text

    transfer_response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": checking["id"],
            "to_account_id": cc_account["id"],
            "amount": "1000.00",
            "date": "2026-05-19",
            "description": "Payment on due date",
        },
        headers=auth_headers,
    )
    assert transfer_response.status_code == 201, transfer_response.text
    payment_credit = transfer_response.json()["credit"]

    allocation_response = await client.post(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        json={
            "payment_transaction_id": payment_credit["id"],
            "bill_id": None,
            "statement_due_date": "2026-05-19",
            "funding_domain_id": domain["id"],
            "amount": "1000.00",
        },
        headers=auth_headers,
    )
    assert allocation_response.status_code == 201, allocation_response.text
    assert allocation_response.json()["statement_due_date"] == "2026-05-19"

    previous_allocations = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        params={"from": "2026-04-15", "to": "2026-05-14"},
        headers=auth_headers,
    )
    next_allocations = await client.get(
        f"/api/accounts/{cc_account['id']}/payment-allocations",
        params={"from": "2026-05-15", "to": "2026-06-14"},
        headers=auth_headers,
    )
    assert previous_allocations.status_code == 200, previous_allocations.text
    assert next_allocations.status_code == 200, next_allocations.text
    assert len(previous_allocations.json()) == 1
    assert next_allocations.json() == []

    report_response = await client.get(
        f"/api/accounts/{cc_account['id']}/statement-funding",
        params={"from": "2026-04-15", "to": "2026-05-14"},
        headers=auth_headers,
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert money(report["allocated_amount"]) == Decimal("1000.00")
    assert money(report["remaining_amount"]) == Decimal("0.00")
