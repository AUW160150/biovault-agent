"""
BioVault Agent — Alerts & Autonomous Escalation
-------------------------------------------------
Handles real-world autonomous actions when the agent detects critical safety flags.

Autonomous actions taken (logged, persisted, optionally POSTed to webhook):
  - Structured JSON alert written to safety_flags table
  - POST to WEBHOOK_URL env var if set (any HTTP listener — Slack, PagerDuty, etc.)
  - Structured JSON log line (parseable by Datadog, CloudWatch, any log aggregator)

Endpoints:
  GET  /alerts                  — all unresolved safety flags
  GET  /alerts/all              — all flags (resolved + unresolved), last 50
  POST /alerts/resolve/{flag_id} — mark a flag resolved
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import database as db

logger = logging.getLogger("biovault.alerts")

router = APIRouter(prefix="/alerts", tags=["alerts"])

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# Deduplicate in-flight webhook calls — don't block the agent loop
_webhook_executor_lock = threading.Lock()


# ─── REST Endpoints ────────────────────────────────────────────────────────────

@router.get("")
async def get_unresolved_alerts():
    """Return all unresolved safety flags across all documents."""
    flags = db.get_unresolved_flags()
    return {
        "status": "ok",
        "count": len(flags),
        "alerts": flags,
    }


@router.get("/all")
async def get_all_alerts():
    """Return all flags (resolved and unresolved), newest first, max 50."""
    flags = db.get_all_flags(limit=50)
    return {
        "status": "ok",
        "count": len(flags),
        "alerts": flags,
    }


@router.post("/resolve/{flag_id}")
async def resolve_alert(flag_id: int):
    """Mark a safety flag as resolved."""
    success = db.resolve_safety_flag(flag_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Flag {flag_id} not found")
    return {"status": "resolved", "flag_id": flag_id}


# ─── Autonomous Dispatch (called by agent.py) ──────────────────────────────────

def dispatch_alert(
    doc_id: str,
    filename: str,
    flag_id: int,
    flag_type: str,
    severity: str,
    details: str,
) -> None:
    """
    Autonomous escalation action — called by the agent when a critical flag is raised.

    Actions:
      1. Log a structured JSON alert line (observable by any log aggregator)
      2. POST to WEBHOOK_URL if configured (non-blocking background thread)
    """
    alert_payload = {
        "event": "BIOVAULT_SAFETY_ALERT",
        "timestamp": _now(),
        "document_id": doc_id,
        "filename": filename,
        "flag_id": flag_id,
        "flag_type": flag_type,
        "severity": severity,
        "details": details,
        "action": "autonomous_escalation",
        "source": "biovault-agent",
    }

    # Action 1: structured log (parseable by Datadog / CloudWatch / any aggregator)
    logger.warning(
        "AUTONOMOUS_ALERT %s",
        json.dumps(alert_payload),
    )

    # Action 2: webhook POST (fire-and-forget, non-blocking)
    if WEBHOOK_URL:
        thread = threading.Thread(
            target=_post_webhook,
            args=(alert_payload,),
            daemon=True,
        )
        thread.start()


def _post_webhook(payload: dict) -> None:
    """POST alert payload to WEBHOOK_URL. Runs in a background thread."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            logger.info(
                "Webhook posted: url=%s status=%d",
                WEBHOOK_URL,
                response.status_code,
            )
    except Exception as exc:
        logger.warning("Webhook POST failed (non-fatal): %s", exc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
