"""
Agent 5 — PDF Report Generation.

Architecture change:
  - LLM (Groq) used ONLY for Section 1 Clinical Summary (2-3 sentences).
  - All other sections are built directly from agent outputs — zero hallucination.
  - Section 2: structured measurements table (ReportLab Table).
  - Section 3: RANO result + verbatim agent2.reasoning.
  - Section 4: longitudinal timepoint table with nadir highlighted.
  - Section 5: actual Qdrant passage text verbatim — no LLM rewriting.
  - Section 6: spec-required caveats only.
"""
from __future__ import annotations
import io, logging, textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle,
)

from app.services.llm_service import call_llm, LLMServiceError
from app.services.storage import upload_bytes_to_r2

logger = logging.getLogger(__name__)

# ── Spec-required fixed strings ───────────────────────────────────────────────
_RAG_UNAVAILABLE = (
    "Clinical guideline context is unavailable for this report. "
    "The knowledge base could not be queried at the time of generation. "
    "Clinicians should consult current RANO / iRANO guidelines directly."
)
_DISSOCIATION_CAVEAT = (
    "NOTE — mRANO Dissociation Detected: The RANO classification indicates "
    "Progressive Disease, yet the enhancing tumour volume remains within 25% of "
    "the nadir. This pattern warrants multidisciplinary review before treatment modification."
)
_CR_PROVISIONAL_NOTICE = (
    "IMPORTANT: This scan meets criteria for Complete Response (Provisional). "
    "Confirmatory imaging ≥4 weeks is required before upgrading to CR_confirmed."
)
_LOW_CONF_CAVEAT = (
    "⚠ Measurement uncertainty flag raised. One or more diameters approach the "
    "resolution limit. Bidimensional product error may reach ±25% near the 10mm RANO threshold."
)
_KNOWN_LIMITATIONS = [
    "L1 — Steroid logic does not incorporate neurological status or performance score.",
    "L2 — Pseudoprogression window: 24 weeks post-RT. MGMT and IDH status incorporated when provided.",
    "L3 — Diameter measurement is strictly axial per RANO spec. Oblique tumours may show small inaccuracy.",
    "L4 — T2/FLAIR non-enhancing progression not tracked. Relevant for low-grade glioma.",
    "L5 — BGE-small (dim=384) embedding model used due to memory constraints on free tier.",
    "L8 — ±10% diameter error can approach ±25% RANO threshold in borderline cases. Confidence flag raised for these.",
    "L9 — Intra-patient co-registration is SimpleITK rigid only. Slight residual misalignment possible.",
    "L10 — CR confirmation requires a second scan ≥4 weeks later. Without it, CR remains CR_provisional.",
]

_RANO_COLOURS = {
    "CR_confirmed":   colors.HexColor("#1a7a4a"),
    "CR_provisional": colors.HexColor("#2e6da4"),
    "PR":             colors.HexColor("#2e6da4"),
    "SD":             colors.HexColor("#7a6a1a"),
    "PD":             colors.HexColor("#a43a2e"),
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ReportSections:
    clinical_summary:        str = ""
    segmentation_findings:   str = ""
    rano_classification:     str = ""
    longitudinal_trajectory: str = ""
    guideline_context:       str = ""
    limitations_caveats:     str = ""


@dataclass
class Agent5Output:
    scan_id: str
    patient_id: str
    r2_key: str
    sections: ReportSections
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_latency_ms: float = 0.0
    generation_ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitise_id(value: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:64]


def _fmt_date(d: str) -> str:
    """Format ISO date string to dd MMM yyyy for display."""
    try:
        from datetime import date
        return date.fromisoformat(d).strftime("%d %b %Y")
    except Exception:
        return d


def _pct_str(pct: Optional[float]) -> str:
    if pct is None:
        return "N/A"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


# ── Section 1 — Clinical Summary (LLM, tightly constrained) ──────────────────

_SUMMARY_SYSTEM = textwrap.dedent("""
    You are a neuro-oncology reporting assistant.
    Write exactly 2-3 sentences summarising the clinical picture for a doctor.
    Rules:
    - Use only the data provided. Do not invent values.
    - Do not mention missing data or what is unavailable.
    - Do not repeat individual numbers — synthesise the clinical meaning.
    - Plain clinical English. No bullet points. No headings.
    - Output ONLY the 2-3 sentences. Nothing else.
""").strip()


def _build_summary_prompt(patient_id, scan_date, a1, a2, a3) -> str:
    rano = getattr(a2, "rano_class", None) or "not classified"
    pct  = _pct_str(getattr(a2, "pct_change_from_baseline", None))
    trend = getattr(a3, "overall_trend", None) or "single timepoint"
    n_tp  = len(getattr(a3, "scan_dates", [])) if a3 else 1
    return (
        f"Patient: {patient_id} | Scan date: {scan_date}\n"
        f"RANO: {rano} | Change from baseline: {pct}\n"
        f"ET volume: {a1.et_volume_ml:.2f} mL | WT volume: {a1.wt_volume_ml:.2f} mL\n"
        f"Longitudinal trend: {trend} over {n_tp} timepoint(s)\n"
        f"Low confidence: {a1.low_confidence_flag}"
    )


def _get_summary(patient_id, scan_date, a1, a2, a3) -> tuple[str, int, int, float]:
    """Returns (text, prompt_tokens, completion_tokens, latency_ms)."""
    try:
        prompt = _build_summary_prompt(patient_id, scan_date, a1, a2, a3)
        resp   = call_llm(_SUMMARY_SYSTEM, prompt)
        return resp.content.strip(), resp.prompt_tokens, resp.completion_tokens, resp.latency_ms
    except LLMServiceError as exc:
        logger.warning("LLM unavailable for summary: %s", exc)
        rano  = getattr(a2, "rano_class", "not classified") or "not classified"
        pct   = _pct_str(getattr(a2, "pct_change_from_baseline", None))
        return (
            f"Brain tumour assessment for patient {patient_id} on {scan_date}. "
            f"RANO classification: {rano} (change from baseline: {pct}). "
            f"Enhancing tumour volume: {a1.et_volume_ml:.2f} mL. "
            "Full clinical interpretation requires qualified radiologist review.",
            0, 0, 0.0,
        )


# ── ReportLab style helpers ───────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    return {
        "title":    ParagraphStyle("Tt", parent=base["Title"],
                                   fontSize=15, spaceAfter=4),
        "head":     ParagraphStyle("Hd", parent=base["Heading2"],
                                   fontSize=11, spaceBefore=14, spaceAfter=4,
                                   textColor=colors.HexColor("#1a3a5c")),
        "subhead":  ParagraphStyle("Sh", parent=base["Normal"],
                                   fontSize=9, spaceBefore=6, spaceAfter=2,
                                   textColor=colors.HexColor("#1a3a5c"),
                                   fontName="Helvetica-Bold"),
        "body":     ParagraphStyle("Bd", parent=base["Normal"],
                                   fontSize=9, leading=14),
        "small":    ParagraphStyle("Sm", parent=base["Normal"],
                                   fontSize=8, leading=12,
                                   textColor=colors.HexColor("#555555")),
        "meta":     ParagraphStyle("Mt", parent=base["Normal"],
                                   fontSize=7.5, textColor=colors.grey,
                                   spaceAfter=3),
        "disc":     ParagraphStyle("Dc", parent=base["Normal"],
                                   fontSize=7.5, textColor=colors.red,
                                   spaceAfter=8),
        "label":    ParagraphStyle("Lb", parent=base["Normal"],
                                   fontSize=8, textColor=colors.HexColor("#777777"),
                                   fontName="Helvetica-Bold"),
        "passage":  ParagraphStyle("Ps", parent=base["Normal"],
                                   fontSize=8.5, leading=13,
                                   textColor=colors.HexColor("#333333")),
        "source":   ParagraphStyle("Sr", parent=base["Normal"],
                                   fontSize=9, fontName="Helvetica-Bold",
                                   textColor=colors.HexColor("#1a3a5c")),
    }


def _hr(thickness=0.4, color=colors.lightgrey):
    return HRFlowable(width="100%", thickness=thickness, color=color)


def _table(data, col_widths, row_styles=None):
    """Build a styled ReportLab table."""
    t = Table(data, colWidths=col_widths)
    base_style = [
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("LEADING",       (0, 0), (-1, -1), 12),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1),
        [colors.HexColor("#f7f9fc"), colors.white]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 0), (0, -1), colors.HexColor("#444444")),
    ]
    if row_styles:
        base_style.extend(row_styles)
    t.setStyle(TableStyle(base_style))
    return t


# ── Section builders ──────────────────────────────────────────────────────────

def _build_section2(a1, s, story):
    """Measurements table — no LLM."""
    story.append(Paragraph("2. Segmentation Findings", s["head"]))
    story.append(_hr())

    conf_text = "LOW ⚠" if a1.low_confidence_flag else "OK"
    conf_color = colors.HexColor("#a43a2e") if a1.low_confidence_flag else colors.HexColor("#1a7a4a")

    data = [
        ["Measurement", "Value"],
        ["Enhancing Tumour (ET) Volume", f"{a1.et_volume_ml:.2f} mL"],
        ["Tumour Core (TC) Volume",      f"{a1.tc_volume_ml:.2f} mL"],
        ["Whole Tumour (WT) Volume",     f"{a1.wt_volume_ml:.2f} mL"],
        ["Resection Cavity (RC) Volume", f"{getattr(a1, 'rc_volume_ml', 0.0):.2f} mL"],
        ["Longest Axial Diameter",       f"{a1.et_diameter1_mm:.1f} mm"],
        ["Perpendicular Diameter",       f"{a1.et_diameter2_mm:.1f} mm"],
        ["Bidimensional Product (BP)",   f"{a1.bidimensional_product_mm2:.1f} mm²"],
        ["Segmentation Confidence",      conf_text],
    ]

    row_styles = [
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 9),
        ("TEXTCOLOR",   (1, 8), (1, 8),  conf_color),
        ("FONTNAME",    (1, 8), (1, 8),  "Helvetica-Bold"),
    ]

    page_w = A4[0] - 5 * cm
    t = _table(data, [page_w * 0.55, page_w * 0.45], row_styles)
    story.append(t)

    if a1.low_confidence_flag and a1.low_confidence_reason:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"⚠ Confidence note: {a1.low_confidence_reason}", s["small"]
        ))


def _build_section3(a2, story, s):
    """RANO classification — verbatim agent2.reasoning, no LLM."""
    story.append(Paragraph("3. RANO Classification & Rationale", s["head"]))
    story.append(_hr())

    rano_class = getattr(a2, "rano_class", None) or "Not classified"
    pct        = getattr(a2, "pct_change_from_baseline", None)
    reasoning  = getattr(a2, "reasoning", "") or ""
    skipped    = getattr(a2, "skipped", False)
    mgmt = getattr(a2, 'mgmt_status', None) or 'not provided'
    

    rano_color = _RANO_COLOURS.get(str(rano_class), colors.HexColor("#555555"))

    # RANO result box
    result_data = [
        ["RANO Classification", "Change from Baseline", "Baseline Type"],
        [
            str(rano_class),
            _pct_str(pct),
            str(getattr(a2, "baseline_type", "—") or "—"),
        ],
    ]
    row_styles = [
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 9),
        ("FONTSIZE",    (0, 1), (0, 1),  11),
        ("FONTNAME",    (0, 1), (0, 1),  "Helvetica-Bold"),
        ("TEXTCOLOR",   (0, 1), (0, 1),  rano_color),
        ("FONTSIZE",    (1, 1), (1, 1),  11),
        ("FONTNAME",    (1, 1), (1, 1),  "Helvetica-Bold"),
    ]
    page_w = A4[0] - 5 * cm
    story.append(_table(result_data, [page_w * 0.4, page_w * 0.3, page_w * 0.3], row_styles))

    # Clinical flags row
    flags_data = [
        ["New Lesion Detected", "Steroid Increase", "Clinical Deterioration"],
        [
            "Yes ⚠" if getattr(a2, "new_lesion_detected", False) else "No",
            "Yes ⚠" if getattr(a2, "steroid_increase",    False) else "No",
            "Yes ⚠" if getattr(a2, "clinical_deterioration", False) else "No",
        ],
    ]
    flag_row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf2")),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
    ]
    story.append(Spacer(1, 0.15 * cm))
    story.append(_table(flags_data, [page_w / 3, page_w / 3, page_w / 3], flag_row_styles))

    # Pseudoprogression flag
    if getattr(a2, "pseudoprogression_flag", False):
        story.append(Spacer(1, 0.2 * cm))
        mgmt = getattr(a2, 'mgmt_status', None) or 'not provided'
        idh  = getattr(a2, 'idh_status',  None) or 'not provided'
        story.append(Paragraph(
            f"⚠ PSEUDOPROGRESSION FLAG: PD detected within "
            f"{getattr(a2, 'weeks_since_rt_completion', '?')} weeks of RT completion. "
            f"MGMT: {mgmt}. IDH: {idh}. "
            "Clinician review required before treatment modification.",
            s["small"],
        ))

    # CR notices
    if str(rano_class) == "CR_provisional":
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(_CR_PROVISIONAL_NOTICE, s["small"]))

    # Reasoning — verbatim from Agent 2
    if reasoning and not skipped:
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("Classification Reasoning", s["subhead"]))
        story.append(Paragraph(reasoning, s["body"]))
    elif skipped:
        skip_reason = getattr(a2, "skip_reason", "No baseline confirmed.")
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"RANO classification skipped: {skip_reason}", s["small"]
        ))


def _build_section4(a3, story, s):
    """Longitudinal trajectory table — no LLM."""
    story.append(Paragraph("4. Longitudinal Trajectory", s["head"]))
    story.append(_hr())

    if a3 is None:
        story.append(Paragraph(
            "Longitudinal data unavailable — requires at least 2 timepoints.", s["body"]
        ))
        return

    scan_dates = getattr(a3, "scan_dates", []) or []
    intervals  = getattr(a3, "trajectory_intervals", []) or []
    nadir_date = getattr(a3, "nadir_scan_date", None) or ""
    nadir_bp   = getattr(a3, "nadir_bp_mm2", 0.0)
    n_tp       = len(scan_dates)

    # Summary row
    summary_data = [
        ["Overall Trend", "Timepoints", "Nadir BP", "Change from Nadir"],
        [
            str(getattr(a3, "overall_trend", "—") or "—").capitalize(),
            str(n_tp),
            f"{nadir_bp:.1f} mm²",
            _pct_str(getattr(a3, "change_from_nadir_pct", None)),
        ],
    ]
    page_w = A4[0] - 5 * cm
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 9),
    ]
    story.append(_table(
        summary_data,
        [page_w * 0.25, page_w * 0.15, page_w * 0.25, page_w * 0.35],
        row_styles,
    ))

    # Timepoint table if we have intervals
    if intervals:
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("Scan Timeline", s["subhead"]))

        tp_data = [["Scan Date", "BP (mm²)", "RC (mL)", "RANO", "Change", "Note"]]

        # First row = baseline (first scan)
        if scan_dates:
            first_date = scan_dates[0]
            note = "NADIR ★" if first_date == nadir_date else "Baseline"
            tp_data.append([
                _fmt_date(first_date), "—", "—", "Baseline (ref)", note,
            ])

        for iv in intervals:
            end_date = iv["end_date"] if isinstance(iv, dict) else iv.end_date
            bp_end   = iv["bp_end"]   if isinstance(iv, dict) else iv.bp_end
            pct_chg  = iv["pct_change"] if isinstance(iv, dict) else iv.pct_change
            rano_end = iv.get("rano_at_end") if isinstance(iv, dict) else getattr(iv, "rano_at_end", None)
            note     = "NADIR ★" if end_date == nadir_date else ""
            tp_data.append([
                _fmt_date(end_date),
                f"{bp_end:.1f}",
                str(rano_end or "—"),
                _pct_str(pct_chg),
                note,
                f"{iv.rc_volume_ml:.1f}"
            ])

        # Highlight nadir rows
        nadir_row_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf2")),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ]
        for i, row in enumerate(tp_data[1:], 1):
            note_val = row[4] if len(row) > 4 else ""
            if "NADIR" in str(note_val):
                nadir_row_styles.append(
                    ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#e8f4ea"))
                )
                nadir_row_styles.append(
                    ("FONTNAME", (0, i), (-1, i), "Helvetica-Bold")
                )

        story.append(_table(
            tp_data,
            [page_w*0.18, page_w*0.13, page_w*0.11, page_w*0.13, page_w*0.18, page_w*0.27],
            nadir_row_styles,
        ))

    # Dissociation flag
    if getattr(a3, "dissociation_flag", False):
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(_DISSOCIATION_CAVEAT, s["small"]))

    # Inflection points
    inflections = getattr(a3, "inflection_points", []) or []
    if inflections:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Trend Turning Points", s["subhead"]))
        for pt in inflections:
            story.append(Paragraph(f"• Trend changed on {_fmt_date(str(pt))}", s["body"]))


def _build_section5(a4, story, s):
    """Guideline context — verbatim Qdrant passages, no LLM."""
    story.append(Paragraph("5. Clinical Guideline Context", s["head"]))
    story.append(_hr())

    if not a4 or not getattr(a4, "rag_available", False):
        story.append(Paragraph(_RAG_UNAVAILABLE, s["body"]))
        return

    passages = getattr(a4, "passages", []) or []
    if not passages:
        story.append(Paragraph(_RAG_UNAVAILABLE, s["body"]))
        return

    story.append(Paragraph(
        "The following passages were retrieved from indexed clinical guidelines "
        "based on this scan's clinical profile. Context only — does not replace "
        "clinical judgement and is clearly separated from system measurements.",
        s["small"],
    ))
    story.append(Spacer(1, 0.2 * cm))

    for i, p in enumerate(passages):
        # Source header
        src  = p.source_document if hasattr(p, "source_document") else p.get("source_document", "")
        ver  = p.guideline_version if hasattr(p, "guideline_version") else p.get("guideline_version", "")
        year = p.publication_year if hasattr(p, "publication_year") else p.get("publication_year", "")
        score = p.score if hasattr(p, "score") else p.get("relevance_score", p.get("score", 0.0))
        text = p.passage_text if hasattr(p, "passage_text") else p.get("passage_text", "")

        pct_score = int(round(score * 100))

        story.append(Paragraph(
            f"{i+1}. {src}  —  {ver}  ({year})  —  {pct_score}% relevant",
            s["source"],
        ))

        # Passage text — truncate at 800 chars to keep PDF manageable
        display_text = text[:800].strip()
        if len(text) > 800:
            display_text += " […]"

        story.append(Paragraph(display_text, s["passage"]))

        if i < len(passages) - 1:
            story.append(_hr(0.3, colors.HexColor("#eeeeee")))
            story.append(Spacer(1, 0.1 * cm))


def _build_section6(a1, a3, story, s):
    """Limitations — spec-required list only, no LLM."""
    story.append(Paragraph("6. Limitations & Caveats", s["head"]))
    story.append(_hr())

    caveats = []
    if (a1 and a1.low_confidence_flag) or (a3 and getattr(a3, "low_confidence_flag", False)):
        caveats.append(_LOW_CONF_CAVEAT)

    for lim in _KNOWN_LIMITATIONS:
        caveats.append(lim)

    for c in caveats:
        story.append(Paragraph(f"• {c}", s["body"]))
        story.append(Spacer(1, 0.1 * cm))


# ── Main PDF renderer ─────────────────────────────────────────────────────────

def _render_pdf(
    summary_text: str,
    patient_id: str,
    scan_date: str,
    ts: str,
    a1, a2, a3, a4,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )
    s     = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Brain Tumour Response Assessment Report", s["title"]))
    story.append(Paragraph(
        f"Patient: {patient_id}  |  Scan: {scan_date}  |  "
        f"Generated: {ts[:19].replace('T', ' ')} UTC",
        s["meta"],
    ))
    story.append(_hr(1, colors.HexColor("#1a3a5c")))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "RESEARCH USE ONLY — NOT FOR CLINICAL DECISION-MAKING WITHOUT EXPERT REVIEW. "
        "De-identified data. AI-generated output. Must be verified by a qualified clinician.",
        s["disc"],
    ))

    # ── Section 1 — Clinical Summary (LLM, constrained) ──────────────────────
    story.append(Paragraph("1. Clinical Summary", s["head"]))
    story.append(_hr())
    story.append(Paragraph(summary_text or "(Summary unavailable.)", s["body"]))

    # ── Section 2 — Segmentation Findings ────────────────────────────────────
    if a1:
        story.append(Spacer(1, 0.1 * cm))
        _build_section2(a1, s, story)

    # ── Section 3 — RANO Classification ──────────────────────────────────────
    if a2:
        story.append(Spacer(1, 0.1 * cm))
        _build_section3(a2, story, s)

    # ── Section 4 — Longitudinal Trajectory ──────────────────────────────────
    story.append(Spacer(1, 0.1 * cm))
    _build_section4(a3, story, s)

    # ── Section 5 — Guideline Context ────────────────────────────────────────
    story.append(Spacer(1, 0.1 * cm))
    _build_section5(a4, story, s)

    # ── Section 6 — Limitations ──────────────────────────────────────────────
    story.append(Spacer(1, 0.1 * cm))
    _build_section6(a1, a3, story, s)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(_hr(1, colors.HexColor("#1a3a5c")))
    story.append(Paragraph(
        "End of report.  Constrained Multi-Agent Framework v2.0  |  "
        "llama-3.3-70b-versatile (summary only)  |  "
        f"Audit ref: {patient_id}",
        s["meta"],
    ))

    doc.build(story)
    return buf.getvalue()


# ── Entry point ───────────────────────────────────────────────────────────────

def run_report_agent(scan_id, patient_id, scan_date, a1, a2, a3, a4) -> Agent5Output:
    ts         = datetime.now(timezone.utc).isoformat()
    r2_key     = f"reports/{scan_id}/report_{ts[:19].replace(':', '-')}.pdf"
    patient_id = _sanitise_id(patient_id)

    # Section 1: constrained LLM summary only
    summary, pt, ct, lat = _get_summary(patient_id, scan_date, a1, a2, a3)

    # Build sections object (for backwards compatibility with DB storage)
    sections = ReportSections(
        clinical_summary=summary,
        segmentation_findings="See structured table in PDF.",
        rano_classification=str(getattr(a2, "rano_class", "N/A")),
        longitudinal_trajectory=str(getattr(a3, "overall_trend", "N/A") if a3 else "N/A"),
        guideline_context=(
            f"{len(getattr(a4, 'passages', []))} passages retrieved."
            if a4 and getattr(a4, "rag_available", False)
            else _RAG_UNAVAILABLE
        ),
        limitations_caveats=" | ".join(_KNOWN_LIMITATIONS[:3]),
    )

    pdf = _render_pdf(summary, patient_id, scan_date, ts, a1, a2, a3, a4)
    upload_bytes_to_r2(r2_key, pdf, content_type="application/pdf")
    logger.info("Agent5 done | scan_id=%s r2_key=%s", scan_id, r2_key)

    return Agent5Output(
        scan_id=scan_id, patient_id=patient_id, r2_key=r2_key,
        sections=sections, prompt_tokens=pt, completion_tokens=ct,
        llm_latency_ms=lat, generation_ts=ts,
    )