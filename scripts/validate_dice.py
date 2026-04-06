"""
Offline Dice validation script.
Compares the system's predicted segmentation mask against a ground truth mask.

Usage:
    python scripts/validate_dice.py \
        --gt  path/to/PatientID_0014_Timepoint_5_tumorMask.nii.gz \
        --scan-id  15e2effb-0192-4204-9cfb-6df66e7207ea

The script downloads the predicted mask from R2 using credentials from .env,
then computes ET / TC / WT Dice scores and prints a summary table.

Requirements: nibabel, numpy, boto3, python-dotenv (all already in your venv)
"""
import argparse
import sys
import tempfile
from pathlib import Path


def _load_mask(path: str):
    import nibabel as nib
    import numpy as np
    from scipy import ndimage
    img = nib.load(path)
    img = nib.as_closest_canonical(img)
    arr = img.get_fdata().astype(np.int32)
    # BraTS 2024 post-treatment labels: 1=NETC, 2=SNFH, 3=ET, 4=RC
    # Post-processing: remap large NETC blobs to SNFH
    netc_mask = (arr == 1)
    labeled_netc, n_netc = ndimage.label(netc_mask)
    for i in range(1, n_netc + 1):
        if (labeled_netc == i).sum() > 5000:
            arr[labeled_netc == i] = 2
    return arr


def _dice(pred, gt, labels: list) -> float:
    import numpy as np
    pred_mask = np.isin(pred, labels)
    gt_mask   = np.isin(gt,   labels)
    intersection = (pred_mask & gt_mask).sum()
    denom = pred_mask.sum() + gt_mask.sum()
    if denom == 0:
        return 1.0  # both empty — perfect match
    return float(2 * intersection / denom)


def _download_predicted_mask(scan_id: str, tmp_dir: str) -> str:
    import os
    import boto3
    from dotenv import load_dotenv
    load_dotenv()

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET_NAME"]

    # Find the mask key in agent1_results
    from app.database.supabase_client import get_supabase_client
    db = get_supabase_client()
    r  = db.table("agent1_results").select("mask_r2_key, patient_id").eq("scan_id", scan_id).execute()
    if not r.data:
        raise RuntimeError(f"No agent1_results row found for scan_id={scan_id}")

    mask_key = r.data[0].get("mask_r2_key")
    if not mask_key:
        raise RuntimeError(f"mask_r2_key is null for scan_id={scan_id}")

    local_path = Path(tmp_dir) / "predicted_mask.nii.gz"
    print(f"Downloading predicted mask from R2: {mask_key}")
    s3.download_file(bucket, mask_key, str(local_path))
    print(f"Downloaded to: {local_path}")
    return str(local_path)


def main():
    parser = argparse.ArgumentParser(description="Compute Dice scores vs ground truth mask")
    parser.add_argument("--gt",      required=True, help="Path to ground truth mask (.nii or .nii.gz)")
    parser.add_argument("--scan-id", required=True, help="Scan UUID from Supabase")
    args = parser.parse_args()

    if not Path(args.gt).exists():
        print(f"ERROR: GT mask not found: {args.gt}")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        try:
            pred_path = _download_predicted_mask(args.scan_id, tmp)
        except Exception as e:
            print(f"ERROR downloading predicted mask: {e}")
            sys.exit(1)

        print("\nLoading masks...")
        gt_arr   = _load_mask(args.gt)
        pred_arr = _load_mask(pred_path)

        if gt_arr.shape != pred_arr.shape:
            print(f"WARNING: Shape mismatch — GT {gt_arr.shape} vs Pred {pred_arr.shape}")
            print("Attempting to proceed anyway (shapes must match for valid Dice)")

        print(f"\nGT   shape: {gt_arr.shape}  | unique labels: {sorted(set(gt_arr.flatten().tolist()))[:10]}")
        print(f"Pred shape: {pred_arr.shape} | unique labels: {sorted(set(pred_arr.flatten().tolist()))[:10]}")

        # ── Volumes ───────────────────────────────────────────────────────────
        print("\n── Ground Truth Volumes ──")
        for label, name in [(1,"NETC"), (2,"SNFH"), (3,"ET"), (4,"RC")]:
            vox = int((gt_arr == label).sum())
            print(f"  Label {label} ({name}): {vox:,} voxels = {vox/1000:.2f} mL")

        print("\n── Predicted Volumes ──")
        for label, name in [(1,"NCR/NET"), (2,"Oedema/ED"), (3,"ET (Enhancing)")]:
            vox = int((pred_arr == label).sum())
            print(f"  Label {label} ({name}): {vox:,} voxels = {vox/1000:.2f} mL")

        # ── Dice scores ───────────────────────────────────────────────────────
        # Per spec Section 10: ET first, then TC, then WT
        dice_et = _dice(pred_arr, gt_arr, [3])
        dice_tc = _dice(pred_arr, gt_arr, [1, 3])
        dice_wt = _dice(pred_arr, gt_arr, [1, 2, 3])
        dice_rc = _dice(pred_arr, gt_arr, [4])
        

        print("\n" + "="*50)
        print("DICE SCORES (higher = better, 1.0 = perfect)")
        print("="*50)
        print(f"  ET Dice  (label 3)       : {dice_et:.4f}  ({dice_et*100:.1f}%)")
        print(f"  TC Dice  (labels 1+3)    : {dice_tc:.4f}  ({dice_tc*100:.1f}%)")
        print(f"  WT Dice  (labels 1+2+3)  : {dice_wt:.4f}  ({dice_wt*100:.1f}%)")
        print(f"  RC Dice  (label 4)       : {dice_rc:.4f}  ({dice_rc*100:.1f}%)")
        print("="*50)

        # ── Interpretation ────────────────────────────────────────────────────
        print("\nInterpretation:")
        thresholds = [(0.8, "Excellent"), (0.6, "Good"), (0.4, "Acceptable"), (0.0, "Poor")]
        for score, label, region in [(dice_et, "ET", "ET Dice"), (dice_tc, "TC", "TC Dice"), (dice_wt, "WT", "WT Dice")]:
            for thresh, rating in thresholds:
                if score >= thresh:
                    print(f"  {region}: {rating} ({score:.3f})")
                    break

        print(f"\nScan ID: {args.scan_id}")
        print(f"GT mask: {args.gt}")


if __name__ == "__main__":
    main()