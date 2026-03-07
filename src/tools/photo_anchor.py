"""photo_anchor — Manually anchor a face to a person (Phase 2)."""

from __future__ import annotations

from .. import db, log
from ..matching import match_face


async def photo_anchor(face_id: int, person_id: str, note: str = "") -> dict:
    """Mark a detected face as a specific person.

    This creates an anchor entry and triggers re-matching of
    all unmatched faces against the updated anchor set.

    Args:
        face_id: The face to anchor.
        person_id: The person_id from family_tree.
        note: Optional annotation.

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

    # Create anchor
    anchor_id = db.insert_anchor(
        face_id=face_id,
        person_id=person_id,
        source="manual",
        confidence=1.0,
        note=note or None,
    )

    # Update the face's person assignment
    db.update_face_match(face_id, person_id, 1.0, "anchor")

    log.info("anchor created", anchor_id=anchor_id, face_id=face_id, person=person["display_name"])

    # Re-match unmatched faces against updated anchors
    unmatched = db.get_conn().execute(
        "SELECT face_id, embedding FROM faces WHERE person_id IS NULL"
    ).fetchall()

    new_matches = 0
    for row in unmatched:
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

    return {
        "anchor_id": anchor_id,
        "person_id": person_id,
        "display_name": person["display_name"],
        "new_auto_matches": new_matches,
    }
