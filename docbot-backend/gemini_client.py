# gemini_client.py
"""
Thin wrapper around the Gemini Generative Language API.
Two helpers:
  - gemini_json()  → ask Gemini for structured JSON output
  - gemini_text()  → ask Gemini for plain text
"""

import json
import requests
from fastapi import HTTPException

from config import GEMINI_API_KEY, MODEL_NAME, GEMINI_BASE


def _endpoint() -> str:
    return f"{GEMINI_BASE}/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if Gemini added them."""
    text = text.strip()
    if text.startswith("```"):
        # drop opening fence (with optional language tag)
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.lstrip("`").lstrip()
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return text


def gemini_json(prompt: str, temperature: float = 0.1, timeout: int = 45) -> dict:
    """Ask Gemini and parse the response as JSON. Raises HTTPException on failure."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    }

    try:
        r = requests.post(_endpoint(), json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise HTTPException(status_code=504, detail=f"Gemini request failed: {e}")

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini returned {r.status_code}: {r.text[:300]}",
        )

    try:
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Malformed Gemini response: {e}")

    cleaned = _strip_code_fences(raw)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini returned invalid JSON: {e}. Raw: {cleaned[:200]}",
        )


def gemini_text(prompt: str, temperature: float = 0.3, timeout: int = 30) -> str:
    """Ask Gemini and return the plain text response."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    try:
        r = requests.post(_endpoint(), json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise HTTPException(status_code=504, detail=f"Gemini request failed: {e}")

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini returned {r.status_code}: {r.text[:300]}",
        )

    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Malformed Gemini response: {e}")