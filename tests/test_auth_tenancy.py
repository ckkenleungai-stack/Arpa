"""Auth + tenancy filters."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_no_auth(app_client):
    r = await app_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_missing_token_401(app_client):
    r = await app_client.get("/v1/conversations")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_401(app_client):
    r = await app_client.get(
        "/v1/conversations",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_and_tenant_isolation(app_client, auth_headers, other_tenant_headers):
    # Create run as tenant-a
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Tenancy check", "workflow_id": "research_publish_v1"},
    )
    assert r.status_code == 200, r.text
    snap = r.json()
    thread_id = snap["thread_id"]
    assert snap["status"] in ("running", "interrupted", "completed")

    # Owner can GET
    r2 = await app_client.get(f"/v1/runs/{thread_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["thread_id"] == thread_id

    # Other tenant → 404 (no leak)
    r3 = await app_client.get(f"/v1/runs/{thread_id}", headers=other_tenant_headers)
    assert r3.status_code == 404

    # Conversations list filtered
    r4 = await app_client.get("/v1/conversations", headers=auth_headers)
    assert r4.status_code == 200
    ids = {c["thread_id"] for c in r4.json()}
    assert thread_id in ids

    r5 = await app_client.get("/v1/conversations", headers=other_tenant_headers)
    assert r5.status_code == 200
    assert thread_id not in {c["thread_id"] for c in r5.json()}
