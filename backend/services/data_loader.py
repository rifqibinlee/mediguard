"""
data_loader.py
Single source of truth for data access.
Locally: reads from CSV files in backend/data/
AWS:     swap get_store() to query Athena via awswrangler — routers unchanged.
"""

import os
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


class DataStore:
    def __init__(self):
        print("\nLoading DataStore...")
        self.medicines          = self._load("medicines.csv")
        self.suppliers          = self._load("suppliers.csv")
        self.facilities         = self._load("facilities.csv")
        self.facility_medicines = self._load("facility_medicines.csv")
        self.complaints         = self._load("complaints.csv")
        self._enrich()
        print(f"  {len(self.facilities)} facilities")
        print(f"  {len(self.complaints)} complaints")
        print(f"  {len(self.suppliers)} suppliers")
        print("DataStore ready.\n")

    # ── Private ────────────────────────────────────────────────────────────

    def _load(self, filename: str) -> pd.DataFrame:
        path = os.path.join(DATA_DIR, filename)
        df   = pd.read_csv(path)
        # Replace NaN → None so FastAPI serialises to JSON null, not float('nan')
        return df.where(pd.notnull(df), None)

    def _enrich(self):
        """Pre-join medicine + facility metadata onto complaints once at startup."""

        # Medicine metadata
        med_meta = self.medicines[[
            "medicine_id", "name", "generic_name", "category", "pres_restrictions"
        ]].rename(columns={"name": "medicine_name"})
        self.complaints = self.complaints.merge(med_meta, on="medicine_id", how="left")

        # Facility name + type (where medicine was purchased)
        fac_meta = self.facilities[["facility_id", "name", "type"]].rename(
            columns={"name": "facility_name", "type": "facility_type"}
        )
        self.complaints = self.complaints.merge(
            fac_meta,
            left_on="purchased_from_facility_id",
            right_on="facility_id",
            how="left",
        )
        self.complaints.drop(columns=["facility_id"], errors="ignore", inplace=True)

        # Left-joins introduce new NaN rows — clean them so every downstream
        # .to_dict("records") call is JSON-safe without extra work in the routers.
        self.complaints = self.complaints.replace([np.nan, np.inf, -np.inf], None)

    # ── Facilities ─────────────────────────────────────────────────────────

    def get_facilities(self, type_filter=None, state=None, district=None):
        df = self.facilities
        if type_filter: df = df[df["type"]     == type_filter]
        if state:       df = df[df["state"]    == state]
        if district:    df = df[df["district"] == district]
        return df

    def get_facility_suppliers(self, facility_id: str):
        fm      = self.facility_medicines[self.facility_medicines["facility_id"] == facility_id]
        sup_ids = fm["supplier_id"].unique()
        return self.suppliers[self.suppliers["supplier_id"].isin(sup_ids)]

    # ── Complaints ─────────────────────────────────────────────────────────

    def get_complaints(
        self,
        state=None, district=None,
        date_from=None, date_to=None,
        medicine_id=None, verified=None,
    ):
        df = self.complaints
        if state:        df = df[df["state"]       == state]
        if district:     df = df[df["district"]    == district]
        if date_from:    df = df[df["date"]        >= date_from]
        if date_to:      df = df[df["date"]        <= date_to]
        if medicine_id:  df = df[df["medicine_id"] == medicine_id]
        if verified is not None:
            df = df[df["verified"] == verified]
        return df

    # ── Suppliers ──────────────────────────────────────────────────────────

    def get_suppliers(self, state=None, suspicious=None):
        df = self.suppliers
        if state:              df = df[df["state"] == state]
        if suspicious is not None:
            df = df[df["is_suspicious"] == suspicious]
        return df

    def get_supplier_facilities(self, supplier_id: str):
        fm      = self.facility_medicines[self.facility_medicines["supplier_id"] == supplier_id]
        fac_ids = fm["facility_id"].unique()
        return self.facilities[self.facilities["facility_id"].isin(fac_ids)]

    # ── Filter options ─────────────────────────────────────────────────────

    def get_filter_options(self):
        return {
            "states":    sorted(self.complaints["state"].dropna().unique().tolist()),
            "districts": sorted(self.complaints["district"].dropna().unique().tolist()),
            "medicines": (
                self.medicines[["medicine_id", "name", "category"]]
                .sort_values("name")
                .to_dict("records")
            ),
            "date_min": self.complaints["date"].min(),
            "date_max": self.complaints["date"].max(),
        }


# ── Singleton ──────────────────────────────────────────────────────────────

_store: DataStore | None = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store