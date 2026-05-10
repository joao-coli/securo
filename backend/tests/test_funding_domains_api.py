import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_funding_domain(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/funding-domains",
        json={
            "name": "Apartamento",
            "icon": "home",
            "color": "#8B5CF6",
            "description": "Short-term apartment reserve",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Apartamento"
    assert created["is_active"] is True

    list_response = await client.get("/api/funding-domains", headers=auth_headers)

    assert list_response.status_code == 200
    domains = list_response.json()
    assert [d["name"] for d in domains] == ["Apartamento"]


@pytest.mark.asyncio
async def test_update_and_delete_funding_domain(client: AsyncClient, auth_headers: dict):
    created = (
        await client.post(
            "/api/funding-domains",
            json={"name": "Otras cosas", "icon": "wallet", "color": "#6B7280"},
            headers=auth_headers,
        )
    ).json()

    update_response = await client.patch(
        f"/api/funding-domains/{created['id']}",
        json={"name": "Outras coisas", "is_active": False},
        headers=auth_headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Outras coisas"
    assert update_response.json()["is_active"] is False

    active_response = await client.get("/api/funding-domains", headers=auth_headers)
    assert active_response.status_code == 200
    assert active_response.json() == []

    all_response = await client.get(
        "/api/funding-domains",
        params={"include_inactive": True},
        headers=auth_headers,
    )
    assert len(all_response.json()) == 1

    delete_response = await client.delete(
        f"/api/funding-domains/{created['id']}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204
