from fastapi import APIRouter, Query
from typing import Optional
from backend.services.data_loader import get_store

router = APIRouter()


@router.get("/facilities")
def list_facilities(
    type:     Optional[str] = Query(None, description="hospital | clinic | pharmacy"),
    state:    Optional[str] = None,
    district: Optional[str] = None,
):
    df = get_store().get_facilities(type_filter=type, state=state, district=district)
    return df.to_dict("records")


@router.get("/facilities/{facility_id}/suppliers")
def facility_suppliers(facility_id: str):
    """Suppliers connected to a specific facility (for map lines)."""
    df = get_store().get_facility_suppliers(facility_id)
    return df.to_dict("records")