"""
Groq LLM client.
Spec: model=llama-3.3-70b-versatile, temperature=0.1, max_tokens=2048, retries=3.
"""
from __future__ import annotations
import logging, time
from dataclasses import dataclass
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, before_sleep_log
from app.core.config import settings

logger = logging.getLogger(__name__)

_GROQ_MODEL      = "llama-3.3-70b-versatile"
_TEMPERATURE     = 0.1
_MAX_TOKENS      = 2048
_GROQ_CHAT_URL   = "https://api.groq.com/openai/v1/chat/completions"
_REQUEST_TIMEOUT = 60.0

class LLMServiceError(RuntimeError):
    pass

@dataclass(frozen=True)
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _call_groq(system_prompt: str, user_prompt: str) -> LLMResponse:
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": _GROQ_MODEL, "temperature": _TEMPERATURE, "max_tokens": _MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    }
    t0 = time.perf_counter()
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        resp = client.post(_GROQ_CHAT_URL, headers=headers, json=payload)
        resp.raise_for_status()
    latency_ms = (time.perf_counter() - t0) * 1000.0
    body   = resp.json()
    usage  = body.get("usage", {})
    return LLMResponse(
        content=body["choices"][0]["message"]["content"],
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        latency_ms=latency_ms,
    )

def call_llm(system_prompt: str, user_prompt: str) -> LLMResponse:
    try:
        return _call_groq(system_prompt, user_prompt)
    except Exception as exc:
        logger.error("Groq permanently failed: %s", exc)
        raise LLMServiceError(f"Groq API unavailable: {exc}") from exc
