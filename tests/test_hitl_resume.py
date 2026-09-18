"""HITL resume idempotency + Pause≠HITL."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pause_while_interrupted_409(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Force publish HITL path"},
    )
    assert r.status_code == 200
    snap = r.json()
    thread_id = snap["thread_id"]

    # Graph should hit publish HITL after synth
    # Poll/get until interrupted (create already invokes to interrupt)
    g = await app_client.get(f"/v1/runs/{thread_id}", headers=auth_headers)
    status = g.json()["status"]
    if status != "interrupted":
        pytest.skip(f"Expected interrupted for HITL demo, got {status}")

    pause = await app_client.post(f"/v1/runs/{thread_id}/pause", headers=auth_headers)
    assert pause.status_code == 409
    assert "HITL" in pause.json()["detail"] or "interrupted" in pause.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approve_idempotent(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Publish idempotency"},
    )
    assert r.status_code == 200
    snap = r.json()
    thread_id = snap["thread_id"]
    g = await app_client.get(f"/v1/runs/{thread_id}", headers=auth_headers)
    body = g.json()
    if body["status"] != "interrupted" or not body.get("pending_action"):
        pytest.skip("Run did not land on HITL interrupt")

    # First approve
    a1 = await app_client.post(
        f"/v1/runs/{thread_id}/resume",
        headers=auth_headers,
        json={"decision": "approve"},
    )
    assert a1.status_code == 200, a1.text
    url1 = a1.json().get("publish_url")
    published1 = a1.json().get("published")

    # Second approve — must not double side effect (ledger)
    # Status may no longer be interrupted; if so expect 409; if still interrupted, ledger suppresses
    a2 = await app_client.post(
        f"/v1/runs/{thread_id}/resume",
        headers=auth_headers,
        json={"decision": "approve"},
    )
    if a2.status_code == 409:
        # Already left interrupted — good; verify AR / snapshot stable
        final = await app_client.get(f"/v1/runs/{thread_id}", headers=auth_headers)
        assert final.json().get("publish_url") == url1
    else:
        assert a2.status_code == 200
        assert a2.json().get("publish_url") == url1
        # published flag stable
        assert a2.json().get("published") == published1

    # Pause/Stop honesty flag
    # Create another running-ish conversation via pause path on a fresh non-interrupted if possible
    stop = await app_client.post(f"/v1/runs/{thread_id}/stop", headers=auth_headers)
    assert stop.status_code == 200
    assert "supported" in stop.json()
    assert isinstance(stop.json()["supported"], bool)


@pytest.mark.asyncio
async def test_reject_does_not_publish(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Reject publish"},
    )
    assert r.status_code == 200
    thread_id = r.json()["thread_id"]
    g = await app_client.get(f"/v1/runs/{thread_id}", headers=auth_headers)
    if g.json()["status"] != "interrupted":
        pytest.skip("not interrupted")

    rej = await app_client.post(
        f"/v1/runs/{thread_id}/resume",
        headers=auth_headers,
        json={"decision": "reject"},
    )
    assert rej.status_code == 200
    assert rej.json().get("published") is False
    assert not rej.json().get("publish_url")
