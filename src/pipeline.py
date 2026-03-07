"""Face detection and embedding pipeline using InsightFace."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from . import db, log
from .config import PHOTO_DET_THRESHOLD, PHOTO_MODEL_DIR, PROJECT_ROOT
from .preprocessing import preprocess

_app: Optional[object] = None


def _get_app():
    """Lazy-load InsightFace FaceAnalysis app."""
    global _app
    if _app is None:
        import insightface
        _app = insightface.app.FaceAnalysis(
            name="buffalo_l",
            root=str(PHOTO_MODEL_DIR),
            providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
        )
        _app.prepare(ctx_id=0, det_thresh=PHOTO_DET_THRESHOLD, det_size=(640, 640))
        log.info("insightface model loaded", model="buffalo_l", det_thresh=PHOTO_DET_THRESHOLD)
    return _app


def detect_faces(img: np.ndarray) -> list[dict]:
    """Run face detection + embedding on a preprocessed image.

    Returns list of dicts with keys: bbox, det_score, embedding, age, gender.
    """
    app = _get_app()
    faces = app.get(img)

    results = []
    h, w = img.shape[:2]
    for face in faces:
        x1, y1, x2, y2 = face.bbox
        # Normalize bbox to [0,1]
        bbox_x = max(0.0, x1 / w)
        bbox_y = max(0.0, y1 / h)
        bbox_w = min(1.0, (x2 - x1) / w)
        bbox_h = min(1.0, (y2 - y1) / h)

        results.append({
            "bbox": (bbox_x, bbox_y, bbox_w, bbox_h),
            "det_score": float(face.det_score),
            "embedding": face.normed_embedding,
            "age": int(face.age) if hasattr(face, "age") else None,
            "gender": "M" if getattr(face, "gender", None) == 1 else "F" if getattr(face, "gender", None) == 0 else None,
        })

    return results


def process_photo(photo_path: str | Path, force_rescan: bool = False) -> dict:
    """Full pipeline: load image -> preprocess -> detect -> store in DB.

    Args:
        photo_path: Absolute or relative-to-PROJECT_ROOT path.
        force_rescan: If True, delete existing faces and re-scan.

    Returns:
        Dict with photo_id, face_count, faces (list of face info).
    """
    photo_path = Path(photo_path)

    # Resolve to absolute
    if not photo_path.is_absolute():
        photo_path = PROJECT_ROOT / photo_path

    if not photo_path.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    # Compute relative path for DB
    try:
        rel_path = str(photo_path.relative_to(PROJECT_ROOT))
    except ValueError:
        rel_path = str(photo_path)

    source_dir = rel_path.split("/")[0] if "/" in rel_path else ""
    filename = photo_path.name

    # Check if already scanned
    existing = db.get_photo_by_path(rel_path)
    if existing and existing["scan_status"] == "scanned" and not force_rescan:
        faces = db.get_faces_for_photo(existing["photo_id"])
        return {
            "photo_id": existing["photo_id"],
            "face_count": len(faces),
            "faces": _faces_to_output(faces),
            "cached": True,
        }

    # Load image
    img = cv2.imread(str(photo_path))
    if img is None:
        photo_id = db.upsert_photo(rel_path, source_dir, filename)
        db.mark_failed(photo_id)
        raise ValueError(f"Cannot read image: {photo_path}")

    h, w = img.shape[:2]

    # Register photo in DB
    photo_id = db.upsert_photo(rel_path, source_dir, filename, width=w, height=h)

    # Force rescan: delete existing faces
    if force_rescan:
        db.delete_faces_for_photo(photo_id)

    # Preprocess and detect
    try:
        img_processed = preprocess(img)
        detected = detect_faces(img_processed)
    except Exception as e:
        db.mark_failed(photo_id)
        log.error("detection failed", photo=rel_path, error=str(e))
        raise

    # Store faces
    face_records = []
    for face_data in detected:
        face_id = db.insert_face(
            photo_id=photo_id,
            bbox=face_data["bbox"],
            det_score=face_data["det_score"],
            embedding=face_data["embedding"],
            age_est=face_data["age"],
            gender_est=face_data["gender"],
        )
        face_records.append({
            "face_id": face_id,
            "bbox": face_data["bbox"],
            "det_score": face_data["det_score"],
            "age_est": face_data["age"],
            "gender_est": face_data["gender"],
        })

    db.mark_scanned(photo_id, len(detected))
    log.info("photo processed", photo=rel_path, faces=len(detected))

    return {
        "photo_id": photo_id,
        "face_count": len(detected),
        "faces": face_records,
        "cached": False,
    }


def _faces_to_output(faces: list[dict]) -> list[dict]:
    """Convert DB face rows to output format (strip embedding blob)."""
    return [
        {
            "face_id": f["face_id"],
            "bbox": (f["bbox_x"], f["bbox_y"], f["bbox_w"], f["bbox_h"]),
            "det_score": f["det_score"],
            "age_est": f["age_est"],
            "gender_est": f["gender_est"],
            "person_id": f.get("person_id"),
            "match_score": f.get("match_score"),
        }
        for f in faces
    ]
