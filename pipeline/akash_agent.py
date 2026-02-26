"""
AkashML Standardization Agent
-------------------------------
Drop-in replacement for the original AWS Bedrock agent.

Calls AkashML's OpenAI-compatible inference endpoint to:
  1. Map diagnosis → ICD-10 code
  2. Normalize drug name variants to WHO INN names
  3. Detect dose variance across cycles (>10% threshold)
  4. Return structured safety flags

AkashML endpoint: https://chatapi.akash.network/api/v1
Model:            Meta-Llama-3-1-8B-Instruct-FP8
API key env var:  AKASH_API_KEY

Function signatures are identical to the original bedrock_agent so the
rest of the pipeline (fhir_builder, validator, main pipeline loop) needs
zero changes.
"""

import json
import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("biovault.akash_agent")

AKASH_API_KEY = os.getenv("AKASH_API_KEY", "")
AKASH_BASE_URL = os.getenv("AKASH_BASE_URL", "https://api.akashml.com/v1")
AKASH_MODEL = os.getenv("AKASH_MODEL", "MiniMaxAI/MiniMax-M2.5")

STANDARDIZATION_SYSTEM = (
    "You are a clinical pharmacist and medical coder specializing in oncology. "
    "You receive raw extracted data from a handwritten chemotherapy chart and must "
    "standardize it for electronic health records. "
    "Return ONLY valid JSON — no markdown fences, no explanation, no preamble."
)

STANDARDIZATION_PROMPT = """You are a clinical pharmacist and medical coder specializing in
oncology. You receive raw extracted data from a handwritten chemotherapy chart and must
standardize it for electronic health records.

Return ONLY valid JSON — no markdown, no explanation.

INPUT DATA:
{extraction_json}

Perform these tasks:

1. ICD-10 CODING: Map the diagnosis to the correct ICD-10-CM code.
   - Acute Myeloid Leukemia (AML) → C92.00 (Acute myeloblastic leukemia, without maturation)
   - Include full description.

2. DRUG STANDARDIZATION: Normalize all drug name variants to standard WHO INN names.
   Known variants:
   - "Dauno", "DAUNORUBICIN", "Daunorubicn", "Daunorubicine" → "Daunorubicin"
   - "Cytosare", "Cytbrar", "cytbror", "Cytarabinr", "Cytosar" → "Cytarabine"

3. DOSE ANALYSIS: For each drug across all cycles:
   - Calculate mean dose
   - Flag if any single dose deviates >10% from the mean
   - Note dose corrections or crossed-out values

4. SAFETY FLAGS: Identify any of the following:
   - Dose inconsistencies across cycles for the same drug
   - Date anomalies
   - Illegible or ambiguous critical values
   - Missing required fields

Return EXACTLY this JSON structure (no extra keys, no markdown):
{{
  "icd10": {{
    "code": "<e.g. C92.00>",
    "description": "<full ICD-10 description>",
    "confidence": <0.0-1.0>
  }},
  "standardized_drugs": [
    {{
      "cycle_id": "<e.g. C1D1>",
      "date": "<YYYY-MM-DD if inferable, else raw>",
      "drug_standard": "<WHO INN name>",
      "drug_raw": "<as written in chart>",
      "dose_mg": <numeric value or null>,
      "route": "<IV/IM/PO>",
      "diluent": "<e.g. Normal Saline 200mL>",
      "infusion_duration": "<e.g. 1 hour>",
      "name_was_corrected": <true/false>
    }}
  ],
  "dose_analysis": {{
    "daunorubicin": {{
      "doses_mg": [<list of all numeric doses>],
      "mean_mg": <float>,
      "variance_flagged": <true/false>,
      "variance_detail": "<explanation or null>"
    }},
    "cytarabine": {{
      "doses_mg": [<list of all numeric doses>],
      "mean_mg": <float>,
      "variance_flagged": <true/false>,
      "variance_detail": "<explanation or null>"
    }}
  }},
  "safety_flags": [
    {{
      "severity": "<HIGH/MEDIUM/LOW>",
      "category": "<DOSE_VARIANCE/DATE_ANOMALY/AMBIGUOUS_NAME/MISSING_DATA/OTHER>",
      "description": "<clear clinical description of the issue>",
      "cycles_affected": ["<e.g. C1D1>"]
    }}
  ],
  "bedrock_notes": "<any additional clinical observations>"
}}"""


def standardize_extraction(raw_extraction: dict, tracer=None) -> dict:
    """
    Standardize raw MiniMax extraction via AkashML inference.

    Identical signature to the original bedrock_agent.standardize_extraction().
    Returns the same dict shape so fhir_builder and validator need no changes.

    Args:
        raw_extraction: dict from minimax_agent.extract_from_image()["extraction"]
        tracer: Optional Datadog tracer callable

    Returns:
        {
            "standardized": <dict>,
            "model": <str>,
            "latency_ms": <int>,
            "input_tokens": <int>,
            "output_tokens": <int>,
        }
    """
    if not AKASH_API_KEY:
        raise ValueError(
            "AKASH_API_KEY not set. Add it to your .env or environment."
        )

    start_time = time.time()

    extraction_json = json.dumps(raw_extraction, indent=2)
    user_prompt = STANDARDIZATION_PROMPT.replace("{extraction_json}", extraction_json)

    payload = {
        "model": AKASH_MODEL,
        "messages": [
            {"role": "system", "content": STANDARDIZATION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {AKASH_API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info("Calling AkashML: model=%s", AKASH_MODEL)

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{AKASH_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"AkashML API error {e.response.status_code}: {e.response.text}"
        )

    elapsed_ms = int((time.time() - start_time) * 1000)
    resp_data = response.json()

    raw_content = resp_data["choices"][0]["message"]["content"]
    usage = resp_data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    # Strip any reasoning tags (e.g. <think>…</think>) some models emit
    raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

    json_str = _extract_json(raw_content)
    try:
        standardized = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"AkashML returned invalid JSON: {e}\nRaw content (first 500): {raw_content[:500]}"
        )

    logger.info(
        "AkashML standardization complete: latency=%dms in=%d out=%d",
        elapsed_ms, input_tokens, output_tokens,
    )

    if tracer:
        tracer(
            agent_name="akash_standardization",
            model=AKASH_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
            success=True,
        )

    return {
        "standardized": standardized,
        "model": AKASH_MODEL,
        "latency_ms": elapsed_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _extract_json(text: str) -> str:
    """Strip markdown code fences if present and return raw JSON string."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])
    # If still not valid, try to extract first {...} block
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
    return text.strip()
