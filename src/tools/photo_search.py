"""photo_search — Semantic photo search using SigLIP image embeddings."""

from __future__ import annotations

from typing import Any

from ..image_embed import (
    batch_embed,
    embed_single,
    search_by_image,
    search_by_text,
    search_hybrid,
    _invalidate_cache,
)
from .. import db
from ..config import EMBED_MODEL


async def photo_search(
    mode: str = "text",
    query: str = "",
    photo_id: str = "",
    photo_path: str = "",
    limit: int = 20,
    scene_filter: str = "",
    source_dir: str = "",
) -> dict[str, Any]:
    """照片語意搜尋工具。

    Args:
        mode:
          - "text": 用自然語言描述搜尋照片（如「碑文」「穿和服的合照」）
          - "similar": 找視覺相似的照片（需 photo_id 或 photo_path）
          - "hybrid": 文字搜尋 + 場景條件篩選
          - "stats": 嵌入覆蓋率統計
          - "embed": 單張嵌入（需 photo_id 或 photo_path）
          - "batch": 批量嵌入所有未處理照片
        query: text/hybrid 模式的搜尋文字。
        photo_id: similar/embed 模式的照片 ID。
        photo_path: similar/embed 模式的照片路徑（替代 photo_id）。
        limit: 結果上限（text/similar/hybrid）或批量上限（batch）。
        scene_filter: hybrid 模式的場景類型篩選。
        source_dir: hybrid/batch 模式的來源篩選。
    """
    if mode == "stats":
        return db.get_embed_stats(model=EMBED_MODEL)

    if mode == "text":
        if not query:
            return {"error": "query is required for text mode"}
        results = search_by_text(query, limit=limit)
        return {"mode": "text", "query": query, "count": len(results), "results": results}

    if mode == "similar":
        pid = _resolve_photo_id(photo_id, photo_path)
        if not pid:
            return {"error": "photo_id or photo_path is required for similar mode"}
        results = search_by_image(pid, limit=limit)
        if results and "error" in results[0]:
            return results[0]
        return {"mode": "similar", "photo_id": pid, "count": len(results), "results": results}

    if mode == "hybrid":
        if not query:
            return {"error": "query is required for hybrid mode"}
        results = search_hybrid(
            query, limit=limit,
            scene_filter=scene_filter, source_dir=source_dir,
        )
        return {
            "mode": "hybrid", "query": query,
            "scene_filter": scene_filter or "(none)",
            "source_dir": source_dir or "(all)",
            "count": len(results), "results": results,
        }

    if mode == "embed":
        pid = _resolve_photo_id(photo_id, photo_path)
        if not pid:
            return {"error": "photo_id or photo_path is required for embed mode"}
        result = embed_single(pid, force=True)
        _invalidate_cache()
        return result

    if mode == "batch":
        result = batch_embed(limit=limit, source_dir=source_dir)
        _invalidate_cache()
        return result

    return {"error": f"Unknown mode: {mode}. Use text/similar/hybrid/stats/embed/batch."}


def _resolve_photo_id(photo_id: str, photo_path: str) -> str:
    """Resolve photo_id from either direct ID or path."""
    if photo_id:
        return photo_id
    if photo_path:
        photo = db.get_photo_by_path(photo_path)
        if photo:
            return photo["photo_id"]
        # Try as relative path from project root
        pid = db.path_to_photo_id(photo_path)
        if db.get_photo(pid):
            return pid
    return ""
