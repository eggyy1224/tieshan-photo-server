"""Tests for database operations."""

from __future__ import annotations

import numpy as np
import pytest

from src import db


class TestPhotos:
    def test_upsert_and_get(self):
        pid = db.upsert_photo("test/photo.jpg", "test", "photo.jpg", 800, 600)
        photo = db.get_photo(pid)
        assert photo is not None
        assert photo["rel_path"] == "test/photo.jpg"
        assert photo["width"] == 800
        assert photo["scan_status"] == "pending"

    def test_mark_scanned(self):
        pid = db.upsert_photo("test/a.jpg", "test", "a.jpg")
        db.mark_scanned(pid, 3)
        photo = db.get_photo(pid)
        assert photo["scan_status"] == "scanned"
        assert photo["face_count"] == 3

    def test_get_by_path(self):
        db.upsert_photo("dir/file.jpg", "dir", "file.jpg")
        photo = db.get_photo_by_path("dir/file.jpg")
        assert photo is not None
        assert photo["filename"] == "file.jpg"


class TestFaces:
    def test_insert_and_retrieve(self):
        pid = db.upsert_photo("test/b.jpg", "test", "b.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.95, emb, age_est=30, gender_est="M")
        assert fid > 0

        faces = db.get_faces_for_photo(pid)
        assert len(faces) == 1
        assert faces[0]["det_score"] == pytest.approx(0.95)
        assert faces[0]["age_est"] == 30

    def test_embedding_roundtrip(self):
        original = np.random.randn(512).astype(np.float32)
        blob = db.embedding_to_blob(original)
        recovered = db.blob_to_embedding(blob)
        np.testing.assert_array_almost_equal(original, recovered)

    def test_delete_faces(self):
        pid = db.upsert_photo("test/c.jpg", "test", "c.jpg")
        emb = np.random.randn(512).astype(np.float32)
        db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        db.insert_face(pid, (0.5, 0.6, 0.1, 0.1), 0.8, emb)
        assert len(db.get_faces_for_photo(pid)) == 2

        db.delete_faces_for_photo(pid)
        assert len(db.get_faces_for_photo(pid)) == 0


class TestPersons:
    def test_upsert_and_find(self):
        db.upsert_person("xu_tiancui", "許天催", '["台灣三世"]', "M", 3, "人物/許天催.md")
        person = db.get_person("xu_tiancui")
        assert person is not None
        assert person["display_name"] == "許天催"

        found = db.find_person_by_name("許天催")
        assert found is not None
        assert found["person_id"] == "xu_tiancui"

    def test_find_by_partial_name(self):
        db.upsert_person("xu_tiankui", "許天奎", '["鐵鋒"]', "M", 3)
        found = db.find_person_by_name("天奎")
        assert found is not None
        assert found["person_id"] == "xu_tiankui"

    def test_find_by_alias(self):
        db.upsert_person("xu_tiankui", "許天奎", '["鐵鋒", "鐵峰"]', "M", 3)
        found = db.find_person_by_name("鐵鋒")
        assert found is not None
        assert found["person_id"] == "xu_tiankui"


class TestAnchors:
    def test_create_anchor(self):
        pid = db.upsert_photo("test/d.jpg", "test", "d.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        db.upsert_person("xu_tiancui", "許天催")

        aid = db.insert_anchor(fid, "xu_tiancui", "manual", 1.0, "test")
        assert aid > 0

        anchors = db.get_anchors_for_person("xu_tiancui")
        assert len(anchors) == 1
        assert anchors[0]["face_id"] == fid

    def test_duplicate_anchor_returns_existing_id(self):
        pid = db.upsert_photo("test/d2.jpg", "test", "d2.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        db.upsert_person("xu_tiancui", "許天催")

        aid1 = db.insert_anchor(fid, "xu_tiancui", "manual", 1.0, "test")
        aid2 = db.insert_anchor(fid, "xu_tiancui", "manual", 1.0, "test")

        assert aid2 == aid1
        assert len(db.get_anchors_for_person("xu_tiancui")) == 1

    def test_conflicting_anchor_raises(self):
        pid = db.upsert_photo("test/d3.jpg", "test", "d3.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        db.upsert_person("xu_tiancui", "許天催")
        db.upsert_person("xu_tiankui", "許天奎")

        db.insert_anchor(fid, "xu_tiancui", "manual", 1.0, "test")

        with pytest.raises(ValueError):
            db.insert_anchor(fid, "xu_tiankui", "manual", 1.0, "test")


class TestStats:
    def test_empty_stats(self):
        stats = db.get_stats()
        assert stats["total_photos"] == 0
        assert stats["face_count"] == 0

    def test_stats_after_inserts(self):
        pid = db.upsert_photo("test/e.jpg", "test", "e.jpg")
        db.mark_scanned(pid, 2)
        emb = np.random.randn(512).astype(np.float32)
        db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        db.insert_face(pid, (0.5, 0.6, 0.1, 0.1), 0.8, emb)

        stats = db.get_stats()
        assert stats["total_photos"] == 1
        assert stats["scanned"] == 1
        assert stats["face_count"] == 2

    def test_stats_by_person_does_not_multiply_rows(self):
        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo("test/f.jpg", "test", "f.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid1 = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        fid2 = db.insert_face(pid, (0.5, 0.6, 0.1, 0.1), 0.8, emb)
        db.update_face_match(fid1, "xu_tiancui", 1.0, "anchor")
        db.update_face_match(fid2, "xu_tiancui", 0.8, "auto")
        db.insert_anchor(fid1, "xu_tiancui", "manual", 1.0, "test")

        stats = db.get_stats_by_person()
        row = next(r for r in stats if r["person_id"] == "xu_tiancui")
        assert row["photo_count"] == 1
        assert row["face_count"] == 2
        assert row["anchor_count"] == 1
