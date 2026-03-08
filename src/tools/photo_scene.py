"""photo_scene — Scene annotation tool using Gemini Flash Vision."""

from __future__ import annotations

from ..scene_annotate import (
    annotate_single,
    batch_annotate,
    get_scene_stats,
    search_scenes,
)


async def photo_scene(
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
    """照片場景標注工具。

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
        limit: batch 模式的最大數量 / search 模式的結果上限。
        force: annotate 模式是否強制重跑（覆蓋舊結果）。
        source_dir: batch 模式篩選特定來源目錄。
    """
    if mode == "stats":
        return get_scene_stats()

    if mode == "annotate":
        if not photo_id:
            return {"error": "photo_id is required for annotate mode"}
        return annotate_single(photo_id, force=force)

    if mode == "batch":
        return batch_annotate(limit=limit, source_dir=source_dir)

    if mode == "search":
        results = search_scenes(
            query=query,
            scene_type=scene_type,
            location=location,
            tag=tag,
            has_text=has_text,
            limit=limit,
        )
        return {"count": len(results), "results": results}

    return {"error": f"Unknown mode: {mode}. Use stats/annotate/batch/search."}
