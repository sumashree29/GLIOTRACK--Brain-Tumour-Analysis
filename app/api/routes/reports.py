"""
Reports routes.
Fix #10 — rate limiter.
Fix #19 — audit log on report download.
Fix P1  — ownership check: only the scan's owning doctor can download its report.
Fix RAG — /full re-runs Qdrant query live using stored query_used so passages
           always appear in the frontend.
Fix SUM — passages are summarised into bullet points by Groq on the backend
           before being sent to the frontend. No API key exposed in browser.
"""
import dataclasses
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import get_current_user
from app.core.rate_limit import api_limiter, get_client_ip
from app.database.crud import (
    get_report_by_scan_id, get_scan_by_id,
    get_agent1_output_by_scan_id, get_agent2_output_by_scan_id,
    get_agent3_output_by_scan_id, get_agent4_meta_by_scan_id,
)
from app.services.audit import log_action
from app.services.storage import generate_presigned_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scans", tags=["reports"])


@router.get("/{scan_id}/report")
def get_report(scan_id: str, request: Request, user=Depends(get_current_user)):
    api_limiter.check(get_client_ip(request))

    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised to access this report")

    report = get_report_by_scan_id(scan_id)
    if not report:
        raise HTTPException(404, "Report not found — pipeline may not have completed yet")

    url = generate_presigned_url(report.r2_key, expires=3600)
    log_action(user["sub"], "REPORT_DOWNLOADED", "report", scan_id, get_client_ip(request))
    return {
        "scan_id":       scan_id,
        "r2_key":        report.r2_key,
        "download_url":  url,
        "generation_ts": report.generation_ts,
    }


def _serialise(obj) -> dict | None:
    """Safely convert a dataclass or Pydantic model to a plain dict."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return None


def _summarise_passages(passages: list[dict]) -> list[dict]:
    """
    Call Groq once to summarise all passages into bullet points.
    Returns passages with a 'bullets' key added to each.
    If Groq fails, passages are returned with bullets=[] — frontend handles gracefully.
    """
    if not passages:
        return passages

    try:
        from app.services.llm_service import call_llm, LLMServiceError
        import json

        passages_text = ""
        for i, p in enumerate(passages):
            passages_text += (
                f"\nPASSAGE {i+1} [{p.get('guideline_version', '')} "
                f"({p.get('publication_year', '')}) — "
                f"{p.get('source_document', '')}]:\n"
                f"{p.get('passage_text', '')[:800]}\n"
            )

        system_prompt = (
            "You are a neuro-oncology clinical assistant. "
            "For each passage provided, extract 3 key clinical bullet points "
            "directly relevant to brain tumour response assessment. "
            "Rules: each bullet must be a complete standalone clinical statement. "
            "Use plain clinical English a doctor can act on immediately. "
            "Do not invent information not present in the passage. "
            "If a passage contains only reference citations with no clinical content, "
            "return exactly one bullet: 'This passage contains reference citations only — see source document for full context.' "
            "Return ONLY a JSON object where keys are 'passage_1', 'passage_2', etc. "
            "and values are arrays of bullet strings. No preamble, no markdown, no other text."
        )

        resp = call_llm(system_prompt, passages_text)
        raw  = resp.content.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        enriched = []
        for i, p in enumerate(passages):
            key     = f"passage_{i+1}"
            bullets = data.get(key, [])
            if not isinstance(bullets, list):
                bullets = []
            enriched.append({**p, "bullets": [str(b) for b in bullets if b]})
        return enriched

    except Exception as exc:
        logger.warning("Passage summarisation failed: %s", exc)
        return [{**p, "bullets": []} for p in passages]


def _live_rag_query(query_used: str) -> dict:
    """
    RAG is disabled on the free tier because loading PyTorch for embeddings
    requires >512MB RAM, which causes an Out of Memory (OOM) crash.
    """
    return {
        "rag_available":  False,
        "passages":       [],
        "failure_reason": "RAG is disabled on the Render Free Tier to prevent out-of-memory crashes.",
        "query_used":     query_used,
    }


@router.get("/{scan_id}/full")
def get_full_report(scan_id: str, request: Request, user=Depends(get_current_user)):
    """
    Returns all agent outputs in one response for the frontend report viewer.
    Agent 4 passages are re-queried live from Qdrant and enriched with
    Groq-generated bullet summaries before being sent to the frontend.
    """
    api_limiter.check(get_client_ip(request))

    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised to access this report")

    report = get_report_by_scan_id(scan_id)
    if not report:
        raise HTTPException(404, "Report not found")

    a1      = get_agent1_output_by_scan_id(scan_id)
    a2      = get_agent2_output_by_scan_id(scan_id)
    a3      = get_agent3_output_by_scan_id(scan_id)
    a4_meta = get_agent4_meta_by_scan_id(scan_id)

    if a4_meta and a4_meta.get("query_used"):
        agent4 = _live_rag_query(a4_meta["query_used"])
    elif a4_meta:
        agent4 = {
            "rag_available":  a4_meta.get("rag_available", False),
            "passages":       [],
            "failure_reason": a4_meta.get(
                "failure_reason",
                "query_used not stored — re-run /resume to regenerate",
            ),
            "query_used": None,
        }
    else:
        agent4 = {
            "rag_available":  False,
            "passages":       [],
            "failure_reason": "Agent 4 has not run for this scan yet",
            "query_used":     None,
        }

    url = generate_presigned_url(report.r2_key, expires=3600)
    log_action(user["sub"], "FULL_REPORT_VIEWED", "report", scan_id, get_client_ip(request))

    return {
        "scan_id":       scan_id,
        "patient_id":    scan.patient_id,
        "scan_date":     scan.scan_date,
        "r2_key":        report.r2_key,
        "download_url":  url,
        "generation_ts": report.generation_ts,
        "agent1":        _serialise(a1),
        "agent2":        _serialise(a2),
        "agent3":        _serialise(a3),
        "agent4":        agent4,
    }