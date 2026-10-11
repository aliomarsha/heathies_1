"""Healthies API + static frontend.

Start:   uvicorn app.main:app --reload        (from the backend/ folder)
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect

from .config import FRONTEND_DIST
from .db import Base, engine, ensure_columns
from .routers import auth_routes, demo, government, participant, provider, public

logging.basicConfig(level=logging.INFO)


_ready = False
_ready_lock = threading.Lock()


def _ensure_ready() -> None:
    global _ready
    if _ready:
        return
    with _ready_lock:
        if not _ready:
            _startup()
            _ready = True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_ready()
    yield


def _startup() -> None:
    """Load the fictional demo data into an empty database (first start, or a fresh serverless
    instance whose /tmp database is empty)."""
    log = logging.getLogger("healthies")
    try:
        if not inspect(engine).has_table("users"):
            from .seed import reset_demo
            log.info("Empty database - loading fictional demo data.")
            reset_demo()
        else:
            Base.metadata.create_all(engine)
            ensure_columns()
    except Exception:  # another instance may be seeding the same shared database at this moment
        log.exception("Startup database check failed; continuing")


app = FastAPI(title="Healthies API", version="0.1.0", lifespan=lifespan,
              description="Research prototype. Fictional demo data. Not an official health service.")

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def _ready_guard(request: Request, call_next):
    # Safety net for serverless platforms: make sure the demo database exists before any request.
    _ensure_ready()
    return await call_next(request)


for r in (public.router, auth_routes.router, participant.router, provider.router, government.router, demo.router):
    app.include_router(r)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):  # pragma: no cover
    logging.getLogger("healthies").exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. The action was not saved."})


# ---- serve the built React app (frontend/dist) -----------------------------------------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
