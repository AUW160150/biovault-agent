"""
Datadog LLM Observability Tracer
----------------------------------
Wraps LLM calls with Datadog tracing for monitoring, cost tracking,
and latency observability across the BioVault pipeline.

Docs: https://docs.datadoghq.com/llm_observability/setup/sdk/python/

Usage:
    from backend.utils.datadog_tracer import trace_llm_call, init_tracer

    init_tracer()  # call once at app startup

    # wrap a call:
    with trace_llm_call("minimax_vision", "MiniMax-Text-01") as span:
        result = minimax_agent.extract_from_image(path)
        span.set_metric("input_tokens", result["tokens_used"])
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("biovault.tracer")

_DD_ENABLED = bool(
    os.getenv("DD_API_KEY")
    and os.getenv("DD_API_KEY") != "your_datadog_api_key_here"
)

_tracer_initialized = False


def init_tracer():
    """
    Initialize Datadog ddtrace with LLM Observability.
    Call once at application startup (in main.py lifespan).
    Safe to call if Datadog is not configured — degrades gracefully.
    """
    global _tracer_initialized

    if not _DD_ENABLED:
        logger.info("Datadog API key not configured — tracing disabled (no-op mode)")
        _tracer_initialized = True
        return

    try:
        import ddtrace
        from ddtrace.llmobs import LLMObs

        LLMObs.enable(
            ml_app=os.getenv("DD_SERVICE", "biovault"),
            agentless_enabled=True,
            api_key=os.getenv("DD_API_KEY"),
            site=os.getenv("DD_SITE", "us5.datadoghq.com"),
        )

        logger.info("Datadog LLM Observability initialized (site=%s)", os.getenv("DD_SITE"))
        _tracer_initialized = True

    except ImportError:
        logger.warning("ddtrace not installed — tracing disabled")
        _tracer_initialized = True
    except Exception as e:
        logger.warning("Datadog init failed (non-fatal): %s", e)
        _tracer_initialized = True


def record_llm_call(
    agent_name: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    success: bool = True,
    error: Optional[str] = None,
    document_type: str = "chemotherapy_chart",
):
    """
    Record a completed LLM call to Datadog.
    This is passed as the `tracer` callable to MiniMax and Bedrock agents.

    Args:
        agent_name: e.g. "minimax_vision" or "bedrock_standardization"
        model: model ID used
        input_tokens: prompt tokens consumed
        output_tokens: completion tokens generated
        latency_ms: wall-clock time in milliseconds
        success: whether the call succeeded
        error: error message if failed
        document_type: type of clinical document processed
    """
    log_msg = (
        f"[LLM] agent={agent_name} model={model} "
        f"input_tokens={input_tokens} output_tokens={output_tokens} "
        f"latency_ms={latency_ms} success={success}"
    )
    if error:
        log_msg += f" error={error}"
    logger.info(log_msg)

    if not _DD_ENABLED:
        return

    try:
        from ddtrace.llmobs import LLMObs

        with LLMObs.llm(
            model_name=model,
            model_provider="minimax" if "minimax" in agent_name.lower() else "aws_bedrock",
            name=agent_name,
            session_id=f"biovault-{int(time.time())}",
        ) as span:
            LLMObs.annotate(
                span=span,
                input_data=[{"role": "user", "content": document_type}],
                output_data=[{"role": "assistant", "content": str(success)}],
                metadata={
                    "agent_name": agent_name,
                    "document_type": document_type,
                    "latency_ms": latency_ms,
                },
                metrics={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            )
    except Exception as e:
        logger.warning("Failed to record Datadog span (non-fatal): %s", e)


@contextmanager
def trace_llm_call(agent_name: str, model: str, document_type: str = "chemotherapy_chart"):
    """
    Context manager for tracing an LLM call block.

    Usage:
        with trace_llm_call("minimax_vision", "MiniMax-Text-01") as ctx:
            result = call_minimax(...)
            ctx["input_tokens"] = result["tokens_used"]
    """
    ctx = {
        "input_tokens": 0,
        "output_tokens": 0,
        "success": True,
        "error": None,
    }
    start = time.time()

    try:
        yield ctx
    except Exception as e:
        ctx["success"] = False
        ctx["error"] = str(e)
        raise
    finally:
        latency_ms = int((time.time() - start) * 1000)
        record_llm_call(
            agent_name=agent_name,
            model=model,
            input_tokens=ctx.get("input_tokens", 0),
            output_tokens=ctx.get("output_tokens", 0),
            latency_ms=latency_ms,
            success=ctx.get("success", True),
            error=ctx.get("error"),
            document_type=document_type,
        )
