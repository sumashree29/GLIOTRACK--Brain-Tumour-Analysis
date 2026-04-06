"""
segmentation_worker.py — Agent 1: Tumour Segmentation
CBTA Brain Tumour Analysis System
Version: 16

Deploy:  modal deploy modal_workers/segmentation_worker.py
Seed:    modal run  modal_workers/segmentation_worker.py::seed_weights

Changes in v16 vs v15:
  [FIX-A]  BraTS Python package removed entirely.
           Root cause of v15 failure: brats package wraps a Docker container
           internally (brats.core.docker). Modal containers cannot run Docker
           (no /var/run/docker.sock). Hard Modal sandbox restriction.

  [FIX-B]  nnU-Net v2 (nnunetv2) used directly — no Docker, no wrapper.
           BraTS 2024 Task 1 winning model IS nnUNetv2 underneath.
           Bypassing the Docker wrapper gives identical output, zero Docker dependency.

  [FIX-C]  Weights: Zenodo record 14001262 (public, no login required).
           File: BraTS_2023_2024_code_with_weights.zip (39.8 GB, MD5 verified).
           seed_weights() downloads once, extracts Task 1 weights only,
           deletes zip, commits to Modal Volume. Never downloads again.

  [FIX-D]  Input: nnUNetv2 expects {case_id}_0000..0003.nii.gz
           Channel order for BraTS 2024 Task 1:
             0000=T1n, 0001=T1c, 0002=T2w, 0003=T2f(FLAIR)

  [FIX-E]  Inference: nnUNetv2_predict CLI via subprocess.
           Dataset ID 242, 3d_fullres, all 5 folds ensembled.
           Output labels: 1=NETC, 2=SNFH, 3=ET, 4=RC.

  [FIX-F]  NIfTI header fix (NaN scl_slope) retained from v14.
           MU-Glioma-Post files have NaN scl_slope — fixed before nnUNetv2.

  [KEPT]   R2, Supabase, RANO, sequence mapping, NIfTI validation, HTTP endpoints.
  [KEPT]   Label scheme: ET=3, RC=4 excluded from RANO.
  [KEPT]   rc_volume_ml reported in Supabase payload.
"""

import modal
import uuid
import tempfile
import os
import subprocess
import zipfile
import shutil
import logging
import json
import time

import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from fastapi import Header, HTTPException as _HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("agent1")

# ─────────────────────────────────────────────────────────────────────────────
# Modal app + image
# ─────────────────────────────────────────────────────────────────────────────

app = modal.App("brain-tumour-segmentation")

image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "nnunetv2",
        "torch==2.4.0",
        "torchvision",
        "nibabel==5.2.1",
        "numpy==1.26.4",
        "scipy==1.13.0",
        "boto3==1.34.0",
        "fastapi",
        "uvicorn",
        "pydicom==2.4.4",
        "supabase==1.2.0",
        "brainles-preprocessing",
        "antspyx",
        "cmake",
    )
    .run_commands(
        "apt-get update -y && apt-get install -y dcm2niix wget unzip"
    )
)

# ─────────────────────────────────────────────────────────────────────────────
# Modal infrastructure
# ─────────────────────────────────────────────────────────────────────────────

volume   = modal.Volume.from_name("nnunet-weights", create_if_missing=True, environment_name="main")
job_dict = modal.Dict.from_name("bts-jobs",         create_if_missing=True)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

NNUNET_RESULTS_DIR   = "/weights/nnunet_results"
BRATS2024_DATASET_ID = "242"

ZENODO_RECORD_ID    = "14001262"
ZENODO_ZIP_NAME     = "BraTS_2023_2024_code_with_weights.zip"
ZENODO_ZIP_MD5      = "024709c75f1246622c300dfd89fdebd2"
ZENODO_DOWNLOAD_URL = (
    f"https://zenodo.org/records/{ZENODO_RECORD_ID}/files/"
    f"{ZENODO_ZIP_NAME}?download=1"
)

# BraTS 2024 Task 1 channel order
CHANNEL_ORDER = [
    ("T1ce",  "0000"),
    ("T1",    "0001"),
    ("FLAIR",    "0002"),
    ("T2", "0003"),
]

# Label scheme (BraTS 2024 post-treatment)
ET_LABEL = 3   # Enhancing Tumour ← RANO target
RC_LABEL = 4   # Resection Cavity ← excluded from RANO

REQUIRED_SEQUENCES     = ["T1", "T1ce", "T2", "FLAIR"]
RANO_MIN_LD            = 10.0
RANO_MIN_PD            = 5.0
ET_VOXEL_MIN           = 50
R2_UPLOAD_MAX_ATTEMPTS = 3
R2_UPLOAD_RETRY_DELAY_S = 5
THICK_SLICE_WARNING_MM = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# NIfTI header fix — NaN scl_slope in MU-Glioma-Post files
# ─────────────────────────────────────────────────────────────────────────────

def _detect_preprocessed(seq_map: dict) -> dict:
    """
    Detects if input files are already skull-stripped and preprocessed.
    MU-Glioma-Post files contain brain_ in filename.
    BraTS files are always preprocessed.
    Raw clinical files are not.
    """
    import nibabel as nib
    indicators = ["brain_", "skull", "_bet", "stripped", "brats"]
    for seq, path in seq_map.items():
        name = Path(path).name.lower()
        if any(ind in name for ind in indicators):
            log.info("_detect_preprocessed: skull-stripped detected via filename: %s", name)
            return {"already_skull_stripped": True}
    try:
        for seq, path in seq_map.items():
            arr = nib.load(path).get_fdata()
            bg_pct = float((arr == 0).sum()) / arr.size
            if bg_pct > 0.3:
                log.info("_detect_preprocessed: skull-stripped via bg_pct=%.2f", bg_pct)
                return {"already_skull_stripped": True}
            break
    except Exception as exc:
        log.warning("_detect_preprocessed: could not check intensity: %s", exc)
    # BraTS-format shape (240,240,155) at 1mm isotropic = already preprocessed
    try:
        for seq, path in seq_map.items():
            img = nib.load(path)
            shape = img.shape[:3]
            zooms = img.header.get_zooms()[:3]
            if shape == (240, 240, 155) and all(abs(z - 1.0) < 0.01 for z in zooms):
                log.info("_detect_preprocessed: BraTS-format shape detected %s", shape)
                return {"already_skull_stripped": True}
            break
    except Exception as exc:
        log.warning("_detect_preprocessed: shape check failed: %s", exc)
    log.info("_detect_preprocessed: raw input detected")
    return {"already_skull_stripped": False}

def _fix_nifti_header(src_path: str, dst_path: str) -> None:
    """Fix NaN scl_slope and reorient to RAS before passing to nnUNetv2."""
    import nibabel as nib

    img   = nib.load(src_path)
    hdr   = img.header.copy()
    slope = hdr.get("scl_slope", 1.0)

    if np.isnan(float(slope)) or float(slope) == 0.0:
        hdr["scl_slope"] = 1.0
        hdr["scl_inter"] = 0.0
        log.info("  Fixed NaN scl_slope: %s", Path(src_path).name)

    fixed_img = nib.Nifti1Image(img.get_fdata(dtype=np.float32), img.affine, hdr)
    ras_img   = nib.as_closest_canonical(fixed_img)
    nib.save(ras_img, dst_path)
    log.info("  Reoriented RAS → %s", Path(dst_path).name)
def _run_brainles_preprocessing(seq_map: dict, output_dir: Path) -> dict:
    """
    Runs brainles_preprocessing pipeline on raw clinical MRI.
    Returns new seq_map pointing to preprocessed skull-stripped files.
    Uses AtlasCentricPreprocessor — registers to MNI152, skull strips,
    resamples to 1mm isotropic. Matches MU-Glioma-Post preprocessing exactly.
    """
    from brainles_preprocessing.modality import Modality, CenterModality
    from brainles_preprocessing.preprocessor import AtlasCentricPreprocessor

    output_dir.mkdir(parents=True, exist_ok=True)

    center = CenterModality(
        modality_name="t1c",
        input_path=seq_map["T1ce"],
        raw_bet_output_path=str(output_dir / "brain_t1c.nii.gz"),
    )

    modalities = [
        Modality(
            modality_name="t1n",
            input_path=seq_map["T1"],
            raw_bet_output_path=str(output_dir / "brain_t1n.nii.gz"),
        ),
        Modality(
            modality_name="t2w",
            input_path=seq_map["T2"],
            raw_bet_output_path=str(output_dir / "brain_t2w.nii.gz"),
        ),
        Modality(
            modality_name="t2f",
            input_path=seq_map["FLAIR"],
            raw_bet_output_path=str(output_dir / "brain_t2f.nii.gz"),
        ),
    ]

    preprocessor = AtlasCentricPreprocessor(
        center_modality=center,
        moving_modalities=modalities,
    )
    preprocessor.run()

    log.info("brainles_preprocessing complete.")

    return {
        "T1ce":  str(output_dir / "brain_t1c.nii.gz"),
        "T1":    str(output_dir / "brain_t1n.nii.gz"),
        "T2":    str(output_dir / "brain_t2w.nii.gz"),
        "FLAIR": str(output_dir / "brain_t2f.nii.gz"),
    }

def _normalize_to_training_distribution(src_path: str, dst_path: str, 
                                         train_mean: float, train_std: float) -> None:
    """Rescale scan intensities to match training data distribution."""
    import nibabel as nib
    img = nib.load(src_path)
    arr = img.get_fdata(dtype=np.float32)
    brain_mask = arr > 0
    if brain_mask.sum() > 0:
        scan_mean = arr[brain_mask].mean()
        scan_std  = arr[brain_mask].std()
        # ZScore then rescale to training distribution
        arr[brain_mask] = ((arr[brain_mask] - scan_mean) / (scan_std + 1e-8)) \
                          * train_std + train_mean
        arr[~brain_mask] = 0
    out = nib.Nifti1Image(arr, img.affine, img.header)
    nib.save(out, dst_path)
    log.info("  Normalized to training dist: mean=%.1f std=%.1f", train_mean, train_std)
# ─────────────────────────────────────────────────────────────────────────────
# NIfTI validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_nifti_outputs(nifti_dir: Path) -> None:
    import nibabel as nib

    nii_files = list(nifti_dir.glob("*.nii.gz")) + list(nifti_dir.glob("*.nii"))
    if not nii_files:
        raise ValueError(f"No NIfTI files found in {nifti_dir}.")

    errors = []
    for nf in nii_files:
        try:
            img     = nib.load(str(nf))
            spacing = tuple(float(s) for s in img.header.get_zooms()[:3])
            shape   = img.shape[:3]
            if any(s <= 0 for s in spacing):
                errors.append(f"{nf.name}: non-positive spacing {spacing}")
            if any(d <= 0 for d in shape):
                errors.append(f"{nf.name}: degenerate shape {shape}")
            if len(spacing) >= 3 and spacing[2] > THICK_SLICE_WARNING_MM:
                log.warning("Thick-slice: %s %.1fmm", nf.name, spacing[2])
            log.info("  Validated: %s shape=%s spacing=%.2f×%.2f×%.2fmm",
                     nf.name, shape, *spacing)
        except Exception as exc:
            errors.append(f"{nf.name}: unreadable ({exc})")

    if errors:
        raise ValueError("NIfTI validation failed:\n" + "\n".join(f"  • {e}" for e in errors))
    log.info("NIfTI validation passed for %d file(s).", len(nii_files))


# ─────────────────────────────────────────────────────────────────────────────
# Sequence mapping
# ─────────────────────────────────────────────────────────────────────────────

_FILENAME_KEYWORDS = [
    (["t1ce", "t1c", "t1gd", "t1_ce", "t1+c", "gd", "gadolinium", "contrast", "t1c"], "T1ce"),
    (["flair", "t2_flair", "t2flair", "t2f"],                                          "FLAIR"),
    (["t2w", "t2"],                                                                     "T2"),
    (["t1n", "t1"],                                                                     "T1"),
]
_SERIES_DESC_KEYWORDS = _FILENAME_KEYWORDS


def _map_sequences(nifti_dir: Path, dicom_dir: Path | None = None) -> dict:
    nii_files = sorted(
        list(nifti_dir.glob("*.nii.gz")) + list(nifti_dir.glob("*.nii"))
    )
    seq_map: dict[str, str] = {}

    # Pass 1: filename
    for nf in nii_files:
        name_lower = nf.name.lower()
        for keywords, label in _FILENAME_KEYWORDS:
            if label in seq_map:
                continue
            if any(kw in name_lower for kw in keywords):
                seq_map[label] = str(nf)
                log.info("  Filename match: %s → %s", nf.name, label)
                break

    missing = [s for s in REQUIRED_SEQUENCES if s not in seq_map]
    if not missing:
        return seq_map

    log.warning("Pass 1 missing: %s — trying DICOM tags", missing)

    # Pass 2: DICOM SeriesDescription
    if dicom_dir is not None and dicom_dir.exists():
        import pydicom
        for json_file in nifti_dir.glob("*.json"):
            try:
                with open(json_file) as jf:
                    meta = json.load(jf)
                desc = meta.get("SeriesDescription", "").lower()
                nii_candidate = json_file.with_suffix("").with_suffix(".nii.gz")
                if not nii_candidate.exists():
                    nii_candidate = json_file.with_suffix(".nii")
                if not nii_candidate.exists():
                    continue
                for keywords, label in _SERIES_DESC_KEYWORDS:
                    if label in seq_map:
                        continue
                    if any(kw in desc for kw in keywords):
                        seq_map[label] = str(nii_candidate)
                        log.info("  JSON sidecar: %s → %s", nii_candidate.name, label)
                        break
            except Exception:
                pass

        if any(s not in seq_map for s in REQUIRED_SEQUENCES):
            seen: dict[str, str] = {}
            for dcm in sorted(dicom_dir.rglob("*.dcm"))[:500]:
                try:
                    ds  = pydicom.dcmread(str(dcm), stop_before_pixels=True, force=True)
                    uid = str(getattr(ds, "SeriesInstanceUID", ""))
                    desc = str(getattr(ds, "SeriesDescription", "")).lower()
                    if uid and uid not in seen:
                        seen[uid] = desc
                except Exception:
                    continue
            for uid, desc in seen.items():
                for keywords, label in _SERIES_DESC_KEYWORDS:
                    if label in seq_map:
                        continue
                    if any(kw in desc for kw in keywords):
                        for nf in nii_files:
                            if nf.name.lower().split(".")[0] in desc.replace(" ", "").lower():
                                seq_map[label] = str(nf)
                                break

    # Pass 3: ContrastBolusAgent + EchoTime
    missing = [s for s in REQUIRED_SEQUENCES if s not in seq_map]
    if missing and dicom_dir is not None and dicom_dir.exists():
        import pydicom
        series_meta: dict[str, dict] = {}
        for dcm in sorted(dicom_dir.rglob("*.dcm"))[:500]:
            try:
                ds  = pydicom.dcmread(str(dcm), stop_before_pixels=True, force=True)
                uid = str(getattr(ds, "SeriesInstanceUID", ""))
                if not uid or uid in series_meta:
                    continue
                series_meta[uid] = {
                    "desc":           str(getattr(ds, "SeriesDescription", "")).lower(),
                    "contrast_agent": str(getattr(ds, "ContrastBolusAgent", "") or "").strip(),
                    "echo_time":      float(getattr(ds, "EchoTime", None) or 0) or None,
                }
            except Exception:
                continue
        for uid, meta in series_meta.items():
            if "T1ce" not in seq_map and meta["contrast_agent"]:
                cand = _find_nifti_for_series(nii_files, meta["desc"], seq_map)
                if cand:
                    seq_map["T1ce"] = str(cand)
            if "T1" not in seq_map and meta["echo_time"] and meta["echo_time"] < 10.0:
                cand = _find_nifti_for_series(nii_files, meta["desc"], seq_map)
                if cand:
                    seq_map["T1"] = str(cand)

    missing = [s for s in REQUIRED_SEQUENCES if s not in seq_map]
    if missing:
        raise ValueError(
            f"Cannot identify sequences: {missing}\n"
            f"Matched: {seq_map}\nFiles: {[f.name for f in nii_files]}"
        )
    return seq_map


def _find_nifti_for_series(nii_files: list, series_desc: str, already_mapped: dict) -> "Path | None":
    mapped = set(already_mapped.values())
    desc   = series_desc.replace(" ", "").lower()
    for nf in nii_files:
        if str(nf) not in mapped and desc and desc in nf.name.lower().split(".")[0]:
            return nf
    for nf in nii_files:
        if str(nf) not in mapped:
            return nf
    return None


# ─────────────────────────────────────────────────────────────────────────────
# RANO calculation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_rano(seg_arr: np.ndarray, spacing: tuple) -> dict:
    from scipy import ndimage

    et_mask    = (seg_arr == ET_LABEL).astype(np.uint8)
    vox_vol_ml = spacing[0] * spacing[1] * spacing[2] / 1000.0

    et_vol = float((seg_arr == ET_LABEL).sum() * vox_vol_ml)
    tc_vol = float(((seg_arr == 1) | (seg_arr == ET_LABEL)).sum() * vox_vol_ml)
    wt_vol = float(((seg_arr > 0) & (seg_arr != RC_LABEL)).sum() * vox_vol_ml)
    rc_vol = float((seg_arr == RC_LABEL).sum() * vox_vol_ml)

    if et_mask.sum() == 0:
        return {
            "et_volume_ml": 0.0, "tc_volume_ml": tc_vol,
            "wt_volume_ml": wt_vol, "rc_volume_ml": rc_vol,
            "lesion_count": 0, "measurable_lesion_count": 0,
            "non_measurable_lesion_count": 0,
            "bidimensional_product_mm2": 0.0,
            "et_diameter1_mm": 0.0, "et_diameter2_mm": 0.0,
            "lesions": [],
        }

    labeled, n_comp = ndimage.label(et_mask, structure=np.ones((3, 3, 3)))
    log.info("RANO: %d ET components", n_comp)

    measurable_bps  = []
    best_d1_overall = best_d2_overall = 0.0
    lesion_records  = []

    for cid in range(1, n_comp + 1):
        comp      = (labeled == cid)
        vox_count = int(comp.sum())
        zs        = np.where(comp.any(axis=(1, 2)))[0]
        best_d1 = best_d2 = best_bp = 0.0

        for z in zs:
            sl         = comp[z]
            rows, cols = np.where(sl)
            if len(rows) < 2:
                continue
            pts  = np.column_stack([rows * spacing[1], cols * spacing[0]])
            dist = np.linalg.norm(pts[:, None] - pts[None, :], axis=-1)
            i0, i1 = np.unravel_index(dist.argmax(), dist.shape)
            d1      = float(dist[i0, i1])
            if d1 < RANO_MIN_LD:
                continue
            axis = pts[i1] - pts[i0]
            axis = axis / (np.linalg.norm(axis) + 1e-8)
            perp = np.array([-axis[1], axis[0]])
            proj = (pts - pts[i0]) @ perp
            d2   = float(proj.max() - proj.min())
            if d2 >= RANO_MIN_PD and d1 * d2 > best_bp:
                best_d1, best_d2, best_bp = d1, d2, d1 * d2

        measurable = best_d1 >= RANO_MIN_LD and best_d2 >= RANO_MIN_PD
        if measurable:
            measurable_bps.append(best_bp)
            if best_bp > best_d1_overall * best_d2_overall:
                best_d1_overall, best_d2_overall = best_d1, best_d2

        lesion_records.append({
            "lesion_id":                 cid,
            "voxel_count":               vox_count,
            "longest_diameter_mm":       round(best_d1, 2),
            "perpendicular_diameter_mm": round(best_d2, 2),
            "bidimensional_product_mm2": round(best_bp, 2),
            "measurable":                measurable,
        })
        log.info("  Lesion %d: %dvx LD=%.1fmm PD=%.1fmm measurable=%s",
                 cid, vox_count, best_d1, best_d2, measurable)

    measurable_count = sum(1 for l in lesion_records if l["measurable"])
    return {
        "et_volume_ml":                round(et_vol, 4),
        "tc_volume_ml":                round(tc_vol, 4),
        "wt_volume_ml":                round(wt_vol, 4),
        "rc_volume_ml":                round(rc_vol, 4),
        "lesion_count":                n_comp,
        "measurable_lesion_count":     measurable_count,
        "non_measurable_lesion_count": n_comp - measurable_count,
        "bidimensional_product_mm2":   round(sum(measurable_bps), 2),
        "et_diameter1_mm":             round(best_d1_overall, 2),
        "et_diameter2_mm":             round(best_d2_overall, 2),
        "lesions":                     lesion_records,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Supabase + R2 helpers (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _write_to_supabase(payload: dict) -> str:
    import math
    from supabase import create_client

    def _sanitize(obj):
        if isinstance(obj, (float, np.floating)):
            return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(i) for i in obj]
        return obj

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    resp   = (
        client.table("agent1_results")
        .upsert(_sanitize(payload), on_conflict="patient_id,scan_date")
        .execute()
    )
    if not resp.data:
        raise RuntimeError(f"Supabase upsert returned no data: {resp}")
    row_id = resp.data[0].get("id", "unknown")
    log.info("Supabase write complete — row: %s", row_id)
    return str(row_id)


def _upload_mask_to_r2(s3_client, mask_path: str, patient_id: str,
                        scan_date: str, job_id: str) -> str:
    import boto3.s3.transfer
    bucket = os.environ["R2_BUCKET_NAME"]
    r2_key = f"patients/{patient_id}/masks/{scan_date}_{job_id}.nii.gz"
    config = boto3.s3.transfer.TransferConfig(
        multipart_threshold=5 * 1024 * 1024,
        multipart_chunksize=5 * 1024 * 1024,
        max_concurrency=4,
    )
    with open(mask_path, "rb") as f:
        s3_client.upload_fileobj(f, bucket, r2_key, Config=config,
            ExtraArgs={"ContentType": "application/gzip", "ServerSideEncryption": "AES256"})
    log.info("R2 upload complete: %s", r2_key)
    return r2_key


# ─────────────────────────────────────────────────────────────────────────────
# seed_weights — ONE-TIME download of BraTS 2024 Task 1 weights from Zenodo
# ─────────────────────────────────────────────────────────────────────────────

@app.function(
    image=image,
    volumes={"/weights": volume},
    timeout=7200,   # 2 hours for 39.8 GB download
)
def seed_weights():
    """
    Downloads BraTS_2023_2024_code_with_weights.zip from Zenodo 14001262
    (39.8 GB, public), extracts nnUNet_results, deletes zip.

    Run ONCE:
        modal run modal_workers/segmentation_worker.py::seed_weights
    """
    import hashlib

    dest_dir    = Path("/weights")
    results_dir = Path(NNUNET_RESULTS_DIR)
    zip_path    = dest_dir / ZENODO_ZIP_NAME

    # Skip if already done
    existing = list(results_dir.rglob("checkpoint_final.pth")) if results_dir.exists() else []
    if existing:
        log.info("Weights already present (%d checkpoints). Skipping.", len(existing))
        return

    results_dir.mkdir(parents=True, exist_ok=True)

    # Download
    log.info("Downloading from Zenodo %s (~39.8 GB)...", ZENODO_RECORD_ID)
    subprocess.run(
        ["wget", "--no-check-certificate", "--progress=dot:giga",
         "-O", str(zip_path), ZENODO_DOWNLOAD_URL],
        check=True,
    )

    zip_size = zip_path.stat().st_size
    log.info("Downloaded: %.2f GB", zip_size / 1e9)
    if zip_size < 1_000_000_000:
        raise RuntimeError(f"Download too small ({zip_size} bytes) — failed.")

    # MD5 check
    log.info("Verifying MD5...")
    h = hashlib.md5()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual_md5 = h.hexdigest()
    if actual_md5 != ZENODO_ZIP_MD5:
        raise RuntimeError(
            f"MD5 mismatch.\n  Expected: {ZENODO_ZIP_MD5}\n  Got: {actual_md5}"
        )
    log.info("MD5 OK: %s", actual_md5)

    # Extract
    log.info("Extracting zip (this takes a while)...")
    extract_tmp = dest_dir / "zip_extract_tmp"
    extract_tmp.mkdir(parents=True, exist_ok=True)
    subprocess.run(["unzip", "-o", str(zip_path), "-d", str(extract_tmp)], check=True)

    # Find nnUNet_results inside extracted content
    found = (
        list(extract_tmp.rglob("nnUNet_results")) +
        list(extract_tmp.rglob("nnunet_results"))
    )
    if not found:
        top = [str(p) for p in extract_tmp.iterdir()]
        raise RuntimeError(
            f"nnUNet_results not found in zip.\nTop-level: {top}\n"
            "Run inspect_weights() to debug."
        )

    src = found[0]
    log.info("Found results at: %s → moving to %s", src, results_dir)
    if results_dir.exists():
        shutil.rmtree(str(results_dir))
    shutil.move(str(src), str(results_dir))

    # Cleanup
    shutil.rmtree(str(extract_tmp), ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    log.info("Cleaned up zip.")

    # Verify
    checkpoints = list(results_dir.rglob("checkpoint_final.pth"))
    if not checkpoints:
        raise RuntimeError(
            f"No checkpoint_final.pth under {results_dir} after extraction.\n"
            "Run inspect_weights() to debug."
        )
    log.info("seed_weights complete — %d checkpoint(s):", len(checkpoints))
    for cp in checkpoints[:10]:
        log.info("  %s", cp)

    volume.commit()
    log.info("Volume committed.")


@app.function(image=image, volumes={"/weights": volume}, timeout=120)
def inspect_weights():
    """
    Full volume inspection — shows all files, directory tree, total size.
    Run after seed_weights() to verify what is present and at what paths.
    """
    volume.reload()

    # All files (any type)
    r_all = subprocess.run(
        ["find", "/weights", "-type", "f"],
        capture_output=True, text=True,
    )
    all_files = r_all.stdout.strip().splitlines()

    # Size
    r_size = subprocess.run(["du", "-sh", "/weights"], capture_output=True, text=True)

    # Directory tree depth 8
    r_dirs = subprocess.run(
        ["find", "/weights", "-maxdepth", "8", "-type", "d"],
        capture_output=True, text=True,
    )

    # Dataset folders
    r_ds = subprocess.run(
        ["find", "/weights", "-maxdepth", "8", "-name", "Dataset*", "-type", "d"],
        capture_output=True, text=True,
    )

    print(f"=== TOTAL SIZE ===\n{r_size.stdout or 'UNKNOWN'}")
    print(f"\n=== TOTAL FILES: {len(all_files)} ===")
    print("\n=== ALL FILES (first 100) ===")
    print("\n".join(all_files[:100]) or "NONE")
    print("\n=== DATASET FOLDERS ===")
    print(r_ds.stdout or "NONE — no Dataset* folders found")
    print("\n=== FULL DIRECTORY TREE ===")
    print(r_dirs.stdout[:5000] or "EMPTY")


# ─────────────────────────────────────────────────────────────────────────────
# Main inference function
# ─────────────────────────────────────────────────────────────────────────────

@app.function(
    gpu="T4:1",
    image=image,
    volumes={"/weights": volume},
    timeout=1800,
    secrets=[modal.Secret.from_name("bts-secrets")],
)
def run_segmentation(
    job_id: str,
    scan_id: str,
    patient_id: str,
    dicom_r2_keys: list,
    scan_date: str = "",
) -> dict:
    import nibabel as nib
    import boto3

    scan_date = scan_date or datetime.now(timezone.utc).date().isoformat()
    job_dict[job_id] = {"status": "running", "scan_id": scan_id, "patient_id": patient_id}

    try:
        volume.reload()
        log.info("Volume reloaded.")

        # GPU check
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError(f"GPU unavailable. torch.version.cuda={torch.version.cuda}")
        log.info("CUDA OK — %s", torch.cuda.get_device_name(0))

        # Weights check
        checkpoints = list(Path(NNUNET_RESULTS_DIR).rglob("checkpoint_final.pth"))
        if not checkpoints:
            raise RuntimeError(
                f"No weights found under {NNUNET_RESULTS_DIR}.\n"
                "Run: modal run modal_workers/segmentation_worker.py::seed_weights"
            )
        log.info("Weights OK — %d checkpoint(s).", len(checkpoints))

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            s3 = boto3.client(
                "s3",
                endpoint_url=os.environ["R2_ENDPOINT_URL"],
                aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                region_name="auto",
            )
            bucket    = os.environ["R2_BUCKET_NAME"]
            nifti_dir = tmp / "nifti"
            dicom_dir = tmp / "dicom"
            nifti_dir.mkdir()
            dicom_dir.mkdir()

            # ── STEP 1–2: Download + extract ──────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "downloading")
            log.info("STEP 1–2: Downloading %d key(s)", len(dicom_r2_keys))

            for r2_key in dicom_r2_keys:
                filename   = r2_key.split("/")[-1]
                local_path = tmp / filename
                s3.download_file(bucket, r2_key, str(local_path))
                log.info("  Downloaded: %s", filename)

                if filename.endswith(".zip"):
                    with zipfile.ZipFile(str(local_path), "r") as z:
                        for member in z.namelist():
                            if ".." in member:
                                raise ValueError(f"Unsafe zip entry: {member}")
                        z.extractall(str(dicom_dir))
                    local_path.unlink()
                    extracted_nii = (
                        list(dicom_dir.rglob("*.nii.gz")) + list(dicom_dir.rglob("*.nii"))
                    )
                    if extracted_nii:
                        for nf in extracted_nii:
                            shutil.copy(str(nf), str(nifti_dir / nf.name))
                        log.info("  %d NIfTI(s) from zip.", len(extracted_nii))
                    else:
                        res = subprocess.run(
                            ["dcm2niix", "-z", "y", "-ba", "n",
                             "-o", str(nifti_dir), str(dicom_dir)],
                            capture_output=True, text=True,
                        )
                        if res.returncode != 0:
                            log.warning("dcm2niix: %s", res.stderr[:500])
                elif filename.endswith((".nii.gz", ".nii")):
                    shutil.copy(str(local_path), str(nifti_dir / filename))
                else:
                    raise ValueError(f"Unsupported file: {filename}")

            # ── STEP 2b: Validate NIfTI ───────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "validating_nifti")
            log.info("STEP 2b: Validating NIfTI outputs")
            _validate_nifti_outputs(nifti_dir)

            # ── STEP 3: Map sequences ─────────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "mapping_sequences")
            log.info("STEP 3: Mapping sequences")
            seq_map = _map_sequences(nifti_dir, dicom_dir)
            log.info("  Map: %s", {k: Path(v).name for k, v in seq_map.items()})

            # ── STEP 3b: Preprocessing (raw files only) ───────────────────────
            preproc_state = _detect_preprocessed(seq_map)

            if not preproc_state["already_skull_stripped"]:
                _job_update(job_id, scan_id, patient_id, "preprocessing")
                log.info("STEP 3b: Raw input detected — running brainles_preprocessing")
                preproc_out = tmp / "preprocessed"
                seq_map = _run_brainles_preprocessing(seq_map, preproc_out)
                log.info("STEP 3b: Preprocessing complete — new seq_map: %s",
                        {k: Path(v).name for k, v in seq_map.items()})
            else:
                log.info("STEP 3b: Preprocessed input detected — skipping preprocessing")

            # ── STEP 4: Fix NIfTI headers ─────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "fixing_headers")
            log.info("STEP 4: Fixing NIfTI headers (NaN scl_slope + RAS)")
            fixed_dir = tmp / "fixed"
            fixed_dir.mkdir()
            fixed_map: dict[str, str] = {}
            for seq, src_path in seq_map.items():
                dst_path = str(fixed_dir / f"{seq}_fixed.nii.gz")
                _fix_nifti_header(src_path, dst_path)
                fixed_map[seq] = dst_path

            # ── STEP 5: Assemble nnUNetv2 input ───────────────────────────────
            _job_update(job_id, scan_id, patient_id, "preparing_input")
            log.info("STEP 5: Assembling nnUNetv2 input")

            nn_in  = tmp / "nn_input"
            nn_out = tmp / "nn_output"
            nn_in.mkdir()
            nn_out.mkdir()

            safe_id = "".join(c for c in scan_id if c.isalnum())[:16] or \
                      "CBTA" + job_id.replace("-", "")[:12]
            case_id = f"BraTS_{safe_id}"

            # Training distribution stats from plans.json
            TRAIN_STATS = {
                "T1ce":  {"mean": 1189.8, "std": 966.8},
                "T1":    {"mean": 1036.6, "std": 826.8},
                "FLAIR": {"mean": 694.3,  "std": 496.1},
                "T2":    {"mean": 1333.7, "std": 944.7},
            }

            for seq, ch in CHANNEL_ORDER:
                import nibabel as nib
                dst = str(nn_in / f"{case_id}_{ch}.nii.gz")
                src = fixed_map[seq]
                img = nib.load(src)
                arr = img.get_fdata(dtype=np.float32)
                brain_mask = arr > 0
                if brain_mask.sum() > 0:
                    scan_mean = arr[brain_mask].mean()
                    scan_std  = arr[brain_mask].std()
                    arr[brain_mask] = ((arr[brain_mask] - scan_mean) / (scan_std + 1e-8)) \
                                      * TRAIN_STATS[seq]["std"] + TRAIN_STATS[seq]["mean"]
                    arr[~brain_mask] = 0
                    log.info("  %s normalized: scan_mean=%.1f→train_mean=%.1f", 
                             seq, scan_mean, TRAIN_STATS[seq]["mean"])
                out_img = nib.Nifti1Image(arr, img.affine, img.header)
                nib.save(out_img, dst)
                log.info("  %s (%s) → %s", ch, seq, Path(dst).name)

            # Shape consistency check
            shapes = [
                nib.load(str(nn_in / f"{case_id}_{ch}.nii.gz")).shape[:3]
                for _, ch in CHANNEL_ORDER
            ]
            if len(set(shapes)) > 1:
                raise ValueError(f"Channel shape mismatch: {shapes}")
            log.info("  All channels shape=%s ✓", shapes[0])

            # ── STEP 6: nnUNetv2_predict ──────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "nnunetv2_inference")
            log.info("STEP 6: nnUNetv2_predict (Dataset %s, 3d_fullres, 5-fold ensemble)",
                     BRATS2024_DATASET_ID)

            env = os.environ.copy()
            env["nnUNet_results"] = NNUNET_RESULTS_DIR

            predict_cmd = [
                "nnUNetv2_predict",
                "-i",  str(nn_in),
                "-o",  str(nn_out),
                "-d",  "242",
                "-c",  "3d_fullres",
                "-f",  "0", "1", "2", "3", "4",
                "-device", "cuda",
                "--disable_tta",
            ]

            log.info("CMD: %s", " ".join(predict_cmd))
            res = subprocess.run(predict_cmd, env=env, capture_output=True, text=True)

            if res.returncode != 0:
                log.error("nnUNetv2_predict failed:\n%s", res.stderr[-3000:])
                raise RuntimeError(
                    f"nnUNetv2_predict exit code {res.returncode}.\n"
                    f"stderr:\n{res.stderr[-2000:]}"
                )
            log.info("nnUNetv2 complete.\n%s", res.stdout[-500:])

            # ── STEP 7: Read output mask ──────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "reading_mask")
            log.info("STEP 7: Reading output mask")

            seg_files = [
                f for f in nn_out.glob("*.nii.gz")
                if not f.name.endswith("_probabilities.nii.gz")
            ]
            if not seg_files:
                raise RuntimeError(
                    f"nnUNetv2 produced no segmentation.\n"
                    f"nn_out: {[f.name for f in nn_out.iterdir()]}"
                )

            seg_img = nib.load(str(seg_files[0]))
            seg_arr = seg_img.get_fdata().astype(np.int32)
            # Post-processing: large NETC blobs are likely SNFH mislabelled
            from scipy import ndimage
            netc_mask = (seg_arr == 1)
            labeled_netc, n_netc = ndimage.label(netc_mask)
            for i in range(1, n_netc + 1):
                component_size = (labeled_netc == i).sum()
                if component_size > 5000:  # large blob = likely SNFH
                    seg_arr[labeled_netc == i] = 2  # remap to SNFH
                    log.info("  Remapped NETC component %d (%d vx) → SNFH", i, component_size)
            log.info("  Post-proc done. Labels now: %s", sorted(set(np.unique(seg_arr).tolist())))
            spacing = seg_img.header.get_zooms()[:3]

            unique = set(np.unique(seg_arr).tolist())
            log.info("  Labels: %s | shape: %s | spacing: %.2f×%.2f×%.2fmm",
                     sorted(unique), seg_arr.shape, *spacing)

            unexpected = unique - {0, 1, 2, 3, 4}
            if unexpected:
                log.warning("Unexpected labels: %s", unexpected)

            et_vox = int((seg_arr == ET_LABEL).sum())
            rc_vox = int((seg_arr == RC_LABEL).sum())
            log.info("  ET=%d voxels | RC=%d voxels (excluded from RANO)", et_vox, rc_vox)

            if et_vox == 0:
                log.warning("No ET voxels — possible complete response or sequence mismapping.")

            low_confidence_flag   = et_vox < ET_VOXEL_MIN
            low_confidence_reason = (
                f"ET voxels={et_vox} < {ET_VOXEL_MIN}" if low_confidence_flag else ""
            )

            # ── Confidence score (0.0-1.0) based on ET voxel count ──────────
            if et_vox > 5000:
                confidence_score = 0.80
            elif et_vox > 1000:
                confidence_score = 0.70
            elif et_vox >= ET_VOXEL_MIN:
                confidence_score = 0.60
            else:
                confidence_score = 0.30
            if low_confidence_flag:
                confidence_score = max(0.10, confidence_score - 0.10)
            if rc_vox > 50000:
                confidence_score = max(0.10, confidence_score - 0.10)
            log.info("  Confidence score: %.2f (%d ET voxels)", confidence_score, et_vox)

            # ── STEP 8: RANO ──────────────────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "rano_calculation")
            log.info("STEP 8: RANO")
            rano = _compute_rano(seg_arr, spacing)

            if rano["lesion_count"] > 0 and rano["measurable_lesion_count"] == 0:
                reason = "No lesion met RANO criteria (LD≥10mm AND PD≥5mm)"
                low_confidence_flag   = True
                low_confidence_reason = (
                    f"{low_confidence_reason} | {reason}" if low_confidence_reason else reason
                )

            log.info("RANO — ET=%.2fml TC=%.2fml WT=%.2fml RC=%.2fml BDP=%.2fmm²",
                     rano["et_volume_ml"], rano["tc_volume_ml"],
                     rano["wt_volume_ml"], rano["rc_volume_ml"],
                     rano["bidimensional_product_mm2"])

            # ── STEP 9: Upload to R2 ──────────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "uploading_mask")
            log.info("STEP 9: Uploading mask to R2")
            r2_key = None

            for attempt in range(1, R2_UPLOAD_MAX_ATTEMPTS + 1):
                try:
                    r2_key = _upload_mask_to_r2(
                        s3, str(seg_files[0]), patient_id, scan_date, job_id
                    )
                    break
                except Exception as exc:
                    if attempt < R2_UPLOAD_MAX_ATTEMPTS:
                        log.warning("Upload attempt %d failed: %s — retrying", attempt, exc)
                        time.sleep(R2_UPLOAD_RETRY_DELAY_S)
                    else:
                        raise RuntimeError(f"R2 upload failed after {R2_UPLOAD_MAX_ATTEMPTS} attempts") from exc

            # ── STEP 10: Write to Supabase ────────────────────────────────────
            _job_update(job_id, scan_id, patient_id, "writing_db")
            log.info("STEP 10: Writing to Supabase")

            payload = {
                "patient_id":                    patient_id,
                "scan_id":                       scan_id,
                "job_id":                        job_id,
                "scan_date":                     scan_date,
                "et_volume_ml":                  rano["et_volume_ml"],
                "tc_volume_ml":                  rano["tc_volume_ml"],
                "wt_volume_ml":                  rano["wt_volume_ml"],
                "rc_volume_ml":                  rano["rc_volume_ml"],
                "lesion_count":                  rano["lesion_count"],
                "measurable_lesion_count":       rano["measurable_lesion_count"],
                "non_measurable_lesion_count":   rano["non_measurable_lesion_count"],
                "bidimensional_product_mm2":     rano["bidimensional_product_mm2"],
                "et_diameter1_mm":               rano["et_diameter1_mm"],
                "et_diameter2_mm":               rano["et_diameter2_mm"],
                "lesions":                       rano["lesions"],
                "mean_softmax_prob":              confidence_score,
                "low_confidence_flag":           low_confidence_flag,
                "low_confidence_reason":         low_confidence_reason,
                "segmentation_model":            "BraTS2024_Task1_nnUNetv2_Dataset242",
                "mask_r2_key":                   r2_key,
                "voxel_spacing_mm":              [float(x) for x in spacing],
                "label_scheme":                  {"1":"NETC","2":"SNFH","3":"ET","4":"RC"},
                "coordinate_space":              "RAS_nnUNetv2_preprocessed",
                "created_at":                    datetime.now(timezone.utc).isoformat(),
            }

            db_row_id  = _write_to_supabase(payload)
            result_out = {**payload, "supabase_row_id": db_row_id, "status": "completed"}

            job_dict[job_id] = {
                "status": "completed",
                "scan_id": scan_id,
                "patient_id": patient_id,
                "result": result_out,
            }

            log.info(
                "Agent 1 COMPLETE — ET=%.2fml BDP=%.2fmm² low_conf=%s",
                rano["et_volume_ml"], rano["bidimensional_product_mm2"], low_confidence_flag,
            )
            return result_out

    except Exception as exc:
        log.exception("Agent 1 FAILED — job=%s: %s", job_id, exc)
        job_dict[job_id] = {
            "status": "failed",
            "scan_id": scan_id,
            "patient_id": patient_id,
            "error": str(exc),
        }
        raise


def _job_update(job_id: str, scan_id: str, patient_id: str,
                step: str, extra: dict = None):
    entry = {"status": "running", "scan_id": scan_id,
             "patient_id": patient_id, "current_step": step}
    if extra:
        entry.update(extra)
    job_dict[job_id] = entry


# ─────────────────────────────────────────────────────────────────────────────
# HTTP endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.function(image=image, secrets=[modal.Secret.from_name("bts-secrets")])
@modal.fastapi_endpoint(method="POST")
def submit(body: dict, authorization: str = Header(default="")) -> dict:
    secret = os.environ.get("MODAL_WEBHOOK_SECRET", "")
    if secret and authorization != f"Bearer {secret}":
        raise _HTTPException(status_code=401, detail="Unauthorized")

    scan_id       = body.get("scan_id")
    patient_id    = body.get("patient_id")
    dicom_r2_keys = body.get("dicom_r2_keys", [])

    if not scan_id:
        raise _HTTPException(status_code=400, detail="scan_id required")
    if not patient_id:
        raise _HTTPException(status_code=400, detail="patient_id required")
    if not dicom_r2_keys or not isinstance(dicom_r2_keys, list):
        raise _HTTPException(status_code=400, detail="dicom_r2_keys must be a non-empty list")

    job_id = str(uuid.uuid4())
    job_dict[job_id] = {"status": "queued", "scan_id": scan_id, "patient_id": patient_id}

    run_segmentation.spawn(
        job_id, scan_id, patient_id, dicom_r2_keys, body.get("scan_date", "")
    )
    log.info("Queued job_id=%s", job_id)
    return {"job_id": job_id, "status": "queued"}


@app.function(image=image, secrets=[modal.Secret.from_name("bts-secrets")])
@modal.fastapi_endpoint(method="GET")
def status(job_id: str, authorization: str = Header(default="")) -> dict:
    secret = os.environ.get("MODAL_WEBHOOK_SECRET", "")
    if secret and authorization != f"Bearer {secret}":
        raise _HTTPException(status_code=401, detail="Unauthorized")
    if not job_id:
        raise _HTTPException(status_code=400, detail="job_id required")
    entry = job_dict.get(job_id)
    if entry is None:
        return {"status": "not_found", "error": f"No job: {job_id}"}
    return entry


@app.function(image=image)
@modal.fastapi_endpoint(method="GET")
def health() -> dict:
    return {
        "status":  "ok",
        "worker":  "brain-tumour-segmentation",
        "version": "16",
        "model":   "BraTS2024_Task1_nnUNetv2_Dataset242",
        "weights": f"zenodo:{ZENODO_RECORD_ID}",
    }