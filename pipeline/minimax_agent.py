"""
MiniMax Vision Agent
--------------------
Calls the MiniMax native chat completion API (MiniMax-Text-01) with a
base64-encoded image to extract structured clinical data from handwritten
chemotherapy charts.

NOTE: The OpenAI-compatible endpoint does NOT support images.
      We use the native endpoint: POST /v1/text/chatcompletion_v2
      which accepts { type: "image_url", image_url: { url: "data:..." } }
"""

import base64
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
MINIMAX_MODEL = "MiniMax-Text-01"

EXTRACTION_SYSTEM_PROMPT = """You are a clinical document digitization specialist.
Your task is to extract ALL information from handwritten chemotherapy charts with
extreme precision. Patient safety depends on accuracy — a misread dose can be fatal.

Return ONLY valid JSON. No markdown, no explanation."""

EXTRACTION_USER_PROMPT = """Extract every piece of information from this chemotherapy
chart image. Return a JSON object with EXACTLY this structure:

{
  "patient": {
    "name_raw": "<exact name as written>",
    "age": <integer or null>,
    "sex": "<M/F/Other or null>",
    "registration_number": "<exact as written>",
    "confidence": <0.0-1.0>
  },
  "hospital": {
    "name": "<hospital name>",
    "unit": "<unit/department name>"
  },
  "diagnosis": {
    "text_raw": "<exact diagnosis text as written>",
    "confidence": <0.0-1.0>
  },
  "regimen": {
    "name": "<chemotherapy regimen name>",
    "confidence": <0.0-1.0>
  },
  "cycles": [
    {
      "date": "<date as written, e.g. 07/03/24>",
      "cycle_id": "<e.g. C1D1, C1D2>",
      "drugs": [
        {
          "name_raw": "<drug name exactly as written>",
          "dose_raw": "<dose exactly as written, e.g. 90mg>",
          "dose_value": <numeric value or null>,
          "dose_unit": "<mg/mcg/g or null>",
          "route": "<IV/IM/PO or null>",
          "diluent": "<e.g. N/S 200ml or null>",
          "duration": "<e.g. over 1 hour or null>",
          "confidence": <0.0-1.0>,
          "ambiguous": <true if hard to read>,
          "ambiguity_note": "<describe what is unclear, or null>"
        }
      ],
      "remarks": "<any remarks column text>",
      "has_correction": <true if crossed-out or corrected values visible>,
      "correction_note": "<describe correction if any>"
    }
  ],
  "flags": [
    "<any field or value that is ambiguous, crossed out, or clinically notable>"
  ],
  "overall_confidence": <0.0-1.0>,
  "extraction_notes": "<any general observations about document quality>"
}

Be especially careful with:
- Drug name spelling variants (OCR artifacts from handwriting)
- Dose values: distinguish between 80mg vs 90mg precisely
- Dates that may conflict with remarks
- Crossed-out or corrected entries
- Cycle numbering (C1D1 = Cycle 1 Day 1)"""


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_map.get(suffix, "image/jpeg")


def extract_from_image(image_path: str, tracer=None) -> dict:
    """
    Send image to MiniMax vision model and extract structured clinical data.

    Args:
        image_path: Path to the chemotherapy chart image
        tracer: Optional Datadog tracer wrapper

    Returns:
        dict with extraction results and metadata
    """
    start_time = time.time()

    if not MINIMAX_API_KEY or MINIMAX_API_KEY == "your_minimax_api_key_here":
        raise ValueError("MINIMAX_API_KEY not set in .env")

    b64_image = encode_image_to_base64(image_path)
    mime_type = get_image_mime_type(image_path)
    data_url = f"data:{mime_type};base64,{b64_image}"

    payload = {
        "model": MINIMAX_MODEL,
        "messages": [
            {
                "role": "system",
                "name": "BioVault",
                "content": EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "name": "User",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_USER_PROMPT,
                    },
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }

    url = f"{MINIMAX_BASE_URL}/text/chatcompletion_v2"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"MiniMax API error {e.response.status_code}: {e.response.text}"
        )

    elapsed_ms = int((time.time() - start_time) * 1000)
    resp_data = response.json()

    raw_content = resp_data["choices"][0]["message"]["content"]
    usage = resp_data.get("usage", {})

    json_str = _extract_json_from_response(raw_content)
    try:
        extracted = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"MiniMax returned invalid JSON: {e}\nRaw: {raw_content[:500]}")

    if tracer:
        tracer(
            agent_name="minimax_vision",
            model=MINIMAX_MODEL,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=elapsed_ms,
            success=True,
        )

    return {
        "extraction": extracted,
        "model": MINIMAX_MODEL,
        "latency_ms": elapsed_ms,
        "tokens_used": usage.get("total_tokens", 0),
        "raw_response": raw_content,
    }


def _extract_json_from_response(text: str) -> str:
    """Strip markdown code fences if present, return raw JSON string."""
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
    return text.strip()
