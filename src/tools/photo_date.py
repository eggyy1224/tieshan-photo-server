"""photo_date — Photo date estimation tool."""

from __future__ import annotations

from ..date_estimate import (
    estimate_photo_year,
    batch_estimate,
    calibration_report,
    get_date_stats,
)


async def photo_date(mode: str = "stats", photo_id: str = "") -> dict:
    """照片年代推估工具。

    Args:
        mode:
          - "stats": 統計概覽（多少照片有推估、年代分布）
          - "estimate": 單張推估（需 photo_id）
          - "batch": 批次推估所有符合條件的照片
          - "calibrate": 校準報告（比對推估 vs 已知年份）
        photo_id: estimate 模式需要的照片 ID。
    """
    if mode == "stats":
        return get_date_stats()

    if mode == "estimate":
        if not photo_id:
            return {"error": "photo_id is required for estimate mode"}
        result = estimate_photo_year(photo_id)
        if result is None:
            return {"error": f"No eligible faces for photo {photo_id}"}
        return result

    if mode == "batch":
        return batch_estimate()

    if mode == "calibrate":
        return calibration_report()

    return {"error": f"Unknown mode: {mode}. Use stats/estimate/batch/calibrate."}
