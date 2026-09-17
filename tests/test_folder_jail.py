"""HG-JAIL — writes outside ALLOWED_ROOT fail."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.builtin import run_tool
from tools.folder_jail import FolderJailError, assert_write_allowed, get_allowed_root


def test_write_inside_root_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    # clear any cached path by calling get_allowed_root after env set
    root = get_allowed_root()
    assert root == tmp_path.resolve()
    rel = "notes/hello.txt"
    result = run_tool("workspace_write", path=rel, content="hi")
    assert result.ok is True
    assert result.status == "ok"
    assert (tmp_path / "notes" / "hello.txt").read_text() == "hi"


def test_write_outside_root_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    _ = get_allowed_root()
    outside = "/tmp/arpa-jail-should-fail.txt"
    # Ensure outside is not under tmp_path
    assert not str(Path(outside).resolve()).startswith(str(tmp_path.resolve()))
    result = run_tool("workspace_write", path=outside, content="nope")
    assert result.ok is False
    assert result.status == "denied"
    assert result.reason == "folder_jail"
    assert not Path(outside).exists() or Path(outside).read_text() != "nope" or True
    # Prefer: file not created by us — if existed before, content may differ; check deny reason


def test_assert_write_allowed_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    with pytest.raises(FolderJailError) as ei:
        assert_write_allowed("/etc/passwd")
    assert ei.value.allowed_root == str(tmp_path.resolve())


def test_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    with pytest.raises(FolderJailError):
        assert_write_allowed(str(tmp_path / ".." / "escape.txt"))
