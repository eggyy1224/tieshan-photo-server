"""photo_stats — Scanning and annotation progress."""

from __future__ import annotations

from .. import db


async def photo_stats(detail: str = "summary") -> dict:
    """Return scanning/annotation statistics.

    Args:
        detail: "summary" | "by_source" | "by_person"
    """
    stats = db.get_stats()

    result: dict = {"summary": stats}

    if detail == "by_source":
        result["by_source"] = db.get_stats_by_source()
    elif detail == "by_person":
        result["by_person"] = db.get_stats_by_person()

    return result
