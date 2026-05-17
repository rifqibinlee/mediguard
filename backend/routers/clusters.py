from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from backend.services.data_loader import get_store
from backend.services.dbscan_engine import (
    compute_clusters, compute_historical_clusters,
    clear_cache, get_cached_result,
)

router = APIRouter()


class ClusterParams(BaseModel):
    hospital_buffer_m:  float = Field(800, ge=100, le=10_000)
    clinic_buffer_m:    float = Field(500, ge=100, le=10_000)
    pharmacy_buffer_m:  float = Field(400, ge=100, le=10_000)


class HistoricalParams(BaseModel):
    date_from:          Optional[str] = None
    date_to:            Optional[str] = None
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


@router.post("/clusters/historical")
def run_historical_clusters(params: HistoricalParams):
    """Run DBSCAN on archived historical complaints for a given date range."""
    s   = get_store()
    df  = s.get_historical_complaints(
        date_from = params.date_from,
        date_to   = params.date_to,
    )
    return compute_historical_clusters(
        historical_df         = df,
        facilities_df         = s.facilities,
        medicines_df          = s.medicines,
        facility_medicines_df = s.facility_medicines,
        suppliers_df          = s.suppliers,
        hospital_buffer_m     = params.hospital_buffer_m,
        clinic_buffer_m       = params.clinic_buffer_m,
        pharmacy_buffer_m     = params.pharmacy_buffer_m,
    )


@router.get("/clusters/viewport")
def get_viewport_clusters(
    lat_min: float = Query(...),
    lat_max: float = Query(...),
    lng_min: float = Query(...),
    lng_max: float = Query(...),
):
    """Return DBSCAN clusters whose centroid falls within the given bounding box,
    sorted by severity_score descending. Also returns top medicines in view."""
    result = get_cached_result()
    if not result:
        return {"clusters": [], "top_medicines": []}

    clusters = [
        c for c in result.get("dbscan_clusters", [])
        if lat_min <= c["centroid_lat"] <= lat_max
        and lng_min <= c["centroid_lng"] <= lng_max
    ]
    clusters.sort(key=lambda x: x["severity_score"], reverse=True)

    # Top medicines from complaints in the viewport (DBSCAN only)
    med_counts: dict = {}
    for c in result.get("complaints", []):
        if c.get("cluster_type") != "dbscan":
            continue
        if not (lat_min <= float(c["lat"]) <= lat_max
                and lng_min <= float(c["lng"]) <= lng_max):
            continue
        med = c.get("medicine_name") or c.get("medicine_id", "Unknown")
        med_counts[med] = med_counts.get(med, 0) + 1

    top_meds = sorted(med_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    return {
        "clusters":     clusters,
        "top_medicines": [{"medicine": m, "count": n} for m, n in top_meds],
    }


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