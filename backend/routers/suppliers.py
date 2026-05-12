from fastapi import APIRouter
from typing import Optional
from backend.services.data_loader import get_store

router = APIRouter()


@router.get("/suppliers")
def list_suppliers(
    state:      Optional[str]  = None,
    suspicious: Optional[bool] = None,
):
    df = get_store().get_suppliers(state=state, suspicious=suspicious)
    return df.to_dict("records")


@router.get("/suppliers/{supplier_id}/facilities")
def supplier_facilities(supplier_id: str):
    """Facilities this supplier delivers to (for map lines)."""
    df = get_store().get_supplier_facilities(supplier_id)
    return df.to_dict("records")