"""
analytics.py
All endpoints powering the Analytics page and its charts/filters.

Endpoints
─────────
GET /api/analytics/summary       → KPI cards
GET /api/analytics/medicines     → most-faked medicines ranked
GET /api/analytics/timeseries    → complaints over time
GET /api/analytics/losses        → loss breakdown by category / state / medicine
GET /api/analytics/suppliers     → supplier risk ranking
GET /api/analytics/clusters      → DBSCAN cluster ranking (for analytics page table)
"""

from enum import Enum
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from backend.services.data_loader import get_store
from backend.services.dbscan_engine import compute_clusters

router = APIRouter()


# ── Enums for validated query params ──────────────────────────────────────

class Granularity(str, Enum):
    daily   = "daily"
    weekly  = "weekly"
    monthly = "monthly"

class GroupBy(str, Enum):
    category = "category"
    state    = "state"
    medicine = "medicine"


# ── Shared filter helper ───────────────────────────────────────────────────

def _filtered(
    state:       Optional[str] = None,
    district:    Optional[str] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    medicine_id: Optional[str] = None,
) -> pd.DataFrame:
    return get_store().get_complaints(
        state=state, district=district,
        date_from=date_from, date_to=date_to,
        medicine_id=medicine_id,
    )


# ── 1. Summary KPIs ───────────────────────────────────────────────────────

@router.get("/analytics/summary")
def get_summary(
    state:       Optional[str] = None,
    district:    Optional[str] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    medicine_id: Optional[str] = None,
):
    """
    Top-line numbers for the KPI cards.
    All values respect the active filter set.
    """
    cmp   = _filtered(state, district, date_from, date_to, medicine_id)
    store = get_store()
    n     = len(cmp)

    total_loss = float(cmp["estimated_loss"].sum())
    verified   = int(cmp["verified"].sum())

    most_affected_state = (
        cmp.groupby("state").size().idxmax() if n > 0 else None
    )

    # Suspicious suppliers reachable through complaints that name a facility
    fac_ids = cmp["purchased_from_facility_id"].dropna().unique()
    linked_sup_ids = store.facility_medicines.loc[
        store.facility_medicines["facility_id"].isin(fac_ids), "supplier_id"
    ].unique()
    n_suspicious = int(
        store.suppliers[
            store.suppliers["supplier_id"].isin(linked_sup_ids)
            & store.suppliers["is_suspicious"]
        ].shape[0]
    )

    return {
        "total_complaints":          n,
        "verified_complaints":       verified,
        "verification_rate_pct":     round(verified / n * 100, 1) if n else 0,
        "total_loss_myr":            round(total_loss, 2),
        "avg_loss_per_complaint":    round(total_loss / n, 2) if n else 0,
        "states_affected":           int(cmp["state"].nunique()),
        "districts_affected":        int(cmp["district"].nunique()),
        "medicines_implicated":      int(cmp["medicine_id"].nunique()),
        "suspicious_suppliers_linked": n_suspicious,
        "most_affected_state":       most_affected_state,
        "street_purchases":          int(cmp["purchased_from_facility_id"].isna().sum()),
        "facility_purchases":        int(cmp["purchased_from_facility_id"].notna().sum()),
    }


# ── 2. Medicine breakdown ─────────────────────────────────────────────────

@router.get("/analytics/medicines")
def get_medicines_breakdown(
    state:     Optional[str] = None,
    district:  Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    limit:     int           = Query(10, ge=1, le=50),
):
    """
    Medicines ranked by complaint count.
    Includes verification rate and total financial loss.
    """
    cmp   = _filtered(state, district, date_from, date_to)
    store = get_store()

    grouped = (
        cmp.groupby("medicine_id")
        .agg(
            complaint_count   = ("complaint_id",   "count"),
            verified_count    = ("verified",        "sum"),
            total_loss        = ("estimated_loss",  "sum"),
            avg_reported_price= ("reported_price",  "mean"),
        )
        .reset_index()
        .merge(
            store.medicines[[
                "medicine_id", "name", "generic_name",
                "category", "standard_price", "pres_restrictions",
            ]],
            on="medicine_id", how="left",
        )
        .sort_values("complaint_count", ascending=False)
        .head(limit)
    )

    grouped["total_loss"]         = grouped["total_loss"].round(2)
    grouped["avg_reported_price"] = grouped["avg_reported_price"].round(2)
    grouped["verification_rate_pct"] = (
        grouped["verified_count"] / grouped["complaint_count"] * 100
    ).round(1)

    return grouped.to_dict("records")


# ── 3. Time series ────────────────────────────────────────────────────────

@router.get("/analytics/timeseries")
def get_timeseries(
    state:       Optional[str] = None,
    district:    Optional[str] = None,
    medicine_id: Optional[str] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    granularity: Granularity   = Granularity.monthly,
):
    """
    Complaint counts and losses over time.
    granularity: daily | weekly | monthly
    """
    cmp = _filtered(state, district, date_from, date_to, medicine_id)
    cmp = cmp.copy()
    cmp["_date"] = pd.to_datetime(cmp["date"])

    if granularity == Granularity.daily:
        cmp["period"] = cmp["_date"].dt.strftime("%Y-%m-%d")
    elif granularity == Granularity.weekly:
        cmp["period"] = cmp["_date"].dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
    else:
        cmp["period"] = cmp["_date"].dt.strftime("%Y-%m")

    series = (
        cmp.groupby("period")
        .agg(
            complaint_count = ("complaint_id", "count"),
            verified_count  = ("verified",     "sum"),
            total_loss      = ("estimated_loss","sum"),
        )
        .reset_index()
        .sort_values("period")
    )
    series["total_loss"] = series["total_loss"].round(2)

    return {
        "granularity": granularity,
        "series":      series.to_dict("records"),
    }


# ── 4. Loss breakdown ─────────────────────────────────────────────────────

@router.get("/analytics/losses")
def get_losses_breakdown(
    state:     Optional[str] = None,
    district:  Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    group_by:  GroupBy       = GroupBy.category,
):
    """
    Financial loss aggregated by category | state | medicine.
    Drives the loss breakdown bar/pie charts on the analytics page.
    """
    cmp = _filtered(state, district, date_from, date_to)

    col_map = {
        GroupBy.category: "category",
        GroupBy.state:    "state",
        GroupBy.medicine: "medicine_name",
    }
    col = col_map[group_by]

    breakdown = (
        cmp.groupby(col)
        .agg(
            complaint_count = ("complaint_id",   "count"),
            verified_count  = ("verified",        "sum"),
            total_loss      = ("estimated_loss",  "sum"),
            avg_loss        = ("estimated_loss",  "mean"),
        )
        .reset_index()
        .sort_values("total_loss", ascending=False)
    )
    breakdown["total_loss"] = breakdown["total_loss"].round(2)
    breakdown["avg_loss"]   = breakdown["avg_loss"].round(2)

    return {
        "group_by":  group_by,
        "breakdown": breakdown.to_dict("records"),
    }


# ── 5. Supplier risk ──────────────────────────────────────────────────────

@router.get("/analytics/suppliers")
def get_supplier_analysis(
    state:      Optional[str]  = None,
    suspicious: Optional[bool] = None,
    limit:      int            = Query(20, ge=1, le=100),
):
    """
    Supplier risk table.
    Shows facilities supplied, complaints linked through those facilities,
    and flags suspicious licence status.
    """
    store = get_store()
    fm    = store.facility_medicines
    cmp   = store.complaints

    # Complaints → facility → complaint count + loss
    fac_stats = (
        cmp[cmp["purchased_from_facility_id"].notna()]
        .groupby("purchased_from_facility_id")
        .agg(
            complaint_count = ("complaint_id",  "count"),
            total_loss      = ("estimated_loss", "sum"),
        )
        .reset_index()
        .rename(columns={"purchased_from_facility_id": "facility_id"})
    )

    # Supplier → distinct facilities count
    sup_fac = (
        fm.groupby("supplier_id")["facility_id"]
        .nunique()
        .reset_index()
        .rename(columns={"facility_id": "facilities_supplied"})
    )

    # Supplier → linked complaint count (via supplied facilities)
    sup_cmp = (
        fm.merge(fac_stats, on="facility_id", how="left")
        .groupby("supplier_id")
        .agg(
            linked_complaints = ("complaint_count", "sum"),
            linked_loss       = ("total_loss",      "sum"),
        )
        .reset_index()
    )

    result = (
        store.suppliers
        .merge(sup_fac, on="supplier_id", how="left")
        .merge(sup_cmp, on="supplier_id", how="left")
    )

    result["facilities_supplied"] = result["facilities_supplied"].fillna(0).astype(int)
    result["linked_complaints"]   = result["linked_complaints"].fillna(0).astype(int)
    result["linked_loss"]         = result["linked_loss"].fillna(0.0).round(2)

    if state:
        result = result[result["state"] == state]
    if suspicious is not None:
        result = result[result["is_suspicious"] == suspicious]

    result = result.sort_values("linked_complaints", ascending=False).head(limit)
    return result.to_dict("records")


# ── 6. Cluster ranking (for analytics table) ──────────────────────────────

@router.get("/analytics/clusters")
def get_cluster_ranking(
    hospital_buffer_m:  float = Query(800, ge=100, le=10_000),
    clinic_buffer_m:    float = Query(500, ge=100, le=10_000),
    pharmacy_buffer_m:  float = Query(400, ge=100, le=10_000),
    limit: int = Query(10, ge=1, le=50),
):
    store  = get_store()
    result = compute_clusters(
        complaints_df         = store.complaints,
        facilities_df         = store.facilities,
        medicines_df          = store.medicines,
        facility_medicines_df = store.facility_medicines,
        suppliers_df          = store.suppliers,
        hospital_buffer_m     = hospital_buffer_m,
        clinic_buffer_m       = clinic_buffer_m,
        pharmacy_buffer_m     = pharmacy_buffer_m,
    )

    cmp_df   = pd.DataFrame(result["complaints"])
    enriched = []

    for cluster in result["dbscan_clusters"][:limit]:
        cid  = cluster["cluster_id"]
        pts  = cmp_df[cmp_df["cluster_id"] == cid]
        enriched.append({
            **cluster,
            "state_breakdown":    pts.groupby("state").size().to_dict() if len(pts) else {},
            "district_breakdown": pts.groupby("district").size().to_dict() if len(pts) else {},
        })

    return {
        "params":   result["params"],
        "summary":  result["summary"],
        "clusters": enriched,
    }