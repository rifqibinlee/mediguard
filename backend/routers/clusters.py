from fastapi import APIRouter
from pydantic import BaseModel, Field
from backend.services.data_loader import get_store
from backend.services.dbscan_engine import compute_clusters, clear_cache, get_cached_result

router = APIRouter()


class ClusterParams(BaseModel):
    hospital_buffer_m:  float = Field(800, ge=100, le=10_000)
    clinic_buffer_m:    float = Field(500, ge=100, le=10_000)
    pharmacy_buffer_m:  float = Field(400, ge=100, le=10_000)


@router.post("/clusters")
def run_clusters(params: ClusterParams):
    s = get_store()
    return compute_clusters(
        complaints_df         = s.complaints,
        facilities_df         = s.facilities,
        medicines_df          = s.medicines,
        facility_medicines_df = s.facility_medicines,
        suppliers_df          = s.suppliers,
        hospital_buffer_m     = params.hospital_buffer_m,
        clinic_buffer_m       = params.clinic_buffer_m,
        pharmacy_buffer_m     = params.pharmacy_buffer_m,
    )


@router.delete("/clusters/cache")
def invalidate_cache():
    clear_cache()
    return {"status": "cache cleared"}

@router.get("/clusters/latest")
def get_latest():
    """Return the cached cluster result loaded from disk on startup."""
    result = get_cached_result()
    if result is None:
        return {"available": False}
    return result