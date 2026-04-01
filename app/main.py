"""CasAI Provenance Lab — FastAPI v3 — full stack"""
import asyncio, logging, subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.core.scheduler import run_scheduler
from app.routers.api import benchmarks_router, runs_router
from app.routers.auth import auth_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

@asynccontextmanager
async def lifespan(app):
    try:
        settings.GIT_SHA = subprocess.check_output(["git","rev-parse","--short","HEAD"],stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        settings.GIT_SHA = "unknown"
    for d in [settings.RUNS_DIR, settings.EXPORTS_DIR, settings.BENCHMARKS_DIR, "./data"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    await init_db()
    task = asyncio.create_task(run_scheduler())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app = FastAPI(title="CasAI Provenance Lab API", version=settings.APP_VERSION, docs_url="/docs", redoc_url="/redoc", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router)
app.include_router(runs_router)
app.include_router(benchmarks_router)

from app.routers.ws import ws_router; app.include_router(ws_router)
from app.routers.uploads import upload_router; app.include_router(upload_router)
from app.routers.settings import settings_router; app.include_router(settings_router)
from app.routers.playground import playground_router; app.include_router(playground_router)

@app.get("/", tags=["Health"])
def root(): return {"service": settings.APP_NAME, "version": settings.APP_VERSION, "git_sha": settings.GIT_SHA, "mock_ml": settings.MOCK_ML, "status": "operational", "docs": "/docs", "playground": "/playground"}

@app.get("/health", tags=["Health"])
def health(): return {"status": "ok"}
