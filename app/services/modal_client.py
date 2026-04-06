"""Thin client for submitting jobs to the Modal segmentation worker."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import httpx
from app.core.config import settings
from app.models.scan import Agent1Output

logger = logging.getLogger(__name__)
_TIMEOUT = 30.0


@dataclass
class JobPollResult:
    status: str
    agent1_output: Optional[Agent1Output] = None
    error: Optional[str] = None


def submit_segmentation_job(
    scan_id: str,
    patient_id: str,
    dicom_r2_keys: list[str],
    scan_date: str = "",
) -> str:
    url = settings.modal_webhook_url
    headers = (
        {"Authorization": f"Bearer {settings.modal_webhook_secret}"}
        if settings.modal_webhook_secret else {}
    )
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post(url, json={
            "scan_id":       scan_id,
            "patient_id":    patient_id,
            "dicom_r2_keys": dicom_r2_keys,
            "scan_date":     scan_date,
        }, headers=headers)
        resp.raise_for_status()
    return resp.json()["job_id"]


def poll_job_result(job_id: str) -> JobPollResult:
    if not settings.modal_status_url:
        raise ValueError(
            "modal_status_url is not set in .env — "
            "set it to your Modal /status endpoint URL"
        )
    url = f"{settings.modal_status_url}?job_id={job_id}"
    headers = (
        {"Authorization": f"Bearer {settings.modal_webhook_secret}"}
        if settings.modal_webhook_secret else {}
    )
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.get(url, headers=headers)
        resp.raise_for_status()

    body   = resp.json()
    status = body.get("status")

    if status == "completed":
        result = body.get("result", {})
        known = set(Agent1Output.model_fields.keys())
        filtered = {k: v for k, v in result.items() if k in known}
        logger.info("Agent1 filtered fields: %s", list(filtered.keys()))  # ADD THIS
        logger.info("Agent1 filtered values: %s", filtered)               # ADD THIS
        return JobPollResult(
            status="completed",
            agent1_output=Agent1Output(**filtered),
        )

    if status == "failed":
        return JobPollResult(status="failed", error=body.get("error"))

    return JobPollResult(status=status)