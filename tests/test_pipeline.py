"""Tests for the preprocessing module (no model required)."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from src import db
from src.pipeline import process_photo
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


class TestProcessPhoto:
    def test_force_rescan_failure_preserves_existing_faces_and_anchors(self, tmp_path):
        photo_path = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100), color="white").save(photo_path)

        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo(str(photo_path), "", photo_path.name, 100, 100)
        db.mark_scanned(pid, 1)
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        db.insert_anchor(fid, "xu_tiancui", "manual", 1.0, "test")
        db.update_face_match(fid, "xu_tiancui", 1.0, "anchor")

        with patch("src.pipeline.detect_faces", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                process_photo(photo_path, force_rescan=True)

        photo = db.get_photo(pid)
        faces = db.get_faces_for_photo(pid)
        anchors = db.get_anchors_for_person("xu_tiancui")
        assert photo is not None
        assert photo["scan_status"] == "scanned"
        assert len(faces) == 1
        assert len(anchors) == 1
