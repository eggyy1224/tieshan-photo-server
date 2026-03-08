"""Estimate photo dates from identified faces' apparent age + known birth year."""

from __future__ import annotations

import statistics
from typing import Any, Optional

from . import db, log

# InsightFace age estimation bias correction (calibrate later)
AGE_BIAS = 0
# Single-face age uncertainty (InsightFace typical ±8 years)
AGE_UNCERTAINTY = 8


def estimate_photo_year(photo_id: str) -> Optional[dict[str, Any]]:
    """Estimate the year a photo was taken based on identified faces.

    For each face with a known person (who has birth_year) and age_est,
    compute candidate_year = birth_year + age_est + AGE_BIAS.
    Use the median of all candidates as the estimate.

    Returns dict with estimate details, or None if insufficient data.
    """
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT f.face_id, f.age_est, p.birth_year, p.display_name
           FROM faces f
           JOIN persons p ON f.person_id = p.person_id
           WHERE f.photo_id = ?
             AND p.birth_year IS NOT NULL
             AND f.age_est IS NOT NULL
             AND f.person_id IS NOT NULL""",
        (photo_id,),
    ).fetchall()

    if not rows:
        return None

    candidates = []
    details = []
    for r in rows:
        year = r["birth_year"] + r["age_est"] + AGE_BIAS
        candidates.append(year)
        details.append({
            "face_id": r["face_id"],
            "person": r["display_name"],
            "birth_year": r["birth_year"],
            "age_est": r["age_est"],
            "candidate_year": year,
        })

    n = len(candidates)
    est_year = int(statistics.median(candidates))

    if n >= 3:
        confidence = "HIGH"
    elif n == 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    spread = max(candidates) - min(candidates) if n > 1 else 0
    margin = max(AGE_UNCERTAINTY, spread // 2 + 2)
    est_lo = est_year - margin
    est_hi = est_year + margin

    # Write to DB
    conn.execute(
        """UPDATE photos SET
             est_year = ?, est_year_lo = ?, est_year_hi = ?,
             est_confidence = ?, est_method = ?, est_n_faces = ?
           WHERE photo_id = ?""",
        (est_year, est_lo, est_hi, confidence, "age_median", n, photo_id),
    )
    conn.commit()

    return {
        "photo_id": photo_id,
        "est_year": est_year,
        "est_year_lo": est_lo,
        "est_year_hi": est_hi,
        "confidence": confidence,
        "n_faces": n,
        "method": "age_median",
        "details": details,
    }


def batch_estimate() -> dict[str, Any]:
    """Run date estimation for all photos with eligible faces.

    Returns summary stats.
    """
    conn = db.get_conn()
    photo_ids = conn.execute(
        """SELECT DISTINCT f.photo_id
           FROM faces f
           JOIN persons p ON f.person_id = p.person_id
           WHERE p.birth_year IS NOT NULL
             AND f.age_est IS NOT NULL
             AND f.person_id IS NOT NULL""",
    ).fetchall()

    estimated = 0
    skipped = 0

    for row in photo_ids:
        result = estimate_photo_year(row["photo_id"])
        if result:
            estimated += 1
        else:
            skipped += 1

    log.info("batch date estimate done", estimated=estimated, skipped=skipped)
    return {
        "estimated": estimated,
        "skipped": skipped,
        "total": estimated + skipped,
    }


def calibration_report() -> dict[str, Any]:
    """Compare estimated years vs known_year (ground truth) for calibration.

    Returns error metrics and per-photo details.
    """
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT photo_id, rel_path, est_year, known_year, est_confidence, est_n_faces
           FROM photos
           WHERE est_year IS NOT NULL AND known_year IS NOT NULL""",
    ).fetchall()

    if not rows:
        return {
            "count": 0,
            "message": "No photos have both est_year and known_year for calibration.",
        }

    errors = []
    details = []
    for r in rows:
        err = r["est_year"] - r["known_year"]
        errors.append(err)
        details.append({
            "photo_id": r["photo_id"],
            "rel_path": r["rel_path"],
            "est_year": r["est_year"],
            "known_year": r["known_year"],
            "error": err,
            "confidence": r["est_confidence"],
            "n_faces": r["est_n_faces"],
        })

    abs_errors = [abs(e) for e in errors]
    mean_err = statistics.mean(errors)
    median_err = statistics.median(errors)
    mae = statistics.mean(abs_errors)

    return {
        "count": len(errors),
        "mean_error": round(mean_err, 1),
        "median_error": round(median_err, 1),
        "mae": round(mae, 1),
        "suggested_bias_correction": round(-mean_err),
        "details": details,
    }


def get_date_stats() -> dict[str, Any]:
    """Return overview statistics for date estimation coverage."""
    conn = db.get_conn()
    total = conn.execute("SELECT COUNT(*) FROM photos WHERE scan_status='scanned'").fetchone()[0]
    estimated = conn.execute("SELECT COUNT(*) FROM photos WHERE est_year IS NOT NULL").fetchone()[0]
    with_known = conn.execute("SELECT COUNT(*) FROM photos WHERE known_year IS NOT NULL").fetchone()[0]

    by_confidence = conn.execute(
        """SELECT est_confidence, COUNT(*) as cnt
           FROM photos WHERE est_year IS NOT NULL
           GROUP BY est_confidence ORDER BY cnt DESC""",
    ).fetchall()

    by_decade = conn.execute(
        """SELECT (est_year / 10) * 10 as decade, COUNT(*) as cnt
           FROM photos WHERE est_year IS NOT NULL
           GROUP BY decade ORDER BY decade""",
    ).fetchall()

    return {
        "total_scanned": total,
        "estimated_photos": estimated,
        "coverage_pct": round(100 * estimated / total, 1) if total else 0,
        "with_known_year": with_known,
        "by_confidence": [dict(r) for r in by_confidence],
        "by_decade": [dict(r) for r in by_decade],
    }
