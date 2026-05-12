from fastapi import APIRouter
from typing import Optional
from backend.services.data_loader import get_store

router = APIRouter()


@router.get("/complaints")
def list_complaints(
    state:       Optional[str]  = None,
    district:    Optional[str]  = None,
    date_from:   Optional[str]  = None,
    date_to:     Optional[str]  = None,
    medicine_id: Optional[str]  = None,
    verified:    Optional[bool] = None,
):
    df = get_store().get_complaints(
        state=state, district=district,
        date_from=date_from, date_to=date_to,
        medicine_id=medicine_id, verified=verified,
    )
    return df.to_dict("records")