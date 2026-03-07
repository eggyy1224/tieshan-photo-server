"""photo_find — Find all photos containing a specific person."""

from __future__ import annotations

from .. import db
from ..matching import find_person_in_photos


async def photo_find(query: str, min_score: float = 0.30, limit: int = 50) -> dict:
    """Find photos containing a person by person_id or display name.

    Args:
        query: person_id (e.g. 'xu_tiancui') or display name (e.g. '許天催').
        min_score: Minimum cosine similarity threshold.
        limit: Max results to return.

    Returns:
        Dict with person info and matching photo list.
    """
    # Resolve person
    person = db.get_person(query)
    if not person:
        person = db.find_person_by_name(query)
    if not person:
        return {"error": "PERSON_NOT_FOUND", "message": f"Person not found: {query}"}

    person_id = person["person_id"]
    results = find_person_in_photos(person_id, min_score=min_score, limit=limit)

    return {
        "person_id": person_id,
        "display_name": person["display_name"],
        "match_count": len(results),
        "min_score": min_score,
        "photos": results,
    }
