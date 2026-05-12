"""
data_loader.py
Single source of truth for data access.

Local dev:   reads CSV files from backend/data/
AWS (prod):  reads from S3 using awswrangler

Switch via environment variables:
  USE_S3=true
  S3_BUCKET=mappro-mediguard
  S3_PREFIX=mediguard/data/
"""

import os
import numpy as np
import pandas as pd

# ── Environment config ─────────────────────────────────────────────────────
USE_S3     = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET  = os.getenv("S3_BUCKET", "mediguard_mappro_demo")
S3_PREFIX  = os.getenv("S3_PREFIX", "mediguard/data/")
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")

if USE_S3:
    import awswrangler as wr


class DataStore:
    def __init__(self):
        src = f"s3://{S3_BUCKET}/{S3_PREFIX}" if USE_S3 else DATA_DIR
        print(f"\nLoading DataStore from {'S3' if USE_S3 else 'local'}: {src}")
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
        if USE_S3:
            df = wr.s3.read_csv(f"s3://{S3_BUCKET}/{S3_PREFIX}{filename}")
        else:
            df = pd.read_csv(os.path.join(DATA_DIR, filename))
        return df.where(pd.notnull(df), None)

    def _enrich(self):
        med_meta = self.medicines[[
            "medicine_id", "name", "generic_name", "category", "pres_restrictions"
        ]].rename(columns={"name": "medicine_name"})
        self.complaints = self.complaints.merge(med_meta, on="medicine_id", how="left")

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

    def get_complaints(self, state=None, district=None,
                       date_from=None, date_to=None,
                       medicine_id=None, verified=None):
        df = self.complaints
        if state:       df = df[df["state"]       == state]
        if district:    df = df[df["district"]    == district]
        if date_from:   df = df[df["date"]        >= date_from]
        if date_to:     df = df[df["date"]        <= date_to]
        if medicine_id: df = df[df["medicine_id"] == medicine_id]
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
