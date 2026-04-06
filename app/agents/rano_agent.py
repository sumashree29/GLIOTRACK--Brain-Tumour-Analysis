"""
Agent 2 — RANO 2010 Classification Agent.
Runs on: Render.com (pure Python, no ML).

Rules implemented:
  - RANO 2010 §2.1: CR, PR, SD thresholds
  - RANO 2010 §2.1: CR_provisional → CR_confirmed (second scan ≥ 4 weeks)
  - RANO 2010 §2.1-2.2: steroid increase ALONE blocks CR and PR
  - RANO 2010 §2.2: PD from steroid + ET + deterioration (all three required)
  - RANO 2010 §2.2: new lesion = immediate PD regardless of measurements
  - Pseudoprogression flag: PD within 24 weeks of RT completion
  - Graceful skip when no confirmed baseline exists
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from enum import Enum
from typing import Optional

from app.core.config import settings
from app.models.scan import Agent1Output, Agent2Output, ClinicalMetadata, BaselineType

logger = logging.getLogger(__name__)


class RANOClass(str, Enum):
    CR_PROVISIONAL = "CR_provisional"
    CR_CONFIRMED   = "CR_confirmed"
    PR             = "PR"
    SD             = "SD"
    PD             = "PD"


# ── Skip helpers ──────────────────────────────────────────────────────────────

def _skipped(reason: str, a1: Agent1Output) -> Agent2Output:
    """Return a clearly skipped Agent2Output with a human-readable reason."""
    logger.info("Agent 2 skipped | scan_id=%s reason=%s", a1.scan_id, reason)
    return Agent2Output(
        skipped=True,
        skip_reason=reason,
        rano_class=None,
        current_bidimensional_product_mm2=a1.bidimensional_product_mm2,
        low_confidence_flag=a1.low_confidence_flag,
        reasoning=f"RANO classification skipped: {reason}",
    )


# ── Steroid rule ──────────────────────────────────────────────────────────────

def _compute_steroid_increase(meta: ClinicalMetadata) -> tuple[bool, str]:
    """
    RANO 2010 §2.1-2.2 — steroid increase defined as current dose
    more than 10% above the baseline dose.
    Returns (steroid_increase: bool, note: str).
    """
    if meta.steroid_dose_current_mg is None or meta.steroid_dose_baseline_mg is None:
        return False, "Steroid doses not provided — steroid rule not applied."
    threshold = meta.steroid_dose_baseline_mg * settings.steroid_increase_threshold
    increased = meta.steroid_dose_current_mg > threshold
    note = (
        f"Steroid dose current={meta.steroid_dose_current_mg}mg "
        f"baseline={meta.steroid_dose_baseline_mg}mg "
        f"threshold={threshold:.2f}mg — "
        f"{'INCREASE DETECTED' if increased else 'no increase'}."
    )
    return increased, note


# ── CR confirmation check ─────────────────────────────────────────────────────

def _is_cr_confirmed(
    prior_cr_provisional_date: Optional[str],
    current_scan_date: str,
) -> bool:
    """
    RANO 2010 §2.1 — CR_confirmed requires a prior CR_provisional scan
    at least 4 weeks (28 days) before the current scan.
    """
    if prior_cr_provisional_date is None:
        return False
    try:
        d_prior   = date.fromisoformat(prior_cr_provisional_date)
        d_current = date.fromisoformat(current_scan_date)
        return (d_current - d_prior) >= timedelta(weeks=settings.cr_confirmation_weeks)
    except ValueError:
        logger.warning(
            "CR confirmation date parse failed: prior=%s current=%s",
            prior_cr_provisional_date, current_scan_date,
        )
        return False


# ── Main classification function ──────────────────────────────────────────────

def run_rano_classification(
    current:    Agent1Output,
    baseline:   Optional[Agent1Output]      = None,
    baseline_scan_id: Optional[str]         = None,
    baseline_type: Optional[str]            = None,
    meta:       ClinicalMetadata            = ClinicalMetadata(),
    prior_cr_provisional_date: Optional[str] = None,
    nadir_bp_mm2: float = 0.0,
) -> Agent2Output:
    """
    Classify RANO treatment response for the current scan.

    Parameters
    ----------
    current:
        Agent 1 output for the scan being classified.
    baseline:
        Agent 1 output for the confirmed baseline scan.
        None → Agent 2 is skipped (first scan or no confirmed baseline).
    baseline_scan_id:
        scan_id of the baseline scan (stored in output for audit).
    baseline_type:
        'post_op' or 'nadir' — must be confirmed by clinician.
        'unconfirmed' or None → Agent 2 is skipped.
    meta:
        Clinical metadata submitted by doctor at upload time.
    prior_cr_provisional_date:
        scan_date of the most recent prior CR_provisional scan for this
        patient, if any. Used to determine CR_confirmed eligibility.
    """

    # ── Step 1: Check baseline exists and is confirmed ─────────────────
    if baseline is None:
        return _skipped(
            "No confirmed baseline scan exists for this patient. "
            "Upload a post-operative scan and set baseline_type='post_op'.",
            current,
        )

    if baseline_type not in (BaselineType.POST_OP.value, BaselineType.NADIR.value):
        return _skipped(
            f"Baseline type '{baseline_type}' is not confirmed. "
            "A clinician must set baseline_type to 'post_op' or 'nadir'.",
            current,
        )

    # ── Step 2: Validate baseline is usable ───────────────────────────
    # RANO spec requires at least one measurable lesion at baseline
    if (
        baseline.measurable_lesion_count is not None
        and baseline.measurable_lesion_count == 0
    ):
        return _skipped(
            "Baseline scan has zero measurable lesions. "
            "RANO bidimensional measurement requires ≥1 measurable lesion at baseline.",
            current,
        )

    bp_baseline = baseline.bidimensional_product_mm2
    bp_current  = current.bidimensional_product_mm2

    # Zero baseline product makes % change undefined — cannot classify
    if bp_baseline < 1e-9:
        return _skipped(
            f"Baseline bidimensional product is effectively zero "
            f"({bp_baseline:.4f} mm²). % change is undefined. "
            "This scan cannot serve as a RANO measurement baseline.",
            current,
        )

    # ── Step 3: Compute % change ──────────────────────────────────────
    pct_change = ((bp_current - bp_baseline) / bp_baseline) * 100.0
    reasoning_parts: list[str] = [
        f"Baseline BP={bp_baseline:.2f}mm² ({baseline_type}) | "
        f"Current BP={bp_current:.2f}mm² | "
        f"Change={pct_change:+.1f}%."
    ]

    # ── Step 4: Steroid rule ──────────────────────────────────────────
    # RANO 2010 §2.1-2.2 — steroid increase ALONE blocks CR and PR
    steroid_increase, steroid_note = _compute_steroid_increase(meta)
    reasoning_parts.append(steroid_note)

    # ── Step 5: Build confidence warning ─────────────────────────────
    confidence_warning: Optional[str] = None
    if current.low_confidence_flag:
        confidence_warning = (
            f"Low segmentation confidence: {current.low_confidence_reason or 'see Agent 1 output'}. "
            "RANO classification should be interpreted with caution."
        )

    # ── Step 6: RANO decision tree (pure rules — no ML) ───────────────

    # PD Rule A — RANO 2010 §2.1: new lesion = immediate PD
    if meta.new_lesion_detected:
        reasoning_parts.append("PD: new lesion detected — immediate progressive disease per RANO 2010 §2.1.")
        return _build_output(
            rano_class="PD",
            pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
            baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
            baseline_type=baseline_type, meta=meta,
            steroid_increase=steroid_increase,
            pseudoprogression_flag=_check_pseudoprogression(meta, reasoning_parts, bp_current=bp_current, nadir_bp=nadir_bp_mm2),
            low_confidence_flag=current.low_confidence_flag,
            reasoning=" ".join(reasoning_parts),
            confidence_warning=confidence_warning,
        )

    # PD Rule B — RANO 2010 §2.1: ≥25% increase from baseline
    if pct_change >= 25.0:
        reasoning_parts.append(
            f"PD: bidimensional product increased ≥25% ({pct_change:+.1f}%) "
            "from baseline per RANO 2010 §2.1."
        )
        return _build_output(
            rano_class="PD",
            pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
            baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
            baseline_type=baseline_type, meta=meta,
            steroid_increase=steroid_increase,
            pseudoprogression_flag=_check_pseudoprogression(meta, reasoning_parts, bp_current=bp_current, nadir_bp=nadir_bp_mm2),
            low_confidence_flag=current.low_confidence_flag,
            reasoning=" ".join(reasoning_parts),
            confidence_warning=confidence_warning,
        )

    # PD Rule C — RANO 2010 §2.2: steroid increase + ET present + clinical deterioration
    # All three conditions required — steroid increase alone does NOT trigger this PD rule
    et_present = current.et_volume_ml >= settings.cr_et_volume_threshold_ml
    if steroid_increase and et_present and meta.clinical_deterioration:
        reasoning_parts.append(
            "PD: steroid increase + ET present + clinical deterioration "
            "— all three conditions met per RANO 2010 §2.2."
        )
        return _build_output(
            rano_class="PD",
            pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
            baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
            baseline_type=baseline_type, meta=meta,
            steroid_increase=steroid_increase,
            pseudoprogression_flag=_check_pseudoprogression(meta, reasoning_parts, bp_current=bp_current, nadir_bp=nadir_bp_mm2),
            low_confidence_flag=current.low_confidence_flag,
            reasoning=" ".join(reasoning_parts),
            confidence_warning=confidence_warning,
        )

    # CR check — RANO 2010 §2.1
    # Requires: ET volume < 0.1ml AND no steroid increase AND no new lesion
    # Steroid increase ALONE blocks CR regardless of measurements
    if current.et_volume_ml < settings.cr_et_volume_threshold_ml and not steroid_increase:
        if _is_cr_confirmed(prior_cr_provisional_date, current.scan_date):
            rano_class = "CR_confirmed"
            reasoning_parts.append(
                f"CR_confirmed: ET volume={current.et_volume_ml:.4f}ml (<0.1ml threshold), "
                f"no steroid increase, confirmatory scan ≥{settings.cr_confirmation_weeks} weeks "
                f"after CR_provisional on {prior_cr_provisional_date}. RANO 2010 §2.1."
            )
        else:
            rano_class = "CR_provisional"
            reasoning_parts.append(
                f"CR_provisional: ET volume={current.et_volume_ml:.4f}ml (<0.1ml threshold), "
                "no steroid increase. A confirmatory scan ≥4 weeks later is required "
                "before CR_confirmed can be assigned. RANO 2010 §2.1."
            )
        return _build_output(
            rano_class=rano_class,
            pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
            baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
            baseline_type=baseline_type, meta=meta,
            steroid_increase=steroid_increase,
            pseudoprogression_flag=False,
            low_confidence_flag=current.low_confidence_flag,
            reasoning=" ".join(reasoning_parts),
            confidence_warning=confidence_warning,
        )

    # PR check — RANO 2010 §2.1
    # Requires: ≤-50% change AND no steroid increase AND no new lesion
    # Steroid increase ALONE blocks PR regardless of measurements
    if pct_change <= -50.0 and not steroid_increase:
        reasoning_parts.append(
            f"PR: bidimensional product decreased ≥50% ({pct_change:+.1f}%) "
            "from baseline, no steroid increase. RANO 2010 §2.1."
        )
        return _build_output(
            rano_class="PR",
            pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
            baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
            baseline_type=baseline_type, meta=meta,
            steroid_increase=steroid_increase,
            pseudoprogression_flag=False,
            low_confidence_flag=current.low_confidence_flag,
            reasoning=" ".join(reasoning_parts),
            confidence_warning=confidence_warning,
        )

    # PR blocked by steroid increase — note it explicitly
    if pct_change <= -50.0 and steroid_increase:
        reasoning_parts.append(
            f"SD (PR blocked): bidimensional product decreased ≥50% ({pct_change:+.1f}%) "
            "but steroid increase detected. RANO 2010 §2.1-2.2: steroid increase alone "
            "blocks PR assignment — classified as SD."
        )
        return _build_output(
            rano_class="SD",
            pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
            baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
            baseline_type=baseline_type, meta=meta,
            steroid_increase=steroid_increase,
            pseudoprogression_flag=False,
            low_confidence_flag=current.low_confidence_flag,
            reasoning=" ".join(reasoning_parts),
            confidence_warning=confidence_warning,
        )

    # SD — all other cases
    reasoning_parts.append(
        f"SD: change of {pct_change:+.1f}% does not meet PD (≥+25%) "
        "or PR (≤-50%) thresholds. RANO 2010 §2.1."
    )
    return _build_output(
        rano_class="SD",
        pct=pct_change, bp_baseline=bp_baseline, bp_current=bp_current,
        baseline_scan_id=baseline_scan_id, baseline_date=baseline.scan_date,
        baseline_type=baseline_type, meta=meta,
        steroid_increase=steroid_increase,
        pseudoprogression_flag=False,
        low_confidence_flag=current.low_confidence_flag,
        reasoning=" ".join(reasoning_parts),
        confidence_warning=confidence_warning,
    )


# ── Internal builders ─────────────────────────────────────────────────────────

def _check_pseudoprogression(
    meta: ClinicalMetadata,
    reasoning_parts: list[str],
    bp_current: float = 0.0,
    nadir_bp: float = 0.0,
) -> bool:
    """
    RANO 2010 S2.2 / pseudoprogression literature.
    Flags PP when apparent progression occurs within 24 weeks of RT completion.
    Two triggers:
      1. RANO=PD AND within RT window (original logic)
      2. Change from nadir >=25% AND within RT window (catches SD that is actually PP)
    This is NOT an automatic override - it is a flag only.
    """
    within_window = (
        meta.weeks_since_rt_completion is not None
        and meta.weeks_since_rt_completion <= settings.pseudoprogression_rt_weeks
    )
    if not within_window:
        return False

    nadir_jump_pct = (
        ((bp_current - nadir_bp) / nadir_bp) * 100.0
        if nadir_bp > 1e-9 and bp_current > nadir_bp
        else 0.0
    )
    nadir_jump = nadir_jump_pct >= 25.0

    if nadir_jump or bp_current > 0:
        mgmt = getattr(meta, "mgmt_status", None) or "not provided"
        idh  = getattr(meta, "idh_status",  None) or "not provided"
        nadir_note = (
            f" Change from nadir: +{nadir_jump_pct:.1f}%."
            if nadir_bp > 1e-9 else ""
        )
        reasoning_parts.append(
            f"PSEUDOPROGRESSION FLAG: Apparent progression "
            f"{meta.weeks_since_rt_completion} weeks after RT completion "
            f"(within {settings.pseudoprogression_rt_weeks}-week window).{nadir_note} "
            f"MGMT: {mgmt}. IDH: {idh}. Clinician review required - "
            "this may represent treatment effect rather than true progression."
        )
        return True
    return False


def _build_output(
    rano_class: str,
    pct: float,
    bp_baseline: float,
    bp_current: float,
    baseline_scan_id: Optional[str],
    baseline_date: str,
    baseline_type: Optional[str],
    meta: ClinicalMetadata,
    steroid_increase: bool,
    pseudoprogression_flag: bool,
    low_confidence_flag: bool,
    reasoning: str,
    confidence_warning: Optional[str],
   
   
) -> Agent2Output:
    return Agent2Output(
        skipped=False,
        skip_reason=None,
        rano_class=rano_class,
        baseline_bidimensional_product_mm2=bp_baseline,
        current_bidimensional_product_mm2=bp_current,
        pct_change_from_baseline=pct,
        baseline_scan_id=baseline_scan_id,
        baseline_date=baseline_date,
        baseline_type=baseline_type,
        steroid_increase=steroid_increase,
        new_lesion_detected=meta.new_lesion_detected,
        clinical_deterioration=meta.clinical_deterioration,
        weeks_since_rt_completion=meta.weeks_since_rt_completion,
        pseudoprogression_flag=pseudoprogression_flag,
        low_confidence_flag=low_confidence_flag,
        reasoning=reasoning,
        confidence_warning=confidence_warning,
        mgmt_status=getattr(meta, 'mgmt_status', None),
        idh_status=getattr(meta, 'idh_status', None),
    )
