"""photo_persons — List all persons in the database with anchor/match counts."""

from __future__ import annotations

from .. import db


async def photo_persons(query: str = "") -> dict:
    """List all persons in the face recognition database.

    Args:
        query: Optional filter — match against person_id or display_name (substring).

    Returns:
        List of persons with anchor counts, sorted by anchor count descending.
    """
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT p.person_id, p.display_name, p.gender, p.birth_year,
                  COUNT(DISTINCT a.anchor_id) as anchor_count,
                  COUNT(DISTINCT CASE WHEN f.match_method IN ('anchor','auto') THEN f.photo_id END) as match_count
           FROM persons p
           LEFT JOIN anchors a ON a.person_id = p.person_id
           LEFT JOIN faces f ON f.person_id = p.person_id
           GROUP BY p.person_id
           ORDER BY match_count DESC, p.display_name"""
    ).fetchall()

    persons = [dict(r) for r in rows]

    if query:
        q = query.lower()
        persons = [
            p for p in persons
            if q in (p["person_id"] or "").lower() or q in (p["display_name"] or "").lower()
        ]

    return {
        "total": len(persons),
        "persons": persons,
    }
