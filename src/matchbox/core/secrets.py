"""Per-profile secret store for the BYOK provider key.

The key lives in a ``0600`` file under ``people/<slug>/.secret`` -- out of the
plaintext ``localStorage`` the prototype used, out of the profile data file, and
bound to the active profile (the ``mb_profile`` cookie resolves the slug). Only
the localhost proxy reads it; it is never serialized back to the browser. This
is the least-privilege home for a credential: owner read/write only, one file
per person, deletable in one call.
"""

from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path

from matchbox.core.db import db_path

KEY_FILENAME = ".secret"
_OWNER_RW = stat.S_IRUSR | stat.S_IWUSR  # 0o600


def _key_path(profile: str | None = None) -> Path:
    """The secret file sits beside the profile's DB -- `people/<slug>/.secret`
    in normal use, and inside the `MATCHBOX_DB` override directory under test,
    so it is isolated exactly like the DB is."""
    return db_path(profile).parent / KEY_FILENAME


def read_key(profile: str | None = None) -> str | None:
    """The stored provider key for this profile, or None when unset/empty."""
    path = _key_path(profile)
    try:
        value = open(path, encoding="utf-8").read().strip()  # noqa: SIM115
    except (FileNotFoundError, OSError):
        return None
    return value or None


def has_key(profile: str | None = None) -> bool:
    return read_key(profile) is not None


def write_key(value: str, profile: str | None = None) -> None:
    """Persist the key with ``0600`` perms. Empty value clears it instead."""
    if not value or not value.strip():
        clear_key(profile)
        return
    path = _key_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with restrictive perms from the start (umask-independent): open the
    # fd 0600, then write. chmod after, too, in case the file pre-existed.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _OWNER_RW)
    try:
        os.write(fd, value.strip().encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, _OWNER_RW)


def clear_key(profile: str | None = None) -> None:
    """Remove the stored key (idempotent)."""
    with contextlib.suppress(FileNotFoundError):
        _key_path(profile).unlink()
