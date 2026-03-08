"""Whole-image embedding with SigLIP for semantic photo search.

Uses google/siglip-base-patch16-384 (768D) for text→image and image→image search.
Lazy-loads the model on first use (same pattern as pipeline.py).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from . import db, log
from .config import (
    EMBED_DEVICE,
    EMBED_DIM,
    EMBED_MODEL,
    PHOTO_MODEL_DIR,
    PROJECT_ROOT,
)

# ── Lazy model singleton ────────────────────────────────────────────

_model = None
_processor = None
_tokenizer = None
_device: Optional[str] = None


def _resolve_device() -> str:
    """Pick device: mps > cpu (auto mode)."""
    if EMBED_DEVICE != "auto":
        return EMBED_DEVICE
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _get_model():
    """Lazy-load SigLIP model + processor + tokenizer."""
    global _model, _processor, _tokenizer, _device
    if _model is not None:
        return _model, _processor, _tokenizer, _device

    import torch
    from transformers import AutoModel, AutoProcessor, AutoTokenizer

    _device = _resolve_device()

    cache_dir = str(PHOTO_MODEL_DIR / "siglip")
    log.info("loading SigLIP model", model=EMBED_MODEL, device=_device, cache_dir=cache_dir)

    _processor = AutoProcessor.from_pretrained(EMBED_MODEL, cache_dir=cache_dir)
    _tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL, cache_dir=cache_dir)
    _model = AutoModel.from_pretrained(EMBED_MODEL, cache_dir=cache_dir)
    _model = _model.to(_device)
    _model.eval()

    log.info("SigLIP model loaded", embed_dim=EMBED_DIM)
    return _model, _processor, _tokenizer, _device


# ── Core embedding functions ────────────────────────────────────────

def embed_image(img: np.ndarray) -> np.ndarray:
    """Embed a single image (BGR numpy array) → normalized 768D float32 vector.

    Uses model.forward() to get properly projected image_embeds (aligned with text space).
    """
    import torch
    from PIL import Image

    model, processor, tokenizer, device = _get_model()

    # BGR → RGB → PIL
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    # SigLIP requires both text and image for forward(), but we can also
    # extract image_embeds by passing a dummy text. However, the cleaner
    # approach: use vision_model + head directly via full forward.
    # We pass a minimal dummy text to satisfy the forward signature.
    inputs = processor(
        text=[""], images=pil_img,
        return_tensors="pt", padding="max_length",
    ).to(device)
    with torch.no_grad():
        outputs = model(**inputs)

    emb = outputs.image_embeds[0].cpu().numpy().astype(np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def embed_text(query: str) -> np.ndarray:
    """Embed a text query → normalized 768D float32 vector.

    Uses model.forward() to get properly projected text_embeds (aligned with image space).
    """
    import torch
    from PIL import Image

    model, processor, _, device = _get_model()

    # SigLIP forward() needs both text and image; use a tiny dummy image.
    dummy_img = Image.new("RGB", (16, 16), color=(128, 128, 128))
    inputs = processor(
        text=[query], images=dummy_img,
        return_tensors="pt", padding="max_length",
    ).to(device)
    with torch.no_grad():
        outputs = model(**inputs)

    emb = outputs.text_embeds[0].cpu().numpy().astype(np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


# ── Single / batch embedding ───────────────────────────────────────

def embed_single(photo_id: str, force: bool = False) -> dict[str, Any]:
    """Embed a single photo and store in DB.

    Returns status dict with photo_id and embedding dimension.
    """
    photo = db.get_photo(photo_id)
    if not photo:
        return {"error": f"Photo not found: {photo_id}"}

    if not force:
        existing = db.get_image_embedding(photo_id, EMBED_MODEL)
        if existing is not None:
            return {"status": "skipped", "photo_id": photo_id, "reason": "already embedded"}

    # Resolve and read image
    abs_path = PROJECT_ROOT / photo["rel_path"]
    if not abs_path.is_file():
        db.mark_embed_status(photo_id, "failed")
        return {"error": f"Image file not found: {photo['rel_path']}"}

    img = cv2.imread(str(abs_path))
    if img is None:
        db.mark_embed_status(photo_id, "failed")
        return {"error": f"Cannot read image: {photo['rel_path']}"}

    # Skip tiny images
    h, w = img.shape[:2]
    if h < 64 or w < 64:
        db.mark_embed_status(photo_id, "skipped")
        return {"status": "skipped", "photo_id": photo_id, "reason": f"too small ({w}x{h})"}

    try:
        emb = embed_image(img)
        db.upsert_image_embedding(photo_id, EMBED_MODEL, emb)
        return {"status": "done", "photo_id": photo_id, "dim": len(emb)}
    except Exception as e:
        db.mark_embed_status(photo_id, "failed")
        return {"error": f"Embedding failed: {e}", "photo_id": photo_id}


def batch_embed(limit: int = 0, source_dir: str = "") -> dict[str, Any]:
    """Batch-embed all pending photos.

    Args:
        limit: Max photos to process (0 = all pending).
        source_dir: Filter by source directory.

    Returns stats dict.
    """
    conn = db.get_conn()
    conditions = ["embed_status='pending'", "scan_status='scanned'"]
    params: list[Any] = []
    if source_dir:
        conditions.append("source_dir=?")
        params.append(source_dir)

    where = " AND ".join(conditions)
    query = f"SELECT photo_id FROM photos WHERE {where}"
    if limit > 0:
        query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    total = len(rows)

    if total == 0:
        return {"total": 0, "embedded": 0, "skipped": 0, "failed": 0, "message": "No pending photos"}

    embedded = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, row in enumerate(rows, 1):
        if i % 50 == 0 or i == 1:
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            log.info(
                "embed progress",
                current=i, total=total,
                rate=f"{rate:.1f}/s", eta=f"{eta:.0f}s",
            )

        result = embed_single(row["photo_id"], force=False)
        status = result.get("status", "")
        if status == "done":
            embedded += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

    elapsed = time.time() - start
    log.info(
        "batch embed complete",
        total=total, embedded=embedded, skipped=skipped, failed=failed,
        elapsed=f"{elapsed:.1f}s",
    )
    return {
        "total": total,
        "embedded": embedded,
        "skipped": skipped,
        "failed": failed,
        "elapsed_s": round(elapsed, 1),
    }


# ── Embedding matrix cache ──────────────────────────────────────────

_embed_cache: Optional[dict[str, Any]] = None


def _load_embedding_matrix() -> tuple[np.ndarray, list[str]]:
    """Load all image embeddings into a numpy matrix for fast cosine similarity.

    Returns (matrix [N x dim], photo_ids [N]).
    Caches in memory; call _invalidate_cache() after new embeddings.
    """
    global _embed_cache
    if _embed_cache is not None:
        return _embed_cache["matrix"], _embed_cache["photo_ids"]

    rows = db.get_all_image_embeddings(EMBED_MODEL)
    if not rows:
        empty = np.zeros((0, EMBED_DIM), dtype=np.float32)
        return empty, []

    photo_ids = [r["photo_id"] for r in rows]
    matrix = np.stack([r["embedding"] for r in rows]).astype(np.float32)

    _embed_cache = {"matrix": matrix, "photo_ids": photo_ids}
    log.info("embedding matrix loaded", n=len(photo_ids), shape=str(matrix.shape))
    return matrix, photo_ids


def _invalidate_cache() -> None:
    """Invalidate the in-memory embedding cache (call after batch embed)."""
    global _embed_cache
    _embed_cache = None


# ── Search functions ────────────────────────────────────────────────

def search_by_text(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search photos by text description using SigLIP text→image alignment.

    Returns list of {photo_id, score, rel_path, source_dir, filename} sorted by score desc.
    """
    matrix, photo_ids = _load_embedding_matrix()
    if len(photo_ids) == 0:
        return []

    query_emb = embed_text(query)  # [dim]
    scores = matrix @ query_emb    # [N]

    # Top-K
    top_k = min(limit, len(scores))
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        pid = photo_ids[idx]
        photo = db.get_photo(pid)
        results.append({
            "photo_id": pid,
            "score": round(float(scores[idx]), 4),
            "rel_path": photo["rel_path"] if photo else "",
            "source_dir": photo["source_dir"] if photo else "",
            "filename": photo["filename"] if photo else "",
        })

    return results


def search_by_image(photo_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find visually similar photos by image→image cosine similarity.

    Returns list of {photo_id, score, rel_path, source_dir, filename} sorted by score desc.
    Top-1 should be the query photo itself (score ≈ 1.0).
    """
    matrix, photo_ids = _load_embedding_matrix()
    if len(photo_ids) == 0:
        return []

    query_emb = db.get_image_embedding(photo_id, EMBED_MODEL)
    if query_emb is None:
        # Try to embed on-the-fly
        result = embed_single(photo_id)
        if result.get("status") != "done":
            return [{"error": f"Cannot embed photo {photo_id}: {result.get('error', 'unknown')}"}]
        _invalidate_cache()
        matrix, photo_ids = _load_embedding_matrix()
        query_emb = db.get_image_embedding(photo_id, EMBED_MODEL)
        if query_emb is None:
            return [{"error": "Embedding failed"}]

    scores = matrix @ query_emb  # [N]

    top_k = min(limit, len(scores))
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        pid = photo_ids[idx]
        photo = db.get_photo(pid)
        results.append({
            "photo_id": pid,
            "score": round(float(scores[idx]), 4),
            "rel_path": photo["rel_path"] if photo else "",
            "source_dir": photo["source_dir"] if photo else "",
            "filename": photo["filename"] if photo else "",
        })

    return results


def search_hybrid(
    query: str,
    limit: int = 20,
    scene_filter: str = "",
    source_dir: str = "",
) -> list[dict[str, Any]]:
    """Hybrid search: SigLIP vector search → SQL scene filter → intersect + rerank.

    Args:
        query: Text description to search for.
        limit: Max results.
        scene_filter: Filter by scene_type (e.g. '室外').
        source_dir: Filter by source directory.
    """
    # Step 1: vector search with a wider net
    vector_results = search_by_text(query, limit=limit * 5)
    if not vector_results:
        return []

    # Step 2: SQL filter (if any filter specified)
    if scene_filter or source_dir:
        conn = db.get_conn()
        candidate_ids = {r["photo_id"] for r in vector_results}

        conditions: list[str] = ["p.photo_id IN ({})".format(",".join("?" * len(candidate_ids)))]
        params: list[Any] = list(candidate_ids)

        if scene_filter:
            conditions.append("s.scene_type = ?")
            params.append(scene_filter)
        if source_dir:
            conditions.append("p.source_dir = ?")
            params.append(source_dir)

        where = " AND ".join(conditions)
        filtered_ids = {
            row["photo_id"]
            for row in conn.execute(
                f"""SELECT p.photo_id FROM photos p
                    LEFT JOIN scenes s ON p.photo_id = s.photo_id
                    WHERE {where}""",
                params,
            ).fetchall()
        }

        # Intersect: keep vector order, filter by SQL
        vector_results = [r for r in vector_results if r["photo_id"] in filtered_ids]

    return vector_results[:limit]
