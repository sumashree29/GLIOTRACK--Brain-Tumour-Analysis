"""
Scans routes.
Fix #9  — create_scan stores doctor_email for ownership.
Fix #10 — rate limiter applied.
Fix #11 — file type and size validation on upload.
Fix #19 — audit logging on upload and pipeline trigger.
Fix S3  — _pending dict replaced with scan_files DB table.
Fix S5  — trigger_pipeline is async; pipeline runs via asyncio.create_task.
Fix S6  — file upload streams to R2 in chunks instead of buffering in RAM.
Agent 2 — /run accepts clinical metadata; /set-baseline marks baseline scan.
"""
import asyncio
from datetime import date
from pathlib import Path as _Path
from typing import Optional
import logging
logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request


from app.core.auth import get_current_user
from app.core.rate_limit import api_limiter, pipeline_limiter, upload_limiter, get_client_ip
from app.database.crud import (
    create_scan, get_scan_by_id, add_scan_file, pop_scan_files,
    save_clinical_metadata, set_scan_as_baseline,
)
from app.models.scan import ClinicalMetadata, BaselineType
from app.services.audit import log_action
from app.services.orchestrator import run_pipeline, _run_agents_2_to_5
from app.services.storage import upload_stream_to_r2
from pydantic import BaseModel

router = APIRouter(prefix="/scans", tags=["scans"])

_ALLOWED_EXTENSIONS = {".dcm", ".nii", ".gz", ".zip"}
_MAX_FILE_BYTES     = 2 * 1024 * 1024 * 1024   # 2 GB — spec Section 3
_CHUNK_SIZE         = 8 * 1024 * 1024           # 8 MB streaming chunks — spec Section 3


class ScanIn(BaseModel):
    patient_id: str
    scan_date:  date


@router.post("", status_code=201)
def create_scan_record(body: ScanIn, request: Request, user=Depends(get_current_user)):
    api_limiter.check(get_client_ip(request))
    scan = create_scan(body.patient_id, body.scan_date.isoformat(), doctor_email=user["sub"])
    return scan


@router.post("/{scan_id}/files")
async def upload_sequence(
    scan_id:  str,
    file:     UploadFile = File(...),
    sequence: str        = Form(...),
    request:  Request    = None,
    user=Depends(get_current_user),
):
    upload_limiter.check(get_client_ip(request))

    filename = file.filename or ""
    _p = _Path(filename.lower())
    ext = ".gz" if filename.lower().endswith(".nii.gz") else _p.suffix
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"File type not allowed. Accepted: .dcm  .nii  .nii.gz  .zip — got '{ext}'",
        )

    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised to upload to this scan")

    r2_key = f"dicoms/{scan_id}/{sequence}/{filename}"

    # Stream to R2 in 8MB chunks — never buffer 2GB in Render RAM (spec Section 3)
    total_bytes = await upload_stream_to_r2(file, r2_key, _MAX_FILE_BYTES, _CHUNK_SIZE)

    add_scan_file(scan_id, r2_key, sequence)

    log_action(
        user["sub"], "FILE_UPLOADED", "scan", scan_id, get_client_ip(request),
        details={"sequence": sequence, "filename": filename, "bytes": total_bytes},
    )
    return {"r2_key": r2_key, "sequence": sequence, "size_bytes": total_bytes}


@router.post("/{scan_id}/run")
async def trigger_pipeline(
    scan_id: str,
    request: Request,
    user=Depends(get_current_user),
    # ── Clinical metadata (Option 1 — submitted at run time) ──────────
    # All optional — first scan will have none of these
    steroid_dose_current_mg:   Optional[float] = Form(default=None),
    steroid_dose_baseline_mg:  Optional[float] = Form(default=None),
    new_lesion_detected:       bool            = Form(default=False),
    weeks_since_rt_completion: Optional[int]   = Form(default=None),
    clinical_deterioration:    bool            = Form(default=False),
):
    """
    Trigger the full pipeline for this scan.
    Clinical metadata is submitted here and stored on the scan row
    so Agent 2 can retrieve it during RANO classification.
    """
    pipeline_limiter.check(get_client_ip(request))

    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised to run pipeline on this scan")

    # Persist clinical metadata before pipeline starts
    meta = ClinicalMetadata(
        steroid_dose_current_mg=steroid_dose_current_mg,
        steroid_dose_baseline_mg=steroid_dose_baseline_mg,
        new_lesion_detected=new_lesion_detected,
        weeks_since_rt_completion=weeks_since_rt_completion,
        clinical_deterioration=clinical_deterioration,
    )
    save_clinical_metadata(scan_id, meta)

    keys = pop_scan_files(scan_id)

    async def _run_pipeline_safe(**kwargs):
        try:
            await run_pipeline(**kwargs)
        except Exception as exc:
            logger.error("Pipeline task crashed | scan_id=%s error=%s", kwargs.get("scan_id"), exc, exc_info=True)

    asyncio.create_task(
        _run_pipeline_safe(
            scan_id=scan_id,
            patient_id=scan.patient_id,
            scan_date=scan.scan_date,
            dicom_r2_keys=keys,
            doctor_email=user["sub"],
        )
    )

    log_action(
        user["sub"], "PIPELINE_TRIGGERED", "scan", scan_id, get_client_ip(request),
        details={"new_lesion_detected": new_lesion_detected,
                 "steroid_dose_current_mg": steroid_dose_current_mg},
    )
    return {"message": "Pipeline started", "scan_id": scan_id}


@router.post("/{scan_id}/set-baseline")
def set_baseline(
    scan_id:       str,
    baseline_type: str,
    request:       Request,
    user=Depends(get_current_user),
):
    """
    Mark this scan as the RANO baseline for its patient.
    baseline_type must be 'post_op' or 'nadir'.
    RANO 2010 §2.1 — baseline must be confirmed by a clinician.
    Only one baseline scan can exist per patient at a time.
    """
    api_limiter.check(get_client_ip(request))

    allowed = {BaselineType.POST_OP.value, BaselineType.NADIR.value}
    if baseline_type not in allowed:
        raise HTTPException(
            400,
            f"baseline_type must be one of {sorted(allowed)}. Got '{baseline_type}'.",
        )

    updated = set_scan_as_baseline(scan_id, baseline_type, doctor_email=user["sub"])
    if not updated:
        raise HTTPException(404, "Scan not found or not authorised.")

    log_action(
        user["sub"], "BASELINE_SET", "scan", scan_id, get_client_ip(request),
        details={"baseline_type": baseline_type},
    )
    return {
        "message": f"Scan {scan_id} set as RANO baseline ({baseline_type}).",
        "scan_id": scan_id,
        "baseline_type": baseline_type,
    }
@router.post("/{scan_id}/resume")
async def resume_pipeline(
    scan_id: str,
    request: Request,
    user=Depends(get_current_user),
):
    """
    Resume pipeline from Agent 2 onward using existing Agent 1 result.
    Skips Modal entirely — costs zero GPU credits.
    Use when Agent 1 already completed but Agents 2-5 failed or need re-run.
    """
    api_limiter.check(get_client_ip(request))

    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised")

    from app.database.crud import get_agent1_output_by_scan_id
    a1 = get_agent1_output_by_scan_id(scan_id)
    if a1 is None:
        raise HTTPException(400, "No Agent 1 result found for this scan — cannot resume. Run full pipeline first.")

    try:
        await _run_agents_2_to_5(
            scan_id=scan_id,
            patient_id=scan.patient_id,
            scan_date=scan.scan_date,
            doctor_email=user["sub"],
            a1=a1,
        )
    except Exception as exc:
        logger.error(
            "Resume task crashed | scan_id=%s error=%s",
            scan_id, exc, exc_info=True
        )
        raise HTTPException(500, f"Resume failed: {exc}")

    return {"message": "Pipeline resumed from Agent 2", "scan_id": scan_id}
@router.delete("/{scan_id}")
def delete_scan(
    scan_id: str,
    request: Request,
    user=Depends(get_current_user),
):
    api_limiter.check(get_client_ip(request))
    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised")
    from app.database.supabase_client import get_supabase_client
    get_supabase_client().table("scans").delete().eq("scan_id", scan_id).execute()
    log_action(user["sub"], "SCAN_DELETED", "scan", scan_id, get_client_ip(request))
    return {"message": f"Scan {scan_id} deleted."}

@router.get("/{scan_id}/status")
def get_status(scan_id: str, request: Request, user=Depends(get_current_user)):
    api_limiter.check(get_client_ip(request))
    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.doctor_email != user["sub"]:
        raise HTTPException(403, "Not authorised to view this scan")
    return {
        "scan_id":      scan_id,
        "status":       scan.status,
        "failed_stage": scan.failed_stage,
        "error":        scan.error,
    }   