#!/usr/bin/env python3
"""
Computes SHA-256 hash of already-downloaded nnU-Net weights in Modal Volume.
Weights are already in the volume from the manual download step.
Run: modal run scripts/setup_modal_volumes.py
"""
import modal

app = modal.App("setup-nnunet-weights")
vol = modal.Volume.from_name("nnunet-weights", create_if_missing=True)

# Exact path confirmed from Modal Volume
CHECKPOINT_PATH = (
    "results/3d_fullres/Task082_BraTS2020/"
    "nnUNetTrainerV2BraTSRegions_DA4_BN_BD__nnUNetPlansv2.1_bs5/"
    "fold_0/model_final_checkpoint.model"
)

@app.function(
    volumes={"/weights": vol},
    timeout=600,
    image=modal.Image.debian_slim()
)
def compute_hash():
    import os, hashlib

    full_path = f"/weights/{CHECKPOINT_PATH}"

    if not os.path.exists(full_path):
        print(f"ERROR: File not found at {full_path}")
        print("Files in /weights:")
        for root, dirs, files in os.walk("/weights"):
            for f in files:
                print(f"  {os.path.join(root, f)}")
        return

    size_mb = os.path.getsize(full_path) / (1024*1024)
    print(f"Found: {full_path}")
    print(f"Size:  {size_mb:.1f} MB")
    print("Computing SHA-256...")

    h = hashlib.sha256()
    with open(full_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)

    hv = h.hexdigest()
    print("\n" + "="*60)
    print("SHA-256 HASH — paste into segmentation_worker.py:")
    print(f"\n  {hv}\n")
    print("="*60)
    print("\nFind this line in modal_workers/segmentation_worker.py:")
    print('  NNUNET_WEIGHT_HASH = "REPLACE_WITH_ACTUAL_SHA256_HASH"')
    print("Replace with:")
    print(f'  NNUNET_WEIGHT_HASH = "{hv}"')
    print("\nThen run: modal deploy modal_workers/segmentation_worker.py")

@app.local_entrypoint()
def main():
    print("Computing SHA-256 hash of checkpoint in Modal Volume...\n")
    compute_hash.remote()
    print("\nDone.")
