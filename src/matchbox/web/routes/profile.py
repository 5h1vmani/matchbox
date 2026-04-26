"""Profile editor endpoints — live-tunable scoring weights.

GET  /p/{profile}/profile/preview  -> normalisation + summary partial
POST /p/{profile}/profile/save     -> persist weights to profile.yaml
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.web.deps import ProfileDep, SettingsDep
from matchbox.web.profile_view import WEIGHT_FIELDS, update_weights
from matchbox.web.render import render

router = APIRouter()


@router.get("/preview", response_class=HTMLResponse)
async def preview(request: Request, profile: ProfileDep) -> HTMLResponse:
    # Reserved for live re-score preview (next phase).
    return HTMLResponse(
        "<div class='text-xs text-slate-400'>Live re-score preview lands in a follow-up.</div>"
    )


@router.post("/save", response_class=HTMLResponse)
async def save(
    request: Request,
    settings: SettingsDep,
    profile: ProfileDep,
    cv_match_weight: Annotated[float, Form()],
    company_mission_fit_weight: Annotated[float, Form()],
    role_mission_fit_weight: Annotated[float, Form()],
    comp_weight: Annotated[float, Form()],
    cultural_weight: Annotated[float, Form()],
    red_flags_weight: Annotated[float, Form()],
) -> HTMLResponse:
    new_weights = {
        "cv_match_weight": cv_match_weight,
        "company_mission_fit_weight": company_mission_fit_weight,
        "role_mission_fit_weight": role_mission_fit_weight,
        "comp_weight": comp_weight,
        "cultural_weight": cultural_weight,
        "red_flags_weight": red_flags_weight,
    }
    try:
        saved = update_weights(settings, profile, new_weights)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e)) from e

    total = sum(saved.values())
    return render(
        request,
        "components/_weights_saved.html",
        {
            "weights": saved,
            "total": total,
            "fields": WEIGHT_FIELDS,
        },
    )
