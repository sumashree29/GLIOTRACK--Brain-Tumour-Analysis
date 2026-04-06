"""
Patients routes.
Fix #9  — all queries scoped to the logged-in doctor's email.
Fix #10 — rate limiter applied.
Fix #19 — audit logging on patient view.
Fix Q3  — patient_id validated: alphanumeric + hyphens/underscores only,
           max 64 chars. Prevents path traversal in R2 keys and injection.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.auth import get_current_user
from app.database.crud import get_or_create_patient, get_scans_for_patient
from app.services.audit import log_action
from app.core.rate_limit import api_limiter, get_client_ip
from pydantic import BaseModel

router = APIRouter(prefix="/patients", tags=["patients"])

_PATIENT_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def _validate_patient_id(patient_id: str):
    if not _PATIENT_ID_RE.match(patient_id):
        raise HTTPException(
            400,
            "patient_id must be 1-64 characters: letters, digits, hyphens and underscores only."
        )


class PatientIn(BaseModel):
    patient_id: str


@router.post("", status_code=201)
def create_patient(body: PatientIn, request: Request, user=Depends(get_current_user)):
    api_limiter.check(get_client_ip(request))
    _validate_patient_id(body.patient_id)
    patient = get_or_create_patient(body.patient_id, doctor_email=user["sub"])
    log_action(user["sub"], "PATIENT_CREATED", "patient", body.patient_id, get_client_ip(request))
    return patient


@router.get("/{patient_id}/scans")
def list_scans(patient_id: str, request: Request, user=Depends(get_current_user)):
    api_limiter.check(get_client_ip(request))
    _validate_patient_id(patient_id)
    scans = get_scans_for_patient(patient_id, doctor_email=user["sub"])
    log_action(user["sub"], "PATIENT_SCANS_VIEWED", "patient", patient_id, get_client_ip(request))
    return scans


@router.get("")
def list_patients(request: Request, user=Depends(get_current_user)):
    """Return all active patients belonging to the logged-in doctor."""
    api_limiter.check(get_client_ip(request))
    from app.database.crud import get_patients_for_doctor
    patients = get_patients_for_doctor(doctor_email=user["sub"])
    log_action(user["sub"], "PATIENTS_LISTED", "patient", "all", get_client_ip(request))
    return patients


@router.get("/archived")
def list_archived_patients(
    request: Request,
    user=Depends(get_current_user)
):
    """Return all archived patients for this doctor."""
    api_limiter.check(get_client_ip(request))
    from app.database.crud import get_archived_patients
    patients = get_archived_patients(doctor_email=user["sub"])
    return patients


@router.get("/{patient_id}")
def get_patient(patient_id: str, request: Request, user=Depends(get_current_user)):
    """Return a single patient record scoped to the logged-in doctor."""
    api_limiter.check(get_client_ip(request))
    _validate_patient_id(patient_id)
    from app.database.crud import get_patient_by_id
    patient = get_patient_by_id(patient_id, doctor_email=user["sub"])
    if not patient:
        raise HTTPException(404, "Patient not found")
    log_action(user["sub"], "PATIENT_VIEWED", "patient", patient_id, get_client_ip(request))
    return patient


@router.post("/{patient_id}/archive")
def archive_patient_route(
    patient_id: str,
    request: Request,
    user=Depends(get_current_user)
):
    """Hide a patient from the active list (soft delete)."""
    api_limiter.check(get_client_ip(request))
    _validate_patient_id(patient_id)
    from app.database.crud import archive_patient
    success = archive_patient(patient_id, doctor_email=user["sub"])
    if not success:
        raise HTTPException(404, "Patient not found or not authorised")
    log_action(
        user["sub"], "PATIENT_ARCHIVED", "patient",
        patient_id, get_client_ip(request)
    )
    return {"message": f"Patient {patient_id} archived successfully"}


@router.post("/{patient_id}/restore")
def restore_patient_route(
    patient_id: str,
    request: Request,
    user=Depends(get_current_user)
):
    """Restore a previously archived patient."""
    api_limiter.check(get_client_ip(request))
    _validate_patient_id(patient_id)
    from app.database.crud import restore_patient
    success = restore_patient(patient_id, doctor_email=user["sub"])
    if not success:
        raise HTTPException(404, "Patient not found or not authorised")
    log_action(
        user["sub"], "PATIENT_RESTORED", "patient",
        patient_id, get_client_ip(request)
    )
    return {"message": f"Patient {patient_id} restored successfully"}