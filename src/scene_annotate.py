"""Scene annotation business logic — annotate photos with Gemini Flash Vision."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import cv2

from . import db, log
from .config import PROJECT_ROOT, GEMINI_MODEL
from .gemini_vision import resize_for_gemini, annotate_photo


# Minimum image dimension (skip tiny thumbnails / icons)
_MIN_DIM = 64


def annotate_single(photo_id: str, force: bool = False) -> dict[str, Any]:
    """Annotate a single photo's scene. Read image → resize → call Gemini → save DB.

    Skips already-annotated photos unless force=True.
    Returns the annotation dict or an error dict.
    """
    photo = db.get_photo(photo_id)
    if not photo:
        return {"error": f"Photo not found: {photo_id}"}

    # Check if already annotated
    if not force:
        existing = db.get_scene(photo_id)
        if existing:
            return {"status": "skipped", "photo_id": photo_id, "reason": "already annotated"}

    # Resolve image path
    rel_path = photo["rel_path"]
    abs_path = PROJECT_ROOT / rel_path
    if not abs_path.is_file():
        db.mark_scene_status(photo_id, "failed")
        return {"error": f"Image file not found: {rel_path}"}

    # Read image
    img = cv2.imread(str(abs_path))
    if img is None:
        db.mark_scene_status(photo_id, "failed")
        return {"error": f"Cannot read image: {rel_path}"}

    h, w = img.shape[:2]
    if max(h, w) < _MIN_DIM:
        db.mark_scene_status(photo_id, "skipped")
        return {"status": "skipped", "photo_id": photo_id, "reason": f"too small ({w}x{h})"}

    # Resize and encode
    try:
        img_b64 = resize_for_gemini(img)
    except RuntimeError as e:
        db.mark_scene_status(photo_id, "failed")
        return {"error": f"Image encoding failed: {e}"}

    # Call Gemini
    try:
        result = annotate_photo(img_b64)
    except RuntimeError as e:
        db.mark_scene_status(photo_id, "failed")
        return {"error": f"Gemini API failed: {e}"}

    # Save to DB
    db.upsert_scene(
        photo_id=photo_id,
        model=GEMINI_MODEL,
        scene_type=result.get("scene_type"),
        location=result.get("location"),
        architecture=result.get("architecture"),
        era_clues=result.get("era_clues"),
        spatial_desc=result.get("spatial_desc"),
        objects_json=json.dumps(result.get("objects"), ensure_ascii=False) if result.get("objects") else None,
        texts_json=json.dumps(result.get("texts"), ensure_ascii=False) if result.get("texts") else None,
        tags_json=json.dumps(result.get("tags"), ensure_ascii=False) if result.get("tags") else None,
        raw_response=json.dumps(result, ensure_ascii=False),
    )
    db.mark_scene_status(photo_id, "done")

    log.info("scene annotated", photo_id=photo_id, scene_type=result.get("scene_type"))

    return {
        "status": "annotated",
        "photo_id": photo_id,
        "scene_type": result.get("scene_type"),
        "location": result.get("location"),
        "architecture": result.get("architecture"),
        "era_clues": result.get("era_clues"),
        "spatial_desc": result.get("spatial_desc"),
        "objects": result.get("objects"),
        "texts": result.get("texts"),
        "tags": result.get("tags"),
    }


def batch_annotate(limit: int = 0, source_dir: str = "") -> dict[str, Any]:
    """Batch-annotate all photos with scene_status='pending'.

    Args:
        limit: Max photos to annotate (0 = all).
        source_dir: Filter by source directory name (empty = all).

    Returns summary stats.
    """
    conn = db.get_conn()

    conditions = ["p.scan_status = 'scanned'"]
    params: list[Any] = []

    # Only photos not yet annotated (no row in scenes, or scene_status = pending)
    if source_dir:
        conditions.append("p.source_dir = ?")
        params.append(source_dir)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT p.photo_id FROM photos p
        LEFT JOIN scenes s ON p.photo_id = s.photo_id
        WHERE {where} AND s.photo_id IS NULL
        ORDER BY p.rel_path
    """
    if limit > 0:
        sql += f" LIMIT {limit}"

    rows = conn.execute(sql, params).fetchall()

    total = len(rows)
    annotated = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, row in enumerate(rows, 1):
        if i % 50 == 0 or i == 1:
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(
                f"[scene {i}/{total}] {elapsed:.0f}s elapsed, "
                f"{rate:.1f}/min, ETA {eta:.0f}s | "
                f"done={annotated} skip={skipped} fail={failed}",
                flush=True,
            )

        result = annotate_single(row["photo_id"])
        status = result.get("status", "")
        if status == "annotated":
            annotated += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
            if failed <= 5:
                log.error("scene annotation failed", photo_id=row["photo_id"], error=result.get("error"))
            elif failed == 6:
                log.warn("suppressing further scene error logs")

    elapsed = time.time() - start
    print(
        f"\n=== Scene annotation complete ===\n"
        f"Total: {total} | Annotated: {annotated} | Skipped: {skipped} | Failed: {failed}\n"
        f"Time: {elapsed:.1f}s\n",
        flush=True,
    )

    return {
        "total": total,
        "annotated": annotated,
        "skipped": skipped,
        "failed": failed,
        "elapsed": round(elapsed, 1),
    }


def get_scene_stats() -> dict[str, Any]:
    """Scene annotation coverage and distribution overview."""
    return db.get_scene_stats_db()


def search_scenes(
    query: str = "",
    scene_type: str = "",
    location: str = "",
    tag: str = "",
    has_text: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Multi-condition search on annotated scenes."""
    return db.search_scenes_db(
        query=query,
        scene_type=scene_type,
        location=location,
        tag=tag,
        has_text=has_text,
        limit=limit,
    )
