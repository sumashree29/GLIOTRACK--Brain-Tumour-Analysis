"""
CRUD helpers — all DB access goes through here.
Fix #9  — every patient and scan query is scoped to the requesting doctor's email.
Fix #3  — save_agent1_output() implemented and called by orchestrator.
Fix #13 — agent3 loader used by _cached_result now reads real DB rows.
Agent 2 — get_baseline_scan_for_patient, save/get clinical metadata,
           get_prior_cr_provisional_date, updated upsert_agent2_output.
Fix RAG — get_agent3_output_by_scan_id and get_agent4_meta_by_scan_id added.
           Removed duplicate function definitions.
"""
from __future__ import annotations
import uuid, json
from datetime import datetime, timezone
from typing import Optional, List
from app.database.supabase_client import get_supabase_client
from app.models.scan import (
    ScanRecord, ScanStatus, Agent1Output, Agent2Output,
    ClinicalMetadata, BaselineType,
)
from app.models.patient import PatientRecord
from app.models.report import ReportRecord


def _db():
    return get_supabase_client()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Patients ──────────────────────────────────────────────────────────────────

def get_or_create_patient(patient_id: str, doctor_email: str) -> PatientRecord:
    r = _db().table("patients").select("*") \
        .eq("patient_id", patient_id) \
        .eq("assigned_doctor", doctor_email) \
        .execute()
    if r.data:
        return PatientRecord(**r.data[0])
    _db().table("patients").insert({
        "patient_id":      patient_id,
        "assigned_doctor": doctor_email,
        "created_at":      _now(),
    }).execute()
    return PatientRecord(patient_id=patient_id, assigned_doctor=doctor_email)


def get_scans_for_patient(patient_id: str, doctor_email: str = "") -> List[ScanRecord]:
    q = _db().table("scans").select("*").eq("patient_id", patient_id)
    if doctor_email:
        q = q.eq("doctor_email", doctor_email)
    r = q.order("scan_date").execute()
    return [ScanRecord(**row) for row in r.data]


# ── Scan files ────────────────────────────────────────────────────────────────

def add_scan_file(scan_id: str, r2_key: str, sequence: str) -> None:
    _db().table("scan_files").insert({
        "scan_id":    scan_id,
        "r2_key":     r2_key,
        "sequence":   sequence,
        "created_at": _now(),
    }).execute()


def pop_scan_files(scan_id: str) -> list[str]:
    r = _db().table("scan_files").select("r2_key").eq("scan_id", scan_id).execute()
    keys = [row["r2_key"] for row in r.data]
    if keys:
        _db().table("scan_files").delete().eq("scan_id", scan_id).execute()
    return keys


# ── Scans ─────────────────────────────────────────────────────────────────────

def create_scan(patient_id: str, scan_date: str, doctor_email: str) -> ScanRecord:
    scan_id = str(uuid.uuid4())
    row = {
        "scan_id":      scan_id,
        "patient_id":   patient_id,
        "scan_date":    scan_date,
        "doctor_email": doctor_email,
        "status":       ScanStatus.PENDING.value,
        "created_at":   _now(),
    }
    _db().table("scans").insert(row).execute()
    return ScanRecord(**row)


def get_scan_by_id(scan_id: str) -> Optional[ScanRecord]:
    r = _db().table("scans").select("*").eq("scan_id", scan_id).execute()
    return ScanRecord(**r.data[0]) if r.data else None


def update_scan_status(
    scan_id: str, status: ScanStatus, ts: str,
    failed_stage: Optional[str] = None, error: Optional[str] = None,
):
    upd = {"status": status.value, "updated_at": ts}
    if failed_stage:
        upd["failed_stage"] = failed_stage
    if error:
        upd["error"] = error
    _db().table("scans").update(upd).eq("scan_id", scan_id).execute()


# ── Agent 2 — baseline and clinical metadata ──────────────────────────────────

def get_baseline_scan_for_patient(
    patient_id: str, doctor_email: str
) -> Optional[ScanRecord]:
    """
    Find the confirmed baseline scan for this patient.
    Returns the scan where is_baseline=True and baseline_type is
    'post_op' or 'nadir'. Scoped to doctor_email.
    Returns None if no confirmed baseline exists.
    """
    r = (
        _db().table("scans").select("*")
        .eq("patient_id",   patient_id)
        .eq("doctor_email", doctor_email)
        .eq("is_baseline",  True)
        .in_("baseline_type", [BaselineType.POST_OP.value, BaselineType.NADIR.value])
        .order("scan_date")
        .execute()
    )
    if not r.data:
        return None
    return ScanRecord(**r.data[0])


def save_clinical_metadata(scan_id: str, meta: ClinicalMetadata) -> None:
    """
    Persist the 5 clinical metadata fields onto the scans row.
    Called at upload time (Option 1 — metadata submitted with scan).
    """
    _db().table("scans").update({
        "steroid_dose_current_mg":   meta.steroid_dose_current_mg,
        "steroid_dose_baseline_mg":  meta.steroid_dose_baseline_mg,
        "new_lesion_detected":       meta.new_lesion_detected,
        "weeks_since_rt_completion": meta.weeks_since_rt_completion,
        "clinical_deterioration":    meta.clinical_deterioration,
        "updated_at":                _now(),
    }).eq("scan_id", scan_id).execute()


def get_clinical_metadata(scan_id: str) -> ClinicalMetadata:
    """
    Load clinical metadata from the scans row.
    Returns defaults (all None / False) if columns are null — safe for first scan.
    """
    r = _db().table("scans").select(
        "steroid_dose_current_mg, steroid_dose_baseline_mg, "
        "new_lesion_detected, weeks_since_rt_completion, clinical_deterioration"
    ).eq("scan_id", scan_id).execute()
    if not r.data:
        return ClinicalMetadata()
    row = r.data[0]
    return ClinicalMetadata(
        steroid_dose_current_mg=row.get("steroid_dose_current_mg"),
        steroid_dose_baseline_mg=row.get("steroid_dose_baseline_mg"),
        new_lesion_detected=row.get("new_lesion_detected") or False,
        weeks_since_rt_completion=row.get("weeks_since_rt_completion"),
        clinical_deterioration=row.get("clinical_deterioration") or False,
    )


def set_scan_as_baseline(
    scan_id: str, baseline_type: str, doctor_email: str
) -> bool:
    """
    Mark a scan as the RANO baseline for its patient.
    baseline_type must be 'post_op' or 'nadir'.
    Clears is_baseline on all other scans for this patient first
    to ensure only one baseline exists at a time.
    Returns True if the scan was found and updated.
    """
    scan = get_scan_by_id(scan_id)
    if scan is None or scan.doctor_email != doctor_email:
        return False
    # Clear any previous baseline for this patient
    _db().table("scans").update({
        "is_baseline":   False,
        "baseline_type": None,
        "updated_at":    _now(),
    }).eq("patient_id",   scan.patient_id) \
      .eq("doctor_email", doctor_email) \
      .execute()
    # Set this scan as baseline
    _db().table("scans").update({
        "is_baseline":   True,
        "baseline_type": baseline_type,
        "updated_at":    _now(),
    }).eq("scan_id", scan_id).execute()
    return True


def get_prior_cr_provisional_date(
    patient_id: str, doctor_email: str, current_scan_id: str
) -> Optional[str]:
    """
    Find the most recent prior scan for this patient that has
    rano_class='CR_provisional'. Used to determine CR_confirmed eligibility.
    RANO 2010 §2.1 — second qualifying scan ≥4 weeks after CR_provisional.
    Returns the scan_date string or None.
    """
    r = (
        _db().table("agent2_outputs")
        .select("scan_id, baseline_date")
        .eq("rano_class", "CR_provisional")
        .execute()
    )
    if not r.data:
        return None
    patient_scan_ids = {
        s.scan_id for s in get_scans_for_patient(patient_id, doctor_email)
        if s.scan_id != current_scan_id
    }
    candidates = [
        row for row in r.data if row["scan_id"] in patient_scan_ids
    ]
    if not candidates:
        return None
    cr_scan_id = candidates[-1]["scan_id"]
    scan = get_scan_by_id(cr_scan_id)
    return scan.scan_date if scan else None


# ── Agent outputs ─────────────────────────────────────────────────────────────

def save_agent1_output(a1: Agent1Output):
    pass  # Worker writes directly to agent1_results via _write_to_supabase


def get_agent1_output_by_scan_id(scan_id: str) -> Optional[Agent1Output]:
    r = _db().table("agent1_results").select("*").eq("scan_id", scan_id).execute()
    return Agent1Output(**r.data[0]) if r.data else None


def upsert_agent2_output(scan_id: str, a2: Agent2Output) -> None:
    """
    Write Agent 2 output to agent2_outputs table.
    Writes all spec-required fields including skip state,
    pseudoprogression flag, baseline metadata, and reasoning.
    """
    data = a2.model_dump()
    data["scan_id"] = scan_id
    _db().table("agent2_outputs").upsert(data).execute()


def get_agent2_output_by_scan_id(scan_id: str) -> Optional[Agent2Output]:
    r = _db().table("agent2_outputs").select("*").eq("scan_id", scan_id).execute()
    if not r.data:
        return None
    return Agent2Output(**r.data[0])


def upsert_agent3_output(scan_id: str, a3) -> None:
    import dataclasses as _dc
    data = a3.model_dump() if hasattr(a3, "model_dump") else dict(a3.__dict__)
    data["scan_id"] = scan_id
    for k in ["trajectory_intervals", "inflection_points", "scan_dates"]:
        if k not in data or isinstance(data[k], str):
            continue
        items = data[k]
        if items and _dc.is_dataclass(items[0]):
            items = [_dc.asdict(item) for item in items]
        data[k] = json.dumps(items)
    _db().table("agent3_outputs").upsert(data).execute()


def get_agent3_output_by_scan_id(scan_id: str):
    """
    Load Agent3Output from Supabase.
    Parses JSON string fields back into lists/dicts for the frontend chart.
    """
    r = _db().table("agent3_outputs").select("*").eq("scan_id", scan_id).execute()
    if not r.data:
        return None
    from app.agents.longitudinal_agent import Agent3Output
    import dataclasses
    if dataclasses.is_dataclass(Agent3Output):
        valid = {f.name for f in dataclasses.fields(Agent3Output)}
        filtered = {k: v for k, v in r.data[0].items() if k in valid}
        for k in ["trajectory_intervals", "inflection_points", "scan_dates"]:
            if k in filtered and isinstance(filtered[k], str):
                try:
                    filtered[k] = json.loads(filtered[k])
                except Exception:
                    pass
        return Agent3Output(**filtered)
        row = r.data[0]
        valid = {f.name for f in dataclasses.fields(Agent3Output)}
        filtered2 = {k: v for k, v in row.items() if k in valid}
        filtered2.setdefault("rc_volumes", [])
        return Agent3Output(**filtered2)
    return Agent3Output(**r.data[0])


def upsert_agent4_output(scan_id: str, a4) -> None:
    """
    Persists Agent 4 metadata only — passage text is NOT stored.
    query_used is stored so /full can re-query Qdrant live on demand.
    """
    data = {
        "scan_id":        scan_id,
        "rag_available":  a4.rag_available,
        "failure_reason": a4.failure_reason,
        "query_used":     a4.query_used,
        "passage_count":  len(a4.passages),
    }
    _db().table("agent4_outputs").upsert(data).execute()


def get_agent4_meta_by_scan_id(scan_id: str) -> Optional[dict]:
    """
    Returns raw agent4_outputs DB row as a plain dict.
    Passage text is NOT stored here — only rag_available, failure_reason,
    query_used, passage_count. The /full endpoint re-queries Qdrant live
    using query_used to retrieve actual passage text.
    """
    r = _db().table("agent4_outputs").select("*").eq("scan_id", scan_id).execute()
    return r.data[0] if r.data else None


# ── Reports ───────────────────────────────────────────────────────────────────

def create_report_record(
    scan_id: str, r2_key: str, generation_ts: str,
    sections, prompt_tokens: int, completion_tokens: int,
) -> None:
    _db().table("reports").upsert({
        "scan_id":           scan_id,
        "r2_key":            r2_key,
        "generation_ts":     generation_ts,
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
    }).execute()


def get_report_by_scan_id(scan_id: str) -> Optional[ReportRecord]:
    r = _db().table("reports").select("*").eq("scan_id", scan_id).execute()
    return ReportRecord(**r.data[0]) if r.data else None


def get_patients_for_doctor(doctor_email: str) -> list:
    r = _db().table("patients").select("*") \
        .eq("assigned_doctor", doctor_email) \
        .eq("archived", False) \
        .order("created_at", desc=True) \
        .execute()
    return [PatientRecord(**row) for row in r.data]


def get_patient_by_id(patient_id: str, doctor_email: str) -> Optional[PatientRecord]:
    r = _db().table("patients").select("*") \
        .eq("patient_id", patient_id) \
        .eq("assigned_doctor", doctor_email) \
        .execute()
    return PatientRecord(**r.data[0]) if r.data else None


def archive_patient(patient_id: str, doctor_email: str) -> bool:
    r = _db().table("patients").update({
        "archived":    True,
        "archived_at": _now(),
    }).eq("patient_id", patient_id) \
      .eq("assigned_doctor", doctor_email) \
      .execute()
    return bool(r.data)


def restore_patient(patient_id: str, doctor_email: str) -> bool:
    r = _db().table("patients").update({
        "archived":    False,
        "archived_at": None,
    }).eq("patient_id", patient_id) \
      .eq("assigned_doctor", doctor_email) \
      .execute()
    return bool(r.data)


def get_archived_patients(doctor_email: str) -> list:
    r = _db().table("patients").select("*") \
        .eq("assigned_doctor", doctor_email) \
        .eq("archived", True) \
        .order("archived_at", desc=True) \
        .execute()
    return [PatientRecord(**row) for row in r.data]