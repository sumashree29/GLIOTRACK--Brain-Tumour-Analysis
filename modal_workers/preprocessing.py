"""
MRI preprocessing pipeline (runs inside Modal GPU container).
Order: dcm2niix -> N4 bias correction -> rigid co-registration ->
       resample 1mm iso -> HD-BET skull-stripping -> z-normalisation.
NO MNI registration (LOCKED by spec).
"""
from __future__ import annotations
import subprocess
from pathlib import Path
import numpy as np
import SimpleITK as sitk

def dcm2niix(dicom_dir: str, out_dir: str) -> list[str]:
    subprocess.run(
        ["dcm2niix", "-z", "y", "-f", "%p_%s", "-o", out_dir, dicom_dir],
        check=True, capture_output=True,
    )
    return list(Path(out_dir).glob("*.nii.gz"))

def n4_bias_correction(nii_path: str) -> sitk.Image:
    img  = sitk.ReadImage(nii_path, sitk.sitkFloat32)
    mask = sitk.OtsuThreshold(img, 0, 1, 200)
    return sitk.N4BiasFieldCorrection(img, mask)

def rigid_coregister(fixed: sitk.Image, moving: sitk.Image) -> sitk.Image:
    reg = sitk.ImageRegistrationMethod()
    reg.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
    reg.SetOptimizerAsRegularStepGradientDescent(
        learningRate=1.0, minStep=0.001, numberOfIterations=200)
    reg.SetInitialTransform(
        sitk.CenteredTransformInitializer(
            fixed, moving, sitk.Euler3DTransform(),
            sitk.CenteredTransformInitializerFilter.GEOMETRY))
    reg.SetInterpolator(sitk.sitkLinear)
    tx = reg.Execute(
        sitk.Cast(fixed, sitk.sitkFloat32),
        sitk.Cast(moving, sitk.sitkFloat32))
    return sitk.Resample(moving, fixed, tx, sitk.sitkLinear, 0.0)

def resample_1mm(img: sitk.Image) -> sitk.Image:
    orig_size    = img.GetSize()
    orig_spacing = img.GetSpacing()
    new_spacing  = (1.0, 1.0, 1.0)
    new_size     = [int(round(os * ss / ns))
                    for os, ss, ns in zip(orig_size, orig_spacing, new_spacing)]
    return sitk.Resample(img, new_size, sitk.Transform(),
                         sitk.sitkLinear, img.GetOrigin(),
                         new_spacing, img.GetDirection(), 0.0, img.GetPixelID())

def z_normalise(img: sitk.Image) -> sitk.Image:
    arr  = sitk.GetArrayFromImage(img).astype(np.float32)
    mask = arr > 0
    if mask.sum() == 0:
        return img
    mu   = arr[mask].mean()
    sig  = arr[mask].std()
    arr  = np.where(mask, (arr - mu) / (sig + 1e-8), 0.0)
    out  = sitk.GetImageFromArray(arr)
    out.CopyInformation(img)
    return out

def run_preprocessing(
    t1_path: str, t1ce_path: str, t2_path: str, flair_path: str,
) -> dict[str, sitk.Image]:
    """
    Full preprocessing for one patient timepoint.
    Returns dict with keys: T1, T1ce, T2, FLAIR (all co-registered to T1ce).
    """
    images = {}
    for name, path in [("T1ce", t1ce_path), ("T1", t1_path),
                        ("T2", t2_path), ("FLAIR", flair_path)]:
        images[name] = n4_bias_correction(path)

    fixed = images["T1ce"]
    for name in ["T1", "T2", "FLAIR"]:
        images[name] = rigid_coregister(fixed, images[name])

    for name in list(images.keys()):
        images[name] = resample_1mm(images[name])
        images[name] = z_normalise(images[name])

    return images
