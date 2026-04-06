"""
Audit logging — every doctor action recorded to Supabase.
Fix #19 — required for HIPAA / DPDP / medical compliance.
"""
from __future__ import annotations
from datetime import datetime, timezone
from app.database.supabase_client import get_supabase_client
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def log_action(
    doctor_email:  str,
    action:        str,
    resource_type: str,
    resource_id:   str,
    ip_address:    Optional[str] = None,
    details:       Optional[dict] = None,
):
    """
    Write one audit log entry. Non-blocking — logs warning on failure, never raises.
    Actions: PATIENT_CREATED, PATIENT_SCANS_VIEWED, FILE_UPLOADED,
             PIPELINE_TRIGGERED, REPORT_DOWNLOADED
    """
    try:
        get_supabase_client().table("audit_logs").insert({
            "doctor_email":  doctor_email,
            "action":        action,
            "resource_type": resource_type,
            "resource_id":   resource_id,
            "ip_address":    ip_address,
            "details":       details or {},
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        logger.warning("Audit log write failed (non-critical): %s", exc)
