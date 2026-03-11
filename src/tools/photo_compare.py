"""photo_compare — Compare faces between a reference photo and a target photo in DB."""

from __future__ import annotations

from pathlib import Path

from .. import db, log
from ..config import PROJECT_ROOT
from ..matching import cosine_similarity
from ..pipeline import detect_faces
from ..preprocessing import preprocess


def _to_float(v) -> float:
    """Convert a value to float, handling bytes (struct-packed) from SQLite."""
    if isinstance(v, bytes):
        import struct
        if len(v) == 4:
            return struct.unpack("f", v)[0]
        if len(v) == 8:
            return struct.unpack("d", v)[0]
        return 0.0
    if v is None:
        return 0.0
    return float(v)


async def photo_compare(
    ref_photo: str,
    target_photo_id: str,
) -> dict:
    """Compare faces in a reference photo against faces in a target photo already in DB.

    Useful for cross-referencing: e.g. compare a TCMB portrait against a family group photo
    to find the same person.

    Args:
        ref_photo: Path to reference photo (absolute, or relative to project root).
        target_photo_id: Photo ID of the target photo (already scanned in DB).

    Returns:
        Per ref-face rankings of target faces by cosine similarity.
    """
    import cv2

    # 1. Resolve ref_photo path
    ref_path = Path(ref_photo)
    if not ref_path.is_absolute():
        ref_path = PROJECT_ROOT / ref_path

    if not ref_path.is_file():
        return {"error": "REF_PHOTO_NOT_FOUND", "message": f"File not found: {ref_photo}"}

    # 2. Load and detect faces in reference image
    ref_img = cv2.imread(str(ref_path))
    if ref_img is None:
        return {"error": "REF_PHOTO_UNREADABLE", "message": f"Cannot read image: {ref_photo}"}

    try:
        ref_processed = preprocess(ref_img)
        ref_faces = detect_faces(ref_processed)

        if not ref_faces:
            return {"error": "NO_FACES_IN_REF", "message": "No faces detected in reference photo"}

        # 3. Get target photo faces from DB
        target_photo = db.get_photo(target_photo_id)
        if not target_photo:
            return {"error": "TARGET_NOT_FOUND", "message": f"Photo not found in DB: {target_photo_id}"}

        target_faces_raw = db.get_faces_for_photo(target_photo_id)
        if not target_faces_raw:
            return {"error": "NO_FACES_IN_TARGET", "message": "No detected faces in target photo"}

        # 4. Compute cosine similarity: each ref face vs each target face
        results = []
        for ref_idx, ref_face in enumerate(ref_faces):
            ref_emb = ref_face["embedding"]
            rankings = []

            for tf in target_faces_raw:
                target_emb = db.blob_to_embedding(tf["embedding"])
                score = cosine_similarity(ref_emb, target_emb)

                rankings.append({
                    "face_id": tf["face_id"],
                    "bbox": [
                        _to_float(tf["bbox_x"]),
                        _to_float(tf["bbox_y"]),
                        _to_float(tf["bbox_w"]),
                        _to_float(tf["bbox_h"]),
                    ],
                    "score": float(round(score, 4)),
                    "person_id": tf["person_id"],
                    "match_method": tf["match_method"],
                })

            rankings.sort(key=lambda x: x["score"], reverse=True)

            results.append({
                "ref_face_index": ref_idx,
                "ref_bbox": [float(v) for v in ref_face["bbox"]],
                "ref_det_score": float(round(ref_face["det_score"], 3)),
                "ref_age_est": int(ref_face["age"]) if ref_face["age"] is not None else None,
                "ref_gender_est": ref_face["gender"],
                "rankings": rankings,
            })

        return {
            "ref_photo": ref_photo,
            "target_photo_id": target_photo_id,
            "ref_face_count": len(ref_faces),
            "target_face_count": len(target_faces_raw),
            "results": results,
        }
    except Exception as e:
        log.error("photo_compare failed", error=str(e))
        return {"error": "COMPARE_ERROR", "message": f"Face comparison failed: {e}"}
