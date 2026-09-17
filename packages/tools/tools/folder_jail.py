"""Folder jail — writes outside ALLOWED_ROOT fail (HG-JAIL)."""
from __future__ import annotations

import os
from pathlib import Path


class FolderJailError(PermissionError):
    """Raised when a write targets a path outside the allowed root."""

    def __init__(self, path: str, allowed_root: str) -> None:
        self.path = path
        self.allowed_root = allowed_root
        super().__init__(
            f"folder_jail: write denied for {path!r} (allowed root: {allowed_root!r})"
        )


def get_allowed_root() -> Path:
    raw = os.environ.get("ALLOWED_ROOT", "").strip()
    if not raw:
        # Sensible default for local scaffold
        raw = os.path.join(os.getcwd(), "workspace_data")
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_under_root(relative_or_abs: str, *, allowed_root: Path | None = None) -> Path:
    root = allowed_root or get_allowed_root()
    candidate = Path(relative_or_abs)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FolderJailError(str(resolved), str(root)) from exc
    return resolved


def assert_write_allowed(path: str, *, allowed_root: Path | None = None) -> Path:
    """Validate path is under ALLOWED_ROOT; return resolved path or raise FolderJailError."""
    return resolve_under_root(path, allowed_root=allowed_root)
