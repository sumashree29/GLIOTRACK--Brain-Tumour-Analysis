"""
Pipeline conductor — chains Agents 1-5.
Polling: 15 s interval / 80 attempts (LOCKED by spec).
Idempotency: (patient_id, scan_date) duplicate returns cached result.

Agent 2 — wired with baseline lookup, clinical metadata, skip logic,
           CR_confirmed prior scan check.
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.agents.rano_agent import run_rano_classification
from app.agents.longitudinal_agent import run_longitudinal_analysis, Agent3Output
from app.agents.clinical_rag_agent import run_clinical_rag, Agent4Output
from app.agents.report_agent import run_report_agent, Agent5Output
from app.database.crud import (
    get_scans_for_patient, update_scan_status,
    get_agent1_output_by_scan_id, get_agent2_output_by_scan_id,
    get_report_by_scan_id, create_report_record,
    save_agent1_output,
    upsert_agent2_output, upsert_agent3_output, upsert_agent4_output,
    get_baseline_scan_for_patient, get_clinical_metadata,
    get_prior_cr_provisional_date,
    set_scan_as_baseline,
)
from app.models.scan import Agent1Output, Agent2Output, ClinicalMetadata, ScanStatus
from app.services.modal_client import submit_segmentation_job, poll_job_result

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S   = 15    # LOCKED by spec
_POLL_MAX_ATTEMPTS = 80    # LOCKED by spec (80 × 15s = 20 min)
_BP_RATIO_ALERT    = 10.0
_PCT_CHANGE_CAP    = 300.0


class OrchestratorError(RuntimeError):
    def __init__(self, stage: str, message: str):
        self.stage   = stage
        self.message = message
        super().__init__(f"[{stage}] {message}")


@dataclass
class PipelineResult:
    scan_id: str; patient_id: str; scan_date: str
    a1: Agent1Output; a2: Agent2Output; a3: Agent3Output
    a4: Agent4Output; a5: Agent5Output
    idempotent_hit: bool = False


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_idempotency(patient_id: str, scan_date: str, doctor_email: str) -> Optional[str]:
    for s in get_scans_for_patient(patient_id, doctor_email=doctor_email):
        if s.scan_date == scan_date and s.status == ScanStatus.REPORT_READY:
            return s.scan_id
    return None


def _check_numerical_diff(new_bp: float, prev_bp: Optional[float], scan_id: str) -> None:
    if prev_bp is None or prev_bp < 1e-6:
        return
    ratio = new_bp / prev_bp
    if ratio > _BP_RATIO_ALERT or ratio < (1.0 / _BP_RATIO_ALERT):
        logger.warning(
            "Numerical diff guard | scan_id=%s prev=%.1f new=%.1f ratio=%.2f",
            scan_id, prev_bp, new_bp, ratio,
        )


def _check_pct_change(pct: Optional[float], scan_id: str) -> None:
    if pct is not None and abs(pct) > _PCT_CHANGE_CAP:
        logger.warning("Pct-change guard | scan_id=%s pct=%.1f", scan_id, pct)


async def _poll_agent1(scan_id: str, job_id: str) -> Agent1Output:
    for attempt in range(1, _POLL_MAX_ATTEMPTS + 1):
        result = poll_job_result(job_id)
        if result.status == "completed":
            return result.agent1_output
        if result.status == "failed":
            raise OrchestratorError("Agent1", f"Worker failed: {result.error}")
        if attempt < _POLL_MAX_ATTEMPTS:
            logger.debug("Polling A1 | attempt=%d/%d", attempt, _POLL_MAX_ATTEMPTS)
            await asyncio.sleep(_POLL_INTERVAL_S)
        else:
            raise OrchestratorError(
                "Agent1",
                f"Timed out after {_POLL_MAX_ATTEMPTS * _POLL_INTERVAL_S}s",
            )
    raise OrchestratorError("Agent1", "Unexpected loop exit")


def _get_prior_scans(
    patient_id: str,
    exclude_id: str,
    doctor_email: str,
    current_scan_date: str,
):
    return sorted(
        [
            s for s in get_scans_for_patient(patient_id, doctor_email=doctor_email)
            if (
                s.scan_id != exclude_id
                and s.status == ScanStatus.REPORT_READY
                and s.scan_date < current_scan_date
            )
        ],
        key=lambda s: s.scan_date,
    )


async def run_pipeline(
    scan_id:       str,
    patient_id:    str,
    scan_date:     str,
    dicom_r2_keys: list[str],
    doctor_email:  str = "",
) -> PipelineResult:

    # ── Step 0: Idempotency ───────────────────────────────────────────
    existing = _check_idempotency(patient_id, scan_date, doctor_email)
    if existing:
        return await _cached_result(existing, patient_id, scan_date)

    # ── Agent 1 — Segmentation ────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.SEGMENTATION_RUNNING, _ts())
    try:
        job_id = submit_segmentation_job(
            scan_id=scan_id, patient_id=patient_id,
            dicom_r2_keys=dicom_r2_keys, scan_date=scan_date,
        )
        a1 = await _poll_agent1(scan_id, job_id)
    except OrchestratorError:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent1")
        raise
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent1")
        raise OrchestratorError("Agent1", str(exc)) from exc

    save_agent1_output(a1)
    if get_baseline_scan_for_patient(patient_id, doctor_email) is None:
        set_scan_as_baseline(scan_id, "post_op", doctor_email)
        logger.info("Auto-baseline set | scan_id=%s patient_id=%s", scan_id, patient_id)
    update_scan_status(scan_id, ScanStatus.SEGMENTATION_COMPLETE, _ts())

    prior_scans = _get_prior_scans(patient_id, scan_id, doctor_email, scan_date)
    prior_a1 = get_agent1_output_by_scan_id(prior_scans[-1].scan_id) if prior_scans else None
    if prior_a1:
        _check_numerical_diff(a1.bidimensional_product_mm2, prior_a1.bidimensional_product_mm2, scan_id)

    # ── Agent 2 — RANO Classification ────────────────────────────────
    update_scan_status(scan_id, ScanStatus.RANO_RUNNING, _ts())
    try:
        # Look up confirmed baseline scan for this patient
        baseline_scan = get_baseline_scan_for_patient(patient_id, doctor_email)
        baseline_a1: Optional[Agent1Output] = None
        if baseline_scan is not None:
            baseline_a1 = get_agent1_output_by_scan_id(baseline_scan.scan_id)

        # Load clinical metadata submitted by doctor at upload time
        meta: ClinicalMetadata = get_clinical_metadata(scan_id)

        # Check for prior CR_provisional — needed for CR_confirmed logic
        # RANO 2010 §2.1: CR_confirmed requires second scan ≥4 weeks later
        prior_cr_date: Optional[str] = get_prior_cr_provisional_date(
            patient_id, doctor_email, current_scan_id=scan_id
        )

        prior_scans_pp = _get_prior_scans(patient_id, scan_id, doctor_email, scan_date)
        prior_a1_pp = [get_agent1_output_by_scan_id(s.scan_id) for s in prior_scans_pp]
        all_bp = [a.bidimensional_product_mm2 for a in prior_a1_pp if a is not None]
        nadir_bp = min(all_bp) if all_bp else 0.0
        a2 = run_rano_classification(
            current=a1,
            baseline=baseline_a1,
            baseline_scan_id=baseline_scan.scan_id if baseline_scan else None,
            baseline_type=baseline_scan.baseline_type if baseline_scan else None,
            meta=meta,
            prior_cr_provisional_date=prior_cr_date,
            nadir_bp_mm2=nadir_bp,
        )

        if not a2.skipped:
            _check_pct_change(a2.pct_change_from_baseline, scan_id)

        upsert_agent2_output(scan_id, a2)

        if a2.skipped:
            logger.info(
                "Agent 2 skipped | scan_id=%s reason=%s", scan_id, a2.skip_reason
            )
        else:
            logger.info(
                "Agent 2 complete | scan_id=%s rano=%s pct=%s",
                scan_id, a2.rano_class, a2.pct_change_from_baseline,
            )

    except OrchestratorError:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent2")
        raise
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent2")
        raise OrchestratorError("Agent2", str(exc)) from exc
    update_scan_status(scan_id, ScanStatus.RANO_COMPLETE, _ts())

    # ── Agent 3 — Longitudinal ────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.LONGITUDINAL_RUNNING, _ts())
    try:
        prior_a1_outputs = [get_agent1_output_by_scan_id(s.scan_id) for s in prior_scans]
        a1_series = [a for a in prior_a1_outputs if a is not None] + [a1]
        a2_series = [
            a for a in [get_agent2_output_by_scan_id(s.scan_id) for s in prior_scans]
            if a is not None
        ] + [a2]
        a3 = run_longitudinal_analysis(a1_series, a2_series)
        upsert_agent3_output(scan_id, a3)
    except OrchestratorError:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent3")
        raise
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent3")
        raise OrchestratorError("Agent3", str(exc)) from exc
    update_scan_status(scan_id, ScanStatus.LONGITUDINAL_COMPLETE, _ts())

    # ── Agent 4 — RAG (non-fatal) ─────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.RAG_RUNNING, _ts())
    try:
        a4 = run_clinical_rag(a2, a3, a1)
        upsert_agent4_output(scan_id, a4)
    except Exception as exc:
        logger.warning("Agent 4 unexpected raise: %s", exc)
        from app.agents.clinical_rag_agent import _unavailable_output
        a4 = _unavailable_output(failure_reason=f"Unexpected: {exc}", query_used=None)
    update_scan_status(scan_id, ScanStatus.RAG_COMPLETE, _ts())

    # ── Agent 5 — Report ──────────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.REPORT_RUNNING, _ts())
    try:
        a5 = run_report_agent(
            scan_id=scan_id, patient_id=patient_id,
            scan_date=scan_date, a1=a1, a2=a2, a3=a3, a4=a4,
        )
        create_report_record(
            scan_id=scan_id, r2_key=a5.r2_key,
            generation_ts=a5.generation_ts, sections=a5.sections,
            prompt_tokens=a5.prompt_tokens,
            completion_tokens=a5.completion_tokens,
        )
    except OrchestratorError:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent5")
        raise
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent5")
        raise OrchestratorError("Agent5", str(exc)) from exc

    update_scan_status(scan_id, ScanStatus.REPORT_READY, _ts())
    logger.info("Pipeline complete | scan_id=%s r2_key=%s", scan_id, a5.r2_key)

    return PipelineResult(
        scan_id=scan_id, patient_id=patient_id, scan_date=scan_date,
        a1=a1, a2=a2, a3=a3, a4=a4, a5=a5,
    )
async def _run_agents_2_to_5(
    scan_id: str,
    patient_id: str,
    scan_date: str,
    doctor_email: str,
    a1: Agent1Output,
) -> None:
    if get_baseline_scan_for_patient(patient_id, doctor_email) is None:
        set_scan_as_baseline(scan_id, "post_op", doctor_email)
        logger.info("Auto-baseline set (resume) | scan_id=%s patient_id=%s", scan_id, patient_id)

    """
    Run Agents 2-5 using an existing Agent 1 result.
    Called by the /resume endpoint — no Modal trigger, zero GPU cost.
    """
    # ── Agent 2 ───────────────────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.RANO_RUNNING, _ts())
    try:
        baseline_scan = get_baseline_scan_for_patient(patient_id, doctor_email)
        baseline_a1: Optional[Agent1Output] = None
        if baseline_scan is not None:
            baseline_a1 = get_agent1_output_by_scan_id(baseline_scan.scan_id)

        meta = get_clinical_metadata(scan_id)
        prior_cr_date = get_prior_cr_provisional_date(
            patient_id, doctor_email, current_scan_id=scan_id
        )
        # Compute nadir BP from all prior scans for PP detection
        prior_scans_pp = _get_prior_scans(patient_id, scan_id, doctor_email, scan_date)
        prior_a1_pp = [get_agent1_output_by_scan_id(s.scan_id) for s in prior_scans_pp]
        all_bp = [a.bidimensional_product_mm2 for a in prior_a1_pp if a is not None]
        nadir_bp = min(all_bp) if all_bp else 0.0
        a2 = run_rano_classification(
            current=a1,
            baseline=baseline_a1,
            baseline_scan_id=baseline_scan.scan_id if baseline_scan else None,
            baseline_type=baseline_scan.baseline_type if baseline_scan else None,
            meta=meta,
            prior_cr_provisional_date=prior_cr_date,
            nadir_bp_mm2=nadir_bp,
        )
        upsert_agent2_output(scan_id, a2)
        logger.info("Resume Agent 2 %s | scan_id=%s",
                    "skipped: " + a2.skip_reason if a2.skipped else "rano=" + str(a2.rano_class),
                    scan_id)
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent2")
        raise OrchestratorError("Agent2", str(exc)) from exc
    update_scan_status(scan_id, ScanStatus.RANO_COMPLETE, _ts())

    # ── Agent 3 ───────────────────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.LONGITUDINAL_RUNNING, _ts())
    try:
        prior_scans = _get_prior_scans(patient_id, scan_id, doctor_email, scan_date)
        prior_a1_outputs = [get_agent1_output_by_scan_id(s.scan_id) for s in prior_scans]
        a1_series = [a for a in prior_a1_outputs if a is not None] + [a1]
        a2_series = [
            a for a in [get_agent2_output_by_scan_id(s.scan_id) for s in prior_scans]
            if a is not None
        ] + [a2]
        a3 = run_longitudinal_analysis(a1_series, a2_series)
        upsert_agent3_output(scan_id, a3)
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent3")
        raise OrchestratorError("Agent3", str(exc)) from exc
    update_scan_status(scan_id, ScanStatus.LONGITUDINAL_COMPLETE, _ts())

    # ── Agent 4 ───────────────────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.RAG_RUNNING, _ts())
    try:
        a4 = run_clinical_rag(a2, a3, a1)
        upsert_agent4_output(scan_id, a4)
    except Exception as exc:
        logger.warning("Agent 4 unexpected raise: %s", exc)
        from app.agents.clinical_rag_agent import _unavailable_output
        a4 = _unavailable_output(failure_reason=f"Unexpected: {exc}", query_used=None)
    update_scan_status(scan_id, ScanStatus.RAG_COMPLETE, _ts())

    # ── Agent 5 ───────────────────────────────────────────────────────
    update_scan_status(scan_id, ScanStatus.REPORT_RUNNING, _ts())
    try:
        a5 = run_report_agent(
            scan_id=scan_id, patient_id=patient_id,
            scan_date=scan_date, a1=a1, a2=a2, a3=a3, a4=a4,
        )
        create_report_record(
            scan_id=scan_id, r2_key=a5.r2_key,
            generation_ts=a5.generation_ts, sections=a5.sections,
            prompt_tokens=a5.prompt_tokens,
            completion_tokens=a5.completion_tokens,
        )
    except Exception as exc:
        update_scan_status(scan_id, ScanStatus.FAILED, _ts(), failed_stage="Agent5")
        raise OrchestratorError("Agent5", str(exc)) from exc

    update_scan_status(scan_id, ScanStatus.REPORT_READY, _ts())
    logger.info("Resume complete | scan_id=%s", scan_id)


async def _cached_result(scan_id: str, patient_id: str, scan_date: str) -> PipelineResult:
    """
    Load all saved agent outputs for a completed scan.
    Agent 2 falls back to a skipped output if no DB row exists
    (first scan — never had RANO classification run).
    """
    from app.agents.clinical_rag_agent import Agent4Output

    report = get_report_by_scan_id(scan_id)
    if report is None:
        raise OrchestratorError("Cache", f"Report row missing for scan_id={scan_id}")

    a1 = get_agent1_output_by_scan_id(scan_id)
    if a1 is None:
        raise OrchestratorError("Cache", f"Agent1 output missing for scan_id={scan_id}")

    # Agent 2 may legitimately be absent for the first scan — return skipped output
    a2 = get_agent2_output_by_scan_id(scan_id)
    if a2 is None:
        a2 = Agent2Output(
            skipped=True,
            skip_reason="No Agent 2 output stored — scan may be a first/baseline scan.",
            low_confidence_flag=a1.low_confidence_flag,
            reasoning="Cached result: no RANO classification available.",
        )

    a3 = await _load_agent3(scan_id)

    a4 = Agent4Output(
        rag_available=False, passages=[],
        failure_reason="Cached result — RAG not re-run", query_used=None,
    )

    from app.agents.report_agent import Agent5Output, ReportSections
    a5 = Agent5Output(
        scan_id=scan_id, patient_id=patient_id,
        r2_key=report.r2_key, sections=ReportSections(),
        generation_ts=report.generation_ts,
    )

    return PipelineResult(
        scan_id=scan_id, patient_id=patient_id, scan_date=scan_date,
        a1=a1, a2=a2, a3=a3, a4=a4, a5=a5, idempotent_hit=True,
    )


async def _load_agent3(scan_id: str) -> Agent3Output:
    """Load Agent3Output from DB with fallback to minimal valid object."""
    from app.database.supabase_client import get_supabase_client
    import json
    try:
        r = (
            get_supabase_client().table("agent3_outputs")
            .select("*").eq("scan_id", scan_id).execute()
        )
        if r.data:
            row = r.data[0]
            for k in ["trajectory_intervals", "inflection_points", "scan_dates"]:
                if isinstance(row.get(k), str):
                    row[k] = json.loads(row[k])
            filtered = {k: v for k, v in row.items() if k in Agent3Output.__dataclass_fields__}
            filtered.setdefault("rc_volumes", [])
            return Agent3Output(**filtered)
    except Exception as exc:
        logger.warning("Could not load Agent3 from DB for cached result: %s", exc)

    from app.database.crud import get_scan_by_id
    scan = get_scan_by_id(scan_id)
    fallback_date = scan.scan_date if scan else ""
    return Agent3Output(
        scan_dates=[fallback_date] if fallback_date else [],
        nadir_bp_mm2=0.0, nadir_scan_date=fallback_date,
        change_from_nadir_pct=0.0, overall_trend=None,
        inflection_points=[], trajectory_intervals=[],
        dissociation_flag=False, low_confidence_flag=False,
        rc_volumes=[],
    )