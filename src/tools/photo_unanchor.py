"""photo_unanchor — Remove an incorrect anchor from a face."""

from __future__ import annotations

from .. import db, log
from .photo_anchor import rematch_faces


async def photo_unanchor(face_id: int) -> dict:
    """Remove an anchor assignment from a face. Use when a face was incorrectly
    identified and the anchor needs to be deleted.

    After removal, auto-matching is re-run on the affected photo.

    Args:
        face_id: The face_id whose anchor should be removed.

    Returns:
        Confirmation with removed person info.
    """
    conn = db.get_conn()

    anchor = conn.execute(
        "SELECT anchor_id, person_id FROM anchors WHERE face_id=?", (face_id,)
    ).fetchone()
    if not anchor:
        return {"error": "NO_ANCHOR", "message": f"No anchor for face {face_id}"}

    person_id = anchor["person_id"]
    face = conn.execute(
        "SELECT photo_id FROM faces WHERE face_id=?", (face_id,)
    ).fetchone()
    if not face:
        return {"error": "FACE_NOT_FOUND", "message": f"Face not found: {face_id}"}

    # Delete anchor
    conn.execute("DELETE FROM anchors WHERE face_id=?", (face_id,))

    # Clear face assignment (only if it was anchored)
    conn.execute(
        "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL "
        "WHERE face_id=? AND match_method='anchor'",
        (face_id,),
    )

    # Record rejection: prevent rematch from re-assigning the same person to this
    # face via remaining anchors of that person elsewhere in the database.
    db.insert_rejected_match(face_id, person_id)

    conn.commit()

    # Global rematch: the anchor may have cascaded auto-matches to many photos,
    # so we must reset and recompute all auto-matches, not just the current photo.
    rematched = rematch_faces(photo_id=None, reset_auto_matches=True)

    person = db.get_person(person_id)
    display_name = person["display_name"] if person else person_id

    log.info("anchor removed", face_id=face_id, person_id=person_id, rematched=rematched)

    return {
        "removed": True,
        "face_id": face_id,
        "person_id": person_id,
        "display_name": display_name,
        "global_rematched": rematched,
    }
