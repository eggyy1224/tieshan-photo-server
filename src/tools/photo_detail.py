"""photo_detail — Get full detail of a single photo including all faces and matches."""

from __future__ import annotations

from .. import db
from ..matching import match_face


async def photo_detail(photo_id: str) -> dict:
    """Get complete information about a photo: metadata, all detected faces,
    current matches, and top-3 candidates per face.

    Args:
        photo_id: The photo_id (hex hash) from the database.

    Returns:
        Photo metadata and per-face details with match rankings.
    """
    photo = db.get_photo(photo_id)
    if not photo:
        return {"error": "NOT_FOUND", "message": f"Photo not found: {photo_id}"}

    faces_raw = db.get_faces_for_photo(photo_id)
    faces = []
    for f in faces_raw:
        emb = db.blob_to_embedding(f["embedding"])
        rejected = db.get_rejected_persons_for_face(f["face_id"])
        exclude = set(rejected) if rejected else None
        matches = match_face(emb, top_k=3, exclude_persons=exclude)
        faces.append({
            "face_id": f["face_id"],
            "bbox": [float(f["bbox_x"] or 0), float(f["bbox_y"] or 0),
                     float(f["bbox_w"] or 0), float(f["bbox_h"] or 0)],
            "det_score": round(float(f["det_score"]), 3),
            "age_est": f["age_est"],
            "gender_est": f["gender_est"],
            "person_id": f["person_id"],
            "match_score": round(f["match_score"], 4) if f["match_score"] else None,
            "match_method": f["match_method"],
            "matches": matches,
            "rejected_persons": rejected or [],
        })
    faces.sort(key=lambda x: x["det_score"], reverse=True)

    return {
        "photo_id": photo["photo_id"],
        "rel_path": photo["rel_path"],
        "source_dir": photo["source_dir"],
        "filename": photo["filename"],
        "width": photo["width"],
        "height": photo["height"],
        "face_count": photo["face_count"],
        "faces": faces,
    }
