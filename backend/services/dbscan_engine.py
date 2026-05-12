"""
dbscan_engine.py

Core clustering pipeline:
  1. Separate buffer test — each facility type has its own adjustable radius.
  2. Auto-DBSCAN        — eps and min_pts are derived from the data using KNN statistics.
                          k = max(4, round(ln(N))) scales with dataset size (boss's correction).
  3. Summaries          — centroids, losses, top medicines, nearby suppliers per cluster.
  4. Cache              — keyed by (hospital_buffer_m, clinic_buffer_m, pharmacy_buffer_m).
"""

import json
import math
import os
import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

EARTH_R_M   = 6_371_000.0
_cache: dict = {}

# AutoDBSCAN constants
BETA       = 2.0
ELBOW_PCT  = 0.745
K_FLOOR    = 4

# ── Environment config ─────────────────────────────────────────────────────
USE_S3    = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "mediguard_mappro_demo")
S3_PREFIX = os.getenv("S3_PREFIX", "mediguard/data/")

if USE_S3:
    import boto3

# ── Disk / S3 persistence ───────────────────────────────────────────────────
CLUSTER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "clusters")
os.makedirs(CLUSTER_DIR, exist_ok=True)


def _cache_path(key: tuple) -> str:
    return os.path.join(CLUSTER_DIR, f"cluster_{int(key[0])}_{int(key[1])}_{int(key[2])}.json")


def _json_safe(obj):
    """Recursively make a result dict JSON-serialisable (handles numpy types)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(i) for i in obj]
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _s3_key(key: tuple) -> str:
    return f"{S3_PREFIX}clusters/cluster_{int(key[0])}_{int(key[1])}_{int(key[2])}.json"


def _save_to_disk(key: tuple, result: dict):
    if USE_S3:
        try:
            boto3.client("s3").put_object(
                Bucket=S3_BUCKET,
                Key=_s3_key(key),
                Body=json.dumps(_json_safe(result)),
                ContentType="application/json",
            )
            print(f"  Cluster saved → s3://{S3_BUCKET}/{_s3_key(key)}")
        except Exception as e:
            print(f"  Warning: could not save cluster to S3: {e}")
    else:
        try:
            with open(_cache_path(key), "w") as f:
                json.dump(_json_safe(result), f)
            print(f"  Cluster saved → {_cache_path(key)}")
        except Exception as e:
            print(f"  Warning: could not save cluster locally: {e}")


def _load_from_disk(key: tuple) -> dict | None:
    if USE_S3:
        try:
            obj = boto3.client("s3").get_object(Bucket=S3_BUCKET, Key=_s3_key(key))
            return json.loads(obj["Body"].read())
        except Exception:
            return None
    else:
        path = _cache_path(key)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                return None
        return None


def get_cached_result() -> dict | None:
    """Return the most recently loaded cluster result from memory cache."""
    if not _cache:
        return None
    return list(_cache.values())[-1]


def load_latest_cluster() -> tuple | None:
    """Load most recently saved cluster into memory on startup (local or S3)."""
    if USE_S3:
        try:
            s3  = boto3.client("s3")
            pfx = f"{S3_PREFIX}clusters/"
            res = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=pfx)
            objects = [o for o in res.get("Contents", [])
                       if o["Key"].endswith(".json") and "cluster_" in o["Key"]]
            if not objects:
                return None
            latest = max(objects, key=lambda o: o["LastModified"])
            name   = latest["Key"].split("/")[-1].replace("cluster_","").replace(".json","")
            parts  = name.split("_")
            key    = (float(parts[0]), float(parts[1]), float(parts[2]))
            result = _load_from_disk(key)
            if result:
                _cache[key] = result
                print(f"  Cluster cache loaded from S3: params={key}")
                return key
        except Exception as e:
            print(f"  Warning: could not load cluster from S3: {e}")
        return None
    else:
        if not os.path.exists(CLUSTER_DIR):
            return None
        files = [f for f in os.listdir(CLUSTER_DIR)
                 if f.startswith("cluster_") and f.endswith(".json")]
        if not files:
            return None
        latest = max(files, key=lambda f: os.path.getmtime(os.path.join(CLUSTER_DIR, f)))
        try:
            name  = latest.replace("cluster_", "").replace(".json", "")
            parts = name.split("_")
            key   = (float(parts[0]), float(parts[1]), float(parts[2]))
            result = _load_from_disk(key)
            if result:
                _cache[key] = result
                print(f"  Cluster cache loaded from disk: params={key}")
                return key
        except Exception as e:
            print(f"  Warning: could not load cluster cache: {e}")
        return None


# ── Haversine helpers ──────────────────────────────────────────────────────

def _rad(df: pd.DataFrame, lat="lat", lng="lng") -> np.ndarray:
    return np.radians(df[[lat, lng]].values.astype(float))


def _haversine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Vectorised pairwise Haversine in metres. a,b: (n,2) radians."""
    lat_a, lng_a = a[:, 0:1], a[:, 1:2]
    lat_b, lng_b = b[:, 0],   b[:, 1]
    dlat = lat_a - lat_b
    dlng = lng_a - lng_b
    h = np.sin(dlat/2)**2 + np.cos(lat_a) * np.cos(lat_b) * np.sin(dlng/2)**2
    return 2 * EARTH_R_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


# ── Auto-DBSCAN parameter estimation ──────────────────────────────────────

def _auto_params(coords_rad: np.ndarray) -> dict:
    """
    Derives eps and min_pts automatically from complaint coordinates.

    Adapted from AutoDBSCAN (DBSCAN parameters.py).  One change from the
    original: instead of a hardcoded n_neighbors=6, k is computed as
        k = max(K_FLOOR, round(ln(N)))
    so the initial KNN fit scales with the number of points being clustered.

    Steps
    ─────
    1. k  = max(4, round(ln(N)))
    2. Fit NearestNeighbors(k) → avg_nn (1st neighbour) and avg_dk (k-th neighbour)
    3. min_pts = min(3, round(BETA × avg_dk/avg_nn))      [per original formula]
    4. Refit NearestNeighbors(min_pts) → sorted k-distances
    5. eps = k_distances at 74.5th percentile             [crude elbow estimate]
    """
    N = len(coords_rad)

    if N < K_FLOOR + 1:
        return {
            "auto": False, "note": f"Too few points ({N}) — defaults used",
            "min_pts": 3, "eps_m": 1000.0,
            "eps_rad": 1000.0 / EARTH_R_M, "k_used": K_FLOOR,
        }

    # Step 1 — dynamic k
    k = max(K_FLOOR, round(math.log(N)))

    # Step 2 — neighbourhood distances
    nn = NearestNeighbors(n_neighbors=k, algorithm="ball_tree", metric="haversine")
    nn.fit(coords_rad)
    dists_rad, _ = nn.kneighbors(coords_rad)          # shape (N, k)
    dists_m      = dists_rad * EARTH_R_M

    avg_nn = float(dists_m[:, 0].mean())              # 1st nearest neighbour
    avg_dk = float(dists_m[:, -1].mean())             # k-th nearest neighbour

    # Guard: duplicate coordinates produce avg_nn=0 → division by zero.
    # Fall back to the smallest non-zero distance in the matrix.
    if avg_nn < 1e-9:
        nonzero = dists_m[dists_m > 0]
        avg_nn  = float(nonzero.min()) if len(nonzero) > 0 else 1.0

    # Step 3 — min_pts  (original formula, capped at 3)
    min_pts = min(3, int(round(BETA * (avg_dk / avg_nn))))
    min_pts = max(2, min_pts)                          # hard floor — DBSCAN needs ≥ 2

    # Step 4 — eps via k-distance graph (74.5th percentile elbow)
    nn_mp = NearestNeighbors(n_neighbors=min_pts, algorithm="ball_tree", metric="haversine")
    nn_mp.fit(coords_rad)
    dists_mp, _ = nn_mp.kneighbors(coords_rad)
    # dists_mp is in radians — convert to metres before building the k-distance graph
    k_dists_m   = np.sort(dists_mp[:, -1] * EARTH_R_M)

    elbow_idx = int(len(k_dists_m) * ELBOW_PCT)
    eps_m     = float(k_dists_m[elbow_idx])
    eps_rad   = eps_m / EARTH_R_M

    return {
        "auto":     True,
        "k_used":   k,
        "N_points": N,
        "avg_nn_m": round(avg_nn, 1),
        "avg_dk_m": round(avg_dk, 1),
        "min_pts":  min_pts,
        "eps_m":    round(eps_m, 1),
        "eps_rad":  eps_rad,
    }


# ── Public API ─────────────────────────────────────────────────────────────

def compute_clusters(
    complaints_df:         pd.DataFrame,
    facilities_df:         pd.DataFrame,
    medicines_df:          pd.DataFrame,
    facility_medicines_df: pd.DataFrame,
    suppliers_df:          pd.DataFrame,
    hospital_buffer_m:  float = 800,
    clinic_buffer_m:    float = 500,
    pharmacy_buffer_m:  float = 400,
) -> dict:
    key = (hospital_buffer_m, clinic_buffer_m, pharmacy_buffer_m)
    if key not in _cache:
        # Try loading from disk before recomputing
        saved = _load_from_disk(key)
        if saved:
            _cache[key] = saved
        else:
            result = _run(
                complaints_df, facilities_df, medicines_df,
                facility_medicines_df, suppliers_df,
                hospital_buffer_m, clinic_buffer_m, pharmacy_buffer_m,
            )
            _cache[key] = result
            _save_to_disk(key, result)
    return _cache[key]


def clear_cache():
    _cache.clear()


# ── Internal pipeline ──────────────────────────────────────────────────────

def _run(
    complaints_df, facilities_df, medicines_df,
    facility_medicines_df, suppliers_df,
    hospital_buffer_m, clinic_buffer_m, pharmacy_buffer_m,
) -> dict:

    cmp   = complaints_df.copy().reset_index(drop=True)
    c_rad = _rad(cmp)

    buf_by_type = {
        "hospital": hospital_buffer_m,
        "clinic":   clinic_buffer_m,
        "pharmacy": pharmacy_buffer_m,
    }

    # ── 1. Per-type buffer test ────────────────────────────────────────────
    for ftype, radius in buf_by_type.items():
        fdf = facilities_df[facilities_df["type"] == ftype]
        col = f"inside_{ftype}_buf"
        if len(fdf) == 0:
            cmp[col] = False
            cmp[f"dist_{ftype}_m"] = None
        else:
            dist = _haversine_matrix(c_rad, _rad(fdf)).min(axis=1)
            cmp[f"dist_{ftype}_m"] = np.round(dist, 1)
            cmp[col] = dist <= radius

    cmp["inside_buffer"] = (
        cmp["inside_hospital_buf"] |
        cmp["inside_clinic_buf"]   |
        cmp["inside_pharmacy_buf"]
    )

    # Overall nearest facility (used for buffer-cluster assignment)
    dist_all    = _haversine_matrix(c_rad, _rad(facilities_df))
    nearest_idx = np.argmin(dist_all, axis=1)
    cmp["nearest_facility_id"]     = facilities_df["facility_id"].values[nearest_idx]
    cmp["nearest_facility_dist_m"] = np.round(dist_all[np.arange(len(cmp)), nearest_idx], 1)

    inside_mask = cmp["inside_buffer"]
    cmp["cluster_type"] = "noise"
    cmp["cluster_id"]   = None
    cmp.loc[inside_mask, "cluster_type"] = "buffer"
    cmp.loc[inside_mask, "cluster_id"]   = cmp.loc[inside_mask, "nearest_facility_id"]

    # ── 2. Auto-DBSCAN on outside-buffer complaints ────────────────────────
    outside_idx  = cmp.index[~inside_mask]
    outside      = cmp.loc[outside_idx]
    dbscan_clusters = []
    auto_params  = {}

    if len(outside) >= K_FLOOR + 1:
        coords_rad  = _rad(outside)
        auto_params = _auto_params(coords_rad)

        labels = DBSCAN(
            eps        = auto_params["eps_rad"],
            min_samples= auto_params["min_pts"],
            algorithm  = "ball_tree",
            metric     = "haversine",
        ).fit_predict(coords_rad)

        cmp.loc[outside_idx, "_label"] = labels
        clustered_mask = cmp["_label"].notna() & (cmp["_label"] >= 0)
        cmp.loc[clustered_mask, "cluster_type"] = "dbscan"
        cmp.loc[clustered_mask, "cluster_id"]   = (
            "DC" + cmp.loc[clustered_mask, "_label"].astype(int).astype(str)
        )

        # ── 3. DBSCAN cluster summaries ────────────────────────────────────
        med_name   = medicines_df.set_index("medicine_id")["name"]
        lbl_series = pd.Series(labels, index=outside_idx)

        for label in sorted(lbl_series.unique()):
            if label < 0:
                continue
            pts        = cmp.loc[lbl_series[lbl_series == label].index]
            n          = len(pts)
            n_verified = int(pts["verified"].sum())
            total_loss = float(pts["estimated_loss"].sum())
            avg_loss   = total_loss / n if n else 0

            top_meds = (
                pts["medicine_id"].map(med_name)
                .value_counts().head(3).to_dict()
            )

            severity = round(
                (min(n, 100) / 100 * 50)
                + (n_verified / n * 25 if n else 0)
                + (min(avg_loss, 200) / 200 * 25),
                1,
            )

            sup_ids   = facility_medicines_df.loc[
                facility_medicines_df["medicine_id"].isin(pts["medicine_id"].unique()),
                "supplier_id",
            ].unique()
            near_sups = suppliers_df[
                suppliers_df["supplier_id"].isin(sup_ids)
            ][["supplier_id","name","lat","lng","city","state","is_suspicious"]
            ].to_dict("records")

            # Convex hull polygon enclosing all complaint points in the cluster
            pts_ll = list(zip(pts["lng"].astype(float), pts["lat"].astype(float)))
            try:
                geom        = MultiPoint(pts_ll).convex_hull
                hull_coords = (list(geom.exterior.coords)
                               if geom.geom_type == "Polygon" else pts_ll)
            except Exception:
                hull_coords = pts_ll

            dbscan_clusters.append({
                "cluster_id":       f"DC{label}",
                "centroid_lat":     float(pts["lat"].mean()),
                "centroid_lng":     float(pts["lng"].mean()),
                "complaint_count":  n,
                "verified_count":   n_verified,
                "total_loss":       round(total_loss, 2),
                "avg_loss":         round(avg_loss, 2),
                "top_medicines":    top_meds,
                "severity_score":   severity,
                "hull_coords":      hull_coords,
                "nearby_suppliers": near_sups,
            })

        dbscan_clusters.sort(key=lambda x: x["severity_score"], reverse=True)

    cmp.drop(columns=["_label"], errors="ignore", inplace=True)

    # ── 4. Buffer cluster summaries ────────────────────────────────────────
    buffer_clusters = []
    fac_lu = facilities_df.set_index("facility_id")

    for fac_id, grp in cmp[cmp["inside_buffer"]].groupby("cluster_id"):
        if fac_id not in fac_lu.index:
            continue
        fac = fac_lu.loc[fac_id]
        buffer_clusters.append({
            "cluster_id":      fac_id,
            "facility_name":   str(fac["name"]),
            "facility_type":   str(fac["type"]),
            "centroid_lat":    float(fac["lat"]),
            "centroid_lng":    float(fac["lng"]),
            "complaint_count": len(grp),
            "verified_count":  int(grp["verified"].sum()),
            "total_loss":      round(float(grp["estimated_loss"].sum()), 2),
        })

    buffer_clusters.sort(key=lambda x: x["complaint_count"], reverse=True)

    n_in = int(inside_mask.sum())

    # Replace any remaining inf/-inf before JSON serialisation
    cmp = cmp.replace([np.inf, -np.inf], None)

    return {
        "params": {
            "hospital_buffer_m": hospital_buffer_m,
            "clinic_buffer_m":   clinic_buffer_m,
            "pharmacy_buffer_m": pharmacy_buffer_m,
        },
        "auto_dbscan": auto_params,   # exposes computed eps/min_pts for transparency
        "summary": {
            "total_complaints":  len(cmp),
            "inside_buffer":     n_in,
            "outside_buffer":    len(cmp) - n_in,
            "inside_hospital":   int(cmp["inside_hospital_buf"].sum()),
            "inside_clinic":     int(cmp["inside_clinic_buf"].sum()),
            "inside_pharmacy":   int(cmp["inside_pharmacy_buf"].sum()),
            "dbscan_clustered":  int((cmp["cluster_type"] == "dbscan").sum()),
            "noise_points":      int((cmp["cluster_type"] == "noise").sum()),
            "n_dbscan_clusters": len(dbscan_clusters),
            "n_buffer_clusters": len(buffer_clusters),
        },
        "complaints":      cmp.to_dict("records"),
        "dbscan_clusters": dbscan_clusters,
        "buffer_clusters": buffer_clusters,
    }
