"""JSON API for the offer module (prefix /api/offers).

Exposes CRUD for offers and a truthful salary benchmark against the user's own
job-pool data. See offers/repo.py and offers/benchmark.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from matchbox.offers import repo
from matchbox.offers.benchmark import benchmark
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/offers")


class CreateOfferBody(BaseModel):
    applicationId: int
    base: float | None = None
    bonus: float | None = None
    equity: str | None = None
    currency: str | None = None
    location: str | None = None
    receivedAt: str | None = None
    notes: str | None = None


class SetStatusBody(BaseModel):
    status: str


@router.get("")
def list_offers(
    conn: ConnDep,
    applicationId: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """All offers, or filtered by ?applicationId=N."""
    if applicationId is not None:
        return repo.list_for_app(conn, applicationId)
    return repo.list_all(conn)


@router.post("")
def create_offer(body: CreateOfferBody, conn: ConnDep) -> dict[str, Any]:
    """Record a new offer."""
    oid = repo.create(
        conn,
        body.applicationId,
        base=body.base,
        bonus=body.bonus,
        equity=body.equity,
        currency=body.currency,
        location=body.location,
        received_at=body.receivedAt,
        notes=body.notes,
    )
    created = repo.get(conn, oid)
    assert created is not None  # just inserted
    return created


@router.post("/{offer_id}/status")
def set_offer_status(offer_id: int, body: SetStatusBody, conn: ConnDep) -> dict[str, Any]:
    """Transition an offer to a new status."""
    try:
        offer = repo.set_status(conn, offer_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if offer is None:
        raise HTTPException(status_code=404, detail="no such offer")
    return offer


@router.get("/benchmark")
def get_benchmark(
    conn: ConnDep,
    base: float = Query(...),
    roleFamily: str | None = Query(default=None),
    currency: str | None = Query(default=None),
) -> dict[str, Any]:
    """Benchmark a base salary against the user's own discovered-job salary data."""
    return benchmark(conn, base=base, role_family=roleFamily, currency=currency)
