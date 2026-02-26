"""
BioVault Agent — FastAPI Application Entry Point
--------------------------------------------------
Starts the autonomous agent loop as a daemon thread inside the FastAPI lifespan.
Single container: one uvicorn process, one agent thread.

Endpoints mounted:
  GET  /health              — agent liveness + heartbeat + uptime
  GET  /dashboard           — live HTML judge demo screen
  POST /intake              — upload document to queue
  GET  /intake/simulate     — inject test batch
  GET  /intake/queue        — queue stats
  GET  /alerts              — unresolved safety flags (JSON)
  GET  /alerts/all          — all flags
  POST /alerts/resolve/{id} — resolve a flag
"""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("biovault.main")

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan:
      startup  — init DB, recover stalled docs, start agent daemon thread
      shutdown — signal the agent loop to stop
    """
    import database as db
    from agent import run_agent_loop, _stop_event
    from pipeline.datadog_tracer import init_tracer

    logger.info("BioVault Agent starting up")

    # Initialize SQLite schema (idempotent)
    db.init_db()
    logger.info("Database initialized: %s", os.getenv("DB_PATH", "/data/biovault.db"))

    # Initialize Datadog tracing (degrades gracefully if not configured)
    init_tracer()

    # Start the autonomous agent loop as a daemon thread
    agent_thread = threading.Thread(
        target=run_agent_loop,
        name="biovault-agent-loop",
        daemon=True,
    )
    agent_thread.start()
    logger.info("Agent daemon thread started: %s", agent_thread.name)

    yield

    # Signal the agent to stop on shutdown (it will finish its current tick)
    _stop_event.set()
    agent_thread.join(timeout=10)
    logger.info("BioVault Agent shut down cleanly")


app = FastAPI(
    title="BioVault Agent API",
    description=(
        "Autonomous clinical document watchdog agent running on Akash Network. "
        "Continuously processes handwritten chemotherapy charts, detects dose "
        "anomalies, and escalates critical safety alerts."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Mount routers ─────────────────────────────────────────────────────────────

from intake import router as intake_router
from alerts import router as alerts_router
from dashboard import router as dashboard_router

app.include_router(intake_router)
app.include_router(alerts_router)
app.include_router(dashboard_router)


# ─── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    """
    Agent liveness check.
    Returns agent status, last heartbeat timestamp, and uptime in seconds.
    Used by Akash infrastructure, load balancers, and judges.
    """
    import database as db

    heartbeat = db.get_heartbeat()
    stats = db.get_stats()
    uptime_seconds = int(time.time() - _start_time)

    last_seen = heartbeat["last_seen"] if heartbeat else None
    agent_status = "running"
    if last_seen:
        try:
            dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            if age > 90:
                agent_status = "stalled"
        except Exception:
            pass

    return {
        "status": agent_status,
        "heartbeat": last_seen,
        "uptime_seconds": uptime_seconds,
        "started_at": heartbeat["started_at"] if heartbeat else None,
        "documents_processed_total": heartbeat["documents_processed_total"] if heartbeat else 0,
        "flags_raised_total": heartbeat["flags_raised_total"] if heartbeat else 0,
        "queue": stats,
        "service": "biovault-agent",
        "version": "2.0.0",
    }


@app.post("/agent/process-now", tags=["meta"])
async def process_now():
    """
    Trigger an immediate agent tick — skips the 30s poll wait.
    Useful for demos and post-upload UX. The agent is still autonomous;
    this just wakes it up early.
    """
    import threading
    from agent import _tick
    t = threading.Thread(target=_tick, daemon=True)
    t.start()
    return {"status": "ok", "message": "Agent tick triggered — check /agent/activity for progress"}


@app.get("/agent/activity", tags=["meta"])
async def agent_activity(limit: int = 60):
    """
    Return recent agent log entries for the live activity feed.
    The dashboard polls this every 3 seconds when any document is processing.
    """
    import database as db
    entries = db.get_recent_log(limit=limit)
    stats   = db.get_stats()
    return {
        "entries": entries,
        "has_active": stats["processing"] > 0,
        "queue_stats": stats,
    }


@app.get("/", tags=["meta"])
async def root():
    """Redirect hint to dashboard."""
    return JSONResponse({
        "service": "BioVault Agent",
        "version": "2.0.0",
        "dashboard": "/dashboard",
        "health": "/health",
        "docs": "/docs",
        "intake": "/intake",
        "alerts": "/alerts",
    })
