from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ScanStatus(str, Enum):
    PENDING                = "PENDING"
    SEGMENTATION_RUNNING   = "SEGMENTATION_RUNNING"
    SEGMENTATION_COMPLETE  = "SEGMENTATION_COMPLETE"
    RANO_RUNNING           = "RANO_RUNNING"
    RANO_COMPLETE          = "RANO_COMPLETE"
    LONGITUDINAL_RUNNING   = "LONGITUDINAL_RUNNING"
    LONGITUDINAL_COMPLETE  = "LONGITUDINAL_COMPLETE"
    RAG_RUNNING            = "RAG_RUNNING"
    RAG_COMPLETE           = "RAG_COMPLETE"
    REPORT_RUNNING         = "REPORT_RUNNING"
    REPORT_READY           = "REPORT_READY"
    FAILED                 = "FAILED"


class BaselineType(str, Enum):
    POST_OP     = "post_op"
    NADIR       = "nadir"
    UNCONFIRMED = "unconfirmed"


class ClinicalMetadata(BaseModel):
    """
    Clinical context submitted by the doctor at scan upload time.
    All fields are optional with safe defaults so the first scan
    (which has no prior context) does not require them.
    Agent 2 uses these to apply RANO steroid and PD rules correctly.
    """
    # RANO 2010 §2.1-2.2 — steroid dose in mg/day dexamethasone equivalent
    steroid_dose_current_mg:  Optional[float] = None
    steroid_dose_baseline_mg: Optional[float] = None

    # RANO 2010 §2.1 — new lesion on any sequence is immediate PD
    new_lesion_detected: bool = False

    # RANO 2010 §2.2 — weeks since radiotherapy completion
    # None means RT not yet completed or not applicable
    weeks_since_rt_completion: Optional[int] = None

    # RANO 2010 §2.2 — clinical deterioration used in conjunction with
    # steroid increase to trigger PD (not standalone)
    clinical_deterioration: bool = False
    mgmt_status: Optional[str] = None
    idh_status: Optional[str] = None
    days_since_diagnosis: Optional[int] = None


class Agent1Output(BaseModel):
    # ── Core fields — present in agent1_outputs DB table ──────────────
    scan_id:   str
    scan_date: str

    et_volume_ml: float
    tc_volume_ml: float
    wt_volume_ml: float
    rc_volume_ml: Optional[float] = None

    et_diameter1_mm:           float
    et_diameter2_mm:           float
    bidimensional_product_mm2: float

    # Validation Dice scores — ET reported first per spec Section 10
    dice_et: Optional[float] = None
    dice_tc: Optional[float] = None
    dice_wt: Optional[float] = None

    low_confidence_flag:   bool            = False
    low_confidence_reason: Optional[str]   = None

    # Agent 2 needs this to validate the baseline is usable
    # Optional so existing DB rows without this column still load
    measurable_lesion_count: Optional[int] = None

    # ── Extra fields returned by Modal worker ─────────────────────────
    patient_id:         Optional[str]   = None
    mean_softmax_prob:  Optional[float] = None
    entropy_score:      Optional[float] = None
    mask_r2_key:        Optional[str]   = None
    skull_strip_method: Optional[str]   = None

    class Config:
        # Silently ignore any extra fields the worker returns that are
        # not listed above. Prevents ValidationError on new worker fields.
        extra = "ignore"


class Agent2Output(BaseModel):
    """
    Full RANO classification output per spec Section 4 Agent 2.
    When Agent 2 is skipped, skipped=True and rano_class=None.
    """
    # ── Classification result ─────────────────────────────────────────
    # None when skipped (no baseline available)
    rano_class: Optional[str] = None

    # ── Skip state ────────────────────────────────────────────────────
    skipped:     bool            = False
    skip_reason: Optional[str]   = None

    # ── Bidimensional products used for classification ─────────────────
    baseline_bidimensional_product_mm2: Optional[float] = None
    current_bidimensional_product_mm2:  Optional[float] = None
    pct_change_from_baseline:           Optional[float] = None

    # ── Baseline reference ────────────────────────────────────────────
    baseline_scan_id:  Optional[str] = None
    baseline_date:     Optional[str] = None
    # RANO 2010 §2.1 — baseline must be post_op or nadir, confirmed by clinician
    baseline_type:     Optional[str] = None

    # ── Clinical metadata applied ─────────────────────────────────────
    steroid_increase:      bool = False
    new_lesion_detected:   bool = False
    clinical_deterioration: bool = False
    weeks_since_rt_completion: Optional[int] = None
    mgmt_status: Optional[str] = None
    idh_status:  Optional[str] = None

    # ── Flags ─────────────────────────────────────────────────────────
    # RANO 2010 §2.2 — PD within 24 weeks of RT → flag for clinician review
    pseudoprogression_flag: bool = False 

    # Propagated from Agent 1
    low_confidence_flag: bool = False

    # ── Audit fields ──────────────────────────────────────────────────
    # Human-readable explanation of every decision made
    reasoning:          str            = ""
    confidence_warning: Optional[str]  = None

    class Config:
        extra = "ignore"


class ScanCreate(BaseModel):
    patient_id: str
    scan_date:  str


class ScanRecord(ScanCreate):
    scan_id:      str
    status:       ScanStatus = ScanStatus.PENDING
    doctor_email: Optional[str] = None
    created_at:   Optional[str] = None
    updated_at:   Optional[str] = None
    failed_stage: Optional[str] = None
    error:        Optional[str] = None

    # ── Agent 2 baseline fields ───────────────────────────────────────
    # Set by the doctor to mark this scan as the RANO baseline
    # RANO 2010 §2.1 — must be post_op (within 72h of surgery) or nadir
    baseline_type: Optional[str] = None
    is_baseline:   bool          = False

    # ── Clinical metadata stored at upload ────────────────────────────
    steroid_dose_current_mg:   Optional[float] = None
    steroid_dose_baseline_mg:  Optional[float] = None
    new_lesion_detected:       bool            = False
    weeks_since_rt_completion: Optional[int]   = None
    clinical_deterioration:    bool            = False

    class Config:
        extra = "ignore"