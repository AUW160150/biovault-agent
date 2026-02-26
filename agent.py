"""
BioVault Autonomous Agent Loop
--------------------------------
Runs as a daemon thread inside the FastAPI process (started in main.py lifespan).
Never exits — polls the document queue every POLL_INTERVAL seconds forever.

Every stage start/complete/flag is written to agent_log so the dashboard
can show a live activity feed to judges watching in real time.
"""

import logging
import os
import threading
import time

import database as db
from alerts import dispatch_alert

logger = logging.getLogger("biovault.agent")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
_stop_event = threading.Event()


def run_agent_loop():
    logger.info("Agent loop starting (poll_interval=%ds)", POLL_INTERVAL)

    recovered = db.recover_stalled_documents()
    if recovered:
        msg = f"Fault recovery: reset {recovered} stalled doc(s) → pending"
        logger.warning(msg)
        db.write_log("recovery", msg, level="warn")

    db.update_heartbeat()
    db.write_log("startup", "Agent loop started — watching queue every %ds" % POLL_INTERVAL)

    while not _stop_event.is_set():
        try:
            _tick()
        except Exception as exc:
            logger.exception("Unhandled error in agent tick: %s", exc)
            db.write_log("error", f"Unhandled tick error: {exc}", level="error")
        _stop_event.wait(POLL_INTERVAL)

    logger.info("Agent loop stopped.")
    db.write_log("shutdown", "Agent loop stopped")


def _tick():
    db.update_heartbeat()

    row = db.get_next_pending()
    if row is None:
        db.write_log("idle", "Queue empty — waiting for documents")
        return

    doc_id   = row["id"]
    filename = row["filename"]
    file_path = row["file_path"]

    logger.info("Processing document: id=%s filename=%s", doc_id, filename)
    db.write_log("doc_start", f"Picked up: {filename}", document_id=doc_id)
    db.set_document_status(doc_id, "processing")

    try:
        _run_pipeline(doc_id, filename, file_path)
        db.set_document_status(doc_id, "complete")
        db.update_heartbeat(docs_delta=1)
        db.write_log("doc_complete", f"✅ Complete: {filename}", document_id=doc_id, level="success")
        logger.info("Document complete: id=%s", doc_id)
    except Exception as exc:
        logger.exception("Pipeline failed for doc %s: %s", doc_id, exc)
        db.set_document_status(doc_id, "failed", error=str(exc))
        db.write_log("doc_failed", f"❌ Failed: {filename} — {exc}", document_id=doc_id, level="error")


def _run_pipeline(doc_id: str, filename: str, file_path: str):
    from pipeline import minimax_agent, akash_agent
    from pipeline.validator import run_validation
    from pipeline.fhir_builder import build_fhir_bundle
    from pipeline.datadog_tracer import record_llm_call

    # ── Stage 1: MiniMax Vision ───────────────────────────────────────────────
    db.write_log("stage_start", "⏳ Stage 1/4 — MiniMax Vision extraction starting…",
                 document_id=doc_id, stage="extraction")

    minimax_result = minimax_agent.extract_from_image(
        image_path=file_path,
        tracer=record_llm_call,
    )
    extraction = minimax_result["extraction"]
    cycles     = len(extraction.get("cycles", []))
    conf       = extraction.get("overall_confidence", 0)

    db.insert_pipeline_result(
        document_id=doc_id, stage="extraction",
        output=extraction, confidence=conf,
    )
    db.write_log(
        "stage_done",
        f"✅ Stage 1/4 — Extraction complete: {cycles} cycles, "
        f"confidence={conf:.0%}, latency={minimax_result['latency_ms']}ms",
        document_id=doc_id, stage="extraction", level="success",
    )

    # ── Stage 2: AkashML Standardization ─────────────────────────────────────
    db.write_log("stage_start", "⏳ Stage 2/4 — AkashML (MiniMax M2.5) standardization starting…",
                 document_id=doc_id, stage="standardization")

    akash_result  = akash_agent.standardize_extraction(raw_extraction=extraction, tracer=record_llm_call)
    standardized  = akash_result["standardized"]
    icd10_code    = standardized.get("icd10", {}).get("code", "?")

    db.insert_pipeline_result(document_id=doc_id, stage="standardization", output=standardized)
    db.write_log(
        "stage_done",
        f"✅ Stage 2/4 — Standardization complete: ICD-10={icd10_code}, "
        f"latency={akash_result['latency_ms']}ms, tokens={akash_result['output_tokens']}",
        document_id=doc_id, stage="standardization", level="success",
    )

    # Escalate HIGH flags from LLM output immediately
    raw_flags     = standardized.get("safety_flags", [])
    critical_count = 0
    for flag in raw_flags:
        severity = flag.get("severity", "LOW")
        if severity == "HIGH":
            flag_id = db.insert_safety_flag(
                document_id=doc_id,
                flag_type=flag.get("category", "OTHER"),
                severity=severity,
                details=flag.get("description", ""),
            )
            critical_count += 1
            desc = flag.get("description", "")[:80]
            db.write_log(
                "flag",
                f"⚠ HIGH flag: {flag.get('category','OTHER')} — {desc}",
                document_id=doc_id, stage="standardization", level="warn",
            )
            dispatch_alert(
                doc_id=doc_id, filename=filename, flag_id=flag_id,
                flag_type=flag.get("category", "OTHER"), severity=severity,
                details=flag.get("description", ""),
            )

    # ── Stage 3: FHIR R4 Bundle ───────────────────────────────────────────────
    db.write_log("stage_start", "⏳ Stage 3/4 — Building FHIR R4 bundle…",
                 document_id=doc_id, stage="fhir")

    fhir_bundle = build_fhir_bundle(minimax_extraction=extraction, standardized=standardized)
    resources   = len(fhir_bundle.get("entry", []))

    db.insert_pipeline_result(document_id=doc_id, stage="fhir", output=fhir_bundle)
    db.write_log(
        "stage_done",
        f"✅ Stage 3/4 — FHIR bundle built: {resources} resources "
        f"(Patient + Condition + {resources-2}× MedicationAdministration)",
        document_id=doc_id, stage="fhir", level="success",
    )

    # ── Stage 4: Safety Validation ────────────────────────────────────────────
    db.write_log("stage_start", "⏳ Stage 4/4 — Running 5 safety checks…",
                 document_id=doc_id, stage="validation")

    validation   = run_validation(
        minimax_extraction=extraction, standardized=standardized, fhir_bundle=fhir_bundle,
    )
    passed       = validation["passed_count"]
    total        = validation["total_count"]

    db.insert_pipeline_result(document_id=doc_id, stage="validation", output=validation)

    # Persist validator flags
    for check in validation.get("checks", []):
        if not check["passed"]:
            severity  = _classify_check_severity(check["name"])
            flag_type = _check_name_to_type(check["name"])
            flag_id   = db.insert_safety_flag(
                document_id=doc_id,
                flag_type=flag_type,
                severity=severity,
                details=check["detail"],
            )
            critical_count += 1
            db.write_log(
                "flag",
                f"⚠ {severity} — {check['name']}: {check['detail'][:80]}",
                document_id=doc_id, stage="validation", level="warn",
            )
            if severity in ("HIGH", "CRITICAL"):
                dispatch_alert(
                    doc_id=doc_id, filename=filename, flag_id=flag_id,
                    flag_type=flag_type, severity=severity, details=check["detail"],
                )

    result_color = "✅" if passed == total else "⚠"
    db.write_log(
        "stage_done",
        f"{result_color} Stage 4/4 — Validation: {passed}/{total} checks passed",
        document_id=doc_id, stage="validation",
        level="success" if passed == total else "warn",
    )

    if critical_count:
        db.increment_critical_flags(doc_id, critical_count)
        db.update_heartbeat(flags_delta=critical_count)
        db.write_log(
            "escalation",
            f"🚨 Autonomous escalation: {critical_count} critical flag(s) raised for {filename}",
            document_id=doc_id, level="error",
        )

    logger.info(
        "[%s] Pipeline done: %d/%d validation passed | %d critical flags",
        doc_id, passed, total, critical_count,
    )


def _classify_check_severity(check_name: str) -> str:
    return {
        "Dose Consistency":          "HIGH",
        "PII De-identification":     "HIGH",
        "Drug Name Standardization": "MEDIUM",
        "ICD-10 Code Validity":      "MEDIUM",
        "FHIR R4 Schema":            "LOW",
    }.get(check_name, "MEDIUM")


def _check_name_to_type(check_name: str) -> str:
    return {
        "Dose Consistency":          "DOSE_VARIANCE",
        "Drug Name Standardization": "AMBIGUOUS_NAME",
        "ICD-10 Code Validity":      "CODING_ERROR",
        "FHIR R4 Schema":            "SCHEMA_ERROR",
        "PII De-identification":     "PII_LEAK",
    }.get(check_name, "OTHER")
