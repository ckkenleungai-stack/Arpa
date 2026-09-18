"""P0 AR behaviors — tool events, jail deny, tenancy, persist, hitl, scrub."""
from __future__ import annotations

import pytest

from ar.emitter import ActionRecordingEmitter, ScrubError, secret_leaks_in
from ar.runtime import clear_emitters, emit_tool_outcome, emit_tool_requested, set_emitter
from control_plane.deps import get_ar_emitter, reset_runtime_for_tests, set_ar_emitter
from tools.builtin import run_tool
from workflows.research_publish_v1.nodes import tools_node


@pytest.mark.asyncio
async def test_ar_tenancy_404(app_client, auth_headers, other_tenant_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "AR tenancy"},
    )
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]

    ok = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["schema_version"] == "arpa.action_recording.v0"
    assert ok.json()["integrity"]["scrubbed"] is True

    denied = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=other_tenant_headers
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_tool_events_in_ar_export(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Need tool AR events"},
    )
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]

    ar = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    assert ar.status_code == 200, ar.text
    body = ar.json()
    types = [e["type"] for e in body["events"]]
    assert "run.started" in types
    assert "tool.requested" in types
    assert "tool.completed" in types
    tool_req = next(e for e in body["events"] if e["type"] == "tool.requested")
    assert tool_req["payload"]["tool_id"] == "web_fetch_readonly"
    assert "args_digest" in tool_req["payload"]
    assert "url" not in tool_req["payload"]  # digests, not raw args


@pytest.mark.asyncio
async def test_jail_deny_appears_in_ar_export(app_client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    # Create a real run so we have an owned thread + emitter registry entry
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Jail deny AR"},
    )
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]

    emitter = get_ar_emitter(thread_id)
    assert emitter is not None

    # Exercise tools_node path with outside-root write
    from langchain_core.runnables import RunnableConfig

    state = {
        "tool_intents": [
            {"name": "workspace_write", "args": {"path": "/tmp/arpa-p0-jail-deny.txt", "content": "x"}}
        ],
        "tool_results": [],
    }
    out = tools_node(state, config=RunnableConfig(configurable={"thread_id": thread_id}))
    assert any(r.get("status") == "denied" for r in out["tool_results"])

    ar = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    # Persist may lag — emitter is in-memory; force persist via another GET after flush
    # Export reads in-memory emitter directly
    assert ar.status_code == 200, ar.text
    denied = [
        e
        for e in ar.json()["events"]
        if e["type"] == "tool.denied" and e["payload"].get("reason") == "folder_jail"
    ]
    assert denied, f"expected folder_jail tool.denied in {ar.json()['events']}"
    assert denied[0]["payload"]["tool_id"] == "workspace_write"


@pytest.mark.asyncio
async def test_ar_persists_after_emitter_cleared(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Persist AR across restart"},
    )
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]

    before = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    assert before.status_code == 200
    seqs_before = [e["seq"] for e in before.json()["events"]]
    assert seqs_before
    assert "tool.requested" in [e["type"] for e in before.json()["events"]]

    # Simulate process restart: wipe in-memory emitters (DB rows remain)
    clear_emitters()
    assert get_ar_emitter(thread_id) is None

    after = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    assert after.status_code == 200, after.text
    types = [e["type"] for e in after.json()["events"]]
    assert "run.started" in types
    assert "tool.requested" in types
    assert after.json()["integrity"]["scrubbed"] is True
    # Must not invent a brand-new stub-only timeline for owned ran threads
    assert after.json().get("_scaffold_note", "").startswith("P0") or "Cold stub" not in after.json().get(
        "_scaffold_note", ""
    )


@pytest.mark.asyncio
async def test_reject_writes_hitl_row(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Reject HITL AR"},
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

    ar = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    assert ar.status_code == 200
    hitl = ar.json()["hitl"]
    assert hitl, "expected hitl[] row on reject"
    assert hitl[-1]["decision"] == "reject"
    assert hitl[-1]["side_effect_executed"] is False


@pytest.mark.asyncio
async def test_reapprove_sets_duplicate_suppressed(app_client, auth_headers):
    r = await app_client.post(
        "/v1/runs",
        headers=auth_headers,
        json={"goal": "Dup suppress AR"},
    )
    assert r.status_code == 200
    thread_id = r.json()["thread_id"]
    g = await app_client.get(f"/v1/runs/{thread_id}", headers=auth_headers)
    body = g.json()
    if body["status"] != "interrupted" or not body.get("pending_action"):
        pytest.skip("not on HITL")

    pending_id = body["pending_action"]["id"]

    a1 = await app_client.post(
        f"/v1/runs/{thread_id}/resume",
        headers=auth_headers,
        json={"decision": "approve"},
    )
    assert a1.status_code == 200, a1.text

    # Force status back to interrupted with same pending so ledger early-return path runs
    from db.session import get_session_factory
    from db import repo
    from control_plane.auth import mint_dev_token
    from control_plane.settings import Settings

    factory = get_session_factory()
    async with factory() as session:
        await repo.update_conversation(
            session,
            thread_id=thread_id,
            tenant_id="tenant-a",
            user_id="user-1",
            status="interrupted",
            metadata_patch={"pending_action": body["pending_action"]},
        )

    a2 = await app_client.post(
        f"/v1/runs/{thread_id}/resume",
        headers=auth_headers,
        json={"decision": "approve"},
    )
    assert a2.status_code == 200, a2.text
    # Same publish URL — no second side effect
    assert a2.json().get("publish_url") == a1.json().get("publish_url")

    ar = await app_client.get(
        f"/v1/runs/{thread_id}/action-recording", headers=auth_headers
    )
    assert ar.status_code == 200
    pub = ar.json().get("publish") or {}
    assert pub.get("duplicate_suppressed") is True


def test_scrub_fail_closed_never_hardcodes_true(monkeypatch):
    em = ActionRecordingEmitter(
        thread_id="t1", tenant_id="ten", user_id="u1"
    )
    em.emit("run.started", summary="ok", payload={"input_ref": "x"})
    # Happy path: scrub pass ⇒ scrubbed True (not hard-coded without check)
    doc = em.export(status_at_export="running", fail_closed=True)
    assert doc["integrity"]["scrubbed"] is True

    # Fail-closed: if scrub leaves secret-like material, export must refuse
    monkeypatch.setattr(
        "ar.emitter.scrub_value",
        lambda v: {"api_key": "sk-abcdefghijklmnop"} if isinstance(v, dict) else v,
    )
    with pytest.raises(ScrubError):
        em.export(status_at_export="running", fail_closed=True)


def test_emit_tool_denied_folder_jail_payload():
    em = ActionRecordingEmitter(thread_id="t2", tenant_id="ten", user_id="u1")
    set_emitter("t2", em)
    emit_tool_requested("t2", tool_id="workspace_write", args={"path": "/etc/x"}, gated=False)
    tr = run_tool("workspace_write", path="/etc/x", content="no")
    assert tr.status == "denied"
    emit_tool_outcome(
        "t2",
        tool_id="workspace_write",
        args={"path": "/etc/x"},
        status=tr.status,
        reason=tr.reason,
        result=tr.result,
        specialist=tr.specialist,
    )
    denied = [e for e in em.events if e["type"] == "tool.denied"]
    assert len(denied) == 1
    assert denied[0]["payload"] == {"tool_id": "workspace_write", "reason": "folder_jail"}
    clear_emitters()
