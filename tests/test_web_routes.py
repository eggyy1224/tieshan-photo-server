"""Tests for Web UI REST API routes."""

from __future__ import annotations

import numpy as np
import pytest

from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from src import db
from src.web.routes import register_routes


@pytest.fixture
def client():
    """Create a TestClient with registered routes."""
    mcp = FastMCP("test")
    register_routes(mcp)
    app = mcp.streamable_http_app()
    return TestClient(app)


@pytest.fixture
def seeded_db():
    """Seed DB with a scanned photo, faces, and persons for testing."""
    db.upsert_person("xu_tiancui", "許天催")
    db.upsert_person("xu_tiankui", "許天奎")

    pid = db.upsert_photo("test/group.jpg", "test", "group.jpg", 800, 600)
    db.mark_scanned(pid, 3)

    emb1 = np.random.randn(512).astype(np.float32)
    emb1 /= np.linalg.norm(emb1)
    emb2 = emb1 + np.random.randn(512).astype(np.float32) * 0.01
    emb2 /= np.linalg.norm(emb2)
    emb3 = np.random.randn(512).astype(np.float32)
    emb3 /= np.linalg.norm(emb3)

    fid1 = db.insert_face(pid, (0.1, 0.2, 0.15, 0.2), 0.95, emb1, age_est=40, gender_est="M")
    fid2 = db.insert_face(pid, (0.4, 0.2, 0.15, 0.2), 0.90, emb2, age_est=35, gender_est="M")
    fid3 = db.insert_face(pid, (0.7, 0.2, 0.15, 0.2), 0.80, emb3, age_est=30, gender_est="F")

    return {"photo_id": pid, "face_ids": [fid1, fid2, fid3]}


# ── GET /ui ──────────────────────────────────────────────────────

class TestUIPage:
    def test_returns_html(self, client):
        r = client.get("/ui")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "鐵山誌" in r.text


# ── GET /api/photos ──────────────────────────────────────────────

class TestPhotosAPI:
    def test_empty_db(self, client):
        r = client.get("/api/photos")
        assert r.status_code == 200
        data = r.json()
        assert data["photos"] == []
        assert data["total"] == 0

    def test_returns_scanned_photos(self, client, seeded_db):
        r = client.get("/api/photos")
        data = r.json()
        assert data["total"] == 1
        photo = data["photos"][0]
        assert photo["filename"] == "group.jpg"
        assert photo["face_count"] == 3

    def test_includes_unid_count(self, client, seeded_db):
        r = client.get("/api/photos")
        photo = r.json()["photos"][0]
        # All 3 faces are unidentified initially
        assert photo["unid_count"] == 3
        assert photo["anchor_count"] == 0

    def test_unid_count_after_anchor(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        # Create anchor
        db.insert_anchor(fid, "xu_tiancui", "manual", 1.0)
        db.update_face_match(fid, "xu_tiancui", 1.0, "anchor")

        r = client.get("/api/photos")
        photo = r.json()["photos"][0]
        assert photo["unid_count"] == 2
        assert photo["anchor_count"] == 1

    def test_source_dir_filter(self, client, seeded_db):
        r = client.get("/api/photos?source_dir=test")
        assert r.json()["total"] == 1

        r = client.get("/api/photos?source_dir=nonexistent")
        assert r.json()["total"] == 0

    def test_has_unidentified_filter(self, client, seeded_db):
        r = client.get("/api/photos?has_unidentified=1")
        assert r.json()["total"] == 1

    def test_rejected_faces_are_not_counted_as_unidentified(self, client, seeded_db):
        fid1, fid2, fid3 = seeded_db["face_ids"]
        db.update_face_match(fid1, None, None, "rejected")
        db.insert_anchor(fid2, "xu_tiancui", "manual", 1.0)
        db.update_face_match(fid2, "xu_tiancui", 1.0, "anchor")
        db.update_face_match(fid3, "xu_tiankui", 0.45, "auto")

        photos = client.get("/api/photos").json()
        assert photos["photos"][0]["unid_count"] == 0

        filtered = client.get("/api/photos?has_unidentified=1").json()
        assert filtered["total"] == 0

    def test_limit_and_offset(self, client, seeded_db):
        r = client.get("/api/photos?limit=1&offset=0")
        data = r.json()
        assert len(data["photos"]) == 1
        assert data["total"] == 1

    def test_pending_photos_excluded(self, client):
        """Photos with scan_status='pending' should not appear."""
        db.upsert_photo("test/pending.jpg", "test", "pending.jpg")
        r = client.get("/api/photos")
        assert r.json()["total"] == 0


# ── GET /api/photo/{photo_id} ────────────────────────────────────

class TestPhotoDetailAPI:
    def test_returns_detail(self, client, seeded_db):
        pid = seeded_db["photo_id"]
        r = client.get(f"/api/photo/{pid}")
        assert r.status_code == 200
        data = r.json()
        assert data["photo_id"] == pid
        assert len(data["faces"]) == 3
        # Faces should have bbox, matches, etc
        face = data["faces"][0]
        assert "bbox" in face
        assert len(face["bbox"]) == 4
        assert "matches" in face
        assert "det_score" in face

    def test_not_found(self, client):
        r = client.get("/api/photo/nonexistent")
        assert r.status_code == 404


# ── GET /api/persons ─────────────────────────────────────────────

class TestPersonsAPI:
    def test_returns_persons(self, client, seeded_db):
        r = client.get("/api/persons")
        assert r.status_code == 200
        persons = r.json()["persons"]
        ids = [p["person_id"] for p in persons]
        assert "xu_tiancui" in ids
        assert "xu_tiankui" in ids

    def test_anchor_count(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        db.insert_anchor(fid, "xu_tiancui", "manual", 1.0)

        r = client.get("/api/persons")
        for p in r.json()["persons"]:
            if p["person_id"] == "xu_tiancui":
                assert p["anchor_count"] == 1
                break


# ── GET /api/source_dirs ─────────────────────────────────────────

class TestSourceDirsAPI:
    def test_returns_dirs(self, client, seeded_db):
        r = client.get("/api/source_dirs")
        assert r.status_code == 200
        dirs = r.json()["source_dirs"]
        assert len(dirs) >= 1
        assert dirs[0]["source_dir"] == "test"


# ── GET /api/dashboard ───────────────────────────────────────────

class TestDashboardAPI:
    def test_empty_db(self, client):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert data["total_faces"] == 0
        assert data["coverage_pct"] == 0
        assert data["persons"] == []

    def test_with_data(self, client, seeded_db):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert data["total_faces"] == 3
        assert data["total_photos"] == 1
        assert data["unidentified"] == 3
        assert data["anchored"] == 0
        assert len(data["source_dirs"]) >= 1
        assert len(data["top_unid_photos"]) >= 1

    def test_after_anchor(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})

        r = client.get("/api/dashboard")
        data = r.json()
        assert data["anchored"] >= 1
        assert data["coverage_pct"] > 0
        assert len(data["persons"]) >= 1
        assert data["persons"][0]["person_id"] == "xu_tiancui"

    def test_rejected_faces_not_in_unidentified(self, client, seeded_db):
        fid1, fid2, fid3 = seeded_db["face_ids"]
        db.update_face_match(fid1, None, None, "rejected")
        db.insert_anchor(fid2, "xu_tiancui", "manual", 1.0)
        db.update_face_match(fid2, "xu_tiancui", 1.0, "anchor")
        db.update_face_match(fid3, "xu_tiankui", 0.45, "auto")

        data = client.get("/api/dashboard").json()
        assert data["rejected"] == 1
        assert data["unidentified"] == 0


# ── POST /api/anchor ─────────────────────────────────────────────

class TestAnchorAPI:
    def test_create_anchor(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        r = client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})
        assert r.status_code == 200
        data = r.json()
        assert data["anchor_id"] > 0
        assert data["display_name"] == "許天催"

    def test_missing_fields(self, client):
        r = client.post("/api/anchor", json={"face_id": 1})
        assert r.status_code == 400

    def test_invalid_json(self, client):
        r = client.post("/api/anchor", content=b"not json",
                        headers={"content-type": "application/json"})
        assert r.status_code == 400

    def test_duplicate_anchor_returns_existing_record(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]

        r1 = client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})
        r2 = client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["anchor_id"] == r1.json()["anchor_id"]

        count = db.get_conn().execute(
            "SELECT COUNT(*) FROM anchors WHERE face_id=?", (fid,)
        ).fetchone()[0]
        assert count == 1

    def test_conflicting_anchor_returns_error(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})

        r = client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiankui"})

        assert r.status_code == 400
        assert r.json()["error"] == "FACE_ALREADY_ANCHORED"


# ── DELETE /api/anchor/{face_id} ──────────────────────────────────

class TestDeleteAnchorAPI:
    def test_remove_anchor(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        # Create anchor first
        client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})
        # Remove it
        r = client.delete(f"/api/anchor/{fid}")
        assert r.status_code == 200
        data = r.json()
        assert data["removed"] is True
        assert data["display_name"] == "許天催"

    def test_remove_nonexistent(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        r = client.delete(f"/api/anchor/{fid}")
        assert r.status_code == 404

    def test_remove_anchor_clears_auto_matches_in_same_photo(self, client, seeded_db):
        fid1, fid2, _ = seeded_db["face_ids"]
        client.post("/api/anchor", json={"face_id": fid1, "person_id": "xu_tiancui"})

        face2 = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid2,)
        ).fetchone()
        assert face2["match_method"] == "auto"

        r = client.delete(f"/api/anchor/{fid1}")
        assert r.status_code == 200

        face1 = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid1,)
        ).fetchone()
        face2 = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid2,)
        ).fetchone()
        assert face1["person_id"] is None
        assert face1["match_method"] is None
        assert face2["person_id"] is None
        assert face2["match_method"] is None


# ── POST /api/face/{face_id}/clear ────────────────────────────────

class TestClearMatchAPI:
    def test_clear_auto_match(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        # Set up an auto-match
        db.update_face_match(fid, "xu_tiancui", 0.45, "auto")

        r = client.post(f"/api/face/{fid}/clear")
        assert r.status_code == 200
        assert r.json()["cleared"] is True

        # Verify face is now rejected
        face = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["person_id"] is None
        assert face["match_method"] == "rejected"

    def test_cannot_clear_anchor(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})

        r = client.post(f"/api/face/{fid}/clear")
        assert r.status_code == 400
        assert r.json()["error"] == "IS_ANCHOR"

    def test_clear_nonexistent_face(self, client):
        r = client.post("/api/face/99999/clear")
        assert r.status_code == 404


# ── POST /api/face/{face_id}/unreject ─────────────────────────────

class TestUnrejectAPI:
    def test_unreject_face(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        # Set up rejected state
        conn = db.get_conn()
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method='rejected' WHERE face_id=?",
            (fid,),
        )
        conn.commit()

        r = client.post(f"/api/face/{fid}/unreject")
        assert r.status_code == 200
        assert r.json()["unrejected"] is True

        face = conn.execute(
            "SELECT match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["match_method"] is None

    def test_unreject_nonexistent(self, client):
        r = client.post("/api/face/99999/unreject")
        assert r.status_code == 404

    def test_cannot_unreject_anchor(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        client.post("/api/anchor", json={"face_id": fid, "person_id": "xu_tiancui"})

        r = client.post(f"/api/face/{fid}/unreject")

        assert r.status_code == 400
        assert r.json()["error"] == "NOT_REJECTED"
        face = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["person_id"] == "xu_tiancui"
        assert face["match_method"] == "anchor"

    def test_cannot_unreject_auto_match(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]
        db.update_face_match(fid, "xu_tiancui", 0.45, "auto")

        r = client.post(f"/api/face/{fid}/unreject")

        assert r.status_code == 400
        assert r.json()["error"] == "NOT_REJECTED"
        face = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["person_id"] == "xu_tiancui"
        assert face["match_method"] == "auto"

    def test_cannot_unreject_unmatched_face(self, client, seeded_db):
        fid = seeded_db["face_ids"][0]

        r = client.post(f"/api/face/{fid}/unreject")

        assert r.status_code == 400
        assert r.json()["error"] == "NOT_REJECTED"
        face = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid,)
        ).fetchone()
        assert face["person_id"] is None
        assert face["match_method"] is None


# ── Rejected face persistence across cascade ──────────────────────

class TestRejectPersistence:
    def test_clear_then_anchor_stays_rejected(self, client, seeded_db):
        """The main bug: clearing auto-match then creating anchor should NOT re-match."""
        fid1, fid2, fid3 = seeded_db["face_ids"]

        # Step 1: Anchor fid1
        r = client.post("/api/anchor", json={"face_id": fid1, "person_id": "xu_tiancui"})
        assert r.status_code == 200

        # fid2 might have been auto-matched (similar embedding)
        face2 = db.get_conn().execute(
            "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid2,)
        ).fetchone()

        if face2["match_method"] == "auto":
            # Step 2: Clear auto-match on fid2
            r = client.post(f"/api/face/{fid2}/clear")
            assert r.status_code == 200

            # Verify rejected
            face2 = db.get_conn().execute(
                "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid2,)
            ).fetchone()
            assert face2["match_method"] == "rejected"

            # Step 3: Anchor another face → triggers cascade
            r = client.post("/api/anchor", json={"face_id": fid3, "person_id": "xu_tiankui"})
            assert r.status_code == 200

            # Step 4: fid2 should STILL be rejected
            face2 = db.get_conn().execute(
                "SELECT person_id, match_method FROM faces WHERE face_id=?", (fid2,)
            ).fetchone()
            assert face2["match_method"] == "rejected"
            assert face2["person_id"] is None
