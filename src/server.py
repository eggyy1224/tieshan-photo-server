"""tieshan-photo MCP server — face detection and recognition for old photos."""

from __future__ import annotations

import asyncio
import sys

from mcp.server.fastmcp import FastMCP

from . import db, log
from .config import PHOTO_SERVER_PORT
from .persons import load_family_tree
from .tools.photo_who import photo_who
from .tools.photo_find import photo_find
from .tools.photo_stats import photo_stats
from .tools.photo_cluster import photo_cluster
from .tools.photo_anchor import photo_anchor

mcp = FastMCP(
    "tieshan-photo",
    version="0.1.0",
    description="Face detection and recognition for Tieshanzhi historical photo research",
)


# ── Phase 1 Tools ────────────────────────────────────────────────────

@mcp.tool()
async def photo_who_tool(photo_path: str, force_rescan: bool = False) -> dict:
    """Identify persons in a photo. Detects faces and matches each against known family members.

    Args:
        photo_path: Path to photo file (absolute, or relative to project root).
        force_rescan: Re-detect faces even if previously scanned.

    Returns:
        Photo ID, face count, and per-face top-3 person matches with confidence.
    """
    return await photo_who(photo_path, force_rescan=force_rescan)


@mcp.tool()
async def photo_find_tool(query: str, min_score: float = 0.30, limit: int = 50) -> dict:
    """Find all photos containing a specific person.

    Args:
        query: Person ID (e.g. 'xu_tiancui') or display name (e.g. '許天催').
        min_score: Minimum cosine similarity threshold (default 0.30).
        limit: Maximum number of results (default 50).

    Returns:
        Person info and list of matching photos with scores and confidence levels.
    """
    return await photo_find(query, min_score=min_score, limit=limit)


@mcp.tool()
async def photo_stats_tool(detail: str = "summary") -> dict:
    """Get scanning and annotation progress statistics.

    Args:
        detail: Level of detail — "summary", "by_source", or "by_person".

    Returns:
        Statistics including total photos, scanned count, face count, anchor count.
    """
    return await photo_stats(detail=detail)


# ── Phase 2 Tools ────────────────────────────────────────────────────

@mcp.tool()
async def photo_cluster_tool(eps: float = 0.55, min_samples: int = 2) -> dict:
    """Auto-cluster unassigned faces using DBSCAN.

    Args:
        eps: Maximum cosine distance for clustering (default 0.55).
        min_samples: Minimum faces per cluster (default 2).

    Returns:
        Cluster list with face counts and sample photos.
    """
    return await photo_cluster(eps=eps, min_samples=min_samples)


@mcp.tool()
async def photo_anchor_tool(face_id: int, person_id: str, note: str = "") -> dict:
    """Mark a detected face as a specific person (manual anchor).

    Creates an anchor entry and triggers re-matching of all unmatched faces.

    Args:
        face_id: The face_id to anchor.
        person_id: The person_id from family tree (e.g. 'xu_tiancui').
        note: Optional annotation.

    Returns:
        Anchor ID and count of new automatic matches triggered.
    """
    return await photo_anchor(face_id=face_id, person_id=person_id, note=note)


# ── Startup ──────────────────────────────────────────────────────────

def main() -> None:
    """Start the MCP server with streamable HTTP transport."""
    # Initialize DB
    db.get_conn()

    # Load family tree
    count = load_family_tree()
    log.info("server starting", port=PHOTO_SERVER_PORT, persons_loaded=count)

    # Run with streamable HTTP
    mcp.run(transport="streamable-http", host="127.0.0.1", port=PHOTO_SERVER_PORT)


if __name__ == "__main__":
    main()
