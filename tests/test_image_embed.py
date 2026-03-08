"""Tests for image embedding and semantic search."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

# Override DB path before importing db module (if not already set by another test)
if "PHOTO_DB_PATH" not in os.environ:
    _tmpdir = tempfile.mkdtemp()
    os.environ["PHOTO_DB_PATH"] = os.path.join(_tmpdir, "test_face.db")

from src import db
from src.config import EMBED_DIM, EMBED_MODEL, PHOTO_DB_PATH


@pytest.fixture(autouse=True)
def fresh_db():
    """Ensure a fresh database for each test."""
    db.close()
    db_path = str(PHOTO_DB_PATH)
    if os.path.exists(db_path):
        os.remove(db_path)
    db._conn = None
    # Also invalidate embed cache
    from src.image_embed import _invalidate_cache
    _invalidate_cache()
    yield
    db.close()


class TestImageEmbeddingsCRUD:
    def test_upsert_and_get(self):
        pid = db.upsert_photo("test/photo.jpg", "test", "photo.jpg", 800, 600)
        emb = np.random.randn(EMBED_DIM).astype(np.float32)
        emb = emb / np.linalg.norm(emb)  # normalize

        db.upsert_image_embedding(pid, EMBED_MODEL, emb)

        recovered = db.get_image_embedding(pid, EMBED_MODEL)
        assert recovered is not None
        np.testing.assert_array_almost_equal(emb, recovered)

    def test_get_nonexistent(self):
        result = db.get_image_embedding("nonexistent", EMBED_MODEL)
        assert result is None

    def test_upsert_overwrites(self):
        pid = db.upsert_photo("test/photo.jpg", "test", "photo.jpg")
        emb1 = np.random.randn(EMBED_DIM).astype(np.float32)
        emb2 = np.random.randn(EMBED_DIM).astype(np.float32)

        db.upsert_image_embedding(pid, EMBED_MODEL, emb1)
        db.upsert_image_embedding(pid, EMBED_MODEL, emb2)

        recovered = db.get_image_embedding(pid, EMBED_MODEL)
        np.testing.assert_array_almost_equal(emb2, recovered)

    def test_embed_status_updated(self):
        pid = db.upsert_photo("test/status_test.jpg", "test", "status_test.jpg")
        emb = np.random.randn(EMBED_DIM).astype(np.float32)

        photo = db.get_photo(pid)
        assert photo["embed_status"] == "pending"

        db.upsert_image_embedding(pid, EMBED_MODEL, emb)

        photo = db.get_photo(pid)
        assert photo["embed_status"] == "done"

    def test_blob_roundtrip_768d(self):
        """Ensure 768D embedding roundtrip works (not just 512D)."""
        original = np.random.randn(EMBED_DIM).astype(np.float32)
        blob = db.embedding_to_blob(original)
        recovered = db.blob_to_embedding(blob)
        assert len(recovered) == EMBED_DIM
        np.testing.assert_array_almost_equal(original, recovered)

    def test_get_all_image_embeddings(self):
        pid1 = db.upsert_photo("test/a.jpg", "test", "a.jpg")
        pid2 = db.upsert_photo("test/b.jpg", "test", "b.jpg")
        emb1 = np.random.randn(EMBED_DIM).astype(np.float32)
        emb2 = np.random.randn(EMBED_DIM).astype(np.float32)

        db.upsert_image_embedding(pid1, EMBED_MODEL, emb1)
        db.upsert_image_embedding(pid2, EMBED_MODEL, emb2)

        all_embs = db.get_all_image_embeddings(EMBED_MODEL)
        assert len(all_embs) == 2
        ids = {e["photo_id"] for e in all_embs}
        assert pid1 in ids
        assert pid2 in ids


class TestEmbedStats:
    def test_empty_stats(self):
        stats = db.get_embed_stats(model=EMBED_MODEL)
        assert stats["total_photos"] == 0
        assert stats["embedded"] == 0
        assert stats["coverage_pct"] == 0

    def test_stats_after_embed(self):
        pid = db.upsert_photo("test/photo.jpg", "test", "photo.jpg")
        emb = np.random.randn(EMBED_DIM).astype(np.float32)
        db.upsert_image_embedding(pid, EMBED_MODEL, emb)

        stats = db.get_embed_stats(model=EMBED_MODEL)
        assert stats["total_photos"] == 1
        assert stats["embedded"] == 1
        assert stats["done"] == 1
        assert stats["coverage_pct"] == 100.0

    def test_stats_partial_coverage(self):
        pid1 = db.upsert_photo("test/a.jpg", "test", "a.jpg")
        db.upsert_photo("test/b.jpg", "test", "b.jpg")
        emb = np.random.randn(EMBED_DIM).astype(np.float32)
        db.upsert_image_embedding(pid1, EMBED_MODEL, emb)

        stats = db.get_embed_stats(model=EMBED_MODEL)
        assert stats["total_photos"] == 2
        assert stats["embedded"] == 1
        assert stats["pending"] == 1
        assert stats["coverage_pct"] == 50.0


class TestSearchFunctions:
    """Test search functions with mock embeddings (no model loading)."""

    def _setup_mock_embeddings(self, n: int = 5) -> list[str]:
        """Create n photos with random embeddings, return photo_ids."""
        pids = []
        for i in range(n):
            pid = db.upsert_photo(f"test/{i}.jpg", "test", f"{i}.jpg", 800, 600)
            db.mark_scanned(pid, 0)
            emb = np.random.randn(EMBED_DIM).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            db.upsert_image_embedding(pid, EMBED_MODEL, emb)
            pids.append(pid)
        return pids

    def test_image_similarity_top1_is_self(self):
        """When searching by image, top-1 should be the query photo itself."""
        from src.image_embed import _invalidate_cache, _load_embedding_matrix

        pids = self._setup_mock_embeddings(5)
        _invalidate_cache()

        matrix, photo_ids = _load_embedding_matrix()
        assert len(photo_ids) == 5

        # Manual search: query with first photo's embedding
        query_emb = db.get_image_embedding(pids[0], EMBED_MODEL)
        scores = matrix @ query_emb
        top_idx = np.argmax(scores)
        assert photo_ids[top_idx] == pids[0]
        assert scores[top_idx] == pytest.approx(1.0, abs=0.01)

    def test_empty_db_search(self):
        """Search on empty DB should return empty list."""
        from src.image_embed import _invalidate_cache, _load_embedding_matrix

        _invalidate_cache()
        matrix, photo_ids = _load_embedding_matrix()
        assert len(photo_ids) == 0
        assert matrix.shape == (0, EMBED_DIM)

    def test_embedding_matrix_shape(self):
        """Matrix should be N x EMBED_DIM."""
        from src.image_embed import _invalidate_cache, _load_embedding_matrix

        self._setup_mock_embeddings(3)
        _invalidate_cache()
        matrix, photo_ids = _load_embedding_matrix()
        assert matrix.shape == (3, EMBED_DIM)
        assert len(photo_ids) == 3

    def test_mark_embed_status(self):
        pid = db.upsert_photo("test/x.jpg", "test", "x.jpg")
        db.mark_embed_status(pid, "failed")
        photo = db.get_photo(pid)
        assert photo["embed_status"] == "failed"
