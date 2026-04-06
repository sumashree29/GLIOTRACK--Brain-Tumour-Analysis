"""
Low-confidence flag logic.
Raised when ET diameters approach measurability floor or segmentation
dice is low (indicating uncertain boundary delineation).
"""
from __future__ import annotations

MIN_D1_CONFIDENT_MM = 12.0   # < 12mm -> borderline (floor is 10mm, +-10% can push below)
MIN_D2_CONFIDENT_MM =  6.0   # <  6mm -> borderline (floor is  5mm)
MIN_DICE_CONFIDENT  =  0.70  # Dice below this -> uncertain segmentation

def compute_low_confidence(
    d1_mm: float,
    d2_mm: float,
    dice_et: float,
) -> tuple[bool, str]:
    """
    Returns (flag, reason_string).
    flag=True if any condition is met.
    """
    reasons = []
    if 0 < d1_mm < MIN_D1_CONFIDENT_MM:
        reasons.append(
            f"d1={d1_mm:.1f}mm near 10mm RANO floor (+-10% error can cause misclassification)"
        )
    if 0 < d2_mm < MIN_D2_CONFIDENT_MM:
        reasons.append(
            f"d2={d2_mm:.1f}mm near 5mm RANO floor"
        )
    if 0 < dice_et < MIN_DICE_CONFIDENT:
        reasons.append(
            f"ET Dice={dice_et:.3f} below confidence threshold {MIN_DICE_CONFIDENT}"
        )
    flag   = len(reasons) > 0
    reason = "; ".join(reasons) if reasons else ""
    return flag, reason
