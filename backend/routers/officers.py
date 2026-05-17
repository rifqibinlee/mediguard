"""
officers.py — Field officer management and cluster assignment.

Assignments are held in-memory for this session.
In a production deployment these would be persisted to a database.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.data_loader import get_store

router = APIRouter()

# In-memory assignment store: { cluster_id: assignment_dict }
_assignments: dict = {}


class AssignBody(BaseModel):
    officer_id: str


@router.get("/officers")
def list_officers():
    return get_store().officers.to_dict("records")


@router.post("/clusters/{cluster_id}/assign")
def assign_officer(cluster_id: str, body: AssignBody):
    s   = get_store()
    row = s.officers[s.officers["officer_id"] == body.officer_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Officer not found")
    officer = row.iloc[0]
    _assignments[cluster_id] = {
        "cluster_id":   cluster_id,
        "officer_id":   body.officer_id,
        "officer_name": str(officer["name"]),
        "department":   str(officer.get("department", "")),
        "state":        str(officer.get("state", "")),
        "assigned_at":  datetime.utcnow().isoformat() + "Z",
        "status":       "investigating",
        "completed_at": None,
    }
    return {"status": "assigned", "assignment": _assignments[cluster_id]}


@router.get("/clusters/{cluster_id}/assignment")
def get_assignment(cluster_id: str):
    return _assignments.get(cluster_id, {"status": "unassigned"})


@router.post("/clusters/{cluster_id}/complete")
def complete_assignment(cluster_id: str):
    """Mark a cluster raid as complete (complaints conceptually archived)."""
    if cluster_id not in _assignments:
        _assignments[cluster_id] = {
            "cluster_id":  cluster_id,
            "officer_id":  None,
            "officer_name": "Unknown",
            "assigned_at": datetime.utcnow().isoformat() + "Z",
            "status":      "completed",
        }
    else:
        _assignments[cluster_id]["status"]       = "completed"
        _assignments[cluster_id]["completed_at"] = datetime.utcnow().isoformat() + "Z"
    return {"status": "completed", "assignment": _assignments[cluster_id]}


@router.get("/assignments")
def list_assignments():
    return list(_assignments.values())
