"""FastAPI dependencies — profile resolution, settings, validation.

Centralised so route files stay focused on their own concern (least privilege:
each route gets exactly the dependencies it needs, nothing more).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi import Path as PathParam

from matchbox.web.config import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


def shell_context(
    settings: Settings, active_profile: str | None, active_page: str
) -> dict[str, Any]:
    """Common context for full-page templates: profile list, active selectors.

    SSOT — both pages and the welcome route must call this so the nav header
    looks consistent. Don't construct this dict by hand anywhere else.
    """
    return {
        "profiles": list_profiles(settings),
        "active_profile": active_profile,
        "active_page": active_page,
    }


SettingsDep = Annotated[Settings, Depends(get_settings)]


def list_profiles(settings: SettingsDep) -> list[str]:
    """Return profile names that have a profile.yaml file."""
    if not settings.people_dir.exists():
        return []
    return sorted(
        d.name
        for d in settings.people_dir.iterdir()
        if d.is_dir() and (d / "profile.yaml").exists()
    )


def validate_profile(
    settings: SettingsDep,
    profile: Annotated[str, PathParam(pattern=r"^[a-z][a-z0-9_-]{0,30}$")],
) -> str:
    """
    Validate a profile name from a URL path.

    Defence in depth: the path-pattern regex blocks traversal at the FastAPI
    layer; this dependency confirms the directory actually exists. Routes that
    accept a profile name MUST depend on this rather than reading the raw path.
    """
    if not (settings.profile_dir(profile) / "profile.yaml").exists():
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile}' not found. Run `matchbox init-profile {profile}`.",
        )
    return profile


ProfileDep = Annotated[str, Depends(validate_profile)]


def safe_output_path(settings: Settings, profile: str, job_id: int, filename: str) -> Path:
    """
    Resolve a file under people/{profile}/output/{job_id}/{filename}, refusing
    any path that escapes that directory (defence against ../ traversal).
    """
    base = settings.output_dir(profile, job_id).resolve()
    candidate = (base / filename).resolve()
    if not str(candidate).startswith(str(base) + "/") and candidate != base:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return candidate
