"""
Agent 4 — Clinical RAG.
Failure policy: ANY exception -> rag_available=False. NEVER raises.
failure_reason NEVER left blank on failure.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.agents.rano_agent import Agent2Output, RANOClass
from app.agents.longitudinal_agent import Agent3Output
from app.models.scan import Agent1Output

@dataclass
class Agent4Output:
    rag_available: bool
    passages: list = field(default_factory=list)
    failure_reason: Optional[str] = None
    query_used: Optional[str] = None

def _unavailable_output(failure_reason: str, query_used: Optional[str]) -> Agent4Output:
    return Agent4Output(rag_available=False, passages=[],
                        failure_reason=failure_reason, query_used=query_used)

def _formulate_query(a2: Agent2Output, a3: Agent3Output, a1: Agent1Output) -> str:
    rano_terms = {
        RANOClass.PD:             "Progressive Disease",
        RANOClass.PR:             "Partial Response",
        RANOClass.SD:             "Stable Disease",
        RANOClass.CR_PROVISIONAL: "Complete Response provisional",
        RANOClass.CR_CONFIRMED:   "Complete Response confirmed",
    }
    rano_term = rano_terms.get(a2.rano_class, "baseline scan") if a2.rano_class else "baseline scan no prior comparison"

    pct = a2.pct_change_from_baseline or 0.0
    if pct >= 25:     bp_desc = "tumour progression significant increase"
    elif pct >= 10:   bp_desc = "mild tumour increase"
    elif pct <= -50:  bp_desc = "significant tumour reduction"
    elif pct <= -10:  bp_desc = "modest tumour decrease"
    else:              bp_desc = "stable tumour size"

    et = a1.et_volume_ml
    if et < 0.1:       et_desc = "minimal enhancement no measurable ET"
    elif et < 1.0:     et_desc = "small enhancing tumour"
    elif et < 5.0:     et_desc = "moderate enhancing tumour volume"
    else:               et_desc = "enhancing tumour volume"

    flags = []
    if a2.new_lesion_detected:          flags.append("new enhancing lesion")
    if a1.low_confidence_flag:          flags.append("measurement uncertainty borderline")
    if a2.steroid_increase:             flags.append("dexamethasone steroid dose increase")
    if getattr(a2, "non_measurable_progression", False): flags.append("non-measurable disease")
    if a3.dissociation_flag:            flags.append("pseudoprogression MGMT mRANO dissociation")

    query = f"{rano_term} brain tumour response assessment {bp_desc} {et_desc}"
    if flags:
        query += " " + " ".join(flags)
    return query[:500]

def run_clinical_rag(a2: Agent2Output, a3: Agent3Output, a1: Agent1Output) -> Agent4Output:
    query = None
    try:
        from rag.knowledge_base import query_knowledge_base
        query = _formulate_query(a2, a3, a1)
        ok, passages, reason = query_knowledge_base(query)
        if not ok:
            return _unavailable_output(reason or "Knowledge base query failed", query)
        return Agent4Output(rag_available=True, passages=passages, query_used=query)
    except Exception as exc:
        return _unavailable_output(str(exc), query)
