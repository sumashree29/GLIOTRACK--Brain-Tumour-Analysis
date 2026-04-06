"""
Agent 3 — Longitudinal Analysis.
Spec: nadir=min(bp) tie-break earliest, N scans -> N-1 intervals,
inflections at interior boundaries only, dissociation: PD + ET < 25% above nadir.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.agents.rano_agent import RANOClass

_VOLUME_EPSILON = 1e-9
_STABLE_THRESHOLD_PCT = 1.0

@dataclass
class TrajectoryInterval:
    start_date: str; end_date: str
    bp_start: float; bp_end: float
    pct_change: float
    rano_at_end: Optional[str] = None
    rc_volume_ml: Optional[float] = None

@dataclass
class Agent3Output:
    scan_dates: list
    nadir_bp_mm2: float
    nadir_scan_date: str
    change_from_nadir_pct: float
    overall_trend: Optional[str]
    inflection_points: list
    trajectory_intervals: list
    dissociation_flag: bool
    low_confidence_flag: bool
    rc_volumes: list = field(default_factory=list)

def _validate_asc(series):
    dates = [a1.scan_date for a1 in series]
    for i in range(1, len(dates)):
        if dates[i] <= dates[i-1]:
            raise ValueError(f"scan_dates not strictly ASC: {dates[i-1]} >= {dates[i]}")

def _find_nadir(series):
    # Nadir = minimum BP after baseline (exclude first scan which is baseline)
    # If only 1 scan, nadir = that scan
    search_series = series[1:] if len(series) > 1 else series
    nadir_bp = min(a1.bidimensional_product_mm2 for a1 in search_series)
    for a1 in search_series:
        if a1.bidimensional_product_mm2 == nadir_bp:
            return nadir_bp, a1.scan_date
    return nadir_bp, series[0].scan_date

def _direction(pct):
    if pct > _STABLE_THRESHOLD_PCT: return 1
    if pct < -_STABLE_THRESHOLD_PCT: return -1
    return 0

def _build_intervals(series, a2_map):
    intervals = []
    for i in range(len(series) - 1):
        a, b = series[i], series[i+1]
        bp_a, bp_b = a.bidimensional_product_mm2, b.bidimensional_product_mm2
        pct = ((bp_b - bp_a) / bp_a * 100.0) if bp_a > _VOLUME_EPSILON else 0.0
        rano = a2_map.get(b.scan_date)
        intervals.append(TrajectoryInterval(
            start_date=a.scan_date, end_date=b.scan_date,
            bp_start=bp_a, bp_end=bp_b, pct_change=pct,
            rano_at_end=(rano.rano_class.value if hasattr(rano.rano_class, 'value') else str(rano.rano_class)) if (rano and rano.rano_class is not None) else None,
            rc_volume_ml=b.rc_volume_ml or 0.0,
        ))
    return intervals

def _detect_inflections(intervals, series):
    if len(intervals) < 2:
        return []
    points = []
    for i in range(len(intervals) - 1):
        left  = _direction(intervals[i].pct_change)
        right = _direction(intervals[i+1].pct_change)
        if left == 0 or right == 0: continue
        if left != right:
            points.append(series[i+1].scan_date)
    return points

def _classify_trend(intervals, inflections):
    if len(inflections) >= 2: return "mixed"
    dirs = [_direction(iv.pct_change) for iv in intervals if _direction(iv.pct_change) != 0]
    if not dirs: return "stable"
    pos = sum(1 for d in dirs if d == 1)
    neg = sum(1 for d in dirs if d == -1)
    total = len(dirs)
    if pos / total > 0.5: return "worsening"
    if neg / total > 0.5: return "improving"
    return "mixed"

def run_longitudinal_analysis(
    a1_series: list,
    a2_series: list = None,
) -> Agent3Output:
    if not a1_series:
        raise ValueError("a1_series is empty")
    _validate_asc(a1_series)

    nadir_bp, nadir_date = _find_nadir(a1_series)
    current_bp = a1_series[-1].bidimensional_product_mm2
    change_from_nadir = ((current_bp - nadir_bp) / nadir_bp * 100.0
                         if nadir_bp > _VOLUME_EPSILON else 0.0)
    low_conf = any(a1.low_confidence_flag for a1 in a1_series)

    if len(a1_series) == 1:
        return Agent3Output(
            scan_dates=[a1_series[0].scan_date],
            nadir_bp_mm2=nadir_bp, nadir_scan_date=nadir_date,
            change_from_nadir_pct=change_from_nadir,
            overall_trend=None, inflection_points=[],
            trajectory_intervals=[], dissociation_flag=False,
            low_confidence_flag=low_conf,
        )

    a2_map = {}
    if a2_series:
        for a1, a2 in zip(a1_series, a2_series):
            if a2: a2_map[a1.scan_date] = a2

    intervals    = _build_intervals(a1_series, a2_map)
    rc_volumes = [a1.rc_volume_ml or 0.0 for a1 in a1_series]
    inflections  = _detect_inflections(intervals, a1_series)
    trend        = _classify_trend(intervals, inflections)

    # Dissociation: most recent RANO=PD but ET still within 25% of nadir
    most_recent_a2 = a2_map.get(a1_series[-1].scan_date)
    dissociation   = (
        most_recent_a2 is not None
        and most_recent_a2.rano_class == RANOClass.PD
        and change_from_nadir < 25.0
    )

    return Agent3Output(
        scan_dates=[a1.scan_date for a1 in a1_series],
        nadir_bp_mm2=nadir_bp, nadir_scan_date=nadir_date,
        change_from_nadir_pct=change_from_nadir,
        overall_trend=trend, inflection_points=inflections,
        trajectory_intervals=intervals,
        dissociation_flag=dissociation, low_confidence_flag=low_conf,
        rc_volumes=rc_volumes
    )
