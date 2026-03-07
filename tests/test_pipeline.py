"""Tests for the preprocessing module (no model required)."""

from __future__ import annotations

import numpy as np
import pytest

from src.preprocessing import preprocess


class TestPreprocess:
    def test_downscale_large_image(self):
        img = np.random.randint(0, 255, (4000, 3000, 3), dtype=np.uint8)
        result = preprocess(img, target_long_edge=2048)
        h, w = result.shape[:2]
        assert max(h, w) <= 2048

    def test_upscale_small_image(self):
        img = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)
        result = preprocess(img, min_long_edge=640)
        h, w = result.shape[:2]
        assert max(h, w) >= 640

    def test_normal_size_unchanged(self):
        img = np.random.randint(0, 255, (1000, 800, 3), dtype=np.uint8)
        result = preprocess(img)
        h, w = result.shape[:2]
        # Size should be close to original (CLAHE doesn't change dimensions)
        assert abs(h - 1000) < 10
        assert abs(w - 800) < 10

    def test_output_same_channels(self):
        img = np.random.randint(0, 255, (640, 480, 3), dtype=np.uint8)
        result = preprocess(img)
        assert result.shape[2] == 3

    def test_clahe_increases_contrast(self):
        # Create a low-contrast image
        img = np.full((640, 480, 3), 128, dtype=np.uint8)
        img[:320, :, :] = 120
        img[320:, :, :] = 136

        result = preprocess(img)
        # After CLAHE, contrast should be higher
        std_before = img.astype(float).std()
        std_after = result.astype(float).std()
        assert std_after >= std_before
