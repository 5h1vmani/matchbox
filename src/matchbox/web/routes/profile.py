"""Profile editor endpoints — live-tunable scoring weights.

POST /p/{profile}/profile/preview  -> live re-score preview (no DB writes)
POST /p/{profile}/profile/save     -> persist weights to profile.yaml
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.core.schema import ScoringWeights
from matchbox.web.deps import ProfileDep, SettingsDep
from matchbox.web.profile_view import WEIGHT_FIELDS, preview_rescore, update_weights
from matchbox.web.render import render

router = APIRouter()


def _form_to_weights(
    cv_match_weight: float,
    company_mission_fit_weight: float,
    role_mission_fit_weight: float,
    comp_weight: float,
    cultural_weight: float,
    red_flags_weight: float,
) -> ScoringWeights:
    return ScoringWeights(
        cv_match_weight=cv_match_weight,
        company_mission_fit_weight=company_mission_fit_weight,
        role_mission_fit_weight=role_mission_fit_weight,
        comp_weight=comp_weight,
        cultural_weight=cultural_weight,
        red_flags_weight=red_flags_weight,
    )


@router.post("/preview", response_class=HTMLResponse)
async def preview(
    request: Request,
    profile: ProfileDep,
    cv_match_weight: Annotated[float, Form()],
    company_mission_fit_weight: Annotated[float, Form()],
    role_mission_fit_weight: Annotated[float, Form()],
    comp_weight: Annotated[float, Form()],
    cultural_weight: Annotated[float, Form()],
    red_flags_weight: Annotated[float, Form()],
) -> HTMLResponse:
    """Render a live re-score preview for the slider values.

    Pure read — no DB writes, no LLM call. weighted_total() recomputes from
    cached dimension scores in milliseconds even for hundreds of jobs.
    """
    weights = _form_to_weights(
        cv_match_weight,
        company_mission_fit_weight,
        role_mission_fit_weight,
        comp_weight,
        cultural_weight,
        red_flags_weight,
    )
    preview_data = preview_rescore(profile, weights, top_n=10)
    return render(
        request,
        "components/_rescore_preview.html",
        {"preview": preview_data, "active_profile": profile},
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
