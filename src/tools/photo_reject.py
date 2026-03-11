"""photo_reject — Reject an incorrect auto-match on a face."""

from __future__ import annotations

from .. import db, log


async def photo_reject(face_id: int) -> dict:
    """Reject an auto-matched person assignment on a face. The rejected person
    will be excluded from future matching for this face.

    Cannot be used on anchored faces — use photo_unanchor for those.

    Args:
        face_id: The face_id whose auto-match should be rejected.

    Returns:
        Confirmation with rejected person info.
    """
    conn = db.get_conn()

    face = conn.execute(
        "SELECT face_id, person_id, match_method FROM faces WHERE face_id=?",
        (face_id,),
    ).fetchone()
    if not face:
        return {"error": "FACE_NOT_FOUND", "message": f"Face not found: {face_id}"}

    if face["match_method"] == "anchor":
        return {
            "error": "IS_ANCHOR",
            "message": "This face is anchored. Use photo_unanchor to remove anchor assignments.",
        }

    rejected_person_id = face["person_id"]
    if not rejected_person_id:
        return {
            "error": "NO_MATCH",
            "message": "This face has no current match to reject.",
        }

    # Record rejection for future exclusion
    db.insert_rejected_match(face_id, rejected_person_id)

    # Clear the match, mark as rejected
    conn.execute(
        "UPDATE faces SET person_id=NULL, match_score=NULL, match_method='rejected' "
        "WHERE face_id=?",
        (face_id,),
    )
    conn.commit()

    log.info("match rejected", face_id=face_id, rejected=rejected_person_id)

    return {
        "rejected": True,
        "face_id": face_id,
        "rejected_person": rejected_person_id,
    }
