"""Batch scan all photos across source directories.

Usage:
    uv run python batch_scan.py [--dry-run] [--match-only]

Scans all image files in PHOTO_SOURCE_DIRS, detects faces, stores embeddings,
then runs a matching pass against all anchored faces.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src import db, log
from src.config import PROJECT_ROOT, PHOTO_SOURCE_DIRS, IMAGE_EXTENSIONS
from src.pipeline import process_photo
from src.matching import match_face, confidence_level
from src.persons import load_family_tree
from src.photo_cards import load_known_years
from src.date_estimate import batch_estimate, calibration_report


def discover_photos() -> list[Path]:
    """Find all image files across source directories."""
    photos = []
    for dir_name in PHOTO_SOURCE_DIRS:
        src_dir = PROJECT_ROOT / dir_name
        if not src_dir.exists():
            log.warn("source dir not found, skipping", path=str(src_dir))
            continue
        for f in sorted(src_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                photos.append(f)
    return photos


def batch_scan(photos: list[Path], dry_run: bool = False) -> dict:
    """Scan all photos. Returns stats dict."""
    total = len(photos)
    scanned = 0
    cached = 0
    failed = 0
    faces_total = 0
    start = time.time()

    for i, photo_path in enumerate(photos, 1):
        elapsed = time.time() - start
        rate = i / elapsed if elapsed > 0 else 0
        eta = (total - i) / rate if rate > 0 else 0

        if i % 50 == 0 or i == 1:
            print(
                f"[{i}/{total}] {elapsed:.0f}s elapsed, "
                f"{rate:.1f} photos/s, ETA {eta:.0f}s | "
                f"scanned={scanned} cached={cached} failed={failed} faces={faces_total}",
                flush=True,
            )

        if dry_run:
            continue

        try:
            result = process_photo(str(photo_path))
            if result.get("cached"):
                cached += 1
            else:
                scanned += 1
            faces_total += result["face_count"]
        except Exception as e:
            failed += 1
            if failed <= 10:
                log.error("scan failed", photo=str(photo_path), error=str(e))
            elif failed == 11:
                log.warn("suppressing further error logs")

    elapsed = time.time() - start
    print(
        f"\n=== Scan complete ===\n"
        f"Total: {total} | New: {scanned} | Cached: {cached} | Failed: {failed}\n"
        f"Faces detected: {faces_total}\n"
        f"Time: {elapsed:.1f}s ({total/elapsed:.1f} photos/s)\n",
        flush=True,
    )

    return {
        "total": total,
        "scanned": scanned,
        "cached": cached,
        "failed": failed,
        "faces": faces_total,
        "elapsed": elapsed,
    }


def match_pass() -> dict:
    """Match all unmatched faces against anchored embeddings."""
    conn = db.get_conn()

    unmatched = conn.execute(
        "SELECT face_id, embedding FROM faces WHERE person_id IS NULL"
    ).fetchall()

    if not unmatched:
        print("No unmatched faces to process.")
        return {"unmatched": 0, "new_matches": 0}

    print(f"Matching {len(unmatched)} unmatched faces against anchors...", flush=True)

    new_matches = 0
    start = time.time()

    for i, row in enumerate(unmatched, 1):
        if i % 200 == 0:
            print(f"  [{i}/{len(unmatched)}] matches so far: {new_matches}", flush=True)

        emb = db.blob_to_embedding(row["embedding"])
        matches = match_face(emb, top_k=1)
        if matches and matches[0]["confidence"] in ("HIGH", "MEDIUM"):
            db.update_face_match(
                row["face_id"],
                matches[0]["person_id"],
                matches[0]["score"],
                "auto",
            )
            new_matches += 1

    elapsed = time.time() - start
    print(
        f"\n=== Match pass complete ===\n"
        f"Unmatched: {len(unmatched)} | New matches: {new_matches}\n"
        f"Time: {elapsed:.1f}s\n",
        flush=True,
    )

    return {"unmatched": len(unmatched), "new_matches": new_matches}


def main():
    parser = argparse.ArgumentParser(description="Batch scan photos for face detection")
    parser.add_argument("--dry-run", action="store_true", help="Count files only, don't scan")
    parser.add_argument("--match-only", action="store_true", help="Skip scanning, only run match pass")
    parser.add_argument("--date-estimate", action="store_true", help="Run date estimation after matching")
    args = parser.parse_args()

    # Init DB + persons
    db.get_conn()
    person_count = load_family_tree()
    print(f"Loaded {person_count} persons\n")

    if not args.match_only:
        # Discover
        print("Discovering photos...", flush=True)
        photos = discover_photos()
        print(f"Found {len(photos)} image files across {len(PHOTO_SOURCE_DIRS)} directories\n")

        if not photos:
            print("No photos found!")
            sys.exit(1)

        # Scan
        scan_stats = batch_scan(photos, dry_run=args.dry_run)

        if args.dry_run:
            print("Dry run complete. No photos were scanned.")
            sys.exit(0)

    # Match pass
    match_stats = match_pass()

    # Date estimation pass
    if args.date_estimate:
        print("Loading known years from photo cards...", flush=True)
        ky_count = load_known_years()
        print(f"Known years loaded: {ky_count}\n")

        print("Running date estimation...", flush=True)
        est_stats = batch_estimate()
        print(
            f"\n=== Date estimation complete ===\n"
            f"Estimated: {est_stats['estimated']} | "
            f"Skipped: {est_stats['skipped']} | "
            f"Total eligible: {est_stats['total']}\n",
            flush=True,
        )

        cal = calibration_report()
        if cal.get("count", 0) > 0:
            print(
                f"=== Calibration ===\n"
                f"Photos with ground truth: {cal['count']}\n"
                f"Mean error: {cal['mean_error']} years\n"
                f"Median error: {cal['median_error']} years\n"
                f"MAE: {cal['mae']} years\n"
                f"Suggested bias correction: {cal['suggested_bias_correction']}\n",
                flush=True,
            )
        else:
            print("No photos with both estimate and known_year for calibration.\n", flush=True)

    # Final summary
    stats = db.get_stats()
    print(
        f"=== Final DB state ===\n"
        f"Photos: {stats['total_photos']} (scanned: {stats['scanned']}, failed: {stats['failed']})\n"
        f"Faces: {stats['face_count']}\n"
        f"Anchored: {stats['anchored_faces']}\n"
        f"Matched: {stats['matched_faces']}\n"
        f"Persons: {stats['person_count']}\n"
    )


if __name__ == "__main__":
    main()
