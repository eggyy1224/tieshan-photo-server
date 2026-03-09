"""photo_anchor — Manually anchor a face to a person (Phase 2)."""

from __future__ import annotations

from .. import db, log
from ..matching import match_face


def rematch_faces(photo_id: str | None = None, reset_auto_matches: bool = False) -> int:
    """Recompute auto-matches for eligible faces.

    When photo_id is provided, only rematch faces in that photo.
    When reset_auto_matches is True, clear existing auto assignments first.
    """
    conn = db.get_conn()

    if reset_auto_matches:
        if photo_id is None:
            conn.execute(
                "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL "
                "WHERE match_method='auto'"
            )
        else:
            conn.execute(
                "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL "
                "WHERE photo_id=? AND match_method='auto'",
                (photo_id,),
            )
        conn.commit()

    if photo_id is None:
        rows = conn.execute(
            "SELECT face_id, embedding FROM faces "
            "WHERE person_id IS NULL AND COALESCE(match_method,'') != 'rejected'"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT face_id, embedding FROM faces "
            "WHERE photo_id=? AND person_id IS NULL "
            "AND COALESCE(match_method,'') != 'rejected'",
            (photo_id,),
        ).fetchall()

    new_matches = 0
    for row in rows:
        emb = db.blob_to_embedding(row["embedding"])
        matches = match_face(emb, top_k=1)
        if matches and matches[0]["confidence"] in ("HIGH", "MEDIUM"):
            db.update_face_match(
                row["face_id"],
                matches[0]["person_id"],
                matches[0]["score"],
                "auto",
            )
            new_matches += 1

    return new_matches


async def photo_anchor(
    face_id: int,
    person_id: str,
    note: str = "",
    scope: str = "all",
) -> dict:
    """Mark a detected face as a specific person.

    This creates an anchor entry and triggers re-matching of
    unmatched faces against the updated anchor set.

    Args:
        face_id: The face to anchor.
        person_id: The person_id from family_tree.
        note: Optional annotation.
        scope: "photo" to only re-match faces in the same photo (fast, for UI),
               "all" to re-match all unmatched faces globally (thorough, for MCP).

    Returns:
        Dict with anchor_id and updated match counts.
    """
    # Validate face exists
    face = db.get_conn().execute(
        "SELECT * FROM faces WHERE face_id=?", (face_id,)
    ).fetchone()
    if not face:
        return {"error": "FACE_NOT_FOUND", "message": f"Face ID {face_id} not found"}

    # Validate person exists
    person = db.get_person(person_id)
    if not person:
        return {"error": "PERSON_NOT_FOUND", "message": f"Person {person_id} not found"}

    existing_anchor = db.get_anchor_for_face(face_id)
    if existing_anchor:
        if existing_anchor["person_id"] != person_id:
            return {
                "error": "FACE_ALREADY_ANCHORED",
                "message": (
                    f"Face ID {face_id} is already anchored to "
                    f"{existing_anchor['person_id']}"
                ),
            }
        db.update_face_match(face_id, person_id, 1.0, "anchor")
        return {
            "anchor_id": existing_anchor["anchor_id"],
            "person_id": person_id,
            "display_name": person["display_name"],
            "new_auto_matches": 0,
            "already_anchored": True,
        }

    # Create anchor
    try:
        anchor_id = db.insert_anchor(
            face_id=face_id,
            person_id=person_id,
            source="manual",
            confidence=1.0,
            note=note or None,
        )
    except ValueError as e:
        return {"error": "FACE_ALREADY_ANCHORED", "message": str(e)}

    # Update the face's person assignment
    db.update_face_match(face_id, person_id, 1.0, "anchor")

    log.info("anchor created", anchor_id=anchor_id, face_id=face_id, person=person["display_name"])

    # Re-match unmatched faces against updated anchors
    # Skip faces with match_method='rejected' (user explicitly cleared)
    target_photo_id = face["photo_id"] if scope == "photo" else None
    new_matches = rematch_faces(photo_id=target_photo_id)

    return {
        "anchor_id": anchor_id,
        "person_id": person_id,
        "display_name": person["display_name"],
        "new_auto_matches": new_matches,
    }
