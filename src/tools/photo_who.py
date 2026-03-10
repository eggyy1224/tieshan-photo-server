"""photo_who — Identify persons in a photo."""

from __future__ import annotations

from .. import db, log
from ..pipeline import process_photo
from ..matching import match_face


async def photo_who(photo_path: str, force_rescan: bool = False) -> dict:
    """Detect faces in a photo and match each against known persons.

    Args:
        photo_path: Path to photo (absolute or relative to PROJECT_ROOT).
        force_rescan: Re-detect even if previously scanned.

    Returns:
        Dict with photo_id, face_count, and per-face top-3 matches.
    """
    try:
        result = process_photo(photo_path, force_rescan=force_rescan)
    except FileNotFoundError:
        return {"error": "PHOTO_NOT_FOUND", "message": f"Photo not found: {photo_path}"}
    except ValueError as e:
        return {"error": "PHOTO_UNREADABLE", "message": str(e)}
    except Exception as e:
        if "model" in str(e).lower() or "insightface" in str(e).lower():
            return {"error": "MODEL_NOT_LOADED", "message": str(e)}
        raise

    # For each face, find top-3 matches
    faces_with_matches = []
    for face in result["faces"]:
        face_id = face["face_id"]

        # Get embedding from DB
        face_row = db.get_conn().execute(
            "SELECT embedding FROM faces WHERE face_id=?", (face_id,)
        ).fetchone()

        matches = []
        if face_row:
            emb = db.blob_to_embedding(face_row["embedding"])
            rejected = db.get_rejected_persons_for_face(face_id)
            exclude = set(rejected) if rejected else None
            matches = match_face(emb, top_k=3, exclude_persons=exclude)

        faces_with_matches.append({
            "face_id": face_id,
            "bbox": face["bbox"],
            "det_score": round(face["det_score"], 3),
            "age_est": face.get("age_est"),
            "gender_est": face.get("gender_est"),
            "matches": matches,
        })

    return {
        "photo_id": result["photo_id"],
        "photo_path": photo_path,
        "face_count": result["face_count"],
        "cached": result.get("cached", False),
        "faces": faces_with_matches,
    }
