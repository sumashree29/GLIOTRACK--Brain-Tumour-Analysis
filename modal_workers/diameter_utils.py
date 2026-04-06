"""
Biaxial diameter measurement for RANO.
ET label=3, 26-connectivity. Measurability: >=10mm AND >=5mm.
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage

ET_LABEL       = 3
MIN_DIAM1_MM   = 10.0
MIN_DIAM2_MM   =  5.0

def _largest_component(mask: np.ndarray) -> np.ndarray:
    """Return binary mask of the largest connected component (26-connectivity)."""
    struct = ndimage.generate_binary_structure(3, 3)   # 26-connectivity
    labelled, n = ndimage.label(mask, structure=struct)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, labelled, range(1, n + 1))
    return (labelled == (np.argmax(sizes) + 1)).astype(bool)

def measure_diameters(
    seg: np.ndarray,
    voxel_size_mm: tuple = (1.0, 1.0, 1.0),
) -> tuple[float, float, float]:
    """
    Measure maximum biaxial diameters of ET (label 3) in mm.
    Returns (d1_mm, d2_mm, bp_mm2).
    d1 >= d2 always.  Returns (0, 0, 0) if ET absent or unmeasurable.
    """
    et_mask = _largest_component(seg == ET_LABEL)
    if not et_mask.any():
        return 0.0, 0.0, 0.0

    # Project onto axial slices; find slice with max area
    areas   = et_mask.sum(axis=(1, 2))
    best_z  = int(np.argmax(areas))
    slice2d = et_mask[best_z]

    # Bounding-box diameters on best axial slice
    rows = np.where(slice2d.any(axis=1))[0]
    cols = np.where(slice2d.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return 0.0, 0.0, 0.0

    d_row = (rows[-1] - rows[0] + 1) * voxel_size_mm[1]
    d_col = (cols[-1] - cols[0] + 1) * voxel_size_mm[2]
    d1    = max(d_row, d_col)
    d2    = min(d_row, d_col)

    if d1 < MIN_DIAM1_MM or d2 < MIN_DIAM2_MM:
        return 0.0, 0.0, 0.0   # unmeasurable — RANO non-measurable

    return d1, d2, d1 * d2
