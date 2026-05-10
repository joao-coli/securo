import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_transaction_with_funding_domain(
    client: AsyncClient,
    auth_headers: dict,
    test_account,
):
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Apartamento", "icon": "home", "color": "#8B5CF6"},
            headers=auth_headers,
        )
    ).json()

    response = await client.post(
        "/api/transactions",
        json={
            "account_id": str(test_account.id),
            "description": "Amazon panelas",
            "amount": "55.54",
            "date": "2026-05-05",
            "type": "debit",
            "currency": "BRL",
            "funding_domain_id": domain["id"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    tx = response.json()
    assert tx["funding_domain_id"] == domain["id"]
    assert tx["funding_domain"]["name"] == "Apartamento"


@pytest.mark.asyncio
async def test_rule_sets_funding_domain_when_transaction_does_not_specify_one(
    client: AsyncClient,
    auth_headers: dict,
    test_account,
):
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Carro", "icon": "car", "color": "#3B82F6"},
            headers=auth_headers,
        )
    ).json()
    rule_response = await client.post(
        "/api/rules",
        json={
            "name": "Fuel domain",
            "conditions_op": "or",
            "conditions": [{"field": "description", "op": "contains", "value": "GASOLINA"}],
            "actions": [{"op": "set_funding_domain", "value": domain["id"]}],
            "priority": 1,
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert rule_response.status_code == 201, rule_response.text

    response = await client.post(
        "/api/transactions",
        json={
            "account_id": str(test_account.id),
            "description": "Gasolina",
            "amount": "100.00",
            "date": "2026-05-05",
            "type": "debit",
            "currency": "BRL",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["funding_domain_id"] == domain["id"]


@pytest.mark.asyncio
async def test_rule_rejects_inactive_funding_domain(
    client: AsyncClient,
    auth_headers: dict,
):
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Inactive", "icon": "archive", "color": "#6B7280"},
            headers=auth_headers,
        )
    ).json()
    await client.patch(
        f"/api/funding-domains/{domain['id']}",
        json={"is_active": False},
        headers=auth_headers,
    )

    response = await client.post(
        "/api/rules",
        json={
            "name": "Inactive domain rule",
            "conditions_op": "or",
            "conditions": [{"field": "description", "op": "contains", "value": "ANY"}],
            "actions": [{"op": "set_funding_domain", "value": domain["id"]}],
            "priority": 1,
            "is_active": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "Funding domain not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rule_rejects_malformed_funding_domain_id(
    client: AsyncClient,
    auth_headers: dict,
):
    response = await client.post(
        "/api/rules",
        json={
            "name": "Bad domain rule",
            "conditions_op": "or",
            "conditions": [{"field": "description", "op": "contains", "value": "ANY"}],
            "actions": [{"op": "set_funding_domain", "value": "not-a-uuid"}],
            "priority": 1,
            "is_active": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "Funding domain not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_apply_all_rules_preserves_manual_funding_domain_without_domain_action(
    client: AsyncClient,
    auth_headers: dict,
    test_account,
    test_categories,
):
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Manual bucket", "icon": "wallet", "color": "#6B7280"},
            headers=auth_headers,
        )
    ).json()
    tx = (
        await client.post(
            "/api/transactions",
            json={
                "account_id": str(test_account.id),
                "description": "Mercado rule match",
                "amount": "88.00",
                "date": "2026-05-05",
                "type": "debit",
                "currency": "BRL",
                "funding_domain_id": domain["id"],
            },
            headers=auth_headers,
        )
    ).json()
    rule_response = await client.post(
        "/api/rules",
        json={
            "name": "Category only",
            "conditions_op": "or",
            "conditions": [{"field": "description", "op": "contains", "value": "MERCADO"}],
            "actions": [{"op": "set_category", "value": str(test_categories[0].id)}],
            "priority": 1,
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert rule_response.status_code == 201, rule_response.text

    apply_response = await client.post("/api/rules/apply-all", headers=auth_headers)
    assert apply_response.status_code == 200, apply_response.text

    refreshed = await client.get(f"/api/transactions/{tx['id']}", headers=auth_headers)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["funding_domain_id"] == domain["id"]


@pytest.mark.asyncio
async def test_create_transaction_rejects_inactive_funding_domain(
    client: AsyncClient,
    auth_headers: dict,
    test_account,
):
    domain = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Old bucket", "icon": "archive", "color": "#6B7280"},
            headers=auth_headers,
        )
    ).json()
    await client.patch(
        f"/api/funding-domains/{domain['id']}",
        json={"is_active": False},
        headers=auth_headers,
    )

    response = await client.post(
        "/api/transactions",
        json={
            "account_id": str(test_account.id),
            "description": "Legacy spend",
            "amount": "10.00",
            "date": "2026-05-05",
            "type": "debit",
            "currency": "BRL",
            "funding_domain_id": domain["id"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "Funding domain not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bulk_funding_domain_only_updates_credit_card_debit_purchases(
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
    cc_debit = (
        await client.post(
            "/api/transactions",
            json={
                "account_id": cc_account["id"],
                "description": "Card purchase",
                "amount": "100.00",
                "date": "2026-05-05",
                "type": "debit",
                "currency": "BRL",
            },
            headers=auth_headers,
        )
    ).json()
    cc_credit = (
        await client.post(
            "/api/transactions",
            json={
                "account_id": cc_account["id"],
                "description": "Card credit",
                "amount": "50.00",
                "date": "2026-05-06",
                "type": "credit",
                "currency": "BRL",
            },
            headers=auth_headers,
        )
    ).json()
    checking_debit = (
        await client.post(
            "/api/transactions",
            json={
                "account_id": checking["id"],
                "description": "Checking purchase",
                "amount": "10.00",
                "date": "2026-05-07",
                "type": "debit",
                "currency": "BRL",
            },
            headers=auth_headers,
        )
    ).json()

    response = await client.patch(
        "/api/transactions/bulk-funding-domain",
        json={
            "transaction_ids": [cc_debit["id"], cc_credit["id"], checking_debit["id"]],
            "funding_domain_id": domain["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 1

    refreshed_cc_debit = await client.get(f"/api/transactions/{cc_debit['id']}", headers=auth_headers)
    refreshed_cc_credit = await client.get(f"/api/transactions/{cc_credit['id']}", headers=auth_headers)
    refreshed_checking_debit = await client.get(f"/api/transactions/{checking_debit['id']}", headers=auth_headers)
    assert refreshed_cc_debit.json()["funding_domain_id"] == domain["id"]
    assert refreshed_cc_credit.json()["funding_domain_id"] is None
    assert refreshed_checking_debit.json()["funding_domain_id"] is None
