"""Tests for cosine similarity matching."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

_tmpdir = tempfile.mkdtemp()
os.environ["PHOTO_DB_PATH"] = os.path.join(_tmpdir, "test_match.db")

from src import db
from src.matching import cosine_similarity, confidence_level, match_face


@pytest.fixture(autouse=True)
def fresh_db():
    db.close()
    test_path = os.path.join(_tmpdir, "test_match.db")
    if os.path.exists(test_path):
        os.remove(test_path)
    db._conn = None
    yield
    db.close()


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = np.random.randn(512).astype(np.float32)
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-5)

    def test_orthogonal_vectors(self):
        a = np.zeros(512, dtype=np.float32)
        b = np.zeros(512, dtype=np.float32)
        a[0] = 1.0
        b[1] = 1.0
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-5)

    def test_opposite_vectors(self):
        v = np.random.randn(512).astype(np.float32)
        assert cosine_similarity(v, -v) == pytest.approx(-1.0, abs=1e-5)

    def test_zero_vector(self):
        v = np.random.randn(512).astype(np.float32)
        z = np.zeros(512, dtype=np.float32)
        assert cosine_similarity(v, z) == 0.0


class TestConfidenceLevel:
    def test_high(self):
        assert confidence_level(0.50) == "HIGH"
        assert confidence_level(0.45) == "HIGH"

    def test_medium(self):
        assert confidence_level(0.40) == "MEDIUM"
        assert confidence_level(0.35) == "MEDIUM"

    def test_low(self):
        assert confidence_level(0.30) == "LOW"
        assert confidence_level(0.25) == "LOW"

    def test_none(self):
        assert confidence_level(0.20) == "NONE"
        assert confidence_level(0.0) == "NONE"


class TestMatchFace:
    def test_no_anchors_returns_empty(self):
        emb = np.random.randn(512).astype(np.float32)
        assert match_face(emb) == []

    def test_match_with_anchor(self):
        # Create person, photo, face, anchor
        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo("test/solo.jpg", "test", "solo.jpg")
        anchor_emb = np.random.randn(512).astype(np.float32)
        anchor_emb /= np.linalg.norm(anchor_emb)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, anchor_emb)
        db.insert_anchor(fid, "xu_tiancui", "manual")

        # Query with same embedding should match perfectly
        matches = match_face(anchor_emb, top_k=3)
        assert len(matches) >= 1
        assert matches[0]["person_id"] == "xu_tiancui"
        assert matches[0]["score"] > 0.99

    def test_match_different_person_lower_score(self):
        db.upsert_person("xu_tiancui", "許天催")
        db.upsert_person("xu_tiankui", "許天奎")

        pid = db.upsert_photo("test/a.jpg", "test", "a.jpg")
        emb_a = np.random.randn(512).astype(np.float32)
        emb_a /= np.linalg.norm(emb_a)
        fid_a = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb_a)
        db.insert_anchor(fid_a, "xu_tiancui", "manual")

        pid2 = db.upsert_photo("test/b.jpg", "test", "b.jpg")
        emb_b = np.random.randn(512).astype(np.float32)
        emb_b /= np.linalg.norm(emb_b)
        fid_b = db.insert_face(pid2, (0.1, 0.2, 0.3, 0.4), 0.9, emb_b)
        db.insert_anchor(fid_b, "xu_tiankui", "manual")

        # Query with emb_a should rank xu_tiancui higher
        matches = match_face(emb_a, top_k=3)
        if len(matches) >= 2:
            assert matches[0]["person_id"] == "xu_tiancui"
