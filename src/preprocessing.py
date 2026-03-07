"""Old photo preprocessing: CLAHE contrast enhancement + denoising."""

from __future__ import annotations

import cv2
import numpy as np

from . import log


def preprocess(img: np.ndarray, target_long_edge: int = 2048, min_long_edge: int = 640) -> np.ndarray:
    """Apply CLAHE + bilateral denoise + resize for old photo face detection.

    Args:
        img: BGR image (OpenCV format).
        target_long_edge: Downscale if longer edge exceeds this.
        min_long_edge: Upscale 2x if longer edge is below this.

    Returns:
        Preprocessed BGR image.
    """
    h, w = img.shape[:2]
    long_edge = max(h, w)

    # Resize if needed
    if long_edge > target_long_edge:
        scale = target_long_edge / long_edge
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        log.debug("downscaled", original=f"{w}x{h}", scale=f"{scale:.2f}")
    elif long_edge < min_long_edge:
        scale = 2.0
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        log.debug("upscaled 2x", original=f"{w}x{h}")

    # Convert to LAB for CLAHE on L channel
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
    img_enhanced = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # Bilateral filter: edge-preserving denoise
    img_denoised = cv2.bilateralFilter(img_enhanced, d=9, sigmaColor=75, sigmaSpace=75)

    return img_denoised


def preprocess_for_comparison(
    img: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return both original-resized and CLAHE-enhanced versions for pilot comparison.

    Returns:
        (resized_original, clahe_enhanced)
    """
    h, w = img.shape[:2]
    long_edge = max(h, w)

    # Standardize size
    if long_edge > 2048:
        scale = 2048 / long_edge
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    elif long_edge < 640:
        img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    original = img.copy()
    enhanced = preprocess(img)
    return original, enhanced
