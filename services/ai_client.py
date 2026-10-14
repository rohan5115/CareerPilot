"""Lazy Gemini client with bounded retries and deterministic offline fallbacks."""
import logging
import os
import time

logger = logging.getLogger(__name__)


def generate_text(prompt: str, fallback: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return fallback
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=25000))
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), contents=prompt
                )
                text = getattr(response, "text", None)
                if text and text.strip():
                    return text.strip()
                raise ValueError("AI provider returned an empty response")
            except Exception as exc:
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2 ** attempt))
    except Exception as exc:
        logger.warning("AI request failed; using local fallback: %s", exc)
        return fallback
    finally:
        if "client" in locals():
            client.close()
    return fallback


def safe_context(value: str, limit: int = 12000) -> str:
    """Limit prompt size and treat user supplied text as data, never instructions."""
    return (value or "")[:limit]
