"""Fail-closed output-directory validation for reproduction commands.

Scientific reproduction must never delete the repository, retained evidence,
or an unrelated path.  Outputs are therefore confined to a new descendant of
``<artifact>/reproductions``.  Existing paths and symlinked ancestors are
rejected; callers create the returned path with ``exist_ok=False``.
"""
from __future__ import annotations

import os
from pathlib import Path


class UnsafeOutput(ValueError):
    """Raised when a requested reproduction output could overwrite evidence."""


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def validate_new_output(root: Path, requested: Path | str) -> Path:
    """Return a safe absolute output path without creating or deleting it.

    The path must be a *new* descendant of ``root/reproductions`` with at least
    one component below that directory.  Existing files/directories, the
    repository root, ancestors, retained ``results`` data, external projects,
    and any route through an existing symlink are rejected.
    """
    root = root.resolve(strict=True)
    raw = Path(requested)
    candidate = raw if raw.is_absolute() else root / raw
    candidate = _absolute_without_resolving(candidate)
    dedicated = root / "reproductions"

    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafeOutput("output must stay inside this artifact repository") from exc

    if len(rel.parts) < 2 or rel.parts[0] != "reproductions":
        raise UnsafeOutput("output must be a new descendant of artifact/reproductions/")
    if candidate.exists() or candidate.is_symlink():
        raise UnsafeOutput("output path already exists; choose a new dedicated directory")

    # Reject any existing symlink from the repository root to the output parent.
    current = root
    for part in rel.parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise UnsafeOutput("output ancestry contains a symbolic link")

    # Resolve all existing ancestors and ensure they still remain under the
    # dedicated output root.  This catches links or mount-like redirections.
    parent_real = candidate.parent.resolve(strict=False)
    dedicated_real = dedicated.resolve(strict=False)
    if parent_real != dedicated_real and dedicated_real not in parent_real.parents:
        raise UnsafeOutput("resolved output parent escapes artifact/reproductions/")
    return candidate


def create_new_output(root: Path, requested: Path | str) -> Path:
    path = validate_new_output(root, requested)
    dedicated = root.resolve(strict=True) / "reproductions"
    dedicated.mkdir(mode=0o755, exist_ok=True)
    if dedicated.is_symlink():
        raise UnsafeOutput("artifact/reproductions must not be a symbolic link")
    # Revalidate after creating the dedicated parent, then create atomically.
    path = validate_new_output(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=0o755, exist_ok=False)
    return path
