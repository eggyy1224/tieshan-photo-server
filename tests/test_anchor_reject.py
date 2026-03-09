"""Tests for anchor cascade matching and rejected face mechanism."""

from __future__ import annotations

import numpy as np
import pytest

from src import db
from src.tools.photo_anchor import photo_anchor


def _make_face(person_id="xu_tiancui", display_name="許天催"):
    """Helper: create a person, photo, and face with a known embedding."""
    db.upsert_person(person_id, display_name)
    pid = db.upsert_photo(f"test/{person_id}.jpg", "test", f"{person_id}.jpg")
    db.mark_scanned(pid, 1)
    emb = np.random.randn(512).astype(np.float32)
    emb /= np.linalg.norm(emb)
    fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
    return pid, fid, emb


class TestAnchorCascade:
    @pytest.mark.asyncio
    async def test_anchor_creates_auto_matches(self):
        """Anchoring a face should auto-match similar unmatched faces."""
        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo("test/group.jpg", "test", "group.jpg")
        db.mark_scanned(pid, 2)

        # Two faces with very similar embeddings
        base_emb = np.random.randn(512).astype(np.float32)
        base_emb /= np.linalg.norm(base_emb)
        similar_emb = base_emb + np.random.randn(512).astype(np.float32) * 0.01
        similar_emb /= np.linalg.norm(similar_emb)

        fid1 = db.insert_face(pid, (0.1, 0.2, 0.1, 0.1), 0.9, base_emb)
        fid2 = db.insert_face(pid, (0.5, 0.2, 0.1, 0.1), 0.85, similar_emb)

        result = await photo_anchor(fid1, "xu_tiancui")
        assert "error" not in result
        assert result["anchor_id"] > 0

        # fid2 should now have an auto-match
        face2 = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid2,)
        ).fetchone()
        assert face2["person_id"] == "xu_tiancui"
        assert face2["match_method"] == "auto"

    @pytest.mark.asyncio
    async def test_anchor_invalid_face(self):
        db.upsert_person("xu_tiancui", "許天催")
        result = await photo_anchor(99999, "xu_tiancui")
        assert result["error"] == "FACE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_anchor_invalid_person(self):
        pid = db.upsert_photo("test/x.jpg", "test", "x.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)
        result = await photo_anchor(fid, "nonexistent_person")
        assert result["error"] == "PERSON_NOT_FOUND"


class TestRejectedFace:
    def test_rejected_face_survives_cascade(self):
        """A face with match_method='rejected' should not be auto-matched."""
        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo("test/group2.jpg", "test", "group2.jpg")
        db.mark_scanned(pid, 2)

        base_emb = np.random.randn(512).astype(np.float32)
        base_emb /= np.linalg.norm(base_emb)
        similar_emb = base_emb + np.random.randn(512).astype(np.float32) * 0.01
        similar_emb /= np.linalg.norm(similar_emb)

        fid1 = db.insert_face(pid, (0.1, 0.2, 0.1, 0.1), 0.9, base_emb)
        fid2 = db.insert_face(pid, (0.5, 0.2, 0.1, 0.1), 0.85, similar_emb)

        # Mark fid2 as rejected
        db.update_face_match(fid2, None, None, "rejected")
        # Verify it's rejected
        conn = db.get_conn()
        face2 = conn.execute(
            "SELECT match_method FROM faces WHERE face_id=?", (fid2,)
        ).fetchone()
        assert face2["match_method"] == "rejected"

        # Now anchor fid1 — cascade should skip fid2
        db.insert_anchor(fid1, "xu_tiancui", "manual", 1.0)
        db.update_face_match(fid1, "xu_tiancui", 1.0, "anchor")

        # Simulate the cascade query from photo_anchor
        unmatched = conn.execute(
            "SELECT face_id FROM faces WHERE person_id IS NULL AND COALESCE(match_method,'') != 'rejected'"
        ).fetchall()
        unmatched_ids = [r["face_id"] for r in unmatched]

        # fid2 should NOT be in the unmatched list
        assert fid2 not in unmatched_ids

    def test_rejected_face_has_null_person_id(self):
        """Rejected faces have person_id=NULL but match_method='rejected'."""
        pid = db.upsert_photo("test/r.jpg", "test", "r.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)

        # Simulate clear auto-match (sets rejected)
        conn = db.get_conn()
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method='rejected' WHERE face_id=?",
            (fid,),
        )
        conn.commit()

        face = conn.execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["person_id"] is None
        assert face["match_method"] == "rejected"

    def test_unreject_restores_to_unmatched(self):
        """Unrejecting a face sets match_method=NULL, making it matchable again."""
        pid = db.upsert_photo("test/u.jpg", "test", "u.jpg")
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)

        conn = db.get_conn()
        # Reject
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method='rejected' WHERE face_id=?",
            (fid,),
        )
        conn.commit()

        # Unreject
        conn.execute(
            "UPDATE faces SET match_method=NULL WHERE face_id=?",
            (fid,),
        )
        conn.commit()

        face = conn.execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["person_id"] is None
        assert face["match_method"] is None

        # Should now appear in unmatched query
        unmatched = conn.execute(
            "SELECT face_id FROM faces WHERE person_id IS NULL AND COALESCE(match_method,'') != 'rejected'"
        ).fetchall()
        assert fid in [r["face_id"] for r in unmatched]

    @pytest.mark.asyncio
    async def test_full_reject_cycle(self):
        """End-to-end: anchor → auto-match → clear(reject) → re-anchor → stays rejected."""
        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo("test/cycle.jpg", "test", "cycle.jpg")
        db.mark_scanned(pid, 3)

        base_emb = np.random.randn(512).astype(np.float32)
        base_emb /= np.linalg.norm(base_emb)
        similar1 = base_emb + np.random.randn(512).astype(np.float32) * 0.01
        similar1 /= np.linalg.norm(similar1)
        similar2 = base_emb + np.random.randn(512).astype(np.float32) * 0.01
        similar2 /= np.linalg.norm(similar2)

        fid_anchor = db.insert_face(pid, (0.1, 0.1, 0.1, 0.1), 0.95, base_emb)
        fid_reject = db.insert_face(pid, (0.3, 0.1, 0.1, 0.1), 0.90, similar1)
        fid_keep = db.insert_face(pid, (0.5, 0.1, 0.1, 0.1), 0.85, similar2)

        # Step 1: Anchor fid_anchor → both others get auto-matched
        result = await photo_anchor(fid_anchor, "xu_tiancui")
        assert result["new_auto_matches"] >= 1

        # Step 2: Reject fid_reject
        conn = db.get_conn()
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method='rejected' WHERE face_id=?",
            (fid_reject,),
        )
        conn.commit()

        # Step 3: Create another person and anchor — triggers cascade
        db.upsert_person("xu_tiankui", "許天奎")
        pid2 = db.upsert_photo("test/solo.jpg", "test", "solo.jpg")
        other_emb = np.random.randn(512).astype(np.float32)
        other_emb /= np.linalg.norm(other_emb)
        fid_other = db.insert_face(pid2, (0.1, 0.1, 0.3, 0.3), 0.9, other_emb)
        await photo_anchor(fid_other, "xu_tiankui")

        # Step 4: Verify fid_reject is still rejected
        face_reject = conn.execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid_reject,)
        ).fetchone()
        assert face_reject["person_id"] is None
        assert face_reject["match_method"] == "rejected"
