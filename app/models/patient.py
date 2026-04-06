from pydantic import BaseModel
from typing import Optional


class PatientCreate(BaseModel):
    patient_id: str
    age_at_diagnosis: Optional[int] = None
    diagnosis: Optional[str] = None


class PatientRecord(PatientCreate):
    # FIX #9 / #15 — assigned_doctor required by scoped queries
    assigned_doctor: Optional[str] = None
    created_at: Optional[str] = None
    archived: bool = False
    archived_at: Optional[str] = None
