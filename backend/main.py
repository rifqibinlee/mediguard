from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from backend.services.data_loader import get_store
from backend.services.dbscan_engine import load_latest_cluster
from backend.routers import facilities, complaints, suppliers, clusters, analytics


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()
    load_latest_cluster()
    yield


app = FastAPI(title="MediGuard API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(facilities.router, prefix="/api", tags=["Facilities"])
app.include_router(complaints.router, prefix="/api", tags=["Complaints"])
app.include_router(suppliers.router,  prefix="/api", tags=["Suppliers"])
app.include_router(clusters.router,   prefix="/api", tags=["Clusters"])
app.include_router(analytics.router,  prefix="/api", tags=["Analytics"])


@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "ok", "service": "MediGuard"}


@app.get("/api/filters", tags=["System"])
def filter_options():
    return get_store().get_filter_options()


_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="static")