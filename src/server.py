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
from .tools.photo_date import photo_date
from .tools.photo_scene import photo_scene
from .tools.photo_search import photo_search
from .web.routes import register_routes

mcp = FastMCP(
    "tieshan-photo",
    instructions="Face detection and recognition for Tieshanzhi historical photo research",
    host="127.0.0.1",
    port=PHOTO_SERVER_PORT,
)

# Web UI routes (custom HTTP endpoints, does not affect MCP protocol)
register_routes(mcp)


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
async def photo_cluster_tool(eps: float = 0.55, min_samples: int = 2, det_score_min: float = 0.0) -> dict:
    """Auto-cluster unassigned faces using DBSCAN.

    Args:
        eps: Maximum cosine distance for clustering (default 0.55).
        min_samples: Minimum faces per cluster (default 2).
        det_score_min: Minimum detection score to include (default 0.0 = all faces).

    Returns:
        Cluster list with face counts and sample photos.
    """
    return await photo_cluster(eps=eps, min_samples=min_samples, det_score_min=det_score_min)


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


# ── Phase 3 Tools ────────────────────────────────────────────────────

@mcp.tool()
async def photo_date_tool(mode: str = "stats", photo_id: str = "") -> dict:
    """照片年代推估工具。利用已辨識人臉的外觀年齡與已知出生年反推拍攝年份。

    Args:
        mode:
          - "stats": 統計概覽（多少照片有推估、年代分布）
          - "estimate": 單張推估（需 photo_id）
          - "batch": 批次推估所有符合條件的照片
          - "calibrate": 校準報告（比對推估 vs 已知年份）
        photo_id: estimate 模式需要的照片 ID。
    """
    return await photo_date(mode=mode, photo_id=photo_id)


# ── Phase 4 Tools ────────────────────────────────────────────────────

@mcp.tool()
async def photo_scene_tool(
    mode: str = "stats",
    photo_id: str = "",
    query: str = "",
    scene_type: str = "",
    location: str = "",
    tag: str = "",
    has_text: bool = False,
    limit: int = 50,
    force: bool = False,
    source_dir: str = "",
) -> dict:
    """照片場景標注工具。使用 Gemini Flash Vision 辨識照片中的場景、文字、物件與建築。

    Args:
        mode:
          - "stats": 標注進度 + 場景/地點/標籤分布
          - "annotate": 單張即時標注（需 photo_id）
          - "batch": 批次標注（尊重 rate limit）
          - "search": 多條件搜尋已標注照片
        photo_id: annotate 模式需要的照片 ID。
        query: search 模式的全文搜尋關鍵字。
        scene_type: 篩選場景類型（室內/室外/混合/不明）。
        location: 篩選地點類型。
        tag: 篩選標籤。
        has_text: 只搜尋有可見文字的照片。
        limit: batch 最大數量 / search 結果上限。
        force: annotate 是否強制重跑。
        source_dir: batch 篩選特定來源目錄。
    """
    return await photo_scene(
        mode=mode, photo_id=photo_id, query=query,
        scene_type=scene_type, location=location, tag=tag,
        has_text=has_text, limit=limit, force=force, source_dir=source_dir,
    )


# ── Phase 5 Tools ────────────────────────────────────────────────────

@mcp.tool()
async def photo_search_tool(
    mode: str = "text",
    query: str = "",
    photo_id: str = "",
    photo_path: str = "",
    limit: int = 20,
    scene_filter: str = "",
    source_dir: str = "",
) -> dict:
    """照片語意搜尋工具。用自然語言找照片，或用一張照片找視覺相似的照片。

    Args:
        mode:
          - "text": 用自然語言描述搜尋照片（如「碑文」「穿和服的合照」「鐵砧山風景」）
          - "similar": 找視覺相似的照片（需 photo_id 或 photo_path）
          - "hybrid": 文字搜尋 + 場景條件篩選（結合向量搜尋與 SQL 篩選）
          - "stats": 嵌入覆蓋率統計
          - "embed": 單張嵌入（需 photo_id 或 photo_path）
          - "batch": 批量嵌入所有未處理照片
        query: text/hybrid 模式的搜尋文字。
        photo_id: similar/embed 模式的照片 ID。
        photo_path: similar/embed 模式的照片路徑（替代 photo_id）。
        limit: 結果上限（text/similar/hybrid）或批量上限（batch）。
        scene_filter: hybrid 模式的場景類型篩選（如「室外」「室內」）。
        source_dir: hybrid/batch 模式的來源目錄篩選。
    """
    return await photo_search(
        mode=mode, query=query, photo_id=photo_id, photo_path=photo_path,
        limit=limit, scene_filter=scene_filter, source_dir=source_dir,
    )


# ── Startup ──────────────────────────────────────────────────────────

def main() -> None:
    """Start the MCP server with streamable HTTP transport."""
    # Initialize DB
    db.get_conn()

    # Load family tree
    count = load_family_tree()
    log.info("server starting", port=PHOTO_SERVER_PORT, persons_loaded=count)

    # Run with streamable HTTP
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
